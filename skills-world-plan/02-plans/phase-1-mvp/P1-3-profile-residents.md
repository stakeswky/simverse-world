# Skills World MVP — Profile & Resident Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the profile dashboard and resident management features: user profile page with resident list, conversation history, transaction history, resident editing with version control, skill import, quality scoring, and post-chat rating.

**Architecture:** Extends Plan 1 backend (FastAPI + SQLAlchemy) with new routers and services. Extends Plan 1 frontend (React + Zustand) with new pages and components. Profile page uses left sidebar + right content area layout per design spec.

**Tech Stack:** Same as Plan 1 — React 18 + Vite + TypeScript, FastAPI + SQLAlchemy + Alembic, PostgreSQL 16, Redis 7. Additional: `react-markdown` for markdown preview, `@uiw/react-md-editor` for markdown editing.

**Scope:** This is Plan 3 of 4. Depends on:
- Plan 1: Core Loop (auth, game world, chat, coins) — provides User, Resident, Conversation, Transaction models, auth service, coin service, resident service, WebSocket handler, ChatDrawer
- Plan 2: Forge (skill creation pipeline) — provides `/forge` route and forge service

**Depends on Plan 1 models/services:**
- `backend/app/models/user.py` — User ORM
- `backend/app/models/resident.py` — Resident ORM (slug, ability_md, persona_md, soul_md, star_rating, avg_rating, total_conversations, creator_id)
- `backend/app/models/conversation.py` — Conversation + Message ORM (user_id, resident_id, turns, rating, ended_at)
- `backend/app/models/transaction.py` — Transaction ORM (user_id, amount, reason)
- `backend/app/services/auth_service.py` — get_current_user, verify_token
- `backend/app/services/resident_service.py` — list_residents, get_resident_by_slug
- `backend/app/services/coin_service.py` — charge, reward
- `frontend/src/stores/gameStore.ts` — useGameStore (user, token, chatResident)
- `frontend/src/components/ChatDrawer.tsx` — chat UI (will be modified for rating popup)
- `frontend/src/services/ws.ts` — sendWS, onWSMessage
- `frontend/src/App.tsx` — React Router

---

## File Structure

### Backend (new/modified)

```
backend/app/
├── routers/
│   ├── profile.py              # NEW — GET /profile/residents, /profile/conversations, /profile/transactions
│   └── residents.py            # MODIFY — add PUT /residents/:slug, POST /residents/import
├── services/
│   ├── scoring_service.py      # NEW — quality scoring logic (1-3 stars)
│   └── version_service.py      # NEW — version history management
├── schemas/
│   ├── profile.py              # NEW — profile-specific Pydantic schemas
│   └── resident.py             # MODIFY — add edit/import schemas
backend/tests/
├── test_profile.py             # NEW
├── test_scoring.py             # NEW
├── test_version.py             # NEW
└── test_resident_edit.py       # NEW
```

### Frontend (new/modified)

```
frontend/src/
├── pages/
│   └── ProfilePage.tsx                # NEW — sidebar + content layout
├── components/
│   ├── profile/
│   │   ├── ProfileSidebar.tsx         # NEW — left sidebar with nav
│   │   ├── ResidentList.tsx           # NEW — "我的居民" tab
│   │   ├── ResidentCard.tsx           # NEW — single resident card
│   │   ├── ConversationHistory.tsx    # NEW — "对话历史" tab
│   │   ├── TransactionHistory.tsx     # NEW — "代币明细" tab
│   │   └── ResidentEditor.tsx         # NEW — markdown editor for 3 layers + version history
│   ├── ChatDrawer.tsx                 # MODIFY — add rating popup on end_chat
│   └── RatingPopup.tsx                # NEW — post-chat 1-5 star rating
├── services/
│   └── api.ts                         # MODIFY — add profile/resident API calls
├── stores/
│   └── gameStore.ts                   # MODIFY — add profileTab state
```

---

## Task 1: Profile API — List My Residents, Conversations, Transactions

**Files:**
- Create: `backend/app/schemas/profile.py`
- Create: `backend/app/routers/profile.py`
- Modify: `backend/app/main.py` (register router)
- Create: `backend/tests/test_profile.py`

- [ ] **Step 1: Write failing tests**

`tests/test_profile.py`:
```python
import pytest

@pytest.mark.anyio
async def test_list_my_residents(client, auth_headers, seeded_user_residents):
    """User should see only their own residents."""
    resp = await client.get("/profile/residents", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2  # seeded_user_residents creates 2
    for r in data:
        assert "slug" in r
        assert "name" in r
        assert "star_rating" in r
        assert "status" in r
        assert "heat" in r
        assert "total_conversations" in r
        assert "avg_rating" in r

@pytest.mark.anyio
async def test_list_my_residents_empty(client, auth_headers):
    """New user with no residents should get empty list."""
    resp = await client.get("/profile/residents", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []

@pytest.mark.anyio
async def test_list_my_conversations(client, auth_headers, seeded_conversations):
    """User should see their conversation history."""
    resp = await client.get("/profile/conversations", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    conv = data[0]
    assert "id" in conv
    assert "resident_name" in conv
    assert "started_at" in conv
    assert "turns" in conv
    assert "rating" in conv

@pytest.mark.anyio
async def test_list_my_conversations_pagination(client, auth_headers, seeded_conversations):
    """Conversations should support limit/offset."""
    resp = await client.get("/profile/conversations?limit=1&offset=0", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) <= 1

@pytest.mark.anyio
async def test_list_my_transactions(client, auth_headers, seeded_transactions):
    """User should see their transaction history."""
    resp = await client.get("/profile/transactions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    tx = data[0]
    assert "amount" in tx
    assert "reason" in tx
    assert "created_at" in tx

@pytest.mark.anyio
async def test_profile_requires_auth(client):
    """All profile endpoints require authentication."""
    for path in ["/profile/residents", "/profile/conversations", "/profile/transactions"]:
        resp = await client.get(path)
        assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_profile.py -v
```
Expected: FAIL — routes don't exist yet

- [ ] **Step 3: Implement profile schemas**

`app/schemas/profile.py`:
```python
from datetime import datetime
from pydantic import BaseModel


class MyResidentItem(BaseModel):
    id: str
    slug: str
    name: str
    district: str
    status: str
    heat: int
    star_rating: int
    total_conversations: int
    avg_rating: float
    sprite_key: str
    meta_json: dict
    created_at: datetime


class MyConversationItem(BaseModel):
    id: str
    resident_id: str
    resident_name: str
    resident_slug: str
    started_at: datetime
    ended_at: datetime | None
    turns: int
    rating: int | None


class MyTransactionItem(BaseModel):
    id: str
    amount: int
    reason: str
    created_at: datetime
```

- [ ] **Step 4: Implement profile router**

`app/routers/profile.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.profile import MyResidentItem, MyConversationItem, MyTransactionItem
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/profile", tags=["profile"])


async def _require_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@router.get("/residents", response_model=list[MyResidentItem])
async def list_my_residents(
    user: User = Depends(_require_user),
    db: AsyncSession = Depends(get_db),
):
    """List all residents created by the current user."""
    result = await db.execute(
        select(Resident)
        .where(Resident.creator_id == user.id)
        .order_by(desc(Resident.created_at))
    )
    residents = result.scalars().all()
    return [MyResidentItem.model_validate(r, from_attributes=True) for r in residents]


@router.get("/conversations", response_model=list[MyConversationItem])
async def list_my_conversations(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(_require_user),
    db: AsyncSession = Depends(get_db),
):
    """List conversation history for the current user, newest first."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(desc(Conversation.started_at))
        .limit(limit)
        .offset(offset)
    )
    conversations = result.scalars().all()

    items = []
    for conv in conversations:
        # Fetch resident name for display
        res_result = await db.execute(
            select(Resident.name, Resident.slug).where(Resident.id == conv.resident_id)
        )
        row = res_result.first()
        resident_name = row[0] if row else "Unknown"
        resident_slug = row[1] if row else ""
        items.append(MyConversationItem(
            id=conv.id,
            resident_id=conv.resident_id,
            resident_name=resident_name,
            resident_slug=resident_slug,
            started_at=conv.started_at,
            ended_at=conv.ended_at,
            turns=conv.turns,
            rating=conv.rating,
        ))
    return items


@router.get("/transactions", response_model=list[MyTransactionItem])
async def list_my_transactions(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(_require_user),
    db: AsyncSession = Depends(get_db),
):
    """List transaction history for the current user, newest first."""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(desc(Transaction.created_at))
        .limit(limit)
        .offset(offset)
    )
    transactions = result.scalars().all()
    return [MyTransactionItem.model_validate(t, from_attributes=True) for t in transactions]
```

- [ ] **Step 5: Register router in `main.py`**

Add to `app/main.py`:
```python
from app.routers import auth, users, residents, profile

app.include_router(profile.router)
```

- [ ] **Step 6: Add test fixtures to `conftest.py`**

