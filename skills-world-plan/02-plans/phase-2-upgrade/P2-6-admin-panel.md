# Plan 6: Admin Panel — 后台管理 API

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Skills World 提供完整的后台管理 API，覆盖仪表盘统计、用户管理、居民管理、炼化监控、经济系统、系统配置六大模块。所有端点要求 `is_admin=True`。

**Architecture:** 在 `app/routers/admin/` 创建路由包，使用统一的 `require_admin` 依赖注入。每个子模块对应一个路由文件。Dashboard 使用 SQL 聚合查询，健康检查使用 HTTP ping。系统配置读写基于 Plan 1 的 ConfigService。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), httpx (health checks), pytest + pytest-asyncio

**Working directory:** `/Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend/`

**Depends on:** Plan 1 (Foundation) — User.is_admin, User.is_banned, SystemConfig model, ConfigService, ForgeSession model

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/routers/admin/__init__.py` | Create | Admin router package, aggregates sub-routers |
| `app/routers/admin/middleware.py` | Create | `require_admin` dependency (auth + is_admin check) |
| `app/routers/admin/dashboard.py` | Create | Dashboard stats, trends, top residents, health |
| `app/routers/admin/users.py` | Create | User list, detail, balance adjust, ban/unban, set admin |
| `app/routers/admin/residents.py` | Create | Resident list, detail, persona edit, preset CRUD, batch ops |
| `app/routers/admin/forge_monitor.py` | Create | Forge session list, detail, SearXNG health |
| `app/routers/admin/economy.py` | Create | Economy stats, transaction log, dynamic config |
| `app/routers/admin/system_config.py` | Create | System config read/write for all config groups |
| `app/schemas/admin.py` | Create | Pydantic schemas for all admin endpoints |
| `app/main.py` | Modify | Include admin router |
| `tests/test_admin_middleware.py` | Create | Admin auth dependency tests |
| `tests/test_admin_dashboard.py` | Create | Dashboard stats endpoint tests |
| `tests/test_admin_users.py` | Create | User management endpoint tests |
| `tests/test_admin_config.py` | Create | System config API tests |

---

## Task 1: Admin Middleware — `require_admin` 依赖

**Files:**
- Create: `app/routers/admin/middleware.py`
- Test: `tests/test_admin_middleware.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_admin_middleware.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend && python -m pytest tests/test_admin_middleware.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routers.admin'`

- [ ] **Step 3: Write implementation**

```python
# app/routers/admin/__init__.py
"""Admin router package — all endpoints require is_admin=True."""
```

```python
# app/routers/admin/middleware.py
"""Admin authentication dependency. Extracts JWT, verifies user, checks is_admin."""
from fastapi import HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.auth_service import get_current_user
from app.models.user import User


async def require_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency that enforces admin access.
    Returns the authenticated admin User, or raises 401/403.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth.removeprefix("Bearer ")
    user = await get_current_user(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if user.is_banned:
        raise HTTPException(status_code=403, detail="Account is banned")

    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")

    return user
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_middleware.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin/__init__.py app/routers/admin/middleware.py tests/test_admin_middleware.py
git commit -m "feat: admin middleware — require_admin dependency with auth + role check"
```

---

## Task 2: Admin Pydantic Schemas

**Files:**
- Create: `app/schemas/admin.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_schemas.py
from app.schemas.admin import (
    DashboardStatsResponse,
    DashboardTrendPoint,
    TopResidentItem,
    ServiceHealthItem,
    AdminUserListItem,
    AdminUserDetail,
    BalanceAdjustRequest,
    AdminResidentListItem,
    ResidentPersonaEditRequest,
    PresetResidentRequest,
    BatchDistrictRequest,
    ForgeSessionListItem,
    ForgeSessionDetail,
    EconomyStatsResponse,
    TransactionLogItem,
    EconomyConfigUpdate,
    ConfigGroupResponse,
    ConfigUpdateRequest,
)


def test_dashboard_stats_serialization():
    """Verify DashboardStatsResponse can be constructed."""
    stats = DashboardStatsResponse(
        online_users=42,
        today_registrations=5,
        active_chats=12,
        soul_coin_net_flow=-300,
    )
    assert stats.online_users == 42


def test_balance_adjust_request_validation():
    """BalanceAdjustRequest should accept positive and negative amounts."""
    req = BalanceAdjustRequest(amount=50, reason="manual top-up")
    assert req.amount == 50

    req2 = BalanceAdjustRequest(amount=-20, reason="penalty")
    assert req2.amount == -20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_admin_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/schemas/admin.py
"""Pydantic schemas for all admin panel endpoints."""
from datetime import datetime
from pydantic import BaseModel


# ── Dashboard ──────────────────────────────────────────────
class DashboardStatsResponse(BaseModel):
    online_users: int
    today_registrations: int
    active_chats: int
    soul_coin_net_flow: int  # today's total issued - total consumed


class DashboardTrendPoint(BaseModel):
    date: str  # "2026-04-07"
    users: int
    conversations: int


class TopResidentItem(BaseModel):
    id: str
    name: str
    slug: str
    heat: int
    district: str
    star_rating: int

    model_config = {"from_attributes": True}


class ServiceHealthItem(BaseModel):
    service: str  # "searxng", "llm_api"
    status: str  # "ok", "error", "timeout"
    latency_ms: int | None = None
    detail: str | None = None


# ── User Management ────────────────────────────────────────
class AdminUserListItem(BaseModel):
    id: str
    name: str
    email: str
    avatar: str | None
    soul_coin_balance: int
    is_admin: bool
    is_banned: bool
    github_id: str | None
    linuxdo_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserDetail(AdminUserListItem):
    linuxdo_trust_level: int | None
    player_resident_id: str | None
    last_x: int
    last_y: int
    settings_json: dict
    custom_llm_enabled: bool
    custom_llm_api_format: str
    custom_llm_base_url: str | None
    custom_llm_model: str | None
    resident_count: int  # number of created residents
    conversation_count: int  # total conversations
    transaction_count: int  # total transactions


class BalanceAdjustRequest(BaseModel):
    amount: int  # positive = add, negative = deduct
    reason: str


class SetAdminRequest(BaseModel):
    is_admin: bool


class SetBanRequest(BaseModel):
    is_banned: bool


# ── Resident Management ────────────────────────────────────
class AdminResidentListItem(BaseModel):
    id: str
    slug: str
    name: str
    district: str
    status: str
    heat: int
    star_rating: int
    resident_type: str
    reply_mode: str
    creator_id: str
    total_conversations: int
    avg_rating: float
    created_at: datetime

    model_config = {"from_attributes": True}


class ResidentPersonaEditRequest(BaseModel):
    """Admin can edit any resident's persona layers."""
    ability_md: str | None = None
    persona_md: str | None = None
    soul_md: str | None = None
    district: str | None = None
    status: str | None = None
    resident_type: str | None = None
    reply_mode: str | None = None


class PresetResidentRequest(BaseModel):
    """CRUD for preset characters."""
    slug: str
    name: str
    district: str = "free"
    ability_md: str = ""
    persona_md: str = ""
    soul_md: str = ""
    sprite_key: str = "伊莎贝拉"
    tile_x: int = 76
    tile_y: int = 50
    resident_type: str = "preset"
    reply_mode: str = "auto"
    meta_json: dict | None = None


class BatchDistrictRequest(BaseModel):
    resident_ids: list[str]
    district: str


class BatchStatusResetRequest(BaseModel):
    resident_ids: list[str]
    status: str = "idle"


# ── Forge Monitor ──────────────────────────────────────────
class ForgeSessionListItem(BaseModel):
    id: str
    user_id: str
    character_name: str
    mode: str
    status: str
    current_stage: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ForgeSessionDetail(ForgeSessionListItem):
    research_data: dict
    extraction_data: dict
    build_output: dict
    validation_report: dict
    refinement_log: dict


# ── Economy ────────────────────────────────────────────────
class EconomyStatsResponse(BaseModel):
    total_issued: int  # sum of positive transactions
    total_consumed: int  # sum of negative transactions (absolute value)
    net_circulation: int  # total_issued - total_consumed
    avg_balance: float
    total_users: int


class TransactionLogItem(BaseModel):
    id: str
    user_id: str
    amount: int
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


class EconomyConfigUpdate(BaseModel):
    """Update one or more economy parameters."""
    signup_bonus: int | None = None
    daily_reward: int | None = None
    chat_cost_per_turn: int | None = None
    creator_reward: int | None = None
    rating_bonus: int | None = None


# ── System Config ──────────────────────────────────────────
class ConfigEntry(BaseModel):
    key: str
    value: str  # JSON-serialized
    group: str
    updated_at: datetime
    updated_by: str

    model_config = {"from_attributes": True}


class ConfigGroupResponse(BaseModel):
    group: str
    entries: dict[str, object]  # key -> typed value


class ConfigUpdateRequest(BaseModel):
    """Update a single config key."""
    key: str
    value: object  # will be JSON-serialized
    group: str


class ConfigBatchUpdateRequest(BaseModel):
    """Update multiple config keys at once."""
    updates: list[ConfigUpdateRequest]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_schemas.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/admin.py tests/test_admin_schemas.py
git commit -m "feat: admin panel Pydantic schemas for all 6 modules"
```

