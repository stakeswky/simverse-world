# Plan 7: User Settings Panel (Backend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现用户设置面板的完整后端 API——6 组设置（账号、角色、交互、隐私、LLM、经济）通过 `/settings/*` 端点暴露，支持读取、修改和特殊操作（绑定/解绑 OAuth、删除账号、重铸角色、测试 LLM 连接）。

**Architecture:** 单一 settings router 承载所有 `/settings/*` 端点。Pydantic schemas 按组分层。业务逻辑集中在 settings_service.py，调用已有的 auth_service（密码变更）、portrait_service / sprite_service（Plan 4 角色视觉）。settings_json 字段存储 interaction / privacy / economy / llm 等非结构化设置。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, httpx (LLM connection test), pytest + pytest-asyncio

**Working directory:** `/Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend/`

**Depends on:** Plan 1 (Foundation) — User model settings_json, custom_llm_* fields; Plan 4 (Character + Visual) — player_resident_id, portrait_service, sprite_service

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/schemas/settings.py` | Create | All Pydantic request/response schemas for 6 setting groups |
| `app/services/settings_service.py` | Create | Settings business logic: validation, deep-merge settings_json, account deletion, LLM test |
| `app/routers/settings.py` | Create | All `/settings/*` endpoints |
| `app/main.py` | Modify | Include settings router |
| `tests/test_settings.py` | Create | Settings API + service tests (TDD) |

---

## Task 1: Pydantic Schemas for All Setting Groups

**Files:**
- Create: `app/schemas/settings.py`
- Test: `tests/test_settings.py` (schema validation only)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_settings.py
import pytest
from pydantic import ValidationError
from app.schemas.settings import (
    AccountSettingsResponse,
    AccountUpdateRequest,
    PasswordChangeRequest,
    CharacterSettingsResponse,
    CharacterUpdateRequest,
    PersonaUpdateRequest,
    InteractionUpdateRequest,
    PrivacyUpdateRequest,
    LLMUpdateRequest,
    LLMTestRequest,
    LLMTestResponse,
    EconomyUpdateRequest,
    AllSettingsResponse,
)


def test_account_update_request_optional_fields():
    """All fields should be optional for PATCH semantics."""
    req = AccountUpdateRequest()
    assert req.display_name is None

    req2 = AccountUpdateRequest(display_name="New Name")
    assert req2.display_name == "New Name"


def test_password_change_requires_both_fields():
    """Password change must have old and new password."""
    with pytest.raises(ValidationError):
        PasswordChangeRequest(old_password="abc")  # missing new_password

    req = PasswordChangeRequest(old_password="old", new_password="newpassword123")
    assert req.new_password == "newpassword123"


def test_persona_update_request_all_layers():
    """Persona update accepts 3-layer markdown."""
    req = PersonaUpdateRequest(
        ability_md="# Abilities",
        persona_md="# Persona",
        soul_md="# Soul",
    )
    assert req.ability_md == "# Abilities"


def test_privacy_update_validates_enum():
    """persona_visibility must be one of the allowed values."""
    req = PrivacyUpdateRequest(persona_visibility="full")
    assert req.persona_visibility == "full"

    with pytest.raises(ValidationError):
        PrivacyUpdateRequest(persona_visibility="invalid_value")


def test_llm_update_validates_api_format():
    """api_format must be openai or anthropic."""
    req = LLMUpdateRequest(api_format="openai")
    assert req.api_format == "openai"

    with pytest.raises(ValidationError):
        LLMUpdateRequest(api_format="gemini")


def test_economy_update_threshold():
    """Low balance alert threshold must be non-negative."""
    req = EconomyUpdateRequest(low_balance_alert=10)
    assert req.low_balance_alert == 10

    with pytest.raises(ValidationError):
        EconomyUpdateRequest(low_balance_alert=-5)


def test_all_settings_response_structure():
    """AllSettingsResponse should compose all sub-groups."""
    resp = AllSettingsResponse(
        account=AccountSettingsResponse(
            display_name="Alice",
            email="a@b.com",
            has_password=True,
            github_bound=False,
            linuxdo_bound=False,
            linuxdo_trust_level=None,
        ),
        character=None,
        interaction={"reply_mode": "manual", "offline_auto_reply": False, "notifications": {}},
        privacy={"map_visible": True, "persona_visibility": "full", "allow_conversation_stats": True},
        llm={"custom_llm_enabled": False},
        economy={"soul_coin_balance": 100, "low_balance_alert": 10},
    )
    assert resp.account.display_name == "Alice"
    assert resp.character is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jimmy/Downloads/Skills-World/.worktrees/mvp-implementation/backend && python -m pytest tests/test_settings.py -v -k "test_account_update or test_password_change or test_persona or test_privacy or test_llm_update or test_economy or test_all_settings"`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.settings'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/schemas/settings.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


# ─── Account (9.1) ───────────────────────────────────────────────

class AccountUpdateRequest(BaseModel):
    display_name: str | None = None


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


class AccountSettingsResponse(BaseModel):
    display_name: str
    email: str
    has_password: bool
    github_bound: bool
    linuxdo_bound: bool
    linuxdo_trust_level: int | None


# ─── Character (9.2) ─────────────────────────────────────────────

class CharacterUpdateRequest(BaseModel):
    name: str | None = None
    sprite_key: str | None = None


class PersonaUpdateRequest(BaseModel):
    ability_md: str
    persona_md: str
    soul_md: str


class CharacterSettingsResponse(BaseModel):
    resident_id: str
    name: str
    sprite_key: str
    portrait_url: str | None
    ability_md: str
    persona_md: str
    soul_md: str

    model_config = {"from_attributes": True}


# ─── Interaction (9.3) ───────────────────────────────────────────

class InteractionUpdateRequest(BaseModel):
    reply_mode: Literal["manual", "auto"] | None = None
    offline_auto_reply: bool | None = None
    notification_chat: bool | None = None
    notification_system: bool | None = None


# ─── Privacy (9.4) ───────────────────────────────────────────────

class PrivacyUpdateRequest(BaseModel):
    map_visible: bool | None = None
    persona_visibility: Literal["full", "identity_card_only", "hidden"] | None = None
    allow_conversation_stats: bool | None = None


# ─── LLM (9.5) ───────────────────────────────────────────────────

class LLMUpdateRequest(BaseModel):
    custom_llm_enabled: bool | None = None
    api_format: Literal["openai", "anthropic"] | None = None
    api_base_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    thinking_enabled: bool | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class LLMTestRequest(BaseModel):
    api_format: Literal["openai", "anthropic"]
    api_base_url: str
    api_key: str
    model_name: str


class LLMTestResponse(BaseModel):
    success: bool
    latency_ms: int | None = None
    model_response: str | None = None
    error: str | None = None


# ─── Economy (9.6) ───────────────────────────────────────────────

class EconomyUpdateRequest(BaseModel):
    low_balance_alert: int | None = Field(default=None, ge=0)


# ─── Composite ───────────────────────────────────────────────────

class AllSettingsResponse(BaseModel):
    account: AccountSettingsResponse
    character: CharacterSettingsResponse | None
    interaction: dict
    privacy: dict
    llm: dict
    economy: dict
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py -v -k "test_account_update or test_password_change or test_persona or test_privacy or test_llm_update or test_economy or test_all_settings"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/settings.py tests/test_settings.py
git commit -m "feat: add Pydantic schemas for all 6 user settings groups"
```

---

## Task 2: Settings Service — Core Logic + settings_json Deep Merge

**Files:**
- Create: `app/services/settings_service.py`
- Test: `tests/test_settings.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_settings.py
from app.services.settings_service import merge_settings_json, build_settings_defaults


def test_merge_settings_json_adds_new_keys():
    """Deep merge should add new keys without clobbering existing."""
    existing = {"interaction": {"reply_mode": "manual"}, "privacy": {"map_visible": True}}
    patch = {"interaction": {"offline_auto_reply": True}}
    result = merge_settings_json(existing, patch)
    assert result["interaction"]["reply_mode"] == "manual"
    assert result["interaction"]["offline_auto_reply"] is True
    assert result["privacy"]["map_visible"] is True


def test_merge_settings_json_overwrites_existing():
    """Deep merge should overwrite scalar values."""
    existing = {"privacy": {"map_visible": True, "persona_visibility": "full"}}
    patch = {"privacy": {"map_visible": False}}
    result = merge_settings_json(existing, patch)
    assert result["privacy"]["map_visible"] is False
    assert result["privacy"]["persona_visibility"] == "full"


def test_merge_settings_json_empty_existing():
    """Merge into empty dict should work."""
    result = merge_settings_json({}, {"economy": {"low_balance_alert": 10}})
    assert result["economy"]["low_balance_alert"] == 10


def test_build_settings_defaults():
    """Should return complete defaults for all groups."""
    defaults = build_settings_defaults()
    assert "interaction" in defaults
    assert "privacy" in defaults
    assert "economy" in defaults
    assert "llm" in defaults
    assert defaults["interaction"]["offline_auto_reply"] is False
    assert defaults["privacy"]["map_visible"] is True
    assert defaults["privacy"]["persona_visibility"] == "full"
    assert defaults["privacy"]["allow_conversation_stats"] is True
    assert defaults["economy"]["low_balance_alert"] == 10
    assert defaults["llm"]["thinking_enabled"] is False
    assert defaults["llm"]["temperature"] == 0.7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings.py -v -k "test_merge or test_build_settings"`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.settings_service'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/settings_service.py
"""
Settings business logic.

Handles deep-merging settings_json, password changes, account deletion,
and LLM connection testing.
"""
from __future__ import annotations

import copy
import time
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.resident import Resident
from app.services.auth_service import pwd_context


# ─── settings_json Helpers ────────────────────────────────────────

def build_settings_defaults() -> dict:
    """Return the canonical default structure for User.settings_json."""
    return {
        "interaction": {
            "offline_auto_reply": False,
            "notification_chat": True,
            "notification_system": True,
        },
        "privacy": {
            "map_visible": True,
            "persona_visibility": "full",
            "allow_conversation_stats": True,
        },
        "economy": {
            "low_balance_alert": 10,
        },
        "llm": {
            "thinking_enabled": False,
            "temperature": 0.7,
        },
    }


def merge_settings_json(existing: dict, patch: dict) -> dict:
    """
    Deep-merge *patch* into a copy of *existing*.
    Only merges one level deep (group → key): group values that are dicts
    are merged; scalar values are overwritten.
    """
    result = copy.deepcopy(existing)
    for group, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(group), dict):
            result[group].update(value)
        else:
            result[group] = value
    return result


def get_effective_settings(user: User) -> dict:
    """Return settings_json with defaults filled in for missing keys."""
    defaults = build_settings_defaults()
    return merge_settings_json(defaults, user.settings_json or {})


# ─── Account Operations ──────────────────────────────────────────

async def change_display_name(db: AsyncSession, user: User, new_name: str) -> User:
    """Update user display name."""
    if not new_name or len(new_name.strip()) == 0:
        raise HTTPException(status_code=422, detail="Display name cannot be empty")
    if len(new_name) > 100:
        raise HTTPException(status_code=422, detail="Display name too long (max 100)")
    user.name = new_name.strip()
    await db.commit()
    await db.refresh(user)
    return user


async def change_password(
    db: AsyncSession, user: User, old_password: str, new_password: str
) -> None:
    """Change password for email-registered users only."""
    if not user.hashed_password:
        raise HTTPException(
            status_code=400,
            detail="Cannot change password for OAuth-only accounts",
        )
    if not pwd_context.verify(old_password, user.hashed_password):
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    user.hashed_password = pwd_context.hash(new_password)
    await db.commit()


async def delete_account(db: AsyncSession, user: User, confirm_email: str) -> None:
    """
    Permanently delete user account.
    Requires the user to confirm by typing their email.
    Cascading: sets creator_id=NULL on owned residents (they become orphaned NPCs).
    """
    if confirm_email != user.email:
        raise HTTPException(
            status_code=400,
            detail="Email confirmation does not match",
        )
    # Orphan any residents created by this user
    result = await db.execute(
        select(Resident).where(Resident.creator_id == user.id)
    )
    for resident in result.scalars().all():
        resident.creator_id = None  # type: ignore[assignment]

    await db.delete(user)
    await db.commit()


# ─── Character Operations ────────────────────────────────────────

async def get_player_resident(db: AsyncSession, user: User) -> Resident | None:
    """Fetch the user's player resident, if bound."""
    if not user.player_resident_id:
        return None
    result = await db.execute(
        select(Resident).where(Resident.id == user.player_resident_id)
    )
    return result.scalar_one_or_none()


async def update_character(
    db: AsyncSession,
    resident: Resident,
    name: str | None = None,
    sprite_key: str | None = None,
) -> Resident:
    """Update character name and/or sprite."""
    if name is not None:
        if not name.strip():
            raise HTTPException(status_code=422, detail="Character name cannot be empty")
        if len(name) > 100:
            raise HTTPException(status_code=422, detail="Character name too long (max 100)")
        resident.name = name.strip()
    if sprite_key is not None:
        resident.sprite_key = sprite_key
    await db.commit()
    await db.refresh(resident)
    return resident


async def update_persona(
    db: AsyncSession,
    resident: Resident,
    ability_md: str,
    persona_md: str,
    soul_md: str,
) -> Resident:
    """Replace all 3 persona layers."""
    resident.ability_md = ability_md
    resident.persona_md = persona_md
    resident.soul_md = soul_md
    await db.commit()
    await db.refresh(resident)
    return resident


# ─── Interaction / Privacy / Economy — settings_json patches ─────

async def patch_settings_group(
    db: AsyncSession,
    user: User,
    group: str,
    updates: dict[str, Any],
) -> dict:
    """
    Patch a single group inside settings_json.
    Also handles reply_mode which lives on Resident, not settings_json.
    """
    current = user.settings_json or {}
    patched = merge_settings_json(current, {group: updates})
    user.settings_json = patched
    await db.commit()
    await db.refresh(user)
    return get_effective_settings(user)


async def update_reply_mode(
    db: AsyncSession, resident: Resident, mode: str
) -> None:
    """Update reply_mode on the player's Resident record."""
    resident.reply_mode = mode
    await db.commit()


# ─── LLM Operations ──────────────────────────────────────────────

async def update_llm_settings(
    db: AsyncSession,
    user: User,
    *,
    custom_llm_enabled: bool | None = None,
    api_format: str | None = None,
    api_base_url: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
    thinking_enabled: bool | None = None,
    temperature: float | None = None,
) -> User:
    """Update custom LLM fields on User + advanced settings in settings_json."""
    if custom_llm_enabled is not None:
        user.custom_llm_enabled = custom_llm_enabled
    if api_format is not None:
        user.custom_llm_api_format = api_format
    if api_base_url is not None:
        user.custom_llm_base_url = api_base_url
    if api_key is not None:
        user.custom_llm_api_key = api_key
    if model_name is not None:
        user.custom_llm_model = model_name

    # Advanced settings go into settings_json.llm
    llm_patch: dict[str, Any] = {}
    if thinking_enabled is not None:
        llm_patch["thinking_enabled"] = thinking_enabled
    if temperature is not None:
        llm_patch["temperature"] = temperature
    if llm_patch:
        current = user.settings_json or {}
        user.settings_json = merge_settings_json(current, {"llm": llm_patch})

    await db.commit()
    await db.refresh(user)
    return user


async def test_llm_connection(
    api_format: str,
    api_base_url: str,
    api_key: str,
    model_name: str,
) -> dict:
    """
    Test a custom LLM endpoint by sending a minimal chat completion request.
    Returns {success, latency_ms, model_response?, error?}.
    """
    headers = {
        "Content-Type": "application/json",
    }

    if api_format == "openai":
        url = f"{api_base_url.rstrip('/')}/v1/chat/completions"
        headers["Authorization"] = f"Bearer {api_key}"
        body = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Say 'connection ok' in 3 words or fewer."}],
            "max_tokens": 20,
        }
    else:  # anthropic
        url = f"{api_base_url.rstrip('/')}/v1/messages"
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        body = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Say 'connection ok' in 3 words or fewer."}],
            "max_tokens": 20,
        }

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=body, headers=headers)
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code >= 400:
            return {
                "success": False,
                "latency_ms": latency_ms,
                "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }

        data = resp.json()
        # Extract text from response
        if api_format == "openai":
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        else:
            content_blocks = data.get("content", [])
            text = content_blocks[0].get("text", "") if content_blocks else ""

        return {
            "success": True,
            "latency_ms": latency_ms,
            "model_response": text.strip(),
        }
    except httpx.TimeoutException:
        return {"success": False, "error": "Connection timed out (15s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py -v -k "test_merge or test_build_settings"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/settings_service.py
git commit -m "feat: add settings_service with deep-merge, defaults, account/character/LLM operations"
```

---

## Task 3: Settings Router — GET /settings (Read All) + Auth Helper

**Files:**
- Create: `app/routers/settings.py`
- Modify: `app/main.py`
- Test: `tests/test_settings.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_settings.py
import pytest
from app.models.user import User
from app.models.resident import Resident
from app.services.auth_service import create_token, pwd_context


@pytest.fixture
async def auth_user(db_session) -> tuple[User, str]:
    """Create a user with password + player resident and return (user, token)."""
    user = User(
        name="TestUser",
        email="test@example.com",
        hashed_password=pwd_context.hash("oldpassword123"),
        settings_json={},
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resident = Resident(
        slug="player-test",
        name="PlayerChar",
        creator_id=user.id,
        resident_type="player",
        sprite_key="伊莎贝拉",
        ability_md="# Ability",
        persona_md="# Persona",
        soul_md="# Soul",
    )
    db_session.add(resident)
    await db_session.commit()
    await db_session.refresh(resident)

    user.player_resident_id = resident.id
    await db_session.commit()
    await db_session.refresh(user)

    token = create_token(user.id)
    return user, token


@pytest.mark.anyio
async def test_get_all_settings(client, auth_user):
    """GET /settings should return composite settings for authenticated user."""
    _, token = auth_user
    resp = await client.get("/settings", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "account" in data
    assert data["account"]["display_name"] == "TestUser"
    assert data["account"]["has_password"] is True
    assert data["account"]["github_bound"] is False
    assert "character" in data
    assert data["character"]["name"] == "PlayerChar"
    assert "interaction" in data
    assert "privacy" in data
    assert "llm" in data
    assert "economy" in data
    assert data["economy"]["soul_coin_balance"] == 100


@pytest.mark.anyio
async def test_get_settings_unauthenticated(client):
    """GET /settings without token should return 401."""
    resp = await client.get("/settings")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings.py::test_get_all_settings -v`
Expected: FAIL (404 — route not found)

- [ ] **Step 3: Write minimal implementation**

```python
# app/routers/settings.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.resident import Resident
from app.services.auth_service import get_current_user
from app.services.settings_service import (
    get_effective_settings,
    get_player_resident,
)
from app.schemas.settings import (
    AccountSettingsResponse,
    CharacterSettingsResponse,
    AllSettingsResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"])


async def _require_user(request: Request, db: AsyncSession = Depends(get_db)) -> tuple[User, AsyncSession]:
    """Extract and verify JWT from Authorization header. Returns (user, db)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user, db


@router.get("", response_model=AllSettingsResponse)
async def get_all_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """GET /settings — return all user settings in one response."""
    user, db = await _require_user(request, db)
    effective = get_effective_settings(user)

    # Account group
    account = AccountSettingsResponse(
        display_name=user.name,
        email=user.email,
        has_password=user.hashed_password is not None,
        github_bound=user.github_id is not None,
        linuxdo_bound=getattr(user, "linuxdo_id", None) is not None,
        linuxdo_trust_level=getattr(user, "linuxdo_trust_level", None),
    )

    # Character group
    resident = await get_player_resident(db, user)
    character = None
    if resident:
        character = CharacterSettingsResponse(
            resident_id=resident.id,
            name=resident.name,
            sprite_key=resident.sprite_key,
            portrait_url=getattr(resident, "portrait_url", None),
            ability_md=resident.ability_md,
            persona_md=resident.persona_md,
            soul_md=resident.soul_md,
        )

    # Interaction — merge reply_mode from Resident
    interaction = effective.get("interaction", {})
    if resident:
        interaction["reply_mode"] = getattr(resident, "reply_mode", "manual")
    else:
        interaction["reply_mode"] = "manual"

    # LLM group — combine column fields + settings_json.llm
    llm_settings = effective.get("llm", {})
    llm_settings.update({
        "custom_llm_enabled": getattr(user, "custom_llm_enabled", False),
        "api_format": getattr(user, "custom_llm_api_format", "anthropic"),
        "api_base_url": getattr(user, "custom_llm_base_url", None),
        "has_api_key": getattr(user, "custom_llm_api_key", None) is not None,
        "model_name": getattr(user, "custom_llm_model", None),
    })

    # Economy group
    economy = effective.get("economy", {})
    economy["soul_coin_balance"] = user.soul_coin_balance

    return AllSettingsResponse(
        account=account,
        character=character,
        interaction=interaction,
        privacy=effective.get("privacy", {}),
        llm=llm_settings,
        economy=economy,
    )
```

Register the router in main.py:

```python
# app/main.py — add import and include_router
# After: from app.routers import auth, users, residents, forge, profile, search, bulletin
# Change to:
from app.routers import auth, users, residents, forge, profile, search, bulletin, settings

# After: app.include_router(bulletin.router)
# Add:
app.include_router(settings.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py::test_get_all_settings tests/test_settings.py::test_get_settings_unauthenticated -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/settings.py app/main.py tests/test_settings.py
git commit -m "feat: add GET /settings endpoint with composite response"
```

---

## Task 4: Account Settings — PATCH + Password Change + Delete Account

**Files:**
- Modify: `app/routers/settings.py`
- Test: `tests/test_settings.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_settings.py

@pytest.mark.anyio
async def test_patch_account_display_name(client, auth_user):
    """PATCH /settings/account should update display name."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/account",
        json={"display_name": "NewName"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "NewName"


@pytest.mark.anyio
async def test_patch_account_change_password(client, auth_user):
    """PATCH /settings/account/password should change password."""
    _, token = auth_user
    resp = await client.post(
        "/settings/account/password",
        json={"old_password": "oldpassword123", "new_password": "newpassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Password changed"


@pytest.mark.anyio
async def test_change_password_wrong_old(client, auth_user):
    """Wrong old password should return 403."""
    _, token = auth_user
    resp = await client.post(
        "/settings/account/password",
        json={"old_password": "wrongpassword", "new_password": "newpassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_delete_account_success(client, auth_user):
    """DELETE /settings/account with correct email should delete user."""
    user, token = auth_user
    resp = await client.request(
        "DELETE",
        "/settings/account",
        json={"confirm_email": user.email},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Account deleted"

    # Verify user is gone
    resp2 = await client.get("/settings", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 401


@pytest.mark.anyio
async def test_delete_account_wrong_email(client, auth_user):
    """DELETE /settings/account with wrong email should return 400."""
    _, token = auth_user
    resp = await client.request(
        "DELETE",
        "/settings/account",
        json={"confirm_email": "wrong@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings.py -v -k "test_patch_account or test_change_password or test_delete_account"`
Expected: FAIL (405 Method Not Allowed — endpoints don't exist)

- [ ] **Step 3: Write minimal implementation**

```python
# append to app/routers/settings.py
from app.schemas.settings import (
    AccountUpdateRequest,
    PasswordChangeRequest,
)
from app.services.settings_service import (
    change_display_name,
    change_password,
    delete_account,
)
from pydantic import BaseModel


class DeleteAccountRequest(BaseModel):
    confirm_email: str


@router.patch("/account")
async def patch_account(
    req: AccountUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/account — update display name."""
    user, db = await _require_user(request, db)
    if req.display_name is not None:
        user = await change_display_name(db, user, req.display_name)
    return {"display_name": user.name, "email": user.email}


@router.post("/account/password")
async def change_password_endpoint(
    req: PasswordChangeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """POST /settings/account/password — change password (email users only)."""
    user, db = await _require_user(request, db)
    await change_password(db, user, req.old_password, req.new_password)
    return {"message": "Password changed"}


@router.delete("/account")
async def delete_account_endpoint(
    req: DeleteAccountRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """DELETE /settings/account — permanently delete account."""
    user, db = await _require_user(request, db)
    await delete_account(db, user, req.confirm_email)
    return {"message": "Account deleted"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py -v -k "test_patch_account or test_change_password or test_delete_account"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/settings.py tests/test_settings.py
git commit -m "feat: add account settings endpoints (display name, password, delete)"
```

---

## Task 5: Character Settings — Name/Sprite, Persona, Avatar, Reforge, Import

**Files:**
- Modify: `app/routers/settings.py`
- Test: `tests/test_settings.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_settings.py

@pytest.mark.anyio
async def test_patch_character_name(client, auth_user):
    """PATCH /settings/character should update character name."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/character",
        json={"name": "NewCharName"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewCharName"


@pytest.mark.anyio
async def test_patch_character_sprite(client, auth_user):
    """PATCH /settings/character should update sprite_key."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/character",
        json={"sprite_key": "艾丽西亚"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["sprite_key"] == "艾丽西亚"


@pytest.mark.anyio
async def test_put_persona(client, auth_user):
    """PUT /settings/character/persona should replace all 3 layers."""
    _, token = auth_user
    resp = await client.put(
        "/settings/character/persona",
        json={
            "ability_md": "# New Ability",
            "persona_md": "# New Persona",
            "soul_md": "# New Soul",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ability_md"] == "# New Ability"
    assert data["persona_md"] == "# New Persona"
    assert data["soul_md"] == "# New Soul"


@pytest.mark.anyio
async def test_patch_character_no_resident(client, db_session):
    """PATCH /settings/character should 404 when user has no player resident."""
    user = User(name="NoResident", email="nores@test.com", settings_json={})
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_token(user.id)

    resp = await client.patch(
        "/settings/character",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "player resident" in resp.json()["detail"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings.py -v -k "test_patch_character or test_put_persona"`
Expected: FAIL (404 — route not found)

- [ ] **Step 3: Write minimal implementation**

```python
# append to app/routers/settings.py
from app.schemas.settings import (
    CharacterUpdateRequest,
    CharacterSettingsResponse,
    PersonaUpdateRequest,
)
from app.services.settings_service import (
    update_character,
    update_persona,
    get_player_resident,
)


async def _require_resident(request: Request, db: AsyncSession) -> tuple[User, Resident, AsyncSession]:
    """Get authenticated user and their player resident, or raise 404."""
    user, db = await _require_user(request, db)
    resident = await get_player_resident(db, user)
    if not resident:
        raise HTTPException(status_code=404, detail="No player resident bound to this account")
    return user, resident, db


@router.patch("/character", response_model=CharacterSettingsResponse)
async def patch_character(
    req: CharacterUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/character — update character name and/or sprite."""
    user, resident, db = await _require_resident(request, db)
    resident = await update_character(db, resident, name=req.name, sprite_key=req.sprite_key)
    return CharacterSettingsResponse(
        resident_id=resident.id,
        name=resident.name,
        sprite_key=resident.sprite_key,
        portrait_url=getattr(resident, "portrait_url", None),
        ability_md=resident.ability_md,
        persona_md=resident.persona_md,
        soul_md=resident.soul_md,
    )


@router.put("/character/persona", response_model=CharacterSettingsResponse)
async def put_persona(
    req: PersonaUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PUT /settings/character/persona — replace all 3 persona layers."""
    user, resident, db = await _require_resident(request, db)
    resident = await update_persona(db, resident, req.ability_md, req.persona_md, req.soul_md)
    return CharacterSettingsResponse(
        resident_id=resident.id,
        name=resident.name,
        sprite_key=resident.sprite_key,
        portrait_url=getattr(resident, "portrait_url", None),
        ability_md=resident.ability_md,
        persona_md=resident.persona_md,
        soul_md=resident.soul_md,
    )


@router.post("/character/reforge")
async def reforge_character(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    POST /settings/character/reforge — re-run forge pipeline on player resident.
    Delegates to forge_service (Plan 2). Returns 501 if forge not available.
    """
    user, resident, db = await _require_resident(request, db)
    try:
        from app.services.forge_service import start_forge_session
        session = await start_forge_session(db, resident.id, user.id)
        return {"message": "Reforge started", "forge_session_id": session.id}
    except (ImportError, AttributeError):
        raise HTTPException(status_code=501, detail="Forge pipeline not available yet")


@router.post("/character/import")
async def import_skill_file(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    POST /settings/character/import — import a Skill JSON file.
    Expects JSON body with skill data. Stub endpoint; full implementation in Plan 2.
    """
    user, resident, db = await _require_resident(request, db)
    body = await request.json()
    if not body:
        raise HTTPException(status_code=422, detail="Empty skill data")
    # Apply persona fields from imported skill
    if "ability_md" in body:
        resident.ability_md = body["ability_md"]
    if "persona_md" in body:
        resident.persona_md = body["persona_md"]
    if "soul_md" in body:
        resident.soul_md = body["soul_md"]
    if "name" in body:
        resident.name = body["name"]
    await db.commit()
    await db.refresh(resident)
    return {"message": "Skill imported", "resident_id": resident.id, "name": resident.name}


@router.post("/character/avatar")
async def regenerate_or_upload_avatar(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    POST /settings/character/avatar — regenerate AI portrait or upload custom.
    Delegates to portrait_service (Plan 4). Returns 501 if not available.
    """
    user, resident, db = await _require_resident(request, db)
    try:
        from app.services.portrait_service import generate_portrait
        portrait_url = await generate_portrait(resident)
        resident.portrait_url = portrait_url
        await db.commit()
        await db.refresh(resident)
        return {"portrait_url": portrait_url}
    except (ImportError, AttributeError):
        raise HTTPException(status_code=501, detail="Portrait service not available yet")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py -v -k "test_patch_character or test_put_persona"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/settings.py tests/test_settings.py
git commit -m "feat: add character settings endpoints (name, sprite, persona, reforge, import, avatar)"
```

---

## Task 6: Interaction + Privacy + Economy Settings — PATCH Endpoints

**Files:**
- Modify: `app/routers/settings.py`
- Test: `tests/test_settings.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_settings.py

@pytest.mark.anyio
async def test_patch_interaction_settings(client, auth_user):
    """PATCH /settings/interaction should update interaction prefs."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/interaction",
        json={"offline_auto_reply": True, "notification_chat": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["interaction"]["offline_auto_reply"] is True
    assert data["interaction"]["notification_chat"] is False
    # Unchanged defaults should still be present
    assert data["interaction"]["notification_system"] is True


@pytest.mark.anyio
async def test_patch_interaction_reply_mode(client, auth_user):
    """PATCH /settings/interaction with reply_mode should update Resident.reply_mode."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/interaction",
        json={"reply_mode": "auto"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["interaction"]["reply_mode"] == "auto"


@pytest.mark.anyio
async def test_patch_privacy_settings(client, auth_user):
    """PATCH /settings/privacy should update privacy prefs."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/privacy",
        json={"map_visible": False, "persona_visibility": "hidden"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["privacy"]["map_visible"] is False
    assert data["privacy"]["persona_visibility"] == "hidden"
    assert data["privacy"]["allow_conversation_stats"] is True  # unchanged default


@pytest.mark.anyio
async def test_patch_economy_settings(client, auth_user):
    """PATCH /settings/economy should update economy prefs."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/economy",
        json={"low_balance_alert": 50},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["economy"]["low_balance_alert"] == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings.py -v -k "test_patch_interaction or test_patch_privacy or test_patch_economy"`
Expected: FAIL (404 — routes not found)

- [ ] **Step 3: Write minimal implementation**

```python
# append to app/routers/settings.py
from app.schemas.settings import (
    InteractionUpdateRequest,
    PrivacyUpdateRequest,
    EconomyUpdateRequest,
)
from app.services.settings_service import (
    patch_settings_group,
    update_reply_mode,
    get_effective_settings,
)


@router.patch("/interaction")
async def patch_interaction(
    req: InteractionUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/interaction — update interaction preferences."""
    user, db = await _require_user(request, db)

    # reply_mode lives on Resident, not settings_json
    if req.reply_mode is not None:
        resident = await get_player_resident(db, user)
        if resident:
            await update_reply_mode(db, resident, req.reply_mode)

    # Other interaction fields go into settings_json
    updates = req.model_dump(exclude_none=True, exclude={"reply_mode"})
    if updates:
        await patch_settings_group(db, user, "interaction", updates)

    # Return full effective settings so frontend can refresh
    await db.refresh(user)
    effective = get_effective_settings(user)
    interaction = effective.get("interaction", {})
    # Merge in reply_mode from Resident
    resident = await get_player_resident(db, user)
    interaction["reply_mode"] = getattr(resident, "reply_mode", "manual") if resident else "manual"

    return {"interaction": interaction}


@router.patch("/privacy")
async def patch_privacy(
    req: PrivacyUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/privacy — update privacy preferences."""
    user, db = await _require_user(request, db)
    updates = req.model_dump(exclude_none=True)
    if updates:
        await patch_settings_group(db, user, "privacy", updates)
    await db.refresh(user)
    effective = get_effective_settings(user)
    return {"privacy": effective.get("privacy", {})}


@router.patch("/economy")
async def patch_economy(
    req: EconomyUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/economy — update economy preferences."""
    user, db = await _require_user(request, db)
    updates = req.model_dump(exclude_none=True)
    if updates:
        await patch_settings_group(db, user, "economy", updates)
    await db.refresh(user)
    effective = get_effective_settings(user)
    economy = effective.get("economy", {})
    economy["soul_coin_balance"] = user.soul_coin_balance
    return {"economy": economy}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py -v -k "test_patch_interaction or test_patch_privacy or test_patch_economy"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/settings.py tests/test_settings.py
git commit -m "feat: add interaction, privacy, economy PATCH settings endpoints"
```

---

## Task 7: LLM Settings — PATCH + Connection Test

**Files:**
- Modify: `app/routers/settings.py`
- Test: `tests/test_settings.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_settings.py
from unittest.mock import AsyncMock, patch
import httpx


@pytest.mark.anyio
async def test_patch_llm_settings(client, auth_user):
    """PATCH /settings/llm should update custom LLM config."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/llm",
        json={
            "custom_llm_enabled": True,
            "api_format": "openai",
            "api_base_url": "https://api.example.com",
            "model_name": "gpt-4o",
            "temperature": 0.9,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["custom_llm_enabled"] is True
    assert data["api_format"] == "openai"
    assert data["api_base_url"] == "https://api.example.com"
    assert data["model_name"] == "gpt-4o"
    assert data["temperature"] == 0.9


@pytest.mark.anyio
async def test_patch_llm_invalid_format(client, auth_user):
    """PATCH /settings/llm with invalid api_format should 422."""
    _, token = auth_user
    resp = await client.patch(
        "/settings/llm",
        json={"api_format": "invalid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_llm_test_connection_success(client, auth_user):
    """POST /settings/llm/test should test the LLM endpoint."""
    _, token = auth_user

    mock_response = httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "connection ok"}}],
        },
        request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
    )

    with patch("app.services.settings_service.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        resp = await client.post(
            "/settings/llm/test",
            json={
                "api_format": "openai",
                "api_base_url": "https://api.example.com",
                "api_key": "sk-test",
                "model_name": "gpt-4o",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["model_response"] == "connection ok"


@pytest.mark.anyio
async def test_llm_test_connection_timeout(client, auth_user):
    """POST /settings/llm/test should handle timeout gracefully."""
    _, token = auth_user

    with patch("app.services.settings_service.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = httpx.TimeoutException("timed out")
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        resp = await client.post(
            "/settings/llm/test",
            json={
                "api_format": "openai",
                "api_base_url": "https://api.example.com",
                "api_key": "sk-test",
                "model_name": "gpt-4o",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "timed out" in data["error"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings.py -v -k "test_patch_llm or test_llm_test"`
Expected: FAIL (404 — routes not found)

- [ ] **Step 3: Write minimal implementation**

```python
# append to app/routers/settings.py
from app.schemas.settings import (
    LLMUpdateRequest,
    LLMTestRequest,
    LLMTestResponse,
)
from app.services.settings_service import (
    update_llm_settings,
    test_llm_connection,
)


@router.patch("/llm")
async def patch_llm(
    req: LLMUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """PATCH /settings/llm — update custom LLM configuration."""
    user, db = await _require_user(request, db)
    user = await update_llm_settings(
        db,
        user,
        custom_llm_enabled=req.custom_llm_enabled,
        api_format=req.api_format,
        api_base_url=req.api_base_url,
        api_key=req.api_key,
        model_name=req.model_name,
        thinking_enabled=req.thinking_enabled,
        temperature=req.temperature,
    )
    effective = get_effective_settings(user)
    llm = effective.get("llm", {})
    llm.update({
        "custom_llm_enabled": user.custom_llm_enabled,
        "api_format": user.custom_llm_api_format,
        "api_base_url": user.custom_llm_base_url,
        "has_api_key": user.custom_llm_api_key is not None,
        "model_name": user.custom_llm_model,
    })
    return llm


@router.post("/llm/test", response_model=LLMTestResponse)
async def test_llm_endpoint(
    req: LLMTestRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """POST /settings/llm/test — test custom LLM connection."""
    await _require_user(request, db)  # auth only
    result = await test_llm_connection(
        api_format=req.api_format,
        api_base_url=req.api_base_url,
        api_key=req.api_key,
        model_name=req.model_name,
    )
    return LLMTestResponse(**result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py -v -k "test_patch_llm or test_llm_test"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/settings.py tests/test_settings.py
git commit -m "feat: add LLM settings PATCH and connection test endpoints"
```

---

## Task 8: OAuth Bind/Unbind Stubs + Integration Test Suite

**Files:**
- Modify: `app/routers/settings.py`
- Test: `tests/test_settings.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_settings.py

@pytest.mark.anyio
async def test_bind_github_returns_redirect_url(client, auth_user):
    """POST /settings/account/bind-github should return an OAuth authorize URL."""
    _, token = auth_user
    resp = await client.post(
        "/settings/account/bind-github",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Should return a redirect URL (or 501 if OAuth not configured)
    assert resp.status_code in (200, 501)


@pytest.mark.anyio
async def test_bind_linuxdo_returns_redirect_url(client, auth_user):
    """POST /settings/account/bind-linuxdo should return an OAuth authorize URL."""
    _, token = auth_user
    resp = await client.post(
        "/settings/account/bind-linuxdo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 501)


@pytest.mark.anyio
async def test_unbind_github_no_binding(client, auth_user):
    """DELETE /settings/account/unbind/github should 400 when not bound."""
    _, token = auth_user
    resp = await client.delete(
        "/settings/account/unbind/github",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "not bound" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_unbind_invalid_provider(client, auth_user):
    """DELETE /settings/account/unbind/invalid should 400."""
    _, token = auth_user
    resp = await client.delete(
        "/settings/account/unbind/invalid",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


# ─── Full Round-Trip Integration ─────────────────────────────────

@pytest.mark.anyio
async def test_settings_round_trip(client, auth_user):
    """Full round-trip: read settings, modify each group, verify changes persist."""
    _, token = auth_user
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Read initial
    resp = await client.get("/settings", headers=headers)
    assert resp.status_code == 200
    initial = resp.json()
    assert initial["account"]["display_name"] == "TestUser"

    # 2. Modify account
    await client.patch("/settings/account", json={"display_name": "RoundTrip"}, headers=headers)

    # 3. Modify privacy
    await client.patch("/settings/privacy", json={"map_visible": False}, headers=headers)

    # 4. Modify economy
    await client.patch("/settings/economy", json={"low_balance_alert": 99}, headers=headers)

    # 5. Read again — all changes should be reflected
    resp = await client.get("/settings", headers=headers)
    assert resp.status_code == 200
    final = resp.json()
    assert final["account"]["display_name"] == "RoundTrip"
    assert final["privacy"]["map_visible"] is False
    assert final["economy"]["low_balance_alert"] == 99
    # Unchanged values should keep defaults
    assert final["privacy"]["allow_conversation_stats"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings.py -v -k "test_bind or test_unbind or test_settings_round_trip"`
Expected: FAIL (404 — bind/unbind routes not found)

- [ ] **Step 3: Write minimal implementation**

```python
# append to app/routers/settings.py
from app.config import settings as app_settings


@router.post("/account/bind-github")
async def bind_github(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """POST /settings/account/bind-github — initiate GitHub OAuth binding flow."""
    user, db = await _require_user(request, db)
    if not app_settings.github_client_id:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")
    # Return authorize URL for frontend to redirect
    authorize_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={app_settings.github_client_id}"
        f"&scope=read:user user:email"
        f"&state=bind:{user.id}"
    )
    return {"authorize_url": authorize_url}


@router.post("/account/bind-linuxdo")
async def bind_linuxdo(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """POST /settings/account/bind-linuxdo — initiate LinuxDo OAuth binding flow."""
    user, db = await _require_user(request, db)
    try:
        from app.services.linuxdo_auth import LinuxDoOAuth
        from app.config import settings as cfg
        oauth = LinuxDoOAuth(
            client_id=getattr(cfg, "linuxdo_client_id", ""),
            client_secret=getattr(cfg, "linuxdo_client_secret", ""),
            redirect_uri=getattr(cfg, "linuxdo_redirect_uri", ""),
        )
        if not oauth.client_id:
            raise HTTPException(status_code=501, detail="LinuxDo OAuth not configured")
        url, state = oauth.build_authorize_url()
        return {"authorize_url": url, "state": state}
    except ImportError:
        raise HTTPException(status_code=501, detail="LinuxDo OAuth not available yet")


@router.delete("/account/unbind/{provider}")
async def unbind_provider(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """DELETE /settings/account/unbind/{provider} — unbind a third-party account."""
    user, db = await _require_user(request, db)

    if provider == "github":
        if not user.github_id:
            raise HTTPException(status_code=400, detail="GitHub not bound")
        # Safety: don't unbind if it's the only login method
        if not user.hashed_password and not getattr(user, "linuxdo_id", None):
            raise HTTPException(
                status_code=400,
                detail="Cannot unbind GitHub — it is your only login method",
            )
        user.github_id = None
        await db.commit()
        return {"message": "GitHub unbound"}

    elif provider == "linuxdo":
        if not getattr(user, "linuxdo_id", None):
            raise HTTPException(status_code=400, detail="LinuxDo not bound")
        if not user.hashed_password and not user.github_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot unbind LinuxDo — it is your only login method",
            )
        user.linuxdo_id = None  # type: ignore[assignment]
        user.linuxdo_trust_level = None  # type: ignore[assignment]
        await db.commit()
        return {"message": "LinuxDo unbound"}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py -v -k "test_bind or test_unbind or test_settings_round_trip"`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/test_settings.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add app/routers/settings.py tests/test_settings.py
git commit -m "feat: add OAuth bind/unbind stubs and full integration test suite"
```

---

## Summary

| Task | Endpoints | Files |
|------|-----------|-------|
| 1 — Schemas | — | `app/schemas/settings.py` |
| 2 — Service core | — | `app/services/settings_service.py` |
| 3 — GET /settings | `GET /settings` | `app/routers/settings.py`, `app/main.py` |
| 4 — Account | `PATCH /settings/account`, `POST .../password`, `DELETE /settings/account` | `app/routers/settings.py` |
| 5 — Character | `PATCH /settings/character`, `PUT .../persona`, `POST .../reforge`, `POST .../import`, `POST .../avatar` | `app/routers/settings.py` |
| 6 — Interaction/Privacy/Economy | `PATCH /settings/interaction`, `PATCH /settings/privacy`, `PATCH /settings/economy` | `app/routers/settings.py` |
| 7 — LLM | `PATCH /settings/llm`, `POST /settings/llm/test` | `app/routers/settings.py` |
| 8 — OAuth + Integration | `POST .../bind-github`, `POST .../bind-linuxdo`, `DELETE .../unbind/{provider}` | `app/routers/settings.py` |

**Total: 15 endpoints across 3 new files + 1 modified file, with ~30 tests.**