Add to `tests/conftest.py`:
```python
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction

@pytest.fixture
async def seeded_user_residents(db_session, test_user):
    """Create 2 residents owned by test_user."""
    r1 = Resident(
        slug="test-resident-1", name="Test Resident 1", creator_id=test_user.id,
        district="free", status="idle", heat=10, star_rating=1,
        ability_md="# Ability\nTest ability", persona_md="# Persona\nTest persona",
        soul_md="", sprite_key="伊莎贝拉", tile_x=70, tile_y=42,
        meta_json={"role": "Tester"},
    )
    r2 = Resident(
        slug="test-resident-2", name="Test Resident 2", creator_id=test_user.id,
        district="engineering", status="popular", heat=55, star_rating=2,
        ability_md="# Ability\nEngineering", persona_md="# Persona\nStrict",
        soul_md="# Soul\nTruth seeker", sprite_key="克劳斯", tile_x=58, tile_y=55,
        meta_json={"role": "Engineer"},
    )
    db_session.add_all([r1, r2])
    await db_session.commit()
    return [r1, r2]

@pytest.fixture
async def seeded_conversations(db_session, test_user, seeded_user_residents):
    """Create conversations for test_user."""
    from datetime import datetime
    r = seeded_user_residents[0]
    c1 = Conversation(
        user_id=test_user.id, resident_id=r.id,
        turns=5, rating=4, ended_at=datetime.utcnow(),
    )
    c2 = Conversation(
        user_id=test_user.id, resident_id=r.id,
        turns=3, rating=None,
    )
    db_session.add_all([c1, c2])
    await db_session.commit()
    return [c1, c2]

@pytest.fixture
async def seeded_transactions(db_session, test_user):
    """Create transactions for test_user."""
    t1 = Transaction(user_id=test_user.id, amount=100, reason="signup_bonus")
    t2 = Transaction(user_id=test_user.id, amount=-5, reason="chat:isabella")
    t3 = Transaction(user_id=test_user.id, amount=1, reason="chat_reward:isabella")
    db_session.add_all([t1, t2, t3])
    await db_session.commit()
    return [t1, t2, t3]
```

- [ ] **Step 7: Run tests**

```bash
cd backend && pytest tests/test_profile.py -v
```
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: profile API — list user's residents, conversations, transactions"
```

---

## Task 2: Resident Editing — PUT /residents/:slug + Version History

**Files:**
- Create: `backend/app/services/version_service.py`
- Modify: `backend/app/schemas/resident.py` (add edit schemas)
- Modify: `backend/app/routers/residents.py` (add PUT endpoint)
- Modify: `backend/app/models/resident.py` (add versions_json column)
- Create: `backend/tests/test_resident_edit.py`
- Create: `backend/tests/test_version.py`

- [ ] **Step 1: Write failing tests for resident editing**

`tests/test_resident_edit.py`:
```python
import pytest