---

## Task 3: Dashboard API — Stats, Trends, Health

**Files:**
- Create: `app/routers/admin/dashboard.py`
- Test: `tests/test_admin_dashboard.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_admin_dashboard.py
import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.user import User
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction


@pytest.mark.anyio
async def test_dashboard_stats(db_session):
    """Dashboard stats should return correct aggregated counts."""
    from app.routers.admin.dashboard import _get_dashboard_stats

    # Create test data
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Users: 2 total, 1 registered today
    u1 = User(name="old_user", email="old@test.com", is_admin=False, is_banned=False,
              created_at=now - timedelta(days=5))
    u2 = User(name="new_user", email="new@test.com", is_admin=False, is_banned=False,
              created_at=now)
    db_session.add_all([u1, u2])
    await db_session.commit()

    # Transactions today: +100 signup, -5 chat
    db_session.add(Transaction(user_id=u2.id, amount=100, reason="signup_bonus", created_at=now))
    db_session.add(Transaction(user_id=u1.id, amount=-5, reason="chat_cost", created_at=now))
    await db_session.commit()

    stats = await _get_dashboard_stats(db_session)
    assert stats["today_registrations"] == 1
    assert stats["soul_coin_net_flow"] == 95  # 100 - 5


@pytest.mark.anyio
async def test_dashboard_trends(db_session):
    """Trends should return 7 data points."""
    from app.routers.admin.dashboard import _get_7day_trends

    trends = await _get_7day_trends(db_session)
    assert len(trends) == 7
    assert all("date" in t and "users" in t and "conversations" in t for t in trends)


@pytest.mark.anyio
async def test_dashboard_top_residents(db_session):
    """Top residents should be sorted by heat descending."""
    from app.routers.admin.dashboard import _get_top_residents

    u = User(name="creator", email="c@test.com", is_admin=False, is_banned=False)
    db_session.add(u)
    await db_session.commit()

    for i in range(3):
        r = Resident(slug=f"r-{i}", name=f"R{i}", creator_id=u.id, heat=i * 10)
        db_session.add(r)
    await db_session.commit()

    top = await _get_top_residents(db_session, limit=10)
    assert len(top) == 3
    assert top[0]["heat"] >= top[1]["heat"] >= top[2]["heat"]


@pytest.mark.anyio
async def test_health_check_formats():
    """Health check should return list of ServiceHealthItem-compatible dicts."""
    from app.routers.admin.dashboard import _check_service_health

    with patch("app.routers.admin.dashboard.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.elapsed = timedelta(milliseconds=50)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        results = await _check_service_health()
    assert isinstance(results, list)
    assert all("service" in r and "status" in r for r in results)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin_dashboard.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/routers/admin/dashboard.py
"""Admin Dashboard — real-time stats, 7-day trends, top residents, health checks."""
from datetime import datetime, timedelta, UTC
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.database import get_db
from app.models.user import User
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction
from app.routers.admin.middleware import require_admin
from app.schemas.admin import (
    DashboardStatsResponse,
    DashboardTrendPoint,
    TopResidentItem,
    ServiceHealthItem,
)
from app.config import settings

router = APIRouter(prefix="/dashboard", tags=["admin-dashboard"])


async def _get_dashboard_stats(db: AsyncSession) -> dict:
    """Compute dashboard metric cards."""
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Today's registrations
    reg_result = await db.execute(
        select(func.count(User.id)).where(User.created_at >= today_start)
    )
    today_registrations = reg_result.scalar() or 0

    # Active chats (conversations with no ended_at)
    chat_result = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.ended_at.is_(None))
    )
    active_chats = chat_result.scalar() or 0

    # Soul Coin net flow today (sum of all transaction amounts today)
    flow_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.created_at >= today_start)
    )
    soul_coin_net_flow = flow_result.scalar() or 0

    # Online users: approximate as users with activity in last 15 min
    # MVP: count users with conversations started in last 15 min
    fifteen_min_ago = now - timedelta(minutes=15)
    online_result = await db.execute(
        select(func.count(func.distinct(Conversation.user_id)))
        .where(Conversation.started_at >= fifteen_min_ago)
    )
    online_users = online_result.scalar() or 0

    return {
        "online_users": online_users,
        "today_registrations": today_registrations,
        "active_chats": active_chats,
        "soul_coin_net_flow": soul_coin_net_flow,
    }


async def _get_7day_trends(db: AsyncSession) -> list[dict]:
    """Return 7-day daily user registration and conversation counts."""
    now = datetime.now(UTC)
    trends = []

    for days_ago in range(6, -1, -1):
        day = (now - timedelta(days=days_ago)).date()
        day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)

        # User registrations that day
        user_result = await db.execute(
            select(func.count(User.id))
            .where(User.created_at >= day_start, User.created_at < day_end)
        )
        user_count = user_result.scalar() or 0

        # Conversations started that day
        conv_result = await db.execute(
            select(func.count(Conversation.id))
            .where(Conversation.started_at >= day_start, Conversation.started_at < day_end)
        )
        conv_count = conv_result.scalar() or 0

        trends.append({
            "date": day.isoformat(),
            "users": user_count,
            "conversations": conv_count,
        })

    return trends


async def _get_top_residents(db: AsyncSession, limit: int = 10) -> list[dict]:
    """Return top N residents by heat."""
    result = await db.execute(
        select(Resident)
        .order_by(Resident.heat.desc())
        .limit(limit)
    )
    residents = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "slug": r.slug,
            "heat": r.heat,
            "district": r.district,
            "star_rating": r.star_rating,
        }
        for r in residents
    ]


async def _check_service_health() -> list[dict]:
    """Ping external services and return health status."""
    results = []

    async with httpx.AsyncClient(timeout=5.0) as client:
        # SearXNG
        try:
            resp = await client.get("http://localhost:8888/healthz")
            latency = int(resp.elapsed.total_seconds() * 1000)
            results.append({
                "service": "searxng",
                "status": "ok" if resp.status_code == 200 else "error",
                "latency_ms": latency,
                "detail": None if resp.status_code == 200 else f"HTTP {resp.status_code}",
            })
        except httpx.TimeoutException:
            results.append({"service": "searxng", "status": "timeout", "latency_ms": None, "detail": "Connection timed out"})
        except Exception as e:
            results.append({"service": "searxng", "status": "error", "latency_ms": None, "detail": str(e)})

        # LLM API (just check if the configured base_url is reachable)
        llm_url = settings.llm_base_url or "https://api.anthropic.com"
        try:
            resp = await client.get(f"{llm_url.rstrip('/')}/v1/models", headers={"x-api-key": "health-check"})
            latency = int(resp.elapsed.total_seconds() * 1000)
            # 401 = reachable but unauthorized = OK for health check
            status = "ok" if resp.status_code in (200, 401) else "error"
            results.append({
                "service": "llm_api",
                "status": status,
                "latency_ms": latency,
                "detail": None if status == "ok" else f"HTTP {resp.status_code}",
            })
        except httpx.TimeoutException:
            results.append({"service": "llm_api", "status": "timeout", "latency_ms": None, "detail": "Connection timed out"})
        except Exception as e:
            results.append({"service": "llm_api", "status": "error", "latency_ms": None, "detail": str(e)})

    return results


@router.get("/stats", response_model=DashboardStatsResponse)
async def dashboard_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Real-time dashboard metric cards."""
    stats = await _get_dashboard_stats(db)
    return DashboardStatsResponse(**stats)


@router.get("/trends", response_model=list[DashboardTrendPoint])
async def dashboard_trends(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """7-day user registration and conversation trends."""
    trends = await _get_7day_trends(db)
    return [DashboardTrendPoint(**t) for t in trends]


@router.get("/top-residents", response_model=list[TopResidentItem])
async def dashboard_top_residents(
    limit: int = 10,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Top N residents by heat."""
    top = await _get_top_residents(db, limit=min(limit, 50))
    return [TopResidentItem(**r) for r in top]


@router.get("/health", response_model=list[ServiceHealthItem])
async def dashboard_health(
    admin: User = Depends(require_admin),
):
    """Ping SearXNG and LLM API health."""
    results = await _check_service_health()
    return [ServiceHealthItem(**r) for r in results]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_dashboard.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin/dashboard.py tests/test_admin_dashboard.py
git commit -m "feat: admin dashboard — stats, 7-day trends, top residents, health checks"
```

