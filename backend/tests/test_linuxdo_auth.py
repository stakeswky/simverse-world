import pytest
from unittest.mock import AsyncMock, patch
import httpx
from app.services.linuxdo_auth import LinuxDoOAuth, LinuxDoUser, find_or_create_user
from app.models.user import User


def test_build_authorize_url():
    """Should build correct LinuxDo authorize URL with state."""
    oauth = LinuxDoOAuth(
        client_id="test-id",
        client_secret="test-secret",
        redirect_uri="http://localhost:8000/auth/linuxdo/callback",
    )
    url, state = oauth.build_authorize_url()

    assert "connect.linux.do/oauth2/authorize" in url
    assert "client_id=test-id" in url
    assert f"state={state}" in url
    assert "response_type=code" in url
    assert len(state) >= 16


@pytest.mark.anyio
async def test_exchange_code_for_user():
    """Should exchange code for token and fetch user info."""
    oauth = LinuxDoOAuth(
        client_id="test-id",
        client_secret="test-secret",
        redirect_uri="http://localhost:8000/auth/linuxdo/callback",
    )

    # Mock token response
    token_response = httpx.Response(
        200,
        json={"access_token": "test-token", "token_type": "bearer"},
        request=httpx.Request("POST", "https://connect.linux.do/oauth2/token"),
    )

    # Mock user info response
    user_response = httpx.Response(
        200,
        json={
            "id": 12345,
            "username": "testuser",
            "name": "Test User",
            "active": True,
            "trust_level": 2,
            "silenced": False,
        },
        request=httpx.Request("GET", "https://connect.linux.do/api/user"),
    )

    with patch("app.services.linuxdo_auth.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=token_response)
        mock_client.get = AsyncMock(return_value=user_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        user = await oauth.exchange_code("test-code")

    assert isinstance(user, LinuxDoUser)
    assert user.id == 12345
    assert user.username == "testuser"
    assert user.name == "Test User"
    assert user.active is True
    assert user.trust_level == 2
    assert user.silenced is False


@pytest.mark.anyio
async def test_exchange_code_rejects_inactive_user():
    """Should raise ValueError for inactive users."""
    oauth = LinuxDoOAuth(
        client_id="test-id",
        client_secret="test-secret",
        redirect_uri="http://localhost:8000/auth/linuxdo/callback",
    )

    token_response = httpx.Response(
        200,
        json={"access_token": "test-token", "token_type": "bearer"},
        request=httpx.Request("POST", "https://connect.linux.do/oauth2/token"),
    )
    user_response = httpx.Response(
        200,
        json={"id": 99, "username": "banned", "name": "Banned", "active": False, "trust_level": 0, "silenced": True},
        request=httpx.Request("GET", "https://connect.linux.do/api/user"),
    )

    with patch("app.services.linuxdo_auth.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=token_response)
        mock_client.get = AsyncMock(return_value=user_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        with pytest.raises(ValueError, match="inactive or silenced"):
            await oauth.exchange_code("test-code")


@pytest.mark.anyio
async def test_find_or_create_user_new(db_session):
    """Should create a new user for unknown LinuxDo account."""
    ld_user = LinuxDoUser(id=12345, username="newuser", name="New User", active=True, trust_level=2, silenced=False)
    user, created = await find_or_create_user(db_session, ld_user)

    assert created is True
    assert user.name == "New User"
    assert user.email == "newuser@linux.do"
    assert user.linuxdo_id == "12345"
    assert user.linuxdo_trust_level == 2
    assert user.soul_coin_balance == 100


@pytest.mark.anyio
async def test_find_or_create_user_existing(db_session):
    """Should find existing user by linuxdo_id."""
    existing = User(name="Old", email="old@linux.do", linuxdo_id="12345", linuxdo_trust_level=1)
    db_session.add(existing)
    await db_session.commit()

    ld_user = LinuxDoUser(id=12345, username="old", name="Old Updated", active=True, trust_level=3, silenced=False)
    user, created = await find_or_create_user(db_session, ld_user)

    assert created is False
    assert user.id == existing.id
    assert user.linuxdo_trust_level == 3  # updated


@pytest.mark.anyio
async def test_find_or_create_user_rejects_low_trust(db_session):
    """Should reject users below minimum trust level."""
    ld_user = LinuxDoUser(id=99, username="noob", name="Noob", active=True, trust_level=0, silenced=False)

    with pytest.raises(ValueError, match="trust_level"):
        await find_or_create_user(db_session, ld_user, min_trust_level=1)