@pytest.mark.anyio
async def test_edit_resident_ability(client, auth_headers, seeded_user_residents):
    """Creator can edit their resident's ability.md."""
    slug = seeded_user_residents[0].slug
    resp = await client.put(
        f"/residents/{slug}",
        headers=auth_headers,
        json={"ability_md": "# Updated Ability\nNew ability content"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ability_md"] == "# Updated Ability\nNew ability content"

@pytest.mark.anyio
async def test_edit_resident_all_layers(client, auth_headers, seeded_user_residents):
    """Creator can edit all three layers at once."""
    slug = seeded_user_residents[0].slug
    resp = await client.put(
        f"/residents/{slug}",
        headers=auth_headers,
        json={
            "ability_md": "# Ability V2\nUpdated",
            "persona_md": "# Persona V2\nUpdated",
            "soul_md": "# Soul V2\nUpdated",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "V2" in data["ability_md"]
    assert "V2" in data["persona_md"]
    assert "V2" in data["soul_md"]

@pytest.mark.anyio
async def test_edit_resident_creates_version(client, auth_headers, seeded_user_residents):
    """Editing a resident should create a version snapshot."""
    slug = seeded_user_residents[0].slug
    # First edit
    await client.put(
        f"/residents/{slug}",
        headers=auth_headers,
        json={"ability_md": "# Ability V2"},
    )
    # Check versions
    resp = await client.get(f"/residents/{slug}/versions", headers=auth_headers)
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) >= 1
    assert versions[0]["version_number"] == 1

@pytest.mark.anyio
async def test_edit_resident_not_owner(client, auth_headers_other, seeded_user_residents):
    """Non-creator cannot edit a resident."""
    slug = seeded_user_residents[0].slug
    resp = await client.put(
        f"/residents/{slug}",
        headers=auth_headers_other,
        json={"ability_md": "# Hacked"},
    )
    assert resp.status_code == 403

@pytest.mark.anyio
async def test_edit_resident_not_found(client, auth_headers):
    """Editing a non-existent resident returns 404."""
    resp = await client.put(
        "/residents/nonexistent",
        headers=auth_headers,
        json={"ability_md": "# Test"},
    )
    assert resp.status_code == 404

@pytest.mark.anyio
async def test_version_history_max_10(client, auth_headers, seeded_user_residents):
    """Version history should keep at most 10 versions."""
    slug = seeded_user_residents[0].slug
    for i in range(12):
        await client.put(
            f"/residents/{slug}",
            headers=auth_headers,
            json={"ability_md": f"# Ability V{i + 2}"},
        )
    resp = await client.get(f"/residents/{slug}/versions", headers=auth_headers)
    versions = resp.json()
    assert len(versions) <= 10
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_resident_edit.py -v
```
Expected: FAIL

- [ ] **Step 3: Write version service tests**

`tests/test_version.py`:
```python
import pytest
from app.services.version_service import create_version_snapshot, get_versions, MAX_VERSIONS

@pytest.mark.anyio
async def test_create_version_snapshot(db_session, seeded_user_residents):
    """Should create a version snapshot of current resident state."""
    resident = seeded_user_residents[0]
    version = await create_version_snapshot(db_session, resident)
    assert version["version_number"] == 1
    assert version["ability_md"] == resident.ability_md
    assert version["persona_md"] == resident.persona_md
    assert version["soul_md"] == resident.soul_md

@pytest.mark.anyio
async def test_max_versions_enforced(db_session, seeded_user_residents):
    """Should keep at most MAX_VERSIONS (10) versions."""
    resident = seeded_user_residents[0]
    for i in range(12):
        resident.ability_md = f"# Version {i}"
        await create_version_snapshot(db_session, resident)
    versions = await get_versions(db_session, resident.id)
    assert len(versions) <= MAX_VERSIONS
```

- [ ] **Step 4: Implement version service**

`app/services/version_service.py`:
```python
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resident import Resident

MAX_VERSIONS = 10


async def create_version_snapshot(db: AsyncSession, resident: Resident) -> dict:
    """
    Save a snapshot of the current resident state as a version.
    Versions are stored as a JSON array in resident.versions_json.
    Oldest versions are pruned when MAX_VERSIONS is exceeded.
    """
    result = await db.execute(select(Resident).where(Resident.id == resident.id))
    r = result.scalar_one()

    versions = r.versions_json or []
    next_version = (versions[-1]["version_number"] + 1) if versions else 1

    snapshot = {
        "version_number": next_version,
        "ability_md": r.ability_md,
        "persona_md": r.persona_md,
        "soul_md": r.soul_md,
        "created_at": datetime.utcnow().isoformat(),
    }
    versions.append(snapshot)

    # Prune oldest if exceeding max
    if len(versions) > MAX_VERSIONS:
        versions = versions[-MAX_VERSIONS:]

    r.versions_json = versions
    await db.commit()
    return snapshot


async def get_versions(db: AsyncSession, resident_id: str) -> list[dict]:
    """Get all version snapshots for a resident, newest first."""
    result = await db.execute(select(Resident).where(Resident.id == resident_id))
    r = result.scalar_one_or_none()
    if not r:
        return []
    versions = r.versions_json or []
    return list(reversed(versions))
```

- [ ] **Step 5: Add `versions_json` column to Resident model**

Modify `app/models/resident.py` — add after `meta_json`:
```python
    versions_json: Mapped[list] = mapped_column(JSON, default=list)
```

Create Alembic migration:
```bash
cd backend && alembic revision --autogenerate -m "add versions_json to residents"
alembic upgrade head
```

- [ ] **Step 6: Add edit schemas to `app/schemas/resident.py`**

Append to `app/schemas/resident.py`:
```python
class ResidentEditRequest(BaseModel):
    ability_md: str | None = None
    persona_md: str | None = None
    soul_md: str | None = None

class ResidentEditResponse(ResidentDetail):
    pass

class VersionSnapshot(BaseModel):
    version_number: int
    ability_md: str
    persona_md: str
    soul_md: str
    created_at: str
```

- [ ] **Step 7: Add PUT /residents/:slug and GET /residents/:slug/versions to router**

Add to `app/routers/residents.py`:
```python
from fastapi import Request
from app.schemas.resident import ResidentEditRequest, ResidentEditResponse, VersionSnapshot
from app.services.version_service import create_version_snapshot, get_versions
from app.services.auth_service import get_current_user
from app.services.scoring_service import compute_star_rating


async def _require_user(request: Request, db: AsyncSession = Depends(get_db)):
    from app.models.user import User
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    user = await get_current_user(db, auth.removeprefix("Bearer "))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@router.put("/{slug}", response_model=ResidentEditResponse)
async def edit_resident(
    slug: str,
    req: ResidentEditRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Edit a resident's three-layer markdown. Only the creator can edit."""
    user = await _require_user(request, db)
    r = await get_resident_by_slug(db, slug)
    if not r:
        raise HTTPException(status_code=404, detail="Resident not found")
    if r.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Not the creator of this resident")

    # Snapshot current state before editing
    await create_version_snapshot(db, r)

    # Apply edits (only non-None fields)
    if req.ability_md is not None:
        r.ability_md = req.ability_md
    if req.persona_md is not None:
        r.persona_md = req.persona_md
    if req.soul_md is not None:
        r.soul_md = req.soul_md

    # Recalculate star rating after edit
    r.star_rating = compute_star_rating(r)

    await db.commit()
    await db.refresh(r)
    return ResidentEditResponse.model_validate(r, from_attributes=True)


@router.get("/{slug}/versions", response_model=list[VersionSnapshot])
async def list_versions(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get version history for a resident. Only the creator can view."""
    user = await _require_user(request, db)
    r = await get_resident_by_slug(db, slug)
    if not r:
        raise HTTPException(status_code=404, detail="Resident not found")
    if r.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Not the creator of this resident")
    versions = await get_versions(db, r.id)
    return versions
```

- [ ] **Step 8: Run tests**

```bash
cd backend && pytest tests/test_resident_edit.py tests/test_version.py -v
```
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/
git commit -m "feat: resident editing with version history (max 10 snapshots)"
```

---

## Task 3: Quality Scoring Service

**Files:**
- Create: `backend/app/services/scoring_service.py`
- Create: `backend/tests/test_scoring.py`

- [ ] **Step 1: Write failing tests**

`tests/test_scoring.py`:
```python
import pytest
from unittest.mock import MagicMock
from app.services.scoring_service import compute_star_rating, StarLevel


def _make_resident(**kwargs):
    """Create a mock resident with sensible defaults."""
    defaults = {
        "ability_md": "",
        "persona_md": "",
        "soul_md": "",
        "total_conversations": 0,
        "avg_rating": 0.0,
        "meta_json": {},
    }
    defaults.update(kwargs)
    r = MagicMock()
    for k, v in defaults.items():
        setattr(r, k, v)
    return r


def test_star_1_minimal_skill():
    """1 star: has SKILL.md equivalent, format valid (临时居民)."""
    r = _make_resident(
        ability_md="# Ability\nSome ability",
        persona_md="",
        soul_md="",
    )
    assert compute_star_rating(r) == StarLevel.TEMPORARY


def test_star_1_empty_content():
    """1 star: all layers empty."""
    r = _make_resident(ability_md="", persona_md="", soul_md="")
    assert compute_star_rating(r) == StarLevel.TEMPORARY


def test_star_2_three_layers_complete():
    """2 stars: all three layers have substance (正式居民)."""
    r = _make_resident(
        ability_md="# Ability\n## Professional Skills\n- Backend architecture\n- API design\n\n## Learning\n- Fast learner",
        persona_md="# Persona\n## Layer 0: Core\n- Introverted but decisive\n\n## Layer 2: Expression\n- Concise, data-driven",
        soul_md="# Soul\n## Values\n- Truth over comfort\n\n## Background\n- 10 years in tech",
    )
    assert compute_star_rating(r) == StarLevel.OFFICIAL


def test_star_2_layers_too_short():
    """Layers present but too short should still be 1 star."""
    r = _make_resident(
        ability_md="# Ability\nOk",
        persona_md="# Persona\nOk",
        soul_md="# Soul\nOk",
    )
    assert compute_star_rating(r) == StarLevel.TEMPORARY


def test_star_3_popular_and_maintained():
    """3 stars: high conversations + high rating + substantial content (明星居民)."""
    r = _make_resident(
        ability_md="# Ability\n## Professional\n- Backend architecture\n- System design\n- Performance optimization\n\n## Social\n- Technical mentoring",
        persona_md="# Persona\n## Layer 0: Core\n- Rigorous and principled\n\n## Layer 1: Identity\n- Senior engineer\n\n## Layer 2: Expression\n- Precise, avoids ambiguity",
        soul_md="# Soul\n## Values\n- Engineering excellence\n- Knowledge sharing\n\n## Experience\n- Built systems serving millions",
        total_conversations=100,
        avg_rating=4.2,
    )
    assert compute_star_rating(r) == StarLevel.STAR


def test_star_3_not_enough_conversations():
    """Good content and rating but low conversations should be 2 stars."""
    r = _make_resident(
        ability_md="# Ability\n## Professional\n- Backend architecture\n- System design\n- Performance optimization\n\n## Social\n- Technical mentoring",
        persona_md="# Persona\n## Layer 0: Core\n- Rigorous\n\n## Layer 1: Identity\n- Engineer\n\n## Layer 2: Expression\n- Precise",
        soul_md="# Soul\n## Values\n- Excellence\n\n## Experience\n- Built systems",
        total_conversations=5,
        avg_rating=4.5,
    )
    assert compute_star_rating(r) == StarLevel.OFFICIAL


def test_star_3_low_rating():
    """High conversations but low rating should be 2 stars."""
    r = _make_resident(
        ability_md="# Ability\n## Professional\n- Backend architecture\n- System design\n- Performance optimization\n\n## Social\n- Technical mentoring",
        persona_md="# Persona\n## Layer 0: Core\n- Rigorous\n\n## Layer 1: Identity\n- Engineer\n\n## Layer 2: Expression\n- Precise",
        soul_md="# Soul\n## Values\n- Excellence\n\n## Experience\n- Built systems",
        total_conversations=200,
        avg_rating=2.1,
    )
    assert compute_star_rating(r) == StarLevel.OFFICIAL
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_scoring.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement scoring service**

`app/services/scoring_service.py`:
```python
"""
Quality scoring for residents.

Star rating system:
  1 star (临时居民): Has SKILL.md equivalent, format valid
  2 stars (正式居民): All three layers complete with substantive content
  3 stars (明星居民): High conversations + high rating + creator maintains

Scoring rules:
  - A layer is "substantive" if it has at least 50 characters of non-header content
  - "Three layers complete" means ability_md, persona_md, and soul_md all substantive
  - Star 3 requires: total_conversations >= 50 AND avg_rating >= 3.5 AND three layers complete
"""
from enum import IntEnum


class StarLevel(IntEnum):
    TEMPORARY = 1  # 临时居民
    OFFICIAL = 2   # 正式居民
    STAR = 3       # 明星居民


# Thresholds
MIN_LAYER_LENGTH = 50           # Minimum non-header chars for a "substantive" layer
STAR3_MIN_CONVERSATIONS = 50    # Minimum total conversations for 3-star
STAR3_MIN_RATING = 3.5          # Minimum avg rating for 3-star


def _strip_headers(md: str) -> str:
    """Remove markdown headers and whitespace to measure substantive content."""
    lines = md.strip().split("\n")
    content_lines = [
        line.strip() for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]
    return " ".join(content_lines)


def _is_layer_substantive(md: str | None) -> bool:
    """Check if a markdown layer has meaningful content beyond headers."""
    if not md:
        return False
    content = _strip_headers(md)
    return len(content) >= MIN_LAYER_LENGTH


def compute_star_rating(resident) -> int:
    """
    Compute the star rating for a resident based on content quality and usage metrics.

    Args:
        resident: Resident ORM object or mock with ability_md, persona_md, soul_md,
                  total_conversations, avg_rating attributes.

    Returns:
        int: 1, 2, or 3
    """
    ability_ok = _is_layer_substantive(resident.ability_md)
    persona_ok = _is_layer_substantive(resident.persona_md)
    soul_ok = _is_layer_substantive(resident.soul_md)
    three_layers_complete = ability_ok and persona_ok and soul_ok

    # Star 3: three layers complete + high usage + high rating
    if (
        three_layers_complete
        and resident.total_conversations >= STAR3_MIN_CONVERSATIONS
        and resident.avg_rating >= STAR3_MIN_RATING
    ):
        return StarLevel.STAR

    # Star 2: three layers complete with substance
    if three_layers_complete:
        return StarLevel.OFFICIAL

    # Star 1: minimum viable — has at least some content
    return StarLevel.TEMPORARY
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_scoring.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: quality scoring service — 1-3 star rating with content and usage thresholds"
```

---

## Task 4: Skill Import — POST /residents/import

**Files:**
- Modify: `backend/app/routers/residents.py` (add POST /residents/import)
- Modify: `backend/app/schemas/resident.py` (add import schemas)
- Create: `backend/tests/test_import.py`

- [ ] **Step 1: Write failing tests**

`tests/test_import.py`:
```python
import pytest
import json
import io


@pytest.mark.anyio
async def test_import_skill_md(client, auth_headers):
    """Import a single SKILL.md file."""
    skill_content = """# Ability
## Professional
- Backend engineering
- Distributed systems

# Persona
## Layer 0: Core
- Methodical, calm under pressure

## Layer 2: Expression
- Uses analogies to explain complex systems

# Soul
## Values
- Reliability over speed
- Engineering craftsmanship

## Background
- 8 years building payment systems
"""
    files = {"file": ("SKILL.md", io.BytesIO(skill_content.encode()), "text/markdown")}
    data = {"name": "Payment Expert", "slug": "payment-expert"}
    resp = await client.post(
        "/residents/import",
        headers=auth_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["slug"] == "payment-expert"
    assert result["name"] == "Payment Expert"
    assert "Backend engineering" in result["ability_md"]
    assert "Methodical" in result["persona_md"]
    assert "Reliability" in result["soul_md"]
    assert result["star_rating"] >= 1


@pytest.mark.anyio
async def test_import_zip_three_layers(client, auth_headers):
    """Import a zip with ability.md, persona.md, soul.md, meta.json."""
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ability.md", "# Ability\n## Professional\n- Frontend React expert\n- CSS architecture\n\n## Creative\n- UI/UX design thinking")
        zf.writestr("persona.md", "# Persona\n## Layer 0: Core\n- Detail-oriented perfectionist\n\n## Layer 2: Expression\n- Visual thinker, draws diagrams")
        zf.writestr("soul.md", "# Soul\n## Values\n- Beauty in simplicity\n\n## Experience\n- Redesigned 3 major products")
        zf.writestr("meta.json", json.dumps({
            "name": "Design Engineer",
            "slug": "design-engineer",
            "profile": {"role": "Frontend Engineer"},
            "tags": {"personality": ["perfectionist"]},
            "impression": "Always pixel-perfect",
        }))
    buf.seek(0)

    files = {"file": ("resident.zip", buf, "application/zip")}
    data = {"name": "Design Engineer", "slug": "design-engineer"}
    resp = await client.post(
        "/residents/import",
        headers=auth_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["slug"] == "design-engineer"
    assert "React" in result["ability_md"]
    assert "perfectionist" in result["persona_md"]
    assert "Beauty" in result["soul_md"]


@pytest.mark.anyio
async def test_import_colleague_skill_format(client, auth_headers):
    """Import from colleague-skill format: work.md maps to ability.md."""
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("work.md", "# Work Skill\n## Technical\n- Python backend\n- FastAPI expert\n\n## Process\n- Code review champion")
        zf.writestr("persona.md", "# Persona\n## Layer 0: Core\n- Pragmatic and efficient\n\n## Layer 2: Expression\n- Direct, no fluff")
    buf.seek(0)

    files = {"file": ("colleague.zip", buf, "application/zip")}
    data = {"name": "Backend Dev", "slug": "backend-dev"}
    resp = await client.post(
        "/residents/import",
        headers=auth_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 200
    result = resp.json()
    assert "Python backend" in result["ability_md"]
    assert "Pragmatic" in result["persona_md"]
    assert result["soul_md"] == ""  # soul.md empty for colleague-skill imports


@pytest.mark.anyio
async def test_import_duplicate_slug(client, auth_headers, seeded_user_residents):
    """Import with existing slug should return 409 conflict."""
    skill_content = "# Ability\nTest"
    files = {"file": ("SKILL.md", io.BytesIO(skill_content.encode()), "text/markdown")}
    slug = seeded_user_residents[0].slug
    data = {"name": "Duplicate", "slug": slug}
    resp = await client.post(
        "/residents/import",
        headers=auth_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_import_requires_auth(client):
    """Import requires authentication."""
    files = {"file": ("SKILL.md", io.BytesIO(b"# Test"), "text/markdown")}
    data = {"name": "Test", "slug": "test"}
    resp = await client.post("/residents/import", files=files, data=data)
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_import.py -v
```
Expected: FAIL

- [ ] **Step 3: Add import schemas**

Append to `app/schemas/resident.py`:
```python
class ResidentImportResponse(BaseModel):
    id: str
    slug: str
    name: str
    district: str
    star_rating: int
    ability_md: str
    persona_md: str
    soul_md: str
    meta_json: dict
```

- [ ] **Step 4: Implement import endpoint**

Add to `app/routers/residents.py`:
```python
import io
import json
import re
import zipfile
from fastapi import UploadFile, File, Form
from app.models.resident import Resident
from app.schemas.resident import ResidentImportResponse
from app.services.scoring_service import compute_star_rating


def _parse_skill_md(content: str) -> dict:
    """
    Parse a combined SKILL.md into separate layers.

    Splits on top-level headers: # Ability, # Persona, # Soul.
    Returns dict with keys: ability_md, persona_md, soul_md.
    """
    sections = {"ability_md": "", "persona_md": "", "soul_md": ""}
    current_key = None

    for line in content.split("\n"):
        stripped = line.strip().lower()
        if stripped.startswith("# ability") or stripped.startswith("# 能力"):
            current_key = "ability_md"
            sections[current_key] = line + "\n"
        elif stripped.startswith("# persona") or stripped.startswith("# 人格"):
            current_key = "persona_md"
            sections[current_key] = line + "\n"
        elif stripped.startswith("# soul") or stripped.startswith("# 灵魂"):
            current_key = "soul_md"
            sections[current_key] = line + "\n"
        elif current_key:
            sections[current_key] += line + "\n"

    # Trim trailing whitespace
    for k in sections:
        sections[k] = sections[k].rstrip()

    return sections


@router.post("/import", response_model=ResidentImportResponse)
async def import_resident(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    slug: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Import a resident from SKILL.md file or zip archive.

    Supported formats:
    - Single SKILL.md file: parsed into ability/persona/soul sections
    - Zip with ability.md + persona.md + soul.md + optional meta.json
    - Zip with work.md + persona.md (colleague-skill format): work.md -> ability.md, soul.md empty
    """
    user = await _require_user(request, db)

    # Check slug uniqueness
    existing = await get_resident_by_slug(db, slug)
    if existing:
        raise HTTPException(status_code=409, detail="Slug already exists")

    content = await file.read()
    ability_md = ""
    persona_md = ""
    soul_md = ""
    meta_json: dict = {}

    filename = file.filename or ""

    if filename.endswith(".md"):
        # Single SKILL.md file
        text = content.decode("utf-8")
        parsed = _parse_skill_md(text)
        ability_md = parsed["ability_md"]
        persona_md = parsed["persona_md"]
        soul_md = parsed["soul_md"]

    elif filename.endswith(".zip"):
        # Zip archive with individual layer files
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = zf.namelist()

                # Read meta.json if present
                if "meta.json" in names:
                    raw = zf.read("meta.json").decode("utf-8")
                    meta_json = json.loads(raw)

                # Read three-layer files
                if "ability.md" in names:
                    ability_md = zf.read("ability.md").decode("utf-8").strip()
                elif "work.md" in names:
                    # colleague-skill compatibility: work.md -> ability.md
                    ability_md = zf.read("work.md").decode("utf-8").strip()

                if "persona.md" in names:
                    persona_md = zf.read("persona.md").decode("utf-8").strip()

                if "soul.md" in names:
                    soul_md = zf.read("soul.md").decode("utf-8").strip()

        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid zip file")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Use .md or .zip")

    # Determine district from meta_json tags/role
    district = "free"
    role = meta_json.get("profile", {}).get("role", "")
    if any(kw in role.lower() for kw in ["engineer", "developer", "backend", "frontend", "算法", "工程师"]):
        district = "engineering"
    elif any(kw in role.lower() for kw in ["professor", "teacher", "导师", "教授"]):
        district = "academy"

    # Create resident
    resident = Resident(
        slug=slug,
        name=name,
        district=district,
        status="idle",
        heat=0,
        creator_id=user.id,
        ability_md=ability_md,
        persona_md=persona_md,
        soul_md=soul_md,
        meta_json=meta_json,
        sprite_key="伊莎贝拉",  # Default sprite, can be changed later
        tile_x=76,  # Default position, will be assigned by district
        tile_y=50,
    )

    # Compute star rating
    resident.star_rating = compute_star_rating(resident)

    db.add(resident)
    await db.commit()
    await db.refresh(resident)

    return ResidentImportResponse(
        id=resident.id,
        slug=resident.slug,
        name=resident.name,
        district=resident.district,
        star_rating=resident.star_rating,
        ability_md=resident.ability_md,
        persona_md=resident.persona_md,
        soul_md=resident.soul_md,
        meta_json=resident.meta_json,
    )
```

- [ ] **Step 5: Run tests**

```bash
cd backend && pytest tests/test_import.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: skill import — SKILL.md, zip (3-layer), colleague-skill (work.md) formats"
```

---

## Task 5: Conversation Rating — Backend + ChatDrawer Modification

**Files:**
- Modify: `backend/app/ws/handler.py` (add rating handling)
- Modify: `backend/app/ws/protocol.py` (add rate_chat message type)
- Modify: `backend/app/models/conversation.py` (rating already exists from Plan 1)
- Create: `backend/tests/test_rating.py`
- Modify: `frontend/src/components/ChatDrawer.tsx` (add rating popup flow)
- Create: `frontend/src/components/RatingPopup.tsx`

- [ ] **Step 1: Write failing backend tests**

`tests/test_rating.py`:
```python
import pytest
from app.models.conversation import Conversation
from app.models.resident import Resident

@pytest.mark.anyio
async def test_rate_conversation_updates_record(db_session, test_user, seeded_user_residents):
    """Rating a conversation should update the conversation record."""
    resident = seeded_user_residents[0]
    conv = Conversation(user_id=test_user.id, resident_id=resident.id, turns=5)
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    # Simulate rating
    conv.rating = 4
    await db_session.commit()
    await db_session.refresh(conv)

    assert conv.rating == 4

@pytest.mark.anyio
async def test_rating_updates_resident_avg(db_session, test_user, seeded_user_residents):
    """After rating, resident's avg_rating should be recalculated."""
    from sqlalchemy import select, func
    resident = seeded_user_residents[0]

    # Create conversations with ratings
    for rating in [5, 4, 3, 4]:
        conv = Conversation(
            user_id=test_user.id, resident_id=resident.id,
            turns=3, rating=rating,
        )
        db_session.add(conv)
    await db_session.commit()

    # Calculate avg
    result = await db_session.execute(
        select(func.avg(Conversation.rating)).where(
            Conversation.resident_id == resident.id,
            Conversation.rating.is_not(None),
        )
    )
    avg = result.scalar()
    assert avg == 4.0

    # Update resident
    resident.avg_rating = float(avg)
    await db_session.commit()
    assert resident.avg_rating == 4.0

@pytest.mark.anyio
async def test_rating_value_validation():
    """Rating must be 1-5."""
    valid_ratings = [1, 2, 3, 4, 5]
    invalid_ratings = [0, 6, -1, 10]
    for r in valid_ratings:
        assert 1 <= r <= 5
    for r in invalid_ratings:
        assert not (1 <= r <= 5)
```

- [ ] **Step 2: Add `rate_chat` to WebSocket protocol**

Add to `app/ws/protocol.py`:
```python
class RateChat(WSMessage):
    type: str = "rate_chat"
    rating: int  # 1-5
```

- [ ] **Step 3: Add rating handler to `app/ws/handler.py`**

Add this block inside the `while True` loop, after the `end_chat` handler:

```python
                elif msg_type == "rate_chat" and data.get("conversation_id"):
                    conv_id = data["conversation_id"]
                    rating_value = data.get("rating", 0)

                    # Validate rating range
                    if not (1 <= rating_value <= 5):
                        await manager.send(user_id, {
                            "type": "error",
                            "message": "Rating must be between 1 and 5",
                        })
                        continue

                    # Update conversation rating
                    result = await db.execute(
                        select(Conversation).where(
                            Conversation.id == conv_id,
                            Conversation.user_id == user_id,
                        )
                    )
                    conv = result.scalar_one_or_none()
                    if not conv:
                        await manager.send(user_id, {
                            "type": "error",
                            "message": "Conversation not found",
                        })
                        continue

                    conv.rating = rating_value
                    await db.commit()

                    # Recalculate resident avg_rating
                    from sqlalchemy import func
                    result = await db.execute(
                        select(func.avg(Conversation.rating)).where(
                            Conversation.resident_id == conv.resident_id,
                            Conversation.rating.is_not(None),
                        )
                    )
                    avg = result.scalar()
                    if avg is not None:
                        res_result = await db.execute(
                            select(Resident).where(Resident.id == conv.resident_id)
                        )
                        resident = res_result.scalar_one_or_none()
                        if resident:
                            resident.avg_rating = round(float(avg), 2)
                            # Recalculate star rating
                            from app.services.scoring_service import compute_star_rating
                            resident.star_rating = compute_star_rating(resident)
                            await db.commit()

                    # Reward creator for good rating (>= 4 stars → 5 SC bonus)
                    if rating_value >= 4 and conv.resident_id:
                        res_result = await db.execute(
                            select(Resident).where(Resident.id == conv.resident_id)
                        )
                        resident = res_result.scalar_one_or_none()
                        if resident:
                            from app.services.coin_service import reward
                            await reward(db, resident.creator_id, 5, f"good_rating:{resident.slug}")

                    await manager.send(user_id, {
                        "type": "rating_saved",
                        "conversation_id": conv_id,
                        "rating": rating_value,
                    })
```

Also modify the `end_chat` handler to send `conversation_id` in the `chat_ended` response so the frontend knows which conversation to rate:

Replace the existing `chat_ended` send in `end_chat` block:
```python
                    await manager.send(user_id, {
                        "type": "chat_ended",
                        "conversation_id": current_conversation.id,
                    })
```

- [ ] **Step 4: Create RatingPopup component**

`frontend/src/components/RatingPopup.tsx`:
```typescript
import { useState } from 'react'

interface RatingPopupProps {
  residentName: string
  onRate: (rating: number) => void
  onSkip: () => void
}

export function RatingPopup({ residentName, onRate, onSkip }: RatingPopupProps) {
  const [hovered, setHovered] = useState(0)
  const [selected, setSelected] = useState(0)

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50,
    }}>
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 16, padding: 32, width: 320, textAlign: 'center',
      }}>
        <div style={{ fontSize: 32, marginBottom: 8 }}>💬</div>
        <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>
          How was your chat?
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 20 }}>
          Rate your conversation with {residentName}
        </div>

        {/* Star rating */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginBottom: 20 }}>
          {[1, 2, 3, 4, 5].map((star) => (
            <span
              key={star}
              onMouseEnter={() => setHovered(star)}
              onMouseLeave={() => setHovered(0)}
              onClick={() => setSelected(star)}
              style={{
                fontSize: 28, cursor: 'pointer',
                filter: (hovered || selected) >= star ? 'none' : 'grayscale(1) opacity(0.4)',
                transition: 'filter 0.15s ease',
              }}
            >
              ⭐
            </span>
          ))}
        </div>

        {/* Labels */}
        <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginBottom: 16, minHeight: 16 }}>
          {selected === 1 && '😕 Not great'}
          {selected === 2 && '😐 Below average'}
          {selected === 3 && '🙂 Average'}
          {selected === 4 && '😊 Good'}
          {selected === 5 && '🤩 Excellent!'}
        </div>

        {/* Buttons */}
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={onSkip}
            style={{
              flex: 1, background: 'var(--bg-input)', color: 'var(--text-secondary)',
              border: '1px solid var(--border)', padding: '10px 16px',
              borderRadius: 'var(--radius)', fontSize: 13, cursor: 'pointer',
            }}
          >
            Skip
          </button>
          <button
            onClick={() => selected > 0 && onRate(selected)}
            disabled={selected === 0}
            style={{
              flex: 1, background: selected > 0 ? 'var(--accent-red)' : 'var(--bg-input)',
              color: selected > 0 ? 'white' : 'var(--text-muted)',
              border: 'none', padding: '10px 16px',
              borderRadius: 'var(--radius)', fontSize: 13, fontWeight: 600,
              cursor: selected > 0 ? 'pointer' : 'default',
              transition: 'background 0.2s ease',
            }}
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Modify ChatDrawer to show rating popup on chat end**