---

## Task 4: User Management API

**Files:**
- Create: `app/routers/admin/users.py`
- Test: `tests/test_admin_users.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_admin_users.py
import pytest
from datetime import datetime, UTC
from app.models.user import User
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction


@pytest.mark.anyio
async def test_admin_list_users_pagination(db_session):
    """User list should support offset/limit pagination."""
    from app.routers.admin.users import _list_users

    for i in range(15):
        db_session.add(User(
            name=f"user{i}", email=f"u{i}@test.com",
            is_admin=False, is_banned=False,
        ))
    await db_session.commit()

    users, total = await _list_users(db_session, offset=0, limit=10)
    assert len(users) == 10
    assert total == 15

    users2, _ = await _list_users(db_session, offset=10, limit=10)
    assert len(users2) == 5


@pytest.mark.anyio
async def test_admin_list_users_search(db_session):
    """User list should support search by name or email."""
    from app.routers.admin.users import _list_users

    db_session.add(User(name="Alice", email="alice@test.com", is_admin=False, is_banned=False))
    db_session.add(User(name="Bob", email="bob@test.com", is_admin=False, is_banned=False))
    await db_session.commit()

    users, total = await _list_users(db_session, search="alice")
    assert total == 1
    assert users[0].name == "Alice"


@pytest.mark.anyio
async def test_admin_get_user_detail(db_session):
    """User detail should include counts of residents, conversations, transactions."""
    from app.routers.admin.users import _get_user_detail

    user = User(name="detail_user", email="detail@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    r = Resident(slug="test-r", name="R", creator_id=user.id)
    db_session.add(r)
    db_session.add(Transaction(user_id=user.id, amount=100, reason="signup"))
    await db_session.commit()

    detail = await _get_user_detail(db_session, user.id)
    assert detail is not None
    assert detail["resident_count"] == 1
    assert detail["transaction_count"] == 1


@pytest.mark.anyio
async def test_admin_adjust_balance(db_session):
    """Balance adjustment should update user balance and create transaction."""
    from app.routers.admin.users import _adjust_balance

    user = User(name="rich", email="rich@test.com", soul_coin_balance=100,
                is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    new_balance = await _adjust_balance(db_session, user.id, amount=50, reason="bonus", admin_id="admin-1")
    assert new_balance == 150

    new_balance2 = await _adjust_balance(db_session, user.id, amount=-30, reason="penalty", admin_id="admin-1")
    assert new_balance2 == 120


@pytest.mark.anyio
async def test_admin_ban_unban(db_session):
    """Ban/unban should toggle is_banned."""
    from app.routers.admin.users import _set_ban_status

    user = User(name="target", email="target@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    result = await _set_ban_status(db_session, user.id, is_banned=True)
    assert result is True

    await db_session.refresh(user)
    assert user.is_banned is True

    result2 = await _set_ban_status(db_session, user.id, is_banned=False)
    assert result2 is True

    await db_session.refresh(user)
    assert user.is_banned is False


@pytest.mark.anyio
async def test_admin_set_admin(db_session):
    """Set admin should toggle is_admin."""
    from app.routers.admin.users import _set_admin_status

    user = User(name="promote", email="promote@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    result = await _set_admin_status(db_session, user.id, is_admin=True)
    assert result is True

    await db_session.refresh(user)
    assert user.is_admin is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin_users.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/routers/admin/users.py
"""Admin User Management — list, detail, balance, ban, admin toggle."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction
from app.routers.admin.middleware import require_admin
from app.schemas.admin import (
    AdminUserListItem,
    AdminUserDetail,
    BalanceAdjustRequest,
    SetAdminRequest,
    SetBanRequest,
)

router = APIRouter(prefix="/users", tags=["admin-users"])


async def _list_users(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 20,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[User], int]:
    """List users with pagination, search, sort."""
    query = select(User)
    count_query = select(func.count(User.id))

    if search:
        pattern = f"%{search}%"
        condition = or_(User.name.ilike(pattern), User.email.ilike(pattern))
        query = query.where(condition)
        count_query = count_query.where(condition)

    # Sort
    sort_col = getattr(User, sort_by, User.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    users = list(result.scalars().all())

    return users, total


async def _get_user_detail(db: AsyncSession, user_id: str) -> dict | None:
    """Get user detail with related counts."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None

    # Count residents
    res_count = (await db.execute(
        select(func.count(Resident.id)).where(Resident.creator_id == user_id)
    )).scalar() or 0

    # Count conversations
    conv_count = (await db.execute(
        select(func.count(Conversation.id)).where(Conversation.user_id == user_id)
    )).scalar() or 0

    # Count transactions
    txn_count = (await db.execute(
        select(func.count(Transaction.id)).where(Transaction.user_id == user_id)
    )).scalar() or 0

    return {
        **{c.key: getattr(user, c.key) for c in User.__table__.columns},
        "resident_count": res_count,
        "conversation_count": conv_count,
        "transaction_count": txn_count,
    }


async def _adjust_balance(
    db: AsyncSession,
    user_id: str,
    amount: int,
    reason: str,
    admin_id: str,
) -> int:
    """Adjust user balance. Returns new balance."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    user.soul_coin_balance += amount
    db.add(Transaction(
        user_id=user_id,
        amount=amount,
        reason=f"admin_adjust:{reason} (by {admin_id})",
    ))
    await db.commit()
    return user.soul_coin_balance


async def _set_ban_status(db: AsyncSession, user_id: str, is_banned: bool) -> bool:
    """Set user ban status."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return False
    user.is_banned = is_banned
    await db.commit()
    return True


async def _set_admin_status(db: AsyncSession, user_id: str, is_admin: bool) -> bool:
    """Set user admin status."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return False
    user.is_admin = is_admin
    await db.commit()
    return True


# ── Routes ─────────────────────────────────────────────────

@router.get("")
async def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all users with pagination and search."""
    users, total = await _list_users(db, offset=offset, limit=limit, search=search,
                                      sort_by=sort_by, sort_order=sort_order)
    return {
        "items": [AdminUserListItem.model_validate(u, from_attributes=True) for u in users],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{user_id}")
async def get_user_detail(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed user info including related counts."""
    detail = await _get_user_detail(db, user_id)
    if not detail:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserDetail(**detail)


@router.post("/{user_id}/balance")
async def adjust_balance(
    user_id: str,
    req: BalanceAdjustRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Adjust user Soul Coin balance (positive = add, negative = deduct)."""
    try:
        new_balance = await _adjust_balance(db, user_id, req.amount, req.reason, admin.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"user_id": user_id, "new_balance": new_balance}


@router.post("/{user_id}/ban")
async def set_ban(
    user_id: str,
    req: SetBanRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Ban or unban a user."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot ban yourself")
    ok = await _set_ban_status(db, user_id, req.is_banned)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "is_banned": req.is_banned}


@router.post("/{user_id}/admin")
async def set_admin(
    user_id: str,
    req: SetAdminRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Grant or revoke admin privileges."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot change your own admin status")
    ok = await _set_admin_status(db, user_id, req.is_admin)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "is_admin": req.is_admin}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_users.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin/users.py tests/test_admin_users.py
git commit -m "feat: admin user management — list, detail, balance adjust, ban, admin toggle"
```

---

## Task 5: Resident Management API

