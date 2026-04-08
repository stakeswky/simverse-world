# Plan 3: LinuxDo OAuth2 登录

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 LinuxDo（linux.do）作为第三方登录方式，采用标准 Authorization Code Grant 流程，直接在 FastAPI 后端实现。

**Architecture:** 两个新端点 `/auth/linuxdo/login`（生成授权 URL 并重定向）和 `/auth/linuxdo/callback`（用 code 换 token，获取用户信息，创建/匹配用户，签发 JWT）。state 参数存入 Redis 防 CSRF。仅接受 active=true 且 trust_level 达标的用户。

**Tech Stack:** Python 3.11+, FastAPI, httpx, Redis, python-jose (JWT)

**Working directory:** `/Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend/`

**Depends on:** Plan 1 (Foundation) — User model linuxdo_id/linuxdo_trust_level fields, Settings linuxdo_* fields

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/services/linuxdo_auth.py` | Create | LinuxDo OAuth2 完整流程（authorize URL、token exchange、user info、用户匹配） |
| `app/routers/auth.py` | Modify | 新增 /auth/linuxdo/login 和 /auth/linuxdo/callback |
| `tests/test_linuxdo_auth.py` | Create | OAuth2 流程测试（mock HTTP 调用） |

---

## Task 1: LinuxDo OAuth2 服务

**Files:**
- Create: `app/services/linuxdo_auth.py`
- Test: `tests/test_linuxdo_auth.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_linuxdo_auth.py
import pytest
from unittest.mock import AsyncMock, patch
import httpx
from app.services.linuxdo_auth import LinuxDoOAuth, LinuxDoUser


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_linuxdo_auth.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/services/linuxdo_auth.py
"""LinuxDo OAuth2 Authorization Code Grant flow."""
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode
import httpx

AUTHORIZE_URL = "https://connect.linux.do/oauth2/authorize"
TOKEN_URL = "https://connect.linux.do/oauth2/token"
USER_INFO_URL = "https://connect.linux.do/api/user"


@dataclass
class LinuxDoUser:
    id: int
    username: str
    name: str
    active: bool
    trust_level: int
    silenced: bool


class LinuxDoOAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def build_authorize_url(self) -> tuple[str, str]:
        """Build LinuxDo authorize URL. Returns (url, state)."""
        state = secrets.token_urlsafe(24)
        params = urlencode({
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "state": state,
        })
        return f"{AUTHORIZE_URL}?{params}", state

    async def exchange_code(self, code: str) -> LinuxDoUser:
        """Exchange authorization code for access token, then fetch user info."""
        async with httpx.AsyncClient(trust_env=False) as client:
            # Step 1: Exchange code for token (HTTP Basic Auth)
            token_resp = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri,
                },
                auth=(self._client_id, self._client_secret),
                timeout=15,
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            # Step 2: Fetch user info
            user_resp = await client.get(
                USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            user_resp.raise_for_status()
            data = user_resp.json()

        user = LinuxDoUser(
            id=data["id"],
            username=data["username"],
            name=data.get("name") or data["username"],
            active=data["active"],
            trust_level=data["trust_level"],
            silenced=data["silenced"],
        )

        if not user.active or user.silenced:
            raise ValueError("LinuxDo account is inactive or silenced")

        return user
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_linuxdo_auth.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/linuxdo_auth.py tests/test_linuxdo_auth.py
git commit -m "feat: LinuxDo OAuth2 service (authorize URL, token exchange, user info)"
```

---

## Task 2: 用户匹配逻辑

**Files:**
- Modify: `app/services/linuxdo_auth.py`
- Test: `tests/test_linuxdo_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_linuxdo_auth.py
from app.models.user import User
from app.services.linuxdo_auth import find_or_create_user


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_linuxdo_auth.py::test_find_or_create_user_new -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

```python
# Add to app/services/linuxdo_auth.py

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.transaction import Transaction


async def find_or_create_user(
    db: AsyncSession,
    ld_user: LinuxDoUser,
    min_trust_level: int = 0,
) -> tuple[User, bool]:
    """Find or create a user from LinuxDo OAuth data. Returns (user, was_created)."""
    if ld_user.trust_level < min_trust_level:
        raise ValueError(
            f"trust_level {ld_user.trust_level} below minimum {min_trust_level}"
        )

    # 1. Find by linuxdo_id
    result = await db.execute(
        select(User).where(User.linuxdo_id == str(ld_user.id))
    )
    user = result.scalar_one_or_none()

    if user:
        # Update trust_level on each login
        user.linuxdo_trust_level = ld_user.trust_level
        await db.commit()
        return user, False

    # 2. Create new user
    import uuid
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        name=ld_user.name,
        email=f"{ld_user.username}@linux.do",
        linuxdo_id=str(ld_user.id),
        linuxdo_trust_level=ld_user.trust_level,
        soul_coin_balance=100,
    )
    db.add(user)
    db.add(Transaction(user_id=user_id, amount=100, reason="signup_bonus"))
    await db.commit()
    await db.refresh(user)
    return user, True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_linuxdo_auth.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/linuxdo_auth.py tests/test_linuxdo_auth.py
git commit -m "feat: LinuxDo user matching (find/create + trust_level gate)"
```

---

## Task 3: Auth 路由端点

**Files:**
- Modify: `app/routers/auth.py`
- Test: `tests/test_linuxdo_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_linuxdo_auth.py
from httpx import AsyncClient


@pytest.mark.anyio
async def test_linuxdo_login_redirects(client: AsyncClient):
    """GET /auth/linuxdo/login should redirect to LinuxDo authorize URL."""
    with patch("app.routers.auth.settings") as mock_settings:
        mock_settings.linuxdo_client_id = "test-client-id"
        mock_settings.linuxdo_client_secret = "test-secret"
        mock_settings.linuxdo_redirect_uri = "http://localhost:8000/auth/linuxdo/callback"
        mock_settings.linuxdo_min_trust_level = 0

        resp = await client.get("/auth/linuxdo/login", follow_redirects=False)

    assert resp.status_code == 307
    assert "connect.linux.do/oauth2/authorize" in resp.headers["location"]
    assert "client_id=test-client-id" in resp.headers["location"]


@pytest.mark.anyio
async def test_linuxdo_login_returns_error_if_not_configured(client: AsyncClient):
    """Should return 501 if LinuxDo OAuth not configured."""
    with patch("app.routers.auth.settings") as mock_settings:
        mock_settings.linuxdo_client_id = ""
        mock_settings.linuxdo_client_secret = ""

        resp = await client.get("/auth/linuxdo/login")

    assert resp.status_code == 501
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_linuxdo_auth.py::test_linuxdo_login_redirects -v`
Expected: FAIL (endpoint doesn't exist)

- [ ] **Step 3: Write implementation**

```python
# Add to app/routers/auth.py — add these imports at top:
from fastapi.responses import RedirectResponse
from app.config import settings
from app.services.linuxdo_auth import LinuxDoOAuth, find_or_create_user
from app.services.auth_service import create_token

# State storage (MVP: in-memory dict. Production: use Redis)
_oauth_states: dict[str, float] = {}  # state -> timestamp

@router.get("/linuxdo/login")
async def linuxdo_login():
    """Redirect to LinuxDo OAuth2 authorize page."""
    if not settings.linuxdo_client_id or not settings.linuxdo_client_secret:
        raise HTTPException(501, "LinuxDo OAuth not configured")

    oauth = LinuxDoOAuth(
        client_id=settings.linuxdo_client_id,
        client_secret=settings.linuxdo_client_secret,
        redirect_uri=settings.linuxdo_redirect_uri,
    )
    url, state = oauth.build_authorize_url()

    # Store state for CSRF validation
    import time
    _oauth_states[state] = time.time()
    # Cleanup old states (> 10 min)
    cutoff = time.time() - 600
    for k in [k for k, v in _oauth_states.items() if v < cutoff]:
        del _oauth_states[k]

    return RedirectResponse(url, status_code=307)


@router.get("/linuxdo/callback")
async def linuxdo_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """LinuxDo OAuth2 callback. Exchanges code for user info, creates/finds user, returns JWT."""
    # Validate state (CSRF)
    if state not in _oauth_states:
        raise HTTPException(400, "Invalid or expired state parameter")
    del _oauth_states[state]

    if not settings.linuxdo_client_id:
        raise HTTPException(501, "LinuxDo OAuth not configured")

    oauth = LinuxDoOAuth(
        client_id=settings.linuxdo_client_id,
        client_secret=settings.linuxdo_client_secret,
        redirect_uri=settings.linuxdo_redirect_uri,
    )

    try:
        ld_user = await oauth.exchange_code(code)
    except Exception as e:
        raise HTTPException(401, f"LinuxDo authentication failed: {e}")

    try:
        user, _ = await find_or_create_user(
            db, ld_user,
            min_trust_level=settings.linuxdo_min_trust_level,
        )
    except ValueError as e:
        raise HTTPException(403, str(e))

    token = create_token(user.id)

    # Redirect to frontend with token
    frontend_url = settings.cors_origins[0] if settings.cors_origins else "http://localhost:5173"
    return RedirectResponse(f"{frontend_url}/auth/callback?token={token}", status_code=302)
```

Also add the needed import to `app/routers/auth.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from fastapi import Depends
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_linuxdo_auth.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Run existing auth tests to verify no regressions**

Run: `python -m pytest tests/test_auth.py -v`
Expected: All existing auth tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/routers/auth.py tests/test_linuxdo_auth.py
git commit -m "feat: /auth/linuxdo/login and /auth/linuxdo/callback endpoints"
```

---

## Task 4: 全量测试

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Manual smoke test (if LinuxDo credentials available)**

```bash
# Set env vars
export LINUXDO_CLIENT_ID="your-client-id"
export LINUXDO_CLIENT_SECRET="your-client-secret"
export LINUXDO_REDIRECT_URI="http://localhost:8000/auth/linuxdo/callback"

# Start server
uvicorn app.main:app --reload

# Open in browser
open http://localhost:8000/auth/linuxdo/login
```

- [ ] **Step 3: Commit if any fixes needed**

```bash
git add -A
git commit -m "chore: Plan 3 LinuxDo OAuth2 integration fixes"
```

---

## Summary

| Task | What it does | Key Files |
|------|-------------|-----------|
| 1 | LinuxDo OAuth2 service (authorize URL, token exchange, user info) | linuxdo_auth.py |
| 2 | User matching (find/create + trust_level gating) | linuxdo_auth.py |
| 3 | Auth router endpoints (/login, /callback) with CSRF state | auth.py |
| 4 | Full test suite verification | — |