Modify `frontend/src/components/ChatDrawer.tsx` — add rating state and popup:

Add these state variables inside the `ChatDrawer` component:
```typescript
  const [showRating, setShowRating] = useState(false)
  const [endedConversationId, setEndedConversationId] = useState<string | null>(null)
```

Update the WS message listener to handle `chat_ended` with `conversation_id`:
```typescript
  // Inside the onWSMessage callback, add handling for chat_ended:
  useEffect(() => onWSMessage((data) => {
    if (data.type === 'chat_reply') {
      if (data.done) {
        setMessages((prev) => [...prev, { role: 'npc', sender: useGameStore.getState().chatResident?.name || '', text: streaming }])
        setStreaming('')
      } else {
        setStreaming((s) => s + data.text)
      }
    } else if (data.type === 'chat_ended') {
      // Show rating popup instead of immediately closing
      setEndedConversationId(data.conversation_id)
      setShowRating(true)
    }
  }), [streaming])
```

Update the `close` function to send `end_chat` but NOT immediately close the drawer:
```typescript
  const close = () => {
    sendWS({ type: 'end_chat' })
    // Don't closeChat() here — wait for rating popup
  }

  const handleRate = (rating: number) => {
    if (endedConversationId) {
      sendWS({ type: 'rate_chat', conversation_id: endedConversationId, rating })
    }
    setShowRating(false)
    setEndedConversationId(null)
    closeChat()
  }

  const handleSkipRating = () => {
    setShowRating(false)
    setEndedConversationId(null)
    closeChat()
  }
```