**Files:**
- Create: `app/routers/admin/residents.py`
- Test: `tests/test_admin_residents.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_admin_residents.py
import pytest
from app.models.user import User
from app.models.resident import Resident


@pytest.mark.anyio
async def test_admin_list_residents_pagination(db_session):
    """Resident list should support pagination and search."""
    from app.routers.admin.residents import _list_residents

    user = User(name="creator", email="c@test.com", is_admin=True, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    for i in range(12):
        db_session.add(Resident(slug=f"r-{i}", name=f"Resident {i}", creator_id=user.id))
    await db_session.commit()

    residents, total = await _list_residents(db_session, offset=0, limit=5)
    assert len(residents) == 5
    assert total == 12


@pytest.mark.anyio
async def test_admin_list_residents_filter_district(db_session):
    """Should filter by district."""
    from app.routers.admin.residents import _list_residents

    user = User(name="cr", email="cr@test.com", is_admin=True, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    db_session.add(Resident(slug="eng-1", name="Eng", creator_id=user.id, district="engineering"))
    db_session.add(Resident(slug="prod-1", name="Prod", creator_id=user.id, district="product"))
    await db_session.commit()

    residents, total = await _list_residents(db_session, district="engineering")
    assert total == 1
    assert residents[0].district == "engineering"


@pytest.mark.anyio
async def test_admin_edit_resident_persona(db_session):
    """Admin can edit any resident's persona, not just own."""
    from app.routers.admin.residents import _edit_resident

    user = User(name="owner", email="owner@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    r = Resident(slug="edit-me", name="Editable", creator_id=user.id,
                 ability_md="old", persona_md="old", soul_md="old")
    db_session.add(r)
    await db_session.commit()

    updated = await _edit_resident(db_session, r.id, ability_md="new ability", district="academy")
    assert updated.ability_md == "new ability"
    assert updated.district == "academy"
    assert updated.persona_md == "old"  # unchanged


@pytest.mark.anyio
async def test_admin_create_preset_resident(db_session):
    """Admin can create a preset character."""
    from app.routers.admin.residents import _create_preset

    preset = await _create_preset(
        db_session,
        slug="preset-sage",
        name="The Sage",
        district="academy",
        ability_md="# Wisdom",
        persona_md="# Ancient one",
        soul_md="",
        sprite_key="伊莎贝拉",
        tile_x=76,
        tile_y=50,
        resident_type="preset",
        reply_mode="auto",
        meta_json=None,
        creator_id="system",
    )
    assert preset.slug == "preset-sage"
    assert preset.resident_type == "preset"
    assert preset.creator_id == "system"


@pytest.mark.anyio
async def test_admin_batch_district(db_session):
    """Batch district change should update all specified residents."""
    from app.routers.admin.residents import _batch_update_district

    user = User(name="bc", email="bc@test.com", is_admin=True, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    r1 = Resident(slug="b1", name="B1", creator_id=user.id, district="free")
    r2 = Resident(slug="b2", name="B2", creator_id=user.id, district="free")
    db_session.add_all([r1, r2])
    await db_session.commit()

    count = await _batch_update_district(db_session, [r1.id, r2.id], "engineering")
    assert count == 2

    await db_session.refresh(r1)
    await db_session.refresh(r2)
    assert r1.district == "engineering"
    assert r2.district == "engineering"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin_residents.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/routers/admin/residents.py
"""Admin Resident Management — list, detail, edit, presets, batch operations."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.resident import Resident
from app.routers.admin.middleware import require_admin
from app.services.scoring_service import compute_star_rating
from app.schemas.admin import (
    AdminResidentListItem,
    ResidentPersonaEditRequest,
    PresetResidentRequest,
    BatchDistrictRequest,
    BatchStatusResetRequest,
)

router = APIRouter(prefix="/residents", tags=["admin-residents"])


async def _list_residents(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 20,
    search: str | None = None,
    district: str | None = None,
    status: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[Resident], int]:
    """List residents with pagination, search, filters."""
    query = select(Resident)
    count_query = select(func.count(Resident.id))

    if search:
        pattern = f"%{search}%"
        condition = or_(Resident.name.ilike(pattern), Resident.slug.ilike(pattern))
        query = query.where(condition)
        count_query = count_query.where(condition)

    if district:
        query = query.where(Resident.district == district)
        count_query = count_query.where(Resident.district == district)

    if status:
        query = query.where(Resident.status == status)
        count_query = count_query.where(Resident.status == status)

    sort_col = getattr(Resident, sort_by, Resident.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    residents = list(result.scalars().all())

    return residents, total


async def _edit_resident(
    db: AsyncSession,
    resident_id: str,
    ability_md: str | None = None,
    persona_md: str | None = None,
    soul_md: str | None = None,
    district: str | None = None,
    status: str | None = None,
    resident_type: str | None = None,
    reply_mode: str | None = None,
) -> Resident:
    """Admin-level edit of any resident's fields."""
    result = await db.execute(select(Resident).where(Resident.id == resident_id))
    resident = result.scalar_one_or_none()
    if not resident:
        raise ValueError("Resident not found")

    if ability_md is not None:
        resident.ability_md = ability_md
    if persona_md is not None:
        resident.persona_md = persona_md
    if soul_md is not None:
        resident.soul_md = soul_md
    if district is not None:
        resident.district = district
    if status is not None:
        resident.status = status
    if resident_type is not None:
        resident.resident_type = resident_type
    if reply_mode is not None:
        resident.reply_mode = reply_mode

    # Recalculate star rating if persona changed
    if any(x is not None for x in [ability_md, persona_md, soul_md]):
        resident.star_rating = compute_star_rating(resident)

    await db.commit()
    await db.refresh(resident)
    return resident


async def _create_preset(
    db: AsyncSession,
    slug: str,
    name: str,
    district: str,
    ability_md: str,
    persona_md: str,
    soul_md: str,
    sprite_key: str,
    tile_x: int,
    tile_y: int,
    resident_type: str,
    reply_mode: str,
    meta_json: dict | None,
    creator_id: str,
) -> Resident:
    """Create a preset resident (admin-managed NPC)."""
    resident = Resident(
        slug=slug,
        name=name,
        district=district,
        ability_md=ability_md,
        persona_md=persona_md,
        soul_md=soul_md,
        sprite_key=sprite_key,
        tile_x=tile_x,
        tile_y=tile_y,
        resident_type=resident_type,
        reply_mode=reply_mode,
        meta_json=meta_json or {"origin": "preset"},
        creator_id=creator_id,
    )
    resident.star_rating = compute_star_rating(resident)
    db.add(resident)
    await db.commit()
    await db.refresh(resident)
    return resident


async def _batch_update_district(
    db: AsyncSession, resident_ids: list[str], district: str
) -> int:
    """Batch update district for multiple residents."""
    result = await db.execute(
        select(Resident).where(Resident.id.in_(resident_ids))
    )
    residents = result.scalars().all()
    for r in residents:
        r.district = district
    await db.commit()
    return len(residents)


async def _batch_reset_status(
    db: AsyncSession, resident_ids: list[str], status: str = "idle"
) -> int:
    """Batch reset status for multiple residents."""
    result = await db.execute(
        select(Resident).where(Resident.id.in_(resident_ids))
    )
    residents = result.scalars().all()
    for r in residents:
        r.status = status
    await db.commit()
    return len(residents)


# ── Routes ─────────────────────────────────────────────────

@router.get("")
async def list_residents(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = None,
    district: str | None = None,
    status: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all residents with filters and pagination."""
    residents, total = await _list_residents(
        db, offset=offset, limit=limit, search=search,
        district=district, status=status, sort_by=sort_by, sort_order=sort_order,
    )
    return {
        "items": [AdminResidentListItem.model_validate(r, from_attributes=True) for r in residents],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{resident_id}")
async def get_resident_detail(
    resident_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get full resident detail (all fields including persona layers)."""
    result = await db.execute(select(Resident).where(Resident.id == resident_id))
    resident = result.scalar_one_or_none()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")
    # Return all columns as dict
    data = {c.key: getattr(resident, c.key) for c in Resident.__table__.columns}
    return data


@router.put("/{resident_id}")
async def edit_resident(
    resident_id: str,
    req: ResidentPersonaEditRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Edit any resident's persona layers, district, status, type, reply mode."""
    try:
        resident = await _edit_resident(
            db, resident_id,
            ability_md=req.ability_md, persona_md=req.persona_md, soul_md=req.soul_md,
            district=req.district, status=req.status,
            resident_type=req.resident_type, reply_mode=req.reply_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return AdminResidentListItem.model_validate(resident, from_attributes=True)


@router.post("/presets")
async def create_preset(
    req: PresetResidentRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new preset (admin-managed) resident."""
    try:
        resident = await _create_preset(
            db,
            slug=req.slug, name=req.name, district=req.district,
            ability_md=req.ability_md, persona_md=req.persona_md, soul_md=req.soul_md,
            sprite_key=req.sprite_key, tile_x=req.tile_x, tile_y=req.tile_y,
            resident_type=req.resident_type, reply_mode=req.reply_mode,
            meta_json=req.meta_json, creator_id="system",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return AdminResidentListItem.model_validate(resident, from_attributes=True)


@router.delete("/presets/{resident_id}")
async def delete_preset(
    resident_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a preset resident. Only allows deletion of resident_type='preset'."""
    result = await db.execute(select(Resident).where(Resident.id == resident_id))
    resident = result.scalar_one_or_none()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")
    if resident.resident_type != "preset":
        raise HTTPException(status_code=400, detail="Can only delete preset residents via this endpoint")
    await db.delete(resident)
    await db.commit()
    return {"deleted": True, "id": resident_id}


@router.post("/batch/district")
async def batch_district(
    req: BatchDistrictRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Batch change district for multiple residents."""
    count = await _batch_update_district(db, req.resident_ids, req.district)
    return {"updated": count}


@router.post("/batch/status-reset")
async def batch_status_reset(
    req: BatchStatusResetRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Batch reset status for multiple residents."""
    count = await _batch_reset_status(db, req.resident_ids, req.status)
    return {"updated": count}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_residents.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin/residents.py tests/test_admin_residents.py
git commit -m "feat: admin resident management — list, edit, presets, batch ops"
```

