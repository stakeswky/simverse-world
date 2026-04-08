import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.routers.admin.middleware import require_admin


@pytest.mark.anyio
async def test_require_admin_no_token_raises_401():
    """Missing Authorization header should raise 401."""
    request = MagicMock()
    request.headers = {}
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(request, db)
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_require_admin_invalid_token_raises_401():
    """Invalid JWT should raise 401."""
    request = MagicMock()
    request.headers = {"Authorization": "Bearer invalid-token"}
    db = AsyncMock()

    with patch("app.routers.admin.middleware.get_current_user", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request, db)
        assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_require_admin_non_admin_raises_403():
    """Authenticated but non-admin user should raise 403."""
    request = MagicMock()
    request.headers = {"Authorization": "Bearer valid-token"}
    db = AsyncMock()

    mock_user = MagicMock()
    mock_user.is_admin = False
    mock_user.is_banned = False

    with patch("app.routers.admin.middleware.get_current_user", return_value=mock_user):
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request, db)
        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_require_admin_banned_user_raises_403():
    """Banned admin should raise 403."""
    request = MagicMock()
    request.headers = {"Authorization": "Bearer valid-token"}
    db = AsyncMock()

    mock_user = MagicMock()
    mock_user.is_admin = True
    mock_user.is_banned = True

    with patch("app.routers.admin.middleware.get_current_user", return_value=mock_user):
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(request, db)
        assert exc_info.value.status_code == 403
        assert "banned" in exc_info.value.detail.lower()


@pytest.mark.anyio
async def test_require_admin_valid_admin_returns_user():
    """Valid admin user should be returned."""
    request = MagicMock()
    request.headers = {"Authorization": "Bearer valid-token"}
    db = AsyncMock()

    mock_user = MagicMock()
    mock_user.is_admin = True
    mock_user.is_banned = False
    mock_user.id = "admin-id-123"

    with patch("app.routers.admin.middleware.get_current_user", return_value=mock_user):
        user = await require_admin(request, db)
    assert user.id == "admin-id-123"