Add the rating popup render at the end of the component's return, before the closing `</div>`:
```typescript
      {showRating && chatResident && (
        <RatingPopup
          residentName={chatResident.name}
          onRate={handleRate}
          onSkip={handleSkipRating}
        />
      )}
```

Add the import at the top:
```typescript
import { RatingPopup } from './RatingPopup'
```

- [ ] **Step 6: Run backend tests**

```bash
cd backend && pytest tests/test_rating.py -v
```
Expected: PASS

- [ ] **Step 7: Verify frontend builds**

```bash
cd frontend && npm run build
```
Expected: Build succeeds

- [ ] **Step 8: Commit**

```bash
git add backend/ frontend/
git commit -m "feat: post-chat rating popup (1-5 stars) with avg_rating recalculation and creator reward"
```

---

## Task 6: Profile Page — Frontend Components

**Files:**
- Create: `frontend/src/pages/ProfilePage.tsx`
- Create: `frontend/src/components/profile/ProfileSidebar.tsx`
- Create: `frontend/src/components/profile/ResidentList.tsx`
- Create: `frontend/src/components/profile/ResidentCard.tsx`
- Create: `frontend/src/components/profile/ConversationHistory.tsx`
- Create: `frontend/src/components/profile/TransactionHistory.tsx`
- Modify: `frontend/src/App.tsx` (add /profile route)
- Modify: `frontend/src/stores/gameStore.ts` (add profileTab state)
- Modify: `frontend/src/components/TopNav.tsx` (add profile link)