---

## Task 6: Forge Monitor API

**Files:**
- Create: `app/routers/admin/forge_monitor.py`
- Test: `tests/test_admin_forge_monitor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_admin_forge_monitor.py
import pytest
from datetime import datetime, UTC
from app.models.user import User
from app.models.forge_session import ForgeSession


@pytest.mark.anyio
async def test_forge_list_sessions(db_session):
    """Should list forge sessions with pagination and filters."""
    from app.routers.admin.forge_monitor import _list_forge_sessions

    user = User(name="forger", email="forger@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    for i in range(5):
        db_session.add(ForgeSession(
            user_id=user.id,
            character_name=f"Char {i}",
            mode="deep" if i % 2 == 0 else "quick",
            status="completed" if i < 3 else "routing",
        ))
    await db_session.commit()

    sessions, total = await _list_forge_sessions(db_session, offset=0, limit=10)
    assert total == 5
    assert len(sessions) == 5


@pytest.mark.anyio
async def test_forge_list_filter_status(db_session):
    """Should filter by status."""
    from app.routers.admin.forge_monitor import _list_forge_sessions

    user = User(name="f2", email="f2@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    db_session.add(ForgeSession(user_id=user.id, character_name="Active", mode="deep", status="routing"))
    db_session.add(ForgeSession(user_id=user.id, character_name="Done", mode="quick", status="completed"))
    await db_session.commit()

    sessions, total = await _list_forge_sessions(db_session, status="routing")
    assert total == 1
    assert sessions[0].status == "routing"


@pytest.mark.anyio
async def test_forge_session_detail(db_session):
    """Should return full session detail including JSON fields."""
    from app.routers.admin.forge_monitor import _get_forge_session

    user = User(name="f3", email="f3@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    session = ForgeSession(
        user_id=user.id,
        character_name="Detailed",
        mode="deep",
        status="completed",
        research_data={"query": "test", "results": 5},
        validation_report={"passed": True, "score": 0.95},
    )
    db_session.add(session)
    await db_session.commit()

    detail = await _get_forge_session(db_session, session.id)
    assert detail is not None
    assert detail.character_name == "Detailed"
    assert detail.research_data["results"] == 5
    assert detail.validation_report["passed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin_forge_monitor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/routers/admin/forge_monitor.py
"""Admin Forge Monitor — session list, detail, SearXNG health."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.database import get_db
from app.models.user import User
from app.models.forge_session import ForgeSession
from app.routers.admin.middleware import require_admin
from app.schemas.admin import ForgeSessionListItem, ForgeSessionDetail, ServiceHealthItem

router = APIRouter(prefix="/forge", tags=["admin-forge"])


async def _list_forge_sessions(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 20,
    status: str | None = None,
    mode: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[ForgeSession], int]:
    """List forge sessions with pagination and filters."""
    query = select(ForgeSession)
    count_query = select(func.count(ForgeSession.id))

    if status:
        query = query.where(ForgeSession.status == status)
        count_query = count_query.where(ForgeSession.status == status)

    if mode:
        query = query.where(ForgeSession.mode == mode)
        count_query = count_query.where(ForgeSession.mode == mode)

    sort_col = getattr(ForgeSession, sort_by, ForgeSession.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    sessions = list(result.scalars().all())

    return sessions, total


async def _get_forge_session(db: AsyncSession, session_id: str) -> ForgeSession | None:
    """Get a single forge session by ID."""
    result = await db.execute(
        select(ForgeSession).where(ForgeSession.id == session_id)
    )
    return result.scalar_one_or_none()


# ── Routes ─────────────────────────────────────────────────

@router.get("")
async def list_forge_sessions(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    mode: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all forge sessions with filters."""
    sessions, total = await _list_forge_sessions(
        db, offset=offset, limit=limit, status=status, mode=mode,
        sort_by=sort_by, sort_order=sort_order,
    )
    return {
        "items": [ForgeSessionListItem.model_validate(s, from_attributes=True) for s in sessions],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/active")
async def list_active_forge_sessions(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List currently active (non-completed, non-error) forge sessions."""
    result = await db.execute(
        select(ForgeSession)
        .where(ForgeSession.status.notin_(["completed", "error"]))
        .order_by(ForgeSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    return [ForgeSessionListItem.model_validate(s, from_attributes=True) for s in sessions]


@router.get("/searxng-health", response_model=ServiceHealthItem)
async def searxng_health(
    admin: User = Depends(require_admin),
):
    """Dedicated SearXNG health check with extended diagnostics."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("http://localhost:8888/healthz")
            latency = int(resp.elapsed.total_seconds() * 1000)
            if resp.status_code == 200:
                return ServiceHealthItem(service="searxng", status="ok", latency_ms=latency)
            return ServiceHealthItem(
                service="searxng", status="error", latency_ms=latency,
                detail=f"HTTP {resp.status_code}",
            )
    except httpx.TimeoutException:
        return ServiceHealthItem(service="searxng", status="timeout", detail="Connection timed out")
    except Exception as e:
        return ServiceHealthItem(service="searxng", status="error", detail=str(e))


@router.get("/{session_id}")
async def get_forge_session_detail(
    session_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get full forge session detail including all JSON data."""
    session = await _get_forge_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Forge session not found")
    return ForgeSessionDetail.model_validate(session, from_attributes=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_forge_monitor.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin/forge_monitor.py tests/test_admin_forge_monitor.py
git commit -m "feat: admin forge monitor — session list, detail, active sessions, SearXNG health"
```

---

## Task 7: Economy API