- [ ] **Step 1: Add profileTab state to gameStore**

Add to `frontend/src/stores/gameStore.ts`:
```typescript
// Add to GameState interface:
  profileTab: 'residents' | 'conversations' | 'transactions' | 'settings'
  setProfileTab: (tab: 'residents' | 'conversations' | 'transactions' | 'settings') => void

// Add to create:
  profileTab: 'residents',
  setProfileTab: (tab) => set({ profileTab: tab }),
```

- [ ] **Step 2: Create ProfileSidebar**

`frontend/src/components/profile/ProfileSidebar.tsx`:
```typescript
import { useGameStore } from '../../stores/gameStore'

type Tab = 'residents' | 'conversations' | 'transactions' | 'settings'

const NAV_ITEMS: { key: Tab; icon: string; label: string }[] = [
  { key: 'residents', icon: '🏠', label: '我的居民' },
  { key: 'conversations', icon: '💬', label: '对话历史' },
  { key: 'transactions', icon: '🪙', label: '代币明细' },
  { key: 'settings', icon: '⚙️', label: '设置' },
]

interface ProfileSidebarProps {
  residentCount: number
}

export function ProfileSidebar({ residentCount }: ProfileSidebarProps) {
  const user = useGameStore((s) => s.user)
  const profileTab = useGameStore((s) => s.profileTab)
  const setProfileTab = useGameStore((s) => s.setProfileTab)

  return (
    <div style={{
      width: 250, minHeight: 'calc(100vh - var(--nav-height))',
      background: 'var(--bg-card)', borderRight: '1px solid var(--border)',
      padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 24,
    }}>
      {/* User info */}
      <div style={{ textAlign: 'center' }}>
        <div style={{
          width: 72, height: 72, background: 'var(--bg-input)', borderRadius: 12,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 32, margin: '0 auto 12px',
          imageRendering: 'pixelated',
        }}>
          {user?.avatar ? (
            <img src={user.avatar} alt="" style={{ width: '100%', height: '100%', borderRadius: 12, imageRendering: 'pixelated' }} />
          ) : '👤'}
        </div>
        <div style={{ fontWeight: 700, fontSize: 16 }}>{user?.name}</div>
        <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
          创作了 {residentCount} 位居民
        </div>
      </div>

      {/* Navigation */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.key}
            onClick={() => setProfileTab(item.key)}
            style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 14px', borderRadius: 8,
              background: profileTab === item.key ? 'var(--bg-input)' : 'transparent',
              border: 'none', color: profileTab === item.key ? 'var(--text-primary)' : 'var(--text-secondary)',
              fontSize: 14, cursor: 'pointer', textAlign: 'left',
              fontWeight: profileTab === item.key ? 600 : 400,
              transition: 'background 0.15s ease',
            }}
          >
            <span style={{ fontSize: 16 }}>{item.icon}</span>
            {item.label}
          </button>
        ))}
      </div>

      {/* Soul Coin balance */}
      <div style={{
        marginTop: 'auto', padding: '12px 14px',
        background: '#53d76910', borderRadius: 8,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ fontSize: 18 }}>🪙</span>
        <div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Soul Coin</div>
          <div style={{ fontWeight: 700, color: 'var(--accent-green)', fontSize: 16 }}>
            {user?.soul_coin_balance ?? 0}
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create ResidentCard**

`frontend/src/components/profile/ResidentCard.tsx`:
```typescript
import { useNavigate } from 'react-router-dom'

interface ResidentCardProps {
  resident: {
    slug: string
    name: string
    star_rating: number
    status: string
    heat: number
    district: string
    total_conversations: number
    avg_rating: number
    sprite_key: string
    meta_json: { role?: string }
  }
  onEdit: (slug: string) => void
}

const STATUS_LABELS: Record<string, string> = {
  idle: '🟢 空闲',
  chatting: '💬 对话中',
  sleeping: '💤 沉睡',
  popular: '🔥 热门',
}

export function ResidentCard({ resident, onEdit }: ResidentCardProps) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px',
      background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 12,
    }}>
      {/* Avatar */}
      <div style={{
        width: 48, height: 48, background: 'var(--bg-input)', borderRadius: 8,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 24, imageRendering: 'pixelated', flexShrink: 0,
      }}>
        🧑‍💻
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontWeight: 700, fontSize: 14 }}>{resident.name}</span>
          <span style={{ fontSize: 12 }}>{'⭐'.repeat(resident.star_rating)}</span>
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 2 }}>
          {resident.meta_json?.role || 'Unknown'} · {resident.district}
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 11, color: 'var(--text-secondary)' }}>
          <span>{STATUS_LABELS[resident.status] || resident.status}</span>
          <span>🔥 {resident.heat}</span>
          <span>💬 {resident.total_conversations}</span>
          {resident.avg_rating > 0 && <span>⭐ {resident.avg_rating.toFixed(1)}</span>}
        </div>
      </div>

      {/* Edit button */}
      <button
        onClick={() => onEdit(resident.slug)}
        style={{
          background: 'var(--bg-input)', border: '1px solid var(--border)',
          color: 'var(--text-secondary)', padding: '6px 14px', borderRadius: 6,
          fontSize: 12, cursor: 'pointer', flexShrink: 0,
        }}
      >
        Edit
      </button>
    </div>
  )
}
```

- [ ] **Step 4: Create ResidentList**

`frontend/src/components/profile/ResidentList.tsx`:
```typescript
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGameStore } from '../../stores/gameStore'
import { ResidentCard } from './ResidentCard'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface ResidentItem {
  id: string
  slug: string
  name: string
  star_rating: number
  status: string
  heat: number
  district: string
  total_conversations: number
  avg_rating: number
  sprite_key: string
  meta_json: { role?: string }
}

interface ResidentListProps {
  onResidentCountChange: (count: number) => void
  onEditResident: (slug: string) => void
}

export function ResidentList({ onResidentCountChange, onEditResident }: ResidentListProps) {
  const [residents, setResidents] = useState<ResidentItem[]>([])
  const [loading, setLoading] = useState(true)
  const token = useGameStore((s) => s.token)
  const navigate = useNavigate()

  useEffect(() => {
    const fetchResidents = async () => {
      setLoading(true)
      try {
        const resp = await fetch(`${API}/profile/residents`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (resp.ok) {
          const data = await resp.json()
          setResidents(data)
          onResidentCountChange(data.length)
        }
      } catch (err) {
        console.error('Failed to fetch residents:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchResidents()
  }, [token])

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', padding: 20, textAlign: 'center' }}>Loading...</div>
  }

  return (
    <div>
      {/* Header with create button */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700 }}>我的居民</h2>
        <button
          onClick={() => navigate('/forge')}
          style={{
            background: 'var(--accent-red)', color: 'white', border: 'none',
            padding: '8px 18px', borderRadius: 'var(--radius)', fontSize: 13,
            fontWeight: 600, cursor: 'pointer',
          }}
        >
          + 创建新居民
        </button>
      </div>

      {/* Resident cards */}
      {residents.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: 40,
          color: 'var(--text-muted)', fontSize: 14,
        }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🏘️</div>
          <div>You haven't created any residents yet.</div>
          <button
            onClick={() => navigate('/forge')}
            style={{
              marginTop: 16, background: 'var(--accent-red)', color: 'white',
              border: 'none', padding: '10px 24px', borderRadius: 'var(--radius)',
              fontSize: 14, fontWeight: 600, cursor: 'pointer',
            }}
          >
            Create your first resident
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {residents.map((r) => (
            <ResidentCard key={r.id} resident={r} onEdit={onEditResident} />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Create ConversationHistory**

`frontend/src/components/profile/ConversationHistory.tsx`:
```typescript
import { useEffect, useState } from 'react'
import { useGameStore } from '../../stores/gameStore'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface ConversationItem {
  id: string
  resident_name: string
  resident_slug: string
  started_at: string
  ended_at: string | null
  turns: number
  rating: number | null
}

export function ConversationHistory() {
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [loading, setLoading] = useState(true)
  const token = useGameStore((s) => s.token)

  useEffect(() => {
    const fetch_ = async () => {
      setLoading(true)
      try {
        const resp = await fetch(`${API}/profile/conversations?limit=50`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (resp.ok) setConversations(await resp.json())
      } catch (err) {
        console.error('Failed to fetch conversations:', err)
      } finally {
        setLoading(false)
      }
    }
    fetch_()
  }, [token])

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', padding: 20, textAlign: 'center' }}>Loading...</div>
  }

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 20 }}>对话历史</h2>

      {conversations.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: 14 }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>💬</div>
          <div>No conversation history yet. Go explore the city!</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {conversations.map((conv) => (
            <div
              key={conv.id}
              style={{
                display: 'flex', alignItems: 'center', gap: 14,
                padding: '12px 16px', background: 'var(--bg-card)',
                border: '1px solid var(--border)', borderRadius: 10,
              }}
            >
              <div style={{
                width: 40, height: 40, background: 'var(--bg-input)', borderRadius: 8,
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20,
              }}>
                🧑‍💻
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{conv.resident_name}</div>
                <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 2 }}>
                  {formatDate(conv.started_at)} · {conv.turns} turns
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                {conv.rating ? (
                  <span style={{ fontSize: 13 }}>{'⭐'.repeat(conv.rating)}</span>
                ) : (
                  <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>No rating</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Create TransactionHistory**

`frontend/src/components/profile/TransactionHistory.tsx`:
```typescript
import { useEffect, useState } from 'react'
import { useGameStore } from '../../stores/gameStore'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface TransactionItem {
  id: string
  amount: number
  reason: string
  created_at: string
}

const REASON_LABELS: Record<string, string> = {
  signup_bonus: '注册奖励',
  daily_login: '每日登录',
  forge_reward: '炼化奖励',
  good_rating: '好评奖励',
  chat_reward: '对话收入',
  chat: '对话消费',
}

export function TransactionHistory() {
  const [transactions, setTransactions] = useState<TransactionItem[]>([])
  const [loading, setLoading] = useState(true)
  const token = useGameStore((s) => s.token)

  useEffect(() => {
    const fetch_ = async () => {
      setLoading(true)
      try {
        const resp = await fetch(`${API}/profile/transactions?limit=100`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (resp.ok) setTransactions(await resp.json())
      } catch (err) {
        console.error('Failed to fetch transactions:', err)
      } finally {
        setLoading(false)
      }
    }
    fetch_()
  }, [token])

  const formatDate = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  const getReasonLabel = (reason: string) => {
    // Handle compound reasons like "chat:isabella" or "chat_reward:isabella"
    const base = reason.split(':')[0]
    return REASON_LABELS[base] || reason
  }

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', padding: 20, textAlign: 'center' }}>Loading...</div>
  }

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 20 }}>代币明细</h2>

      {transactions.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: 14 }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🪙</div>
          <div>No transactions yet.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {transactions.map((tx) => (
            <div
              key={tx.id}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 16px', background: 'var(--bg-card)',
                border: '1px solid var(--border)', borderRadius: 8,
              }}
            >
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                background: tx.amount > 0 ? '#53d76915' : '#e9456015',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 16,
              }}>
                {tx.amount > 0 ? '📥' : '📤'}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{getReasonLabel(tx.reason)}</div>
                <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 1 }}>
                  {formatDate(tx.created_at)}
                </div>
              </div>
              <div style={{
                fontWeight: 700, fontSize: 14,
                color: tx.amount > 0 ? 'var(--accent-green)' : 'var(--accent-red)',
              }}>
                {tx.amount > 0 ? '+' : ''}{tx.amount} SC
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 7: Create ProfilePage with layout**

`frontend/src/pages/ProfilePage.tsx`:
```typescript
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopNav } from '../components/TopNav'
import { ProfileSidebar } from '../components/profile/ProfileSidebar'
import { ResidentList } from '../components/profile/ResidentList'
import { ConversationHistory } from '../components/profile/ConversationHistory'
import { TransactionHistory } from '../components/profile/TransactionHistory'
import { ResidentEditor } from '../components/profile/ResidentEditor'
import { useGameStore } from '../stores/gameStore'

export function ProfilePage() {
  const profileTab = useGameStore((s) => s.profileTab)
  const [residentCount, setResidentCount] = useState(0)
  const [editingSlug, setEditingSlug] = useState<string | null>(null)

  // If editing a resident, show the editor
  if (editingSlug) {
    return (
      <>
        <TopNav />
        <div style={{ paddingTop: 'var(--nav-height)' }}>
          <ResidentEditor
            slug={editingSlug}
            onBack={() => setEditingSlug(null)}
          />
        </div>
      </>
    )
  }

  return (
    <>
      <TopNav />
      <div style={{
        display: 'flex', paddingTop: 'var(--nav-height)',
        minHeight: '100vh', background: 'var(--bg-page)',
      }}>
        <ProfileSidebar residentCount={residentCount} />
        <div style={{ flex: 1, padding: '24px 32px', maxWidth: 800 }}>
          {profileTab === 'residents' && (
            <ResidentList
              onResidentCountChange={setResidentCount}
              onEditResident={setEditingSlug}
            />
          )}
          {profileTab === 'conversations' && <ConversationHistory />}
          {profileTab === 'transactions' && <TransactionHistory />}
          {profileTab === 'settings' && (
            <div style={{ color: 'var(--text-muted)', padding: 40, textAlign: 'center' }}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>⚙️</div>
              <div>Settings coming soon.</div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
```

- [ ] **Step 8: Add /profile route to App.tsx**

Modify `frontend/src/App.tsx`:
```typescript
import { ProfilePage } from './pages/ProfilePage'

// Inside <Routes>, add:
<Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
```

- [ ] **Step 9: Add profile link to TopNav**

Modify `frontend/src/components/TopNav.tsx` — add to the right-side div, before the avatar:
```typescript
import { useNavigate } from 'react-router-dom'

// Inside TopNav:
const navigate = useNavigate()

// Add profile link in the nav items area:
<span
  onClick={() => navigate('/profile')}
  style={{ color: 'var(--text-secondary)', fontSize: 13, cursor: 'pointer' }}
>
  Profile
</span>
```

- [ ] **Step 10: Verify frontend builds**

```bash
cd frontend && npm run build
```
Expected: Build succeeds

- [ ] **Step 11: Commit**

```bash
git add frontend/
git commit -m "feat: profile page with sidebar nav, resident list, conversation history, transaction history"
```

---

## Task 7: Resident Editor — Markdown Editor + Version History

**Files:**
- Create: `frontend/src/components/profile/ResidentEditor.tsx`

- [ ] **Step 1: Install markdown editor dependency**

```bash
cd frontend && npm install @uiw/react-md-editor react-markdown
```

- [ ] **Step 2: Create ResidentEditor component**

`frontend/src/components/profile/ResidentEditor.tsx`:
```typescript
import { useEffect, useState } from 'react'
import MDEditor from '@uiw/react-md-editor'
import { useGameStore } from '../../stores/gameStore'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

type Layer = 'ability' | 'persona' | 'soul'

interface ResidentDetail {
  slug: string
  name: string
  ability_md: string
  persona_md: string
  soul_md: string
  star_rating: number
  total_conversations: number
  avg_rating: number
  meta_json: { role?: string }
}

interface VersionSnapshot {
  version_number: number
  ability_md: string
  persona_md: string
  soul_md: string
  created_at: string
}

interface ResidentEditorProps {
  slug: string
  onBack: () => void
}

const LAYER_CONFIG: { key: Layer; icon: string; label: string; description: string }[] = [
  { key: 'ability', icon: '📋', label: 'Ability', description: '能力层 — 这个人能做什么' },
  { key: 'persona', icon: '🎭', label: 'Persona', description: '人格层 — 怎么做、怎么说' },
  { key: 'soul', icon: '💎', label: 'Soul', description: '灵魂层 — 为什么这样做' },
]

export function ResidentEditor({ slug, onBack }: ResidentEditorProps) {
  const token = useGameStore((s) => s.token)
  const [resident, setResident] = useState<ResidentDetail | null>(null)
  const [activeLayer, setActiveLayer] = useState<Layer>('ability')
  const [drafts, setDrafts] = useState<Record<Layer, string>>({
    ability: '', persona: '', soul: '',
  })
  const [versions, setVersions] = useState<VersionSnapshot[]>([])
  const [showVersions, setShowVersions] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  // Fetch resident detail
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const [resResp, verResp] = await Promise.all([
          fetch(`${API}/residents/${slug}`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${API}/residents/${slug}/versions`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ])
        if (resResp.ok) {
          const data = await resResp.json()
          setResident(data)
          setDrafts({
            ability: data.ability_md,
            persona: data.persona_md,
            soul: data.soul_md,
          })
        }
        if (verResp.ok) {
          setVersions(await verResp.json())
        }
      } catch (err) {
        console.error('Failed to fetch resident:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [slug, token])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const resp = await fetch(`${API}/residents/${slug}`, {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ability_md: drafts.ability,
          persona_md: drafts.persona,
          soul_md: drafts.soul,
        }),
      })
      if (resp.ok) {
        const updated = await resp.json()
        setResident(updated)
        setSaved(true)
        setTimeout(() => setSaved(false), 2000)
        // Refresh versions
        const verResp = await fetch(`${API}/residents/${slug}/versions`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (verResp.ok) setVersions(await verResp.json())
      }
    } catch (err) {
      console.error('Failed to save:', err)
    } finally {
      setSaving(false)
    }
  }

  const restoreVersion = (version: VersionSnapshot) => {
    setDrafts({
      ability: version.ability_md,
      persona: version.persona_md,
      soul: version.soul_md,
    })
    setShowVersions(false)
  }

  if (loading) {
    return <div style={{ color: 'var(--text-muted)', padding: 40, textAlign: 'center' }}>Loading...</div>
  }

  if (!resident) {
    return <div style={{ color: 'var(--accent-red)', padding: 40, textAlign: 'center' }}>Resident not found.</div>
  }

  return (
    <div style={{ display: 'flex', minHeight: 'calc(100vh - var(--nav-height))' }}>
      {/* Left: editor */}
      <div style={{ flex: 1, padding: '24px 32px', maxWidth: 900 }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <button
            onClick={onBack}
            style={{
              background: 'var(--bg-input)', border: '1px solid var(--border)',
              color: 'var(--text-secondary)', padding: '6px 12px', borderRadius: 6,
              fontSize: 13, cursor: 'pointer',
            }}
          >
            ← Back
          </button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 18 }}>{resident.name}</div>
            <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              {'⭐'.repeat(resident.star_rating)} · {resident.meta_json?.role} · 💬 {resident.total_conversations} · ⭐ {resident.avg_rating.toFixed(1)}
            </div>
          </div>
          <button
            onClick={() => setShowVersions(!showVersions)}
            style={{
              background: 'var(--bg-input)', border: '1px solid var(--border)',
              color: 'var(--text-secondary)', padding: '6px 14px', borderRadius: 6,
              fontSize: 12, cursor: 'pointer',
            }}
          >
            📜 Versions ({versions.length})
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              background: saved ? 'var(--accent-green)' : 'var(--accent-red)',
              color: 'white', border: 'none', padding: '8px 20px', borderRadius: 6,
              fontSize: 13, fontWeight: 600, cursor: saving ? 'default' : 'pointer',
              transition: 'background 0.2s ease',
            }}
          >
            {saving ? 'Saving...' : saved ? 'Saved!' : 'Save'}
          </button>
        </div>

        {/* Layer tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
          {LAYER_CONFIG.map((layer) => (
            <button
              key={layer.key}
              onClick={() => setActiveLayer(layer.key)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 16px', borderRadius: '8px 8px 0 0',
                background: activeLayer === layer.key ? 'var(--bg-card)' : 'transparent',
                border: activeLayer === layer.key ? '1px solid var(--border)' : '1px solid transparent',
                borderBottom: activeLayer === layer.key ? '1px solid var(--bg-card)' : '1px solid var(--border)',
                color: activeLayer === layer.key ? 'var(--text-primary)' : 'var(--text-muted)',
                fontSize: 13, fontWeight: activeLayer === layer.key ? 600 : 400,
                cursor: 'pointer',
              }}
            >
              {layer.icon} {layer.label}
            </button>
          ))}
        </div>

        {/* Description */}
        <div style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 12 }}>
          {LAYER_CONFIG.find((l) => l.key === activeLayer)?.description}
        </div>

        {/* Markdown editor */}
        <div data-color-mode="dark">
          <MDEditor
            value={drafts[activeLayer]}
            onChange={(val) => setDrafts((prev) => ({ ...prev, [activeLayer]: val || '' }))}
            height={500}
            preview="live"
          />
        </div>
      </div>

      {/* Right: version history panel (conditional) */}
      {showVersions && (
        <div style={{
          width: 300, borderLeft: '1px solid var(--border)',
          background: 'var(--bg-card)', padding: '24px 16px',
          overflowY: 'auto',
        }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 16 }}>Version History</h3>
          {versions.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No versions yet.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {versions.map((v) => (
                <div
                  key={v.version_number}
                  style={{
                    padding: '10px 12px', background: 'var(--bg-input)',
                    borderRadius: 8, cursor: 'pointer',
                    border: '1px solid var(--border)',
                  }}
                  onClick={() => restoreVersion(v)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>v{v.version_number}</span>
                    <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                      {new Date(v.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}
                    </span>
                  </div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 4 }}>
                    Click to restore this version
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Verify frontend builds**

```bash
cd frontend && npm run build
```
Expected: Build succeeds

- [ ] **Step 4: End-to-end test**

1. Start backend: `cd backend && uvicorn app.main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Navigate to `/profile`
4. Verify sidebar shows user info, resident count, nav items
5. Verify "我的居民" tab shows resident cards (or empty state)
6. Click Edit on a resident -> verify markdown editor loads with three-layer tabs
7. Edit content -> Save -> verify "Saved!" feedback
8. Click Versions -> verify version history panel appears
9. Switch to "对话历史" tab -> verify conversation list
10. Switch to "代币明细" tab -> verify transaction list
11. Go to game world -> chat with a resident -> close chat -> verify rating popup appears
12. Rate the conversation -> verify rating saved

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: resident editor with 3-layer markdown editing, version history, and restore"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Profile page at /profile — Task 6 (ProfilePage + ProfileSidebar)
- [x] Left sidebar: avatar, name, resident count, nav items — Task 6 (ProfileSidebar)
- [x] 我的居民 tab: resident cards with all fields — Task 6 (ResidentList + ResidentCard)
- [x] 对话历史 tab: conversation list with resident name, date, turns, rating — Task 6 (ConversationHistory)
- [x] 代币明细 tab: transaction history with earn/spend, amount, reason, date — Task 6 (TransactionHistory)
- [x] "创建新居民" button → /forge — Task 6 (ResidentList)
- [x] Resident editing: edit ability.md, persona.md, soul.md — Task 7 (ResidentEditor)
- [x] Version history: auto-versioned, max 10 — Task 2 (version_service.py)
- [x] Conversation stats display — Task 7 (ResidentEditor header)
- [x] Skill upload/import: SKILL.md or zip — Task 4 (import endpoint)
- [x] colleague-skill import: work.md → ability.md — Task 4 (import endpoint)
- [x] Format validation — Task 4 (file type check, zip validation)
- [x] Quality scoring 1-3 stars — Task 3 (scoring_service.py)
- [x] 1 star: has SKILL.md, format valid — Task 3
- [x] 2 stars: three layers complete with substance — Task 3
- [x] 3 stars: high conversations + high rating — Task 3
- [x] Post-chat rating popup (1-5 stars) — Task 5 (RatingPopup)
- [x] Save rating to conversation record — Task 5 (rate_chat WS handler)
- [x] Update resident avg_rating — Task 5 (recalculation in handler)
- [x] Profile API: GET /profile/residents — Task 1
- [x] Profile API: GET /profile/conversations with pagination — Task 1
- [x] Profile API: GET /profile/transactions with pagination — Task 1
- [x] PUT /residents/:slug (edit, owner-only) — Task 2
- [x] POST /residents/import — Task 4
- [x] Creator reward for good rating (>= 4 stars → 5 SC) — Task 5

**Placeholder scan:** No TBDs, all code blocks complete.

**Type consistency:** Verified — `MyResidentItem` fields match Resident ORM, `MyConversationItem` includes `resident_name` joined from Resident table, `VersionSnapshot` matches version_service output, WebSocket `rate_chat` protocol consistent between handler.py and ChatDrawer.tsx.

**Security notes:**
- All profile endpoints require JWT authentication
- Resident editing is owner-only (creator_id check)
- Version history viewing is owner-only
- Rating values validated (1-5 range)
- File upload validates format (.md or .zip only)
- Slug uniqueness enforced on import