**Files:**
- Create: `app/routers/admin/economy.py`
- Test: `tests/test_admin_economy.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_admin_economy.py
import pytest
from app.models.user import User
from app.models.transaction import Transaction


@pytest.mark.anyio
async def test_economy_global_stats(db_session):
    """Economy stats should aggregate correctly."""
    from app.routers.admin.economy import _get_economy_stats

    u1 = User(name="u1", email="u1@test.com", soul_coin_balance=150,
              is_admin=False, is_banned=False)
    u2 = User(name="u2", email="u2@test.com", soul_coin_balance=50,
              is_admin=False, is_banned=False)
    db_session.add_all([u1, u2])
    await db_session.commit()

    # Positive transactions (issued)
    db_session.add(Transaction(user_id=u1.id, amount=100, reason="signup"))
    db_session.add(Transaction(user_id=u2.id, amount=100, reason="signup"))
    db_session.add(Transaction(user_id=u1.id, amount=50, reason="daily"))
    # Negative transactions (consumed)
    db_session.add(Transaction(user_id=u2.id, amount=-50, reason="chat"))
    await db_session.commit()

    stats = await _get_economy_stats(db_session)
    assert stats["total_issued"] == 250  # 100 + 100 + 50
    assert stats["total_consumed"] == 50  # abs(-50)
    assert stats["net_circulation"] == 200  # 250 - 50
    assert stats["total_users"] == 2
    assert stats["avg_balance"] == 100.0  # (150 + 50) / 2


@pytest.mark.anyio
async def test_economy_transaction_log(db_session):
    """Transaction log should support pagination and filters."""
    from app.routers.admin.economy import _get_transaction_log

    u = User(name="txn", email="txn@test.com", is_admin=False, is_banned=False)
    db_session.add(u)
    await db_session.commit()

    for i in range(8):
        db_session.add(Transaction(
            user_id=u.id,
            amount=10 if i % 2 == 0 else -5,
            reason="signup" if i % 2 == 0 else "chat",
        ))
    await db_session.commit()

    txns, total = await _get_transaction_log(db_session, offset=0, limit=5)
    assert total == 8
    assert len(txns) == 5

    # Filter by reason
    txns2, total2 = await _get_transaction_log(db_session, reason="chat")
    assert total2 == 4


@pytest.mark.anyio
async def test_economy_config_update(db_session):
    """Economy config update should write to ConfigService."""
    from app.routers.admin.economy import _update_economy_config
    from app.services.config_service import ConfigService

    svc = ConfigService(db_session)
    await _update_economy_config(db_session, admin_id="admin-1", signup_bonus=200, daily_reward=10)

    value = await svc.get("economy.signup_bonus", default=100)
    assert value == 200

    value2 = await svc.get("economy.daily_reward", default=5)
    assert value2 == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin_economy.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/routers/admin/economy.py
"""Admin Economy — global stats, transaction log, dynamic config."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.transaction import Transaction
from app.routers.admin.middleware import require_admin
from app.services.config_service import ConfigService
from app.schemas.admin import (
    EconomyStatsResponse,
    TransactionLogItem,
    EconomyConfigUpdate,
)

router = APIRouter(prefix="/economy", tags=["admin-economy"])


async def _get_economy_stats(db: AsyncSession) -> dict:
    """Compute global economy statistics."""
    # Total issued (sum of positive amounts)
    issued_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.amount > 0)
    )
    total_issued = issued_result.scalar() or 0

    # Total consumed (sum of negative amounts, as absolute value)
    consumed_result = await db.execute(
        select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0))
        .where(Transaction.amount < 0)
    )
    total_consumed = consumed_result.scalar() or 0

    # User stats
    user_stats = await db.execute(
        select(
            func.count(User.id),
            func.coalesce(func.avg(User.soul_coin_balance), 0),
        )
    )
    row = user_stats.one()
    total_users = row[0] or 0
    avg_balance = float(row[1] or 0)

    return {
        "total_issued": total_issued,
        "total_consumed": total_consumed,
        "net_circulation": total_issued - total_consumed,
        "total_users": total_users,
        "avg_balance": round(avg_balance, 2),
    }


async def _get_transaction_log(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 20,
    user_id: str | None = None,
    reason: str | None = None,
) -> tuple[list[Transaction], int]:
    """Get transaction log with filters and pagination."""
    query = select(Transaction)
    count_query = select(func.count(Transaction.id))

    if user_id:
        query = query.where(Transaction.user_id == user_id)
        count_query = count_query.where(Transaction.user_id == user_id)

    if reason:
        pattern = f"%{reason}%"
        query = query.where(Transaction.reason.ilike(pattern))
        count_query = count_query.where(Transaction.reason.ilike(pattern))

    query = query.order_by(Transaction.created_at.desc())
    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    transactions = list(result.scalars().all())

    return transactions, total


async def _update_economy_config(
    db: AsyncSession,
    admin_id: str,
    signup_bonus: int | None = None,
    daily_reward: int | None = None,
    chat_cost_per_turn: int | None = None,
    creator_reward: int | None = None,
    rating_bonus: int | None = None,
) -> dict:
    """Update economy parameters in dynamic config."""
    svc = ConfigService(db)
    updated = {}

    params = {
        "economy.signup_bonus": signup_bonus,
        "economy.daily_reward": daily_reward,
        "economy.chat_cost_per_turn": chat_cost_per_turn,
        "economy.creator_reward": creator_reward,
        "economy.rating_bonus": rating_bonus,
    }

    for key, value in params.items():
        if value is not None:
            await svc.set(key, value, group="economy", updated_by=admin_id)
            updated[key] = value

    return updated


# ── Routes ─────────────────────────────────────────────────

@router.get("/stats", response_model=EconomyStatsResponse)
async def economy_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Global economy statistics."""
    stats = await _get_economy_stats(db)
    return EconomyStatsResponse(**stats)


@router.get("/transactions")
async def transaction_log(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: str | None = None,
    reason: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Transaction log with filters and pagination."""
    transactions, total = await _get_transaction_log(
        db, offset=offset, limit=limit, user_id=user_id, reason=reason,
    )
    return {
        "items": [TransactionLogItem.model_validate(t, from_attributes=True) for t in transactions],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.put("/config")
async def update_economy_config(
    req: EconomyConfigUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update economy dynamic parameters."""
    updated = await _update_economy_config(
        db, admin_id=admin.id,
        signup_bonus=req.signup_bonus, daily_reward=req.daily_reward,
        chat_cost_per_turn=req.chat_cost_per_turn,
        creator_reward=req.creator_reward, rating_bonus=req.rating_bonus,
    )
    if not updated:
        raise HTTPException(status_code=400, detail="No parameters to update")
    return {"updated": updated}


@router.get("/config")
async def get_economy_config(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get current economy config values with defaults."""
    svc = ConfigService(db)
    return {
        "signup_bonus": await svc.get("economy.signup_bonus", default=100),
        "daily_reward": await svc.get("economy.daily_reward", default=5),
        "chat_cost_per_turn": await svc.get("economy.chat_cost_per_turn", default=1),
        "creator_reward": await svc.get("economy.creator_reward", default=1),
        "rating_bonus": await svc.get("economy.rating_bonus", default=2),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_economy.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin/economy.py tests/test_admin_economy.py
git commit -m "feat: admin economy — global stats, transaction log, dynamic config CRUD"
```

---

## Task 8: System Config API

**Files:**
- Create: `app/routers/admin/system_config.py`
- Test: `tests/test_admin_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_admin_config.py
import pytest
from app.services.config_service import ConfigService


@pytest.mark.anyio
async def test_get_config_group(db_session):
    """Should return all entries in a config group."""
    from app.routers.admin.system_config import _get_config_group

    svc = ConfigService(db_session)
    await svc.set("llm.system_model", "claude-sonnet-4-20250514", group="llm", updated_by="admin")
    await svc.set("llm.system_temperature", 0.3, group="llm", updated_by="admin")
    await svc.set("economy.signup_bonus", 100, group="economy", updated_by="admin")

    result = await _get_config_group(db_session, "llm")
    assert result == {
        "llm.system_model": "claude-sonnet-4-20250514",
        "llm.system_temperature": 0.3,
    }


@pytest.mark.anyio
async def test_set_config_single(db_session):
    """Should update a single config entry."""
    from app.routers.admin.system_config import _set_config

    await _set_config(db_session, key="heat.popular_threshold", value=80,
                      group="heat", admin_id="admin-1")

    svc = ConfigService(db_session)
    val = await svc.get("heat.popular_threshold", default=50)
    assert val == 80


@pytest.mark.anyio
async def test_set_config_batch(db_session):
    """Should update multiple config entries at once."""
    from app.routers.admin.system_config import _set_config_batch

    updates = [
        {"key": "llm.system_model", "value": "claude-haiku-4-5-20251001", "group": "llm"},
        {"key": "llm.system_timeout", "value": 60, "group": "llm"},
    ]
    await _set_config_batch(db_session, updates, admin_id="admin-1")

    svc = ConfigService(db_session)
    assert await svc.get("llm.system_model") == "claude-haiku-4-5-20251001"
    assert await svc.get("llm.system_timeout") == 60


@pytest.mark.anyio
async def test_get_all_config_groups(db_session):
    """Should list all distinct config groups."""
    from app.routers.admin.system_config import _get_all_groups

    svc = ConfigService(db_session)
    await svc.set("llm.model", "x", group="llm", updated_by="a")
    await svc.set("economy.bonus", 1, group="economy", updated_by="a")
    await svc.set("heat.threshold", 50, group="heat", updated_by="a")

    groups = await _get_all_groups(db_session)
    assert set(groups) == {"llm", "economy", "heat"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin_config.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# app/routers/admin/system_config.py
"""Admin System Config — read/write dynamic config for all groups.

Config groups:
- llm: system_model, system_temperature, system_timeout, system_max_retries,
       user_model, user_temperature_chat, user_temperature_forge, user_timeout,
       user_max_retries, user_concurrency,
       portrait_model, portrait_base_url, portrait_timeout,
       thinking_enabled, thinking_budget, fallback_model
- economy: signup_bonus, daily_reward, chat_cost_per_turn, creator_reward, rating_bonus
- heat: popular_threshold, sleeping_days, scoring_weights
- district: map_config
- oauth: linuxdo_enabled, github_enabled
- sprite: template_list
- user_llm: allow_custom_llm
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.system_config import SystemConfig
from app.routers.admin.middleware import require_admin
from app.services.config_service import ConfigService
from app.schemas.admin import (
    ConfigGroupResponse,
    ConfigUpdateRequest,
    ConfigBatchUpdateRequest,
    ConfigEntry,
)

router = APIRouter(prefix="/system", tags=["admin-system"])


async def _get_config_group(db: AsyncSession, group: str) -> dict:
    """Get all config entries for a group."""
    svc = ConfigService(db)
    return await svc.get_group(group)


async def _set_config(
    db: AsyncSession,
    key: str,
    value: object,
    group: str,
    admin_id: str,
) -> None:
    """Set a single config entry."""
    svc = ConfigService(db)
    await svc.set(key, value, group=group, updated_by=admin_id)


async def _set_config_batch(
    db: AsyncSession,
    updates: list[dict],
    admin_id: str,
) -> None:
    """Set multiple config entries at once."""
    svc = ConfigService(db)
    for entry in updates:
        await svc.set(
            entry["key"], entry["value"],
            group=entry["group"], updated_by=admin_id,
        )


async def _get_all_groups(db: AsyncSession) -> list[str]:
    """Get all distinct config groups."""
    result = await db.execute(
        select(func.distinct(SystemConfig.group)).order_by(SystemConfig.group)
    )
    return [row[0] for row in result.all()]


# ── Routes ─────────────────────────────────────────────────

@router.get("/groups")
async def list_config_groups(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all distinct config groups."""
    groups = await _get_all_groups(db)
    return {"groups": groups}


@router.get("/groups/{group}", response_model=ConfigGroupResponse)
async def get_config_group(
    group: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all config entries for a specific group."""
    entries = await _get_config_group(db, group)
    return ConfigGroupResponse(group=group, entries=entries)


@router.get("/entries")
async def list_all_config_entries(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all config entries across all groups."""
    result = await db.execute(
        select(SystemConfig).order_by(SystemConfig.group, SystemConfig.key)
    )
    entries = result.scalars().all()
    return [ConfigEntry.model_validate(e, from_attributes=True) for e in entries]


@router.put("/entry")
async def update_config_entry(
    req: ConfigUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a single config entry."""
    await _set_config(db, key=req.key, value=req.value, group=req.group, admin_id=admin.id)
    return {"key": req.key, "value": req.value, "group": req.group}


@router.put("/batch")
async def update_config_batch(
    req: ConfigBatchUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update multiple config entries at once."""
    updates = [{"key": u.key, "value": u.value, "group": u.group} for u in req.updates]
    await _set_config_batch(db, updates, admin_id=admin.id)
    return {"updated": len(updates)}


# ── Convenience: LLM Config ───────────────────────────────

@router.get("/llm")
async def get_llm_config(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all LLM-related config with defaults."""
    svc = ConfigService(db)
    return {
        "system_model": await svc.get("llm.system_model", default="claude-haiku-4-5-20251001"),
        "system_temperature": await svc.get("llm.system_temperature", default=0.3),
        "system_timeout": await svc.get("llm.system_timeout", default=30),
        "system_max_retries": await svc.get("llm.system_max_retries", default=2),
        "user_temperature_chat": await svc.get("llm.user_temperature_chat", default=0.7),
        "user_temperature_forge": await svc.get("llm.user_temperature_forge", default=0.5),
        "user_timeout": await svc.get("llm.user_timeout", default=120),
        "user_max_retries": await svc.get("llm.user_max_retries", default=3),
        "user_concurrency": await svc.get("llm.user_concurrency", default=5),
        "portrait_model": await svc.get("llm.portrait_model", default="gemini-3-pro-image-preview"),
        "portrait_timeout": await svc.get("llm.portrait_timeout", default=180),
        "thinking_enabled": await svc.get("llm.thinking_enabled", default=False),
        "thinking_budget": await svc.get("llm.thinking_budget", default=10000),
        "fallback_model": await svc.get("llm.fallback_model", default=""),
    }


@router.get("/heat")
async def get_heat_config(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get heat/scoring config with defaults."""
    svc = ConfigService(db)
    return {
        "popular_threshold": await svc.get("heat.popular_threshold", default=50),
        "sleeping_days": await svc.get("heat.sleeping_days", default=7),
        "scoring_weights": await svc.get("heat.scoring_weights", default={
            "persona_length": 0.3,
            "conversations": 0.3,
            "avg_rating": 0.4,
        }),
    }


@router.get("/user-llm-policy")
async def get_user_llm_policy(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get user custom LLM policy."""
    svc = ConfigService(db)
    return {
        "allow_custom_llm": await svc.get("user_llm.allow_custom_llm", default=False),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_config.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin/system_config.py tests/test_admin_config.py
git commit -m "feat: admin system config — group CRUD, LLM config, heat config, batch update"
```

---

## Task 9: Admin Router Aggregation + main.py Integration

**Files:**
- Modify: `app/routers/admin/__init__.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_router_integration.py
import pytest


def test_admin_router_has_all_sub_routers():
    """Admin router should include all 6 sub-routers."""
    from app.routers.admin import admin_router

    # Collect all route paths
    paths = set()
    for route in admin_router.routes:
        if hasattr(route, "path"):
            paths.add(route.path)

    # Verify each module contributes at least one route
    assert any("/dashboard" in p for p in paths), "Missing dashboard routes"
    assert any("/users" in p for p in paths), "Missing users routes"
    assert any("/residents" in p for p in paths), "Missing residents routes"
    assert any("/forge" in p for p in paths), "Missing forge routes"
    assert any("/economy" in p for p in paths), "Missing economy routes"
    assert any("/system" in p for p in paths), "Missing system routes"


def test_app_includes_admin_router():
    """Main FastAPI app should include the admin router under /admin prefix."""
    from app.main import app

    paths = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)

    # Check that admin-prefixed routes exist
    assert any("/admin" in p for p in paths), f"No /admin routes found in: {paths}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin_router_integration.py -v`
Expected: FAIL (admin_router not defined, /admin not in app)

- [ ] **Step 3: Write implementation**

```python
# app/routers/admin/__init__.py
"""Admin router package — all endpoints require is_admin=True.

Aggregates sub-routers for dashboard, users, residents, forge, economy, system config.
Mount as: app.include_router(admin_router, prefix="/admin")
"""
from fastapi import APIRouter

from app.routers.admin.dashboard import router as dashboard_router
from app.routers.admin.users import router as users_router
from app.routers.admin.residents import router as residents_router
from app.routers.admin.forge_monitor import router as forge_router
from app.routers.admin.economy import router as economy_router
from app.routers.admin.system_config import router as system_router

admin_router = APIRouter()

admin_router.include_router(dashboard_router)
admin_router.include_router(users_router)
admin_router.include_router(residents_router)
admin_router.include_router(forge_router)
admin_router.include_router(economy_router)
admin_router.include_router(system_router)
```

Modify `app/main.py` — add admin router import and include:

```python
# app/main.py — add after existing router imports:
from app.routers.admin import admin_router

# add after existing include_router calls:
app.include_router(admin_router, prefix="/admin", tags=["admin"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_router_integration.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin/__init__.py app/main.py tests/test_admin_router_integration.py
git commit -m "feat: aggregate admin sub-routers and mount at /admin in main app"
```

---

## Task 10: End-to-End Admin API Test (Integration)

**Files:**
- Create: `tests/test_admin_e2e.py`

- [ ] **Step 1: Write integration tests using test client**

```python
# tests/test_admin_e2e.py
"""End-to-end tests for admin API endpoints using FastAPI TestClient."""
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient


@pytest.fixture
def admin_headers():
    """Generate auth headers for a valid admin user."""
    from app.services.auth_service import create_token
    token = create_token("admin-e2e-user-id")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def non_admin_headers():
    """Generate auth headers for a non-admin user."""
    from app.services.auth_service import create_token
    token = create_token("regular-e2e-user-id")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_admin_endpoint_rejects_unauthenticated(client: AsyncClient):
    """All admin endpoints should reject requests without auth."""
    resp = await client.get("/admin/dashboard/stats")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_admin_endpoint_rejects_non_admin(client: AsyncClient, db_session, non_admin_headers):
    """Admin endpoints should reject non-admin users."""
    from app.models.user import User

    user = User(id="regular-e2e-user-id", name="regular", email="reg@e2e.com",
                is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    resp = await client.get("/admin/dashboard/stats", headers=non_admin_headers)
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_admin_dashboard_stats_e2e(client: AsyncClient, db_session, admin_headers):
    """Full e2e: create admin user, hit dashboard stats, verify response shape."""
    from app.models.user import User

    admin = User(id="admin-e2e-user-id", name="admin", email="admin@e2e.com",
                 is_admin=True, is_banned=False)
    db_session.add(admin)
    await db_session.commit()

    resp = await client.get("/admin/dashboard/stats", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "online_users" in data
    assert "today_registrations" in data
    assert "active_chats" in data
    assert "soul_coin_net_flow" in data


@pytest.mark.anyio
async def test_admin_users_list_e2e(client: AsyncClient, db_session, admin_headers):
    """Full e2e: admin user list with pagination."""
    from app.models.user import User

    admin = User(id="admin-e2e-user-id", name="admin", email="admin@e2e.com",
                 is_admin=True, is_banned=False)
    db_session.add(admin)
    await db_session.commit()

    resp = await client.get("/admin/users?limit=10", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1  # at least the admin user


@pytest.mark.anyio
async def test_admin_economy_stats_e2e(client: AsyncClient, db_session, admin_headers):
    """Full e2e: economy stats."""
    from app.models.user import User

    admin = User(id="admin-e2e-user-id", name="admin", email="admin@e2e.com",
                 is_admin=True, is_banned=False)
    db_session.add(admin)
    await db_session.commit()

    resp = await client.get("/admin/economy/stats", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_issued" in data
    assert "net_circulation" in data


@pytest.mark.anyio
async def test_admin_system_config_round_trip(client: AsyncClient, db_session, admin_headers):
    """Full e2e: write a config entry, then read it back."""
    from app.models.user import User

    admin = User(id="admin-e2e-user-id", name="admin", email="admin@e2e.com",
                 is_admin=True, is_banned=False)
    db_session.add(admin)
    await db_session.commit()

    # Write
    resp = await client.put(
        "/admin/system/entry",
        headers=admin_headers,
        json={"key": "test.e2e_key", "value": 42, "group": "test"},
    )
    assert resp.status_code == 200

    # Read back
    resp = await client.get("/admin/system/groups/test", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"]["test.e2e_key"] == 42


@pytest.mark.anyio
async def test_admin_cannot_ban_self(client: AsyncClient, db_session, admin_headers):
    """Admin should not be able to ban themselves."""
    from app.models.user import User

    admin = User(id="admin-e2e-user-id", name="admin", email="admin@e2e.com",
                 is_admin=True, is_banned=False)
    db_session.add(admin)
    await db_session.commit()

    resp = await client.post(
        "/admin/users/admin-e2e-user-id/ban",
        headers=admin_headers,
        json={"is_banned": True},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_admin_e2e.py -v`
Expected: All 8 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_admin_e2e.py
git commit -m "test: admin panel end-to-end integration tests"
```

---

## Task 11: Full Test Suite Verification

**Files:**
- No new files

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend && python -m pytest tests/ -v`
Expected: All tests PASS (existing + all new admin tests)

- [ ] **Step 2: Verify all imports work**

```bash
python -c "
from app.routers.admin import admin_router
from app.routers.admin.middleware import require_admin
from app.routers.admin.dashboard import router as dashboard_router
from app.routers.admin.users import router as users_router
from app.routers.admin.residents import router as residents_router
from app.routers.admin.forge_monitor import router as forge_router
from app.routers.admin.economy import router as economy_router
from app.routers.admin.system_config import router as system_router
from app.schemas.admin import DashboardStatsResponse, AdminUserListItem, EconomyStatsResponse
print('All admin imports OK')
print(f'Dashboard routes: {len(dashboard_router.routes)}')
print(f'User routes: {len(users_router.routes)}')
print(f'Resident routes: {len(residents_router.routes)}')
print(f'Forge routes: {len(forge_router.routes)}')
print(f'Economy routes: {len(economy_router.routes)}')
print(f'System routes: {len(system_router.routes)}')
"
```

Expected: "All admin imports OK" + route counts printed.

- [ ] **Step 3: Verify OpenAPI docs include admin routes**

```bash
python -c "
from app.main import app
admin_routes = [r.path for r in app.routes if hasattr(r, 'path') and '/admin' in r.path]
print(f'Admin routes registered: {len(admin_routes)}')
for r in sorted(admin_routes):
    print(f'  {r}')
"
```

Expected: ~25+ admin routes listed.

- [ ] **Step 4: Commit if any fixes needed**

```bash
git add -A
git commit -m "chore: Plan 6 admin panel final integration verification"
```

---

## Summary

| Task | What it does | Key Files |
|------|-------------|-----------|
| 1 | Admin middleware (`require_admin` dependency) | middleware.py, test |
| 2 | Pydantic schemas for all 6 admin modules | admin.py (schemas), test |
| 3 | Dashboard API (stats, trends, top residents, health) | dashboard.py, test |
| 4 | User management (list, detail, balance, ban, admin) | users.py, test |
| 5 | Resident management (list, edit, presets, batch) | residents.py, test |
| 6 | Forge monitor (sessions, active, SearXNG health) | forge_monitor.py, test |
| 7 | Economy (stats, transactions, dynamic config) | economy.py, test |
| 8 | System config (groups, entries, LLM/heat/policy) | system_config.py, test |
| 9 | Router aggregation + main.py mount at /admin | __init__.py, main.py, test |
| 10 | End-to-end integration tests | test_admin_e2e.py |
| 11 | Full test suite verification | — |

### API Route Summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/dashboard/stats` | Real-time metric cards |
| GET | `/admin/dashboard/trends` | 7-day registration + conversation trends |
| GET | `/admin/dashboard/top-residents` | Top N residents by heat |
| GET | `/admin/dashboard/health` | SearXNG + LLM API health |
| GET | `/admin/users` | User list (paginated, searchable) |
| GET | `/admin/users/{id}` | User detail with counts |
| POST | `/admin/users/{id}/balance` | Adjust Soul Coin balance |
| POST | `/admin/users/{id}/ban` | Ban/unban user |
| POST | `/admin/users/{id}/admin` | Grant/revoke admin |
| GET | `/admin/residents` | Resident list (filtered, paginated) |
| GET | `/admin/residents/{id}` | Full resident detail |
| PUT | `/admin/residents/{id}` | Edit any resident |
| POST | `/admin/residents/presets` | Create preset character |
| DELETE | `/admin/residents/presets/{id}` | Delete preset character |
| POST | `/admin/residents/batch/district` | Batch district change |
| POST | `/admin/residents/batch/status-reset` | Batch status reset |
| GET | `/admin/forge` | Forge session list |
| GET | `/admin/forge/active` | Active forge sessions |
| GET | `/admin/forge/searxng-health` | SearXNG health check |
| GET | `/admin/forge/{id}` | Forge session detail |
| GET | `/admin/economy/stats` | Global economy statistics |
| GET | `/admin/economy/transactions` | Transaction log |
| PUT | `/admin/economy/config` | Update economy parameters |
| GET | `/admin/economy/config` | Get economy parameters |
| GET | `/admin/system/groups` | List config groups |
| GET | `/admin/system/groups/{group}` | Get group config |
| GET | `/admin/system/entries` | List all config entries |
| PUT | `/admin/system/entry` | Update single config |
| PUT | `/admin/system/batch` | Batch config update |
| GET | `/admin/system/llm` | LLM config with defaults |
| GET | `/admin/system/heat` | Heat/scoring config |
| GET | `/admin/system/user-llm-policy` | User custom LLM policy |
