# Skills World MVP — Economy & Social Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the remaining MVP features: daily login rewards, resident search, central plaza bulletin board, heat calculation cron, advanced coin tracking with creator passive income, and multi-player awareness on the map.

**Architecture:** Extends the existing FastAPI backend (Plans 1-3) with new services, routers, and cron tasks. Extends the React + Phaser frontend with new UI components and WebSocket message handlers.

**Tech Stack:** Same as Plan 1 — FastAPI + SQLAlchemy + Alembic (backend), React 18 + Vite + TypeScript + Phaser 3.80 (frontend), PostgreSQL 16, Redis 7.

**Scope:** This is Plan 4 of 4. Plans 1-3 cover:
- Plan 1: Core Loop — map, movement, chat, coins
- Plan 2: Forge — Skill creation pipeline
- Plan 3: Profile & Resident Management — CRUD, import, quality scoring

**Prerequisites from Plans 1-3:**
- All ORM models (`User`, `Resident`, `Conversation`, `Message`, `Transaction`)
- Services: `auth_service`, `chat_service`, `coin_service`, `resident_service`
- Routers: `auth`, `users`, `residents`
- WebSocket `manager` with `broadcast()` and `send()`
- Zustand `gameStore` with `user`, `token`, `updateBalance`
- `TopNav`, `GameScene`, `NpcManager`, `ws.ts`

---

## File Structure

### Backend (new/modified)

```
backend/
├── app/
│   ├── routers/
│   │   └── search.py              # NEW: GET /search?q=...
│   ├── services/
│   │   ├── heat_service.py        # NEW: heat calculation + status transitions
│   │   ├── daily_reward_service.py # NEW: login reward logic
│   │   └── coin_service.py        # MODIFY: add creator_passive_income, skill_creation_reward
│   ├── tasks/
│   │   └── heat_cron.py           # NEW: periodic heat recalculation
│   ├── models/
│   │   └── user.py                # MODIFY: add last_daily_reward_at column
│   └── main.py                    # MODIFY: register search router, startup cron
├── alembic/
│   └── versions/
│       └── xxx_add_search_and_reward_fields.py  # NEW migration
├── tests/
│   ├── test_heat.py               # NEW
│   ├── test_search.py             # NEW
│   └── test_daily_reward.py       # NEW
```

### Frontend (new/modified)

```
frontend/src/
├── components/
│   ├── SearchDropdown.tsx          # NEW: search UI in TopNav
│   ├── BulletinBoard.tsx           # NEW: hot residents + newest
│   ├── CoinNotification.tsx        # NEW: floating coin animation
│   └── TopNav.tsx                  # MODIFY: add search icon + dropdown
├── game/
│   └── GameScene.ts               # MODIFY: render other players, bulletin board zone
├── services/
│   └── ws.ts                      # MODIFY: handle player_moved, position sync, heat updates
├── stores/
│   └── gameStore.ts               # MODIFY: add onlinePlayers, searchResults, dailyRewardClaimed
```

---

## Task 1: Database Migration — Search Index + Daily Reward Tracking

**Files:**
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/resident.py`
- Create: `backend/alembic/versions/xxx_add_search_and_reward_fields.py`

- [ ] **Step 1: Write failing test for daily reward field**

`tests/test_daily_reward.py` (initial — just verifies field exists):
```python
import pytest
from datetime import datetime

@pytest.mark.anyio
async def test_user_has_last_daily_reward_field(db_session, test_user):
    assert hasattr(test_user, "last_daily_reward_at")
    assert test_user.last_daily_reward_at is None
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd backend && pytest tests/test_daily_reward.py -v
```
Expected: FAIL — `last_daily_reward_at` does not exist on User model yet.

- [ ] **Step 3: Add `last_daily_reward_at` to User model**

Modify `app/models/user.py` — add field after `created_at`:
```python
    last_daily_reward_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 4: Add `search_vector` to Resident model**

Modify `app/models/resident.py` — add imports and field:
```python
from sqlalchemy import String, Integer, Float, DateTime, Text, JSON, Index, Column
from sqlalchemy.dialects.postgresql import TSVECTOR

class Resident(Base):
    __tablename__ = "residents"

    # ... existing fields ...

    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    __table_args__ = (
        Index("ix_residents_search_vector", "search_vector", postgresql_using="gin"),
    )
```

- [ ] **Step 5: Create Alembic migration**

```bash
cd backend && alembic revision --autogenerate -m "add search_vector and last_daily_reward_at"
```

Then manually edit the generated migration to add the trigger that keeps `search_vector` up to date:

```python
"""add search_vector and last_daily_reward_at"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

def upgrade() -> None:
    # Add last_daily_reward_at to users
    op.add_column("users", sa.Column("last_daily_reward_at", sa.DateTime(), nullable=True))

    # Add search_vector to residents
    op.add_column("residents", sa.Column("search_vector", TSVECTOR(), nullable=True))
    op.create_index("ix_residents_search_vector", "residents", ["search_vector"], postgresql_using="gin")

    # Populate search_vector for existing rows
    op.execute("""
        UPDATE residents SET search_vector =
            setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(district, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(meta_json->>'role', '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(meta_json->>'impression', '')), 'C') ||
            setweight(to_tsvector('simple', coalesce(
                array_to_string(
                    ARRAY(SELECT jsonb_array_elements_text(
                        coalesce(meta_json->'tags'->'personality', '[]'::jsonb) ||
                        coalesce(meta_json->'tags'->'culture', '[]'::jsonb)
                    )),
                    ' '
                ), ''
            )), 'B')
    """)

    # Create trigger to auto-update search_vector on INSERT/UPDATE
    op.execute("""
        CREATE OR REPLACE FUNCTION residents_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('simple', coalesce(NEW.name, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(NEW.district, '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(NEW.meta_json->>'role', '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(NEW.meta_json->>'impression', '')), 'C') ||
                setweight(to_tsvector('simple', coalesce(
                    array_to_string(
                        ARRAY(SELECT jsonb_array_elements_text(
                            coalesce(NEW.meta_json->'tags'->'personality', '[]'::jsonb) ||
                            coalesce(NEW.meta_json->'tags'->'culture', '[]'::jsonb)
                        )),
                        ' '
                    ), ''
                )), 'B');
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER residents_search_vector_trigger
            BEFORE INSERT OR UPDATE OF name, district, meta_json
            ON residents
            FOR EACH ROW
            EXECUTE FUNCTION residents_search_vector_update();
    """)

def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS residents_search_vector_trigger ON residents")
    op.execute("DROP FUNCTION IF EXISTS residents_search_vector_update()")
    op.drop_index("ix_residents_search_vector", table_name="residents")
    op.drop_column("residents", "search_vector")
    op.drop_column("users", "last_daily_reward_at")
```

- [ ] **Step 6: Run migration**

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 7: Run test**

```bash
cd backend && pytest tests/test_daily_reward.py -v
```
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: add search_vector tsvector index on residents + last_daily_reward_at on users"
```

---

## Task 2: Daily Login Reward Service

**Files:**
- Create: `backend/app/services/daily_reward_service.py`
- Modify: `backend/app/ws/handler.py` (send reward notification on connect)
- Create: `backend/tests/test_daily_reward.py` (extend)

- [ ] **Step 1: Write failing tests**

`tests/test_daily_reward.py`:
```python
import pytest
from datetime import datetime, timedelta
from app.services.daily_reward_service import claim_daily_reward

@pytest.mark.anyio
async def test_user_has_last_daily_reward_field(db_session, test_user):
    assert hasattr(test_user, "last_daily_reward_at")
    assert test_user.last_daily_reward_at is None

@pytest.mark.anyio
async def test_claim_daily_reward_first_time(db_session, test_user):
    """First daily claim should succeed and give 5 SC."""
    initial_balance = test_user.soul_coin_balance
    result = await claim_daily_reward(db_session, test_user.id)
    assert result["claimed"] is True
    assert result["amount"] == 5
    assert result["new_balance"] == initial_balance + 5

@pytest.mark.anyio
async def test_claim_daily_reward_already_claimed_today(db_session, test_user):
    """Second claim same calendar day should be rejected."""
    await claim_daily_reward(db_session, test_user.id)
    result = await claim_daily_reward(db_session, test_user.id)
    assert result["claimed"] is False
    assert result["reason"] == "already_claimed_today"

@pytest.mark.anyio
async def test_claim_daily_reward_new_day(db_session, test_user):
    """Claim should succeed if last claim was yesterday."""
    # Simulate yesterday's claim
    test_user.last_daily_reward_at = datetime.utcnow() - timedelta(days=1)
    await db_session.commit()

    result = await claim_daily_reward(db_session, test_user.id)
    assert result["claimed"] is True
    assert result["amount"] == 5
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_daily_reward.py -v
```
Expected: FAIL — `daily_reward_service` module does not exist.

- [ ] **Step 3: Implement daily reward service**

`app/services/daily_reward_service.py`:
```python
from datetime import datetime, date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.transaction import Transaction

DAILY_REWARD_AMOUNT = 5

async def claim_daily_reward(db: AsyncSession, user_id: str) -> dict:
    """
    Claim daily login reward. Returns dict with:
    - claimed: bool
    - amount: int (if claimed)
    - new_balance: int (if claimed)
    - reason: str (if not claimed)
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"claimed": False, "reason": "user_not_found"}

    today = date.today()

    # Check if already claimed today
    if user.last_daily_reward_at is not None:
        last_claim_date = user.last_daily_reward_at.date()
        if last_claim_date == today:
            return {"claimed": False, "reason": "already_claimed_today"}

    # Grant reward
    user.soul_coin_balance += DAILY_REWARD_AMOUNT
    user.last_daily_reward_at = datetime.utcnow()
    db.add(Transaction(
        user_id=user_id,
        amount=DAILY_REWARD_AMOUNT,
        reason="daily_login_reward"
    ))
    await db.commit()
    await db.refresh(user)

    return {
        "claimed": True,
        "amount": DAILY_REWARD_AMOUNT,
        "new_balance": user.soul_coin_balance,
    }
```

- [ ] **Step 4: Integrate daily reward into WebSocket connect flow**

Modify `app/ws/handler.py` — after `await manager.connect(user_id, ws)`, add the daily reward check:

```python
from app.services.daily_reward_service import claim_daily_reward

async def websocket_handler(ws: WebSocket):
    # ... existing auth + connect code ...

    await manager.connect(user_id, ws)

    # Attempt daily login reward on connect
    async with async_session() as db:
        reward_result = await claim_daily_reward(db, user_id)
        if reward_result["claimed"]:
            await manager.send(user_id, {
                "type": "daily_reward",
                "amount": reward_result["amount"],
                "new_balance": reward_result["new_balance"],
            })

    # ... rest of handler ...
```

- [ ] **Step 5: Run tests**

```bash
cd backend && pytest tests/test_daily_reward.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: daily login reward service — 5 SC per calendar day, triggered on WebSocket connect"
```

---

## Task 3: Resident Search — Backend + Frontend

**Files:**
- Create: `backend/app/routers/search.py`
- Modify: `backend/app/main.py` (register router)
- Create: `backend/tests/test_search.py`
- Create: `frontend/src/components/SearchDropdown.tsx`
- Modify: `frontend/src/components/TopNav.tsx`

- [ ] **Step 1: Write failing backend tests**

`tests/test_search.py`:
```python
import pytest

@pytest.mark.anyio
async def test_search_by_name(client, seeded_db):
    """Search for a resident by name."""
    resp = await client.get("/search?q=伊莎贝拉")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert any(r["name"] == "伊莎贝拉" for r in results)

@pytest.mark.anyio
async def test_search_by_role(client, seeded_db):
    """Search by role from meta_json."""
    resp = await client.get("/search?q=研究员")
    assert resp.status_code == 200
    results = resp.json()
    assert any(r["name"] == "克劳斯" for r in results)

@pytest.mark.anyio
async def test_search_by_district(client, seeded_db):
    """Search by district name."""
    resp = await client.get("/search?q=engineering")
    assert resp.status_code == 200
    results = resp.json()
    assert any(r["district"] == "engineering" for r in results)

@pytest.mark.anyio
async def test_search_empty_query(client):
    """Empty query returns empty list."""
    resp = await client.get("/search?q=")
    assert resp.status_code == 200
    assert resp.json() == []

@pytest.mark.anyio
async def test_search_no_results(client, seeded_db):
    """Non-matching query returns empty list."""
    resp = await client.get("/search?q=xyznonexistent")
    assert resp.status_code == 200
    assert resp.json() == []

@pytest.mark.anyio
async def test_search_limit(client, seeded_db):
    """Results capped at 20."""
    resp = await client.get("/search?q=a&limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) <= 3
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_search.py -v
```
Expected: FAIL — `/search` route does not exist.

- [ ] **Step 3: Implement search router**

`app/routers/search.py`:
```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.resident import Resident
from app.schemas.resident import ResidentListItem

router = APIRouter(prefix="/search", tags=["search"])

@router.get("", response_model=list[ResidentListItem])
async def search_residents(
    q: str = Query("", min_length=0, max_length=200),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Full-text search across resident name, tags, district, and role.
    Uses PostgreSQL tsvector with 'simple' config for CJK support.
    Falls back to ILIKE for single-character queries.
    """
    if not q.strip():
        return []

    q_stripped = q.strip()

    # For short queries (1-2 chars), use ILIKE since tsvector tokenization
    # may not handle very short CJK strings well
    if len(q_stripped) <= 2:
        stmt = (
            select(Resident)
            .where(
                Resident.name.ilike(f"%{q_stripped}%")
                | Resident.district.ilike(f"%{q_stripped}%")
            )
            .order_by(Resident.heat.desc())
            .limit(limit)
        )
    else:
        # Use tsvector full-text search with ts_rank for ordering
        ts_query = func.to_tsquery("simple", " & ".join(q_stripped.split()))
        stmt = (
            select(Resident)
            .where(Resident.search_vector.op("@@")(ts_query))
            .order_by(func.ts_rank(Resident.search_vector, ts_query).desc())
            .limit(limit)
        )

    result = await db.execute(stmt)
    residents = result.scalars().all()

    # If tsvector returned nothing, fall back to ILIKE
    if not residents and len(q_stripped) > 2:
        fallback_stmt = (
            select(Resident)
            .where(
                Resident.name.ilike(f"%{q_stripped}%")
                | Resident.district.ilike(f"%{q_stripped}%")
            )
            .order_by(Resident.heat.desc())
            .limit(limit)
        )
        result = await db.execute(fallback_stmt)
        residents = result.scalars().all()

    return [ResidentListItem.model_validate(r, from_attributes=True) for r in residents]
```

- [ ] **Step 4: Register search router in `main.py`**

Add to `app/main.py`:
```python
from app.routers import auth, users, residents, search

app.include_router(search.router)
```

- [ ] **Step 5: Run backend tests**

```bash
cd backend && pytest tests/test_search.py -v
```
Expected: PASS

- [ ] **Step 6: Create SearchDropdown frontend component**

`frontend/src/components/SearchDropdown.tsx`:
```typescript
import { useState, useRef, useEffect, useCallback } from 'react'
import { bridge } from '../game/phaserBridge'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface SearchResult {
  id: string
  slug: string
  name: string
  district: string
  status: string
  heat: number
  sprite_key: string
  tile_x: number
  tile_y: number
  star_rating: number
  token_cost_per_turn: number
  meta_json: { role?: string; impression?: string }
}

export function SearchDropdown() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Focus input when opened
  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const search = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); return }
    setLoading(true)
    try {
      const resp = await fetch(`${API}/search?q=${encodeURIComponent(q)}&limit=10`)
      if (resp.ok) {
        setResults(await resp.json())
      }
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [])

  const onQueryChange = (value: string) => {
    setQuery(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => search(value), 300)
  }

  const navigateToResident = (r: SearchResult) => {
    // Emit event so Phaser camera pans to resident location
    bridge.emit('camera:pan_to', { x: r.tile_x * 32, y: r.tile_y * 32, slug: r.slug })
    setOpen(false)
    setQuery('')
    setResults([])
  }

  const statusEmoji: Record<string, string> = {
    idle: '\u{1F7E2}',     // green circle
    sleeping: '\u{1F4A4}', // zzz
    chatting: '\u{1F4AC}', // speech bubble
    popular: '\u{1F525}',  // fire
  }

  const starStr = (n: number) => '\u2B50'.repeat(n)

  return (
    <div ref={dropdownRef} style={{ position: 'relative' }}>
      {/* Search icon button */}
      <div
        onClick={() => setOpen(!open)}
        style={{
          cursor: 'pointer', fontSize: 16, padding: '4px 8px',
          borderRadius: 6, background: open ? 'var(--bg-input)' : 'transparent',
          transition: 'background 0.2s',
        }}
        title="Search residents"
      >
        \u{1F50D}
      </div>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: 'absolute', top: 38, right: 0, width: 320,
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 10, boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          zIndex: 30, overflow: 'hidden',
        }}>
          {/* Search input */}
          <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              onKeyDown={(e) => e.stopPropagation()}
              onFocus={() => {
                // Prevent Phaser from capturing keys
                const { useGameStore } = require('../stores/gameStore')
                useGameStore.getState().setInputFocused(true)
              }}
              onBlur={() => {
                const { useGameStore } = require('../stores/gameStore')
                useGameStore.getState().setInputFocused(false)
              }}
              placeholder="Search by name, role, tag, district..."
              style={{
                width: '100%', background: 'var(--bg-input)', border: '1px solid var(--border)',
                color: 'var(--text-primary)', padding: '8px 12px', borderRadius: 'var(--radius)',
                fontSize: 13, outline: 'none',
              }}
            />
          </div>

          {/* Results */}
          <div style={{ maxHeight: 320, overflowY: 'auto' }}>
            {loading && (
              <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
                Searching...
              </div>
            )}

            {!loading && query && results.length === 0 && (
              <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
                No residents found
              </div>
            )}

            {results.map((r) => (
              <div
                key={r.id}
                onClick={() => navigateToResident(r)}
                style={{
                  padding: '10px 12px', cursor: 'pointer', display: 'flex',
                  alignItems: 'center', gap: 10, borderBottom: '1px solid var(--border)',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-input)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                {/* Avatar placeholder */}
                <div style={{
                  width: 36, height: 36, background: 'var(--bg-input)', borderRadius: 8,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 18, imageRendering: 'pixelated' as any,
                }}>
                  \u{1F9D1}\u200D\u{1F4BB}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-primary)' }}>
                      {r.name}
                    </span>
                    <span style={{ fontSize: 10 }}>{starStr(r.star_rating)}</span>
                    <span style={{ fontSize: 11, marginLeft: 'auto' }}>
                      {statusEmoji[r.status] || ''} {r.status}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    {r.meta_json?.role || r.district} · Heat {r.heat}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 7: Integrate SearchDropdown into TopNav**

Modify `frontend/src/components/TopNav.tsx` — add the search component before the coin display:

```typescript
import { useGameStore } from '../stores/gameStore'
import { SearchDropdown } from './SearchDropdown'

export function TopNav() {
  const user = useGameStore((s) => s.user)
  const balance = user?.soul_coin_balance ?? 0

  return (
    <nav style={{
      position: 'fixed', top: 0, left: 0, right: 0, height: 'var(--nav-height)',
      background: 'var(--bg-card)', borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 16px', zIndex: 20,
    }}>
      <span style={{ fontWeight: 700, fontSize: 15 }}>\u{1F3D9}\uFE0F Skills World</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <SearchDropdown />
        <span style={{
          color: 'var(--accent-green)', fontSize: 13,
          background: '#53d76915', padding: '4px 12px', borderRadius: 16,
        }}>\u{1FA99} {balance}</span>
        <div style={{
          width: 30, height: 30, background: 'var(--bg-input)', borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
        }}>\u{1F464}</div>
      </div>
    </nav>
  )
}
```

- [ ] **Step 8: Add `camera:pan_to` handler in GameScene**

Modify `frontend/src/game/GameScene.ts` — in `setupWorld()`, listen for search navigation:

```typescript
// In setupWorld(), after camera setup:
bridge.on('camera:pan_to', (target: { x: number; y: number; slug: string }) => {
  // Smoothly pan camera to target tile position
  this.cameras.main.pan(target.x, target.y, 800, 'Sine.easeInOut')
  // After pan, move player near the target
  this.time.delayedCall(900, () => {
    this.player.setPosition(target.x - 40, target.y)
  })
})
```

- [ ] **Step 9: Commit**

```bash
git add backend/ frontend/
git commit -m "feat: resident search with PostgreSQL full-text search + SearchDropdown UI in TopNav"
```

---

## Task 4: Heat Calculation Cron + Status Transitions

**Files:**
- Create: `backend/app/services/heat_service.py`
- Create: `backend/app/tasks/heat_cron.py`
- Modify: `backend/app/main.py` (register startup cron)
- Create: `backend/tests/test_heat.py`

- [ ] **Step 1: Write failing tests**

`tests/test_heat.py`:
```python
import pytest
from datetime import datetime, timedelta
from app.services.heat_service import recalculate_heat, POPULAR_THRESHOLD, SLEEPING_DAYS

@pytest.mark.anyio
async def test_heat_calculation_from_conversations(db_session, test_resident, make_conversations):
    """Heat should equal number of conversations in the last 7 days."""
    # Create 10 conversations in last 7 days
    await make_conversations(test_resident.id, count=10, days_ago=3)
    # Create 5 conversations older than 7 days (should not count)
    await make_conversations(test_resident.id, count=5, days_ago=10)

    changes = await recalculate_heat(db_session)
    assert test_resident.heat == 10

@pytest.mark.anyio
async def test_status_transitions_to_popular(db_session, test_resident, make_conversations):
    """Resident with heat >= 50 should become popular."""
    await make_conversations(test_resident.id, count=55, days_ago=2)
    changes = await recalculate_heat(db_session)

    assert test_resident.status == "popular"
    assert any(c["slug"] == test_resident.slug and c["new_status"] == "popular" for c in changes)

@pytest.mark.anyio
async def test_status_transitions_to_sleeping(db_session, test_resident):
    """Resident with no conversations in 7 days should become sleeping."""
    test_resident.last_conversation_at = datetime.utcnow() - timedelta(days=8)
    test_resident.status = "idle"
    await db_session.commit()

    changes = await recalculate_heat(db_session)
    assert test_resident.status == "sleeping"
    assert test_resident.heat == 0

@pytest.mark.anyio
async def test_popular_drops_to_idle(db_session, test_resident, make_conversations):
    """Popular resident whose heat drops below threshold should become idle."""
    test_resident.status = "popular"
    # Only 5 recent conversations (below threshold)
    await make_conversations(test_resident.id, count=5, days_ago=2)

    changes = await recalculate_heat(db_session)
    assert test_resident.status == "idle"
    assert test_resident.heat == 5

@pytest.mark.anyio
async def test_chatting_resident_skipped(db_session, test_resident):
    """Residents currently chatting should not have status changed."""
    test_resident.status = "chatting"
    test_resident.last_conversation_at = datetime.utcnow() - timedelta(days=8)
    await db_session.commit()

    changes = await recalculate_heat(db_session)
    assert test_resident.status == "chatting"  # unchanged
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_heat.py -v
```
Expected: FAIL — `heat_service` module does not exist.

- [ ] **Step 3: Implement heat service**

`app/services/heat_service.py`:
```python
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resident import Resident
from app.models.conversation import Conversation

POPULAR_THRESHOLD = 50
SLEEPING_DAYS = 7

async def recalculate_heat(db: AsyncSession) -> list[dict]:
    """
    Recalculate heat for all residents.
    heat = number of conversations in the last 7 days.
    Returns list of status changes for WebSocket broadcast.
    """
    seven_days_ago = datetime.utcnow() - timedelta(days=SLEEPING_DAYS)

    # Count conversations per resident in the last 7 days
    conv_counts_stmt = (
        select(
            Conversation.resident_id,
            func.count(Conversation.id).label("conv_count"),
        )
        .where(Conversation.started_at >= seven_days_ago)
        .group_by(Conversation.resident_id)
    )
    conv_result = await db.execute(conv_counts_stmt)
    heat_map: dict[str, int] = {row.resident_id: row.conv_count for row in conv_result}

    # Load all residents
    all_residents_result = await db.execute(select(Resident))
    all_residents = list(all_residents_result.scalars().all())

    status_changes: list[dict] = []

    for resident in all_residents:
        new_heat = heat_map.get(resident.id, 0)
        old_status = resident.status
        old_heat = resident.heat

        # Update heat
        resident.heat = new_heat

        # Skip status update for residents currently in a conversation
        if resident.status == "chatting":
            continue

        # Determine new status
        new_status = old_status
        if new_heat >= POPULAR_THRESHOLD:
            new_status = "popular"
        elif new_heat == 0:
            # Check if truly inactive (no conversation in 7 days)
            if resident.last_conversation_at is None or resident.last_conversation_at < seven_days_ago:
                new_status = "sleeping"
            else:
                new_status = "idle"
        else:
            new_status = "idle"

        if new_status != old_status:
            resident.status = new_status
            status_changes.append({
                "resident_id": resident.id,
                "slug": resident.slug,
                "old_status": old_status,
                "new_status": new_status,
                "heat": new_heat,
            })

    await db.commit()
    return status_changes
```

- [ ] **Step 4: Create cron task runner**

`app/tasks/heat_cron.py`:
```python
import asyncio
import logging
from app.database import async_session
from app.services.heat_service import recalculate_heat
from app.ws.manager import manager

logger = logging.getLogger(__name__)

HEAT_CRON_INTERVAL_SECONDS = 3600  # 1 hour

async def heat_cron_loop():
    """Background task that recalculates heat every hour."""
    while True:
        try:
            async with async_session() as db:
                changes = await recalculate_heat(db)

            # Broadcast status changes to all connected players
            for change in changes:
                await manager.broadcast({
                    "type": "resident_status",
                    "resident_slug": change["slug"],
                    "status": change["new_status"],
                    "heat": change["heat"],
                })
                logger.info(
                    f"Resident {change['slug']}: {change['old_status']} -> {change['new_status']} "
                    f"(heat={change['heat']})"
                )

            if changes:
                logger.info(f"Heat cron: {len(changes)} status changes broadcast")

        except Exception as e:
            logger.error(f"Heat cron error: {e}")

        await asyncio.sleep(HEAT_CRON_INTERVAL_SECONDS)
```

- [ ] **Step 5: Register cron on app startup**

Modify `app/main.py` — add startup event:

```python
import asyncio
from contextlib import asynccontextmanager
from app.tasks.heat_cron import heat_cron_loop

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background tasks
    task = asyncio.create_task(heat_cron_loop())
    yield
    # Cleanup
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="Skills World API", lifespan=lifespan)
```

- [ ] **Step 6: Run tests**

```bash
cd backend && pytest tests/test_heat.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat: heat calculation cron — hourly recalc, auto status transitions, WebSocket broadcast"
```

---

## Task 5: Central Plaza Bulletin Board

**Files:**
- Create: `backend/app/routers/bulletin.py`
- Modify: `backend/app/main.py` (register router)
- Create: `frontend/src/components/BulletinBoard.tsx`
- Modify: `frontend/src/game/GameScene.ts` (bulletin board zone trigger)

- [ ] **Step 1: Implement bulletin board backend endpoint**

`app/routers/bulletin.py`:
```python
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.schemas.resident import ResidentListItem

router = APIRouter(prefix="/bulletin", tags=["bulletin"])

@router.get("")
async def get_bulletin(db: AsyncSession = Depends(get_db)):
    """
    Central plaza bulletin board data:
    - Top 10 hot residents (by heat)
    - 5 newest residents (by created_at)
    - Recent conversations count (last 24h)
    """
    # Top 10 hot residents
    hot_stmt = select(Resident).order_by(Resident.heat.desc()).limit(10)
    hot_result = await db.execute(hot_stmt)
    hot_residents = [
        ResidentListItem.model_validate(r, from_attributes=True)
        for r in hot_result.scalars().all()
    ]

    # 5 newest residents
    new_stmt = select(Resident).order_by(Resident.created_at.desc()).limit(5)
    new_result = await db.execute(new_stmt)
    new_residents = [
        ResidentListItem.model_validate(r, from_attributes=True)
        for r in new_result.scalars().all()
    ]

    # Recent conversations count (last 24h)
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    count_stmt = select(func.count(Conversation.id)).where(
        Conversation.started_at >= twenty_four_hours_ago
    )
    count_result = await db.execute(count_stmt)
    recent_conv_count = count_result.scalar() or 0

    return {
        "hot_residents": hot_residents,
        "new_residents": new_residents,
        "recent_conversations_24h": recent_conv_count,
    }
```

Register in `app/main.py`:
```python
from app.routers import auth, users, residents, search, bulletin

app.include_router(bulletin.router)
```

- [ ] **Step 2: Create BulletinBoard React component**

`frontend/src/components/BulletinBoard.tsx`:
```typescript
import { useState, useEffect } from 'react'
import { bridge } from '../game/phaserBridge'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface BulletinResident {
  id: string
  slug: string
  name: string
  district: string
  status: string
  heat: number
  sprite_key: string
  tile_x: number
  tile_y: number
  star_rating: number
  token_cost_per_turn: number
  meta_json: { role?: string }
}

interface BulletinData {
  hot_residents: BulletinResident[]
  new_residents: BulletinResident[]
  recent_conversations_24h: number
}

export function BulletinBoard() {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<BulletinData | null>(null)
  const [loading, setLoading] = useState(false)

  // Listen for player entering/exiting bulletin board zone
  useEffect(() => {
    const unsub1 = bridge.on('bulletin:open', () => {
      setOpen(true)
      fetchBulletin()
    })
    const unsub2 = bridge.on('bulletin:close', () => setOpen(false))
    return () => { unsub1(); unsub2() }
  }, [])

  const fetchBulletin = async () => {
    setLoading(true)
    try {
      const resp = await fetch(`${API}/bulletin`)
      if (resp.ok) setData(await resp.json())
    } catch { /* silently fail */ }
    finally { setLoading(false) }
  }

  const navigateToResident = (r: BulletinResident) => {
    bridge.emit('camera:pan_to', { x: r.tile_x * 32, y: r.tile_y * 32, slug: r.slug })
    setOpen(false)
  }

  if (!open) return null

  const statusEmoji: Record<string, string> = {
    idle: '\u{1F7E2}', sleeping: '\u{1F4A4}', chatting: '\u{1F4AC}', popular: '\u{1F525}',
  }

  return (
    <div style={{
      position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
      width: 520, maxHeight: '80vh', overflowY: 'auto', zIndex: 25,
      background: '#18181bf5', border: '2px solid #f59e0b44', borderRadius: 16,
      padding: 0, backdropFilter: 'blur(12px)',
      boxShadow: '0 0 60px rgba(245,158,11,0.15), 0 8px 32px rgba(0,0,0,0.6)',
    }}>
      {/* Header */}
      <div style={{
        padding: '18px 20px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: '#f59e0b10',
      }}>
        <div>
          <div style={{ fontWeight: 800, fontSize: 16, color: '#f59e0b' }}>
            \u{1F4CB} Central Plaza Bulletin Board
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 2 }}>
            {data ? `${data.recent_conversations_24h} conversations in the last 24h` : 'Loading...'}
          </div>
        </div>
        <div
          onClick={() => setOpen(false)}
          style={{ color: 'var(--text-muted)', fontSize: 18, cursor: 'pointer', padding: '4px 8px' }}
        >
          \u2715
        </div>
      </div>

      {loading && (
        <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>Loading...</div>
      )}

      {data && (
        <div style={{ padding: '16px 20px' }}>
          {/* Hot Residents */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: '#f59e0b', marginBottom: 10 }}>
              \u{1F525} Top Residents by Heat
            </div>
            {data.hot_residents.map((r, i) => (
              <div
                key={r.id}
                onClick={() => navigateToResident(r)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                  cursor: 'pointer', borderRadius: 8, marginBottom: 4,
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-input)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <span style={{
                  width: 22, height: 22, borderRadius: '50%', fontSize: 11, fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: i < 3 ? '#f59e0b22' : 'var(--bg-input)',
                  color: i < 3 ? '#f59e0b' : 'var(--text-muted)',
                }}>
                  {i + 1}
                </span>
                <div style={{ flex: 1 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{r.name}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: 11, marginLeft: 6 }}>
                    {r.meta_json?.role || r.district}
                  </span>
                </div>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {statusEmoji[r.status] || ''} Heat {r.heat}
                </span>
              </div>
            ))}
          </div>

          {/* Newest Residents */}
          <div>
            <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--accent-blue)', marginBottom: 10 }}>
              \u{2728} Newest Arrivals
            </div>
            {data.new_residents.map((r) => (
              <div
                key={r.id}
                onClick={() => navigateToResident(r)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                  cursor: 'pointer', borderRadius: 8, marginBottom: 4,
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-input)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{
                  width: 32, height: 32, background: 'var(--bg-input)', borderRadius: 8,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16,
                }}>
                  \u{1F9D1}\u200D\u{1F4BB}
                </div>
                <div style={{ flex: 1 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{r.name}</span>
                  <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                    {r.meta_json?.role || r.district} · {'  \u2B50'.repeat(r.star_rating)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Add BulletinBoard to GamePage**

Modify `frontend/src/pages/GamePage.tsx`:
```typescript
import { BulletinBoard } from '../components/BulletinBoard'

export function GamePage() {
  // ... existing code ...
  return (
    <>
      <TopNav />
      <div ref={containerRef} id="game-container" style={{ /* existing */ }} />
      <NpcTooltip />
      <ChatDrawer />
      <BulletinBoard />
    </>
  )
}
```

- [ ] **Step 4: Add bulletin board zone trigger in GameScene**

Modify `frontend/src/game/GameScene.ts` — in `setupWorld()`, define a bulletin board zone in the central plaza area:

```typescript
// Bulletin board zone — central plaza area (approximate coordinates)
const BULLETIN_ZONE = { x: 74 * 32, y: 48 * 32, width: 4 * 32, height: 4 * 32 }

// Add a visual marker for the bulletin board
const bulletinMarker = this.add.text(
  BULLETIN_ZONE.x + BULLETIN_ZONE.width / 2,
  BULLETIN_ZONE.y - 8,
  '\u{1F4CB} Bulletin Board',
  { font: 'bold 12px system-ui', color: '#f59e0b', backgroundColor: '#18181bee', padding: { x: 6, y: 3 } }
).setOrigin(0.5).setDepth(3)
this.tweens.add({
  targets: bulletinMarker, y: bulletinMarker.y - 3,
  duration: 2000, yoyo: true, repeat: -1, ease: 'Sine.easeInOut'
})
```

Then in the `update()` method, check proximity:

```typescript
// In update(), after NPC proximity check:
const inBulletinZone =
  this.player.x >= BULLETIN_ZONE.x &&
  this.player.x <= BULLETIN_ZONE.x + BULLETIN_ZONE.width &&
  this.player.y >= BULLETIN_ZONE.y &&
  this.player.y <= BULLETIN_ZONE.y + BULLETIN_ZONE.height

if (inBulletinZone && Phaser.Input.Keyboard.JustDown(this.eKey)) {
  bridge.emit('bulletin:open')
}
```

Store `BULLETIN_ZONE` as a class property and `inBulletinZone` state to emit `bulletin:close` when leaving:

```typescript
// Class properties:
private wasInBulletinZone = false

// In update():
if (inBulletinZone && !this.wasInBulletinZone) {
  // Show hint: "Press E to view bulletin board"
  bridge.emit('npc:nearby', {
    name: 'Bulletin Board', slug: '__bulletin__',
    status: 'idle', meta_json: { role: 'Press E to view' },
    tile_x: 0, tile_y: 0, heat: 0, star_rating: 0,
    token_cost_per_turn: 0, sprite_key: '',
  })
}
if (!inBulletinZone && this.wasInBulletinZone) {
  bridge.emit('bulletin:close')
}
this.wasInBulletinZone = inBulletinZone
```

- [ ] **Step 5: Commit**

```bash
git add backend/ frontend/
git commit -m "feat: central plaza bulletin board — top 10 hot residents, newest arrivals, 24h conversation count"
```

---

## Task 6: Advanced Coin Tracking + Notifications

**Files:**
- Modify: `backend/app/services/coin_service.py` (add creator passive income, skill creation reward)
- Modify: `backend/app/ws/handler.py` (send coin notifications to creator)
- Create: `frontend/src/components/CoinNotification.tsx`
- Modify: `frontend/src/pages/GamePage.tsx` (mount CoinNotification)
- Modify: `frontend/src/services/ws.ts` (handle coin_earned, daily_reward)

- [ ] **Step 1: Extend coin service with creator income and skill reward**

Modify `app/services/coin_service.py` — add new functions:

```python
async def reward_creator_passive(db: AsyncSession, creator_id: str, resident_slug: str) -> dict | None:
    """
    Award 1 SC to the resident creator when their resident gets a conversation.
    Returns notification payload if reward was given, None otherwise.
    """
    if creator_id == "system":
        return None  # Don't reward system-created residents

    result = await db.execute(select(User).where(User.id == creator_id))
    user = result.scalar_one_or_none()
    if not user:
        return None

    user.soul_coin_balance += 1
    db.add(Transaction(user_id=creator_id, amount=1, reason=f"creator_passive:{resident_slug}"))
    await db.commit()

    return {
        "type": "coin_earned",
        "amount": 1,
        "reason": "creator_passive",
        "resident_slug": resident_slug,
        "new_balance": user.soul_coin_balance,
    }

async def reward_skill_creation(db: AsyncSession, creator_id: str, resident_slug: str, star_rating: int) -> dict | None:
    """
    Award 50 SC when a resident passes quality check (star_rating >= 2).
    Returns notification payload if reward was given, None otherwise.
    """
    if star_rating < 2:
        return None

    result = await db.execute(select(User).where(User.id == creator_id))
    user = result.scalar_one_or_none()
    if not user:
        return None

    user.soul_coin_balance += 50
    db.add(Transaction(user_id=creator_id, amount=50, reason=f"skill_creation:{resident_slug}"))
    await db.commit()

    return {
        "type": "coin_earned",
        "amount": 50,
        "reason": "skill_creation",
        "resident_slug": resident_slug,
        "new_balance": user.soul_coin_balance,
    }
```

- [ ] **Step 2: Send creator notification via WebSocket on chat**

Modify `app/ws/handler.py` — in the `chat_msg` handler, after the existing creator reward code, replace it with the new function and send a WS notification:

```python
from app.services.coin_service import charge, reward_creator_passive

# Replace the existing reward call in chat_msg handler:
# Old:
#   from app.services.coin_service import reward
#   await reward(db, current_resident.creator_id, 1, f"chat_reward:{current_resident.slug}")
#
# New:
creator_notification = await reward_creator_passive(db, current_resident.creator_id, current_resident.slug)
if creator_notification:
    await manager.send(current_resident.creator_id, creator_notification)
```

- [ ] **Step 3: Create CoinNotification floating animation component**

`frontend/src/components/CoinNotification.tsx`:
```typescript
import { useState, useEffect, useCallback, useRef } from 'react'
import { onWSMessage } from '../services/ws'

interface CoinNotif {
  id: number
  amount: number
  reason: string
  resident_slug?: string
}

let notifId = 0

const REASON_LABELS: Record<string, string> = {
  daily_login_reward: 'Daily Login',
  creator_passive: 'Creator Income',
  skill_creation: 'Skill Creation',
  chat: 'Chat',
  signup_bonus: 'Welcome Bonus',
}

export function CoinNotification() {
  const [notifications, setNotifications] = useState<CoinNotif[]>([])
  const timeoutsRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const addNotification = useCallback((amount: number, reason: string, resident_slug?: string) => {
    const id = ++notifId
    const notif: CoinNotif = { id, amount, reason, resident_slug }
    setNotifications((prev) => [...prev, notif])

    // Auto-remove after 3 seconds
    const timeout = setTimeout(() => {
      setNotifications((prev) => prev.filter((n) => n.id !== id))
      timeoutsRef.current.delete(id)
    }, 3000)
    timeoutsRef.current.set(id, timeout)
  }, [])

  useEffect(() => {
    const unsub = onWSMessage((data) => {
      if (data.type === 'coin_earned' || data.type === 'daily_reward') {
        addNotification(data.amount, data.reason || data.type, data.resident_slug)
      }
      if (data.type === 'coin_update' && data.delta < 0) {
        addNotification(data.delta, data.reason || 'chat')
      }
    })
    return unsub
  }, [addNotification])

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      timeoutsRef.current.forEach((t) => clearTimeout(t))
    }
  }, [])

  if (notifications.length === 0) return null

  return (
    <div style={{
      position: 'fixed', top: 56, left: '50%', transform: 'translateX(-50%)',
      zIndex: 30, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
      pointerEvents: 'none',
    }}>
      {notifications.map((n) => (
        <div
          key={n.id}
          style={{
            padding: '8px 18px', borderRadius: 20,
            fontSize: 14, fontWeight: 700, letterSpacing: 0.5,
            animation: 'coinFloatUp 3s ease-out forwards',
            background: n.amount > 0
              ? 'linear-gradient(135deg, #53d76930, #53d76910)'
              : 'linear-gradient(135deg, #e9456030, #e9456010)',
            color: n.amount > 0 ? '#53d769' : '#e94560',
            border: `1px solid ${n.amount > 0 ? '#53d76933' : '#e9456033'}`,
            backdropFilter: 'blur(8px)',
          }}
        >
          <span style={{ marginRight: 6 }}>\u{1FA99}</span>
          {n.amount > 0 ? '+' : ''}{n.amount} SC
          <span style={{ color: 'var(--text-muted)', fontSize: 11, marginLeft: 8 }}>
            {REASON_LABELS[n.reason] || n.reason}
          </span>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Add CSS animation for coin float**

Append to `frontend/src/styles/global.css`:
```css
@keyframes coinFloatUp {
  0% {
    opacity: 0;
    transform: translateY(20px) scale(0.8);
  }
  15% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
  70% {
    opacity: 1;
    transform: translateY(-10px) scale(1);
  }
  100% {
    opacity: 0;
    transform: translateY(-30px) scale(0.9);
  }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
```

- [ ] **Step 5: Mount CoinNotification in GamePage**

Modify `frontend/src/pages/GamePage.tsx`:
```typescript
import { CoinNotification } from '../components/CoinNotification'

export function GamePage() {
  // ... existing code ...
  return (
    <>
      <TopNav />
      <CoinNotification />
      <div ref={containerRef} id="game-container" style={{ /* existing */ }} />
      <NpcTooltip />
      <ChatDrawer />
      <BulletinBoard />
    </>
  )
}
```

- [ ] **Step 6: Handle daily_reward and coin_earned in ws.ts**

Modify `frontend/src/services/ws.ts` — update the `onmessage` handler:

```typescript
socket.onmessage = (event) => {
  const data = JSON.parse(event.data)

  // Update balance for any coin-related message
  if (data.type === 'coin_update') {
    useGameStore.getState().updateBalance(data.balance)
  }
  if (data.type === 'daily_reward') {
    useGameStore.getState().updateBalance(data.new_balance)
  }
  if (data.type === 'coin_earned') {
    useGameStore.getState().updateBalance(data.new_balance)
  }

  // Forward all messages to listeners
  wsListeners.forEach((cb) => cb(data))
}
```

- [ ] **Step 7: Commit**

```bash
git add backend/ frontend/
git commit -m "feat: advanced coin tracking — creator passive income, skill creation reward, floating coin notifications"
```

---

## Task 7: Multi-Player Awareness (Position Sync via WebSocket)

**Files:**
- Modify: `backend/app/ws/handler.py` (handle `move` messages, broadcast `player_moved`)
- Modify: `backend/app/ws/manager.py` (track player positions)
- Modify: `frontend/src/game/GameScene.ts` (render other players)
- Modify: `frontend/src/services/ws.ts` (send position updates, receive `player_moved`)
- Modify: `frontend/src/stores/gameStore.ts` (add online players state)

- [ ] **Step 1: Extend WebSocket manager with player position tracking**

Modify `app/ws/manager.py`:
```python
import json
import time
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}       # user_id -> ws
        self.positions: dict[str, dict] = {}          # user_id -> {x, y, direction, name}
        self.chatting: dict[str, str] = {}            # resident_id -> user_id (lock)

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)
        self.positions.pop(user_id, None)
        # Release any chatting locks held by this user
        to_remove = [rid for rid, uid in self.chatting.items() if uid == user_id]
        for rid in to_remove:
            del self.chatting[rid]

    def update_position(self, user_id: str, x: float, y: float, direction: str, name: str):
        self.positions[user_id] = {
            "x": x, "y": y, "direction": direction, "name": name
        }

    def get_online_players(self, exclude: str | None = None) -> list[dict]:
        return [
            {"player_id": uid, **pos}
            for uid, pos in self.positions.items()
            if uid != exclude
        ]

    def lock_resident(self, resident_id: str, user_id: str) -> bool:
        """Attempt to lock a resident for chatting. Returns False if already locked."""
        if resident_id in self.chatting:
            return False
        self.chatting[resident_id] = user_id
        return True

    def unlock_resident(self, resident_id: str):
        self.chatting.pop(resident_id, None)

    async def send(self, user_id: str, data: dict):
        ws = self.active.get(user_id)
        if ws:
            await ws.send_json(data)

    async def broadcast(self, data: dict, exclude: str | None = None):
        for uid, ws in self.active.items():
            if uid != exclude:
                try:
                    await ws.send_json(data)
                except Exception:
                    pass

manager = ConnectionManager()
```

- [ ] **Step 2: Handle `move` messages in WebSocket handler**

Modify `app/ws/handler.py` — add `move` case in the message loop, and update the `start_chat` flow to use locking:

```python
# In the message loop, add before the existing msg_type checks:

if msg_type == "move":
    x = data.get("x", 0)
    y = data.get("y", 0)
    direction = data.get("direction", "down")
    # Get user name for display
    from app.models.user import User
    result = await db.execute(select(User).where(User.id == user_id))
    user_record = result.scalar_one_or_none()
    name = user_record.name if user_record else "?"

    manager.update_position(user_id, x, y, direction, name)
    await manager.broadcast(
        {"type": "player_moved", "player_id": user_id, "x": x, "y": y,
         "direction": direction, "name": name},
        exclude=user_id,
    )

# Update start_chat to use locking:
elif msg_type == "start_chat":
    slug = data["resident_slug"]
    result = await db.execute(select(Resident).where(Resident.slug == slug))
    resident = result.scalar_one_or_none()
    if not resident:
        await manager.send(user_id, {"type": "error", "message": "Resident not found"})
        continue

    # Check lock (another player chatting)
    if not manager.lock_resident(resident.id, user_id):
        await manager.send(user_id, {"type": "error", "message": "Resident is busy with another player"})
        continue

    if resident.status == "sleeping":
        resident.status = "idle"

    # ... rest of start_chat logic ...

# Update end_chat to release lock:
elif msg_type == "end_chat" and current_conversation and current_resident:
    # ... existing end_chat logic ...
    manager.unlock_resident(current_resident.id)
    # ... rest of cleanup ...
```

Also update the WebSocket disconnect handler:

```python
except WebSocketDisconnect:
    if current_conversation and current_resident:
        manager.unlock_resident(current_resident.id)
        async with async_session() as db:
            result = await db.execute(select(Resident).where(Resident.id == current_resident.id))
            r = result.scalar_one_or_none()
            if r:
                r.status = "popular" if r.heat >= 50 else "idle"
                await db.commit()
        # Broadcast player left
        await manager.broadcast(
            {"type": "player_left", "player_id": user_id},
            exclude=user_id,
        )
    manager.disconnect(user_id)
```

- [ ] **Step 3: Send initial online players list on connect**

In `app/ws/handler.py`, after the daily reward check, send the current online players:

```python
# Send existing online players to new connection
online_players = manager.get_online_players(exclude=user_id)
if online_players:
    await manager.send(user_id, {
        "type": "online_players",
        "players": online_players,
    })

# Notify others about new player
await manager.broadcast(
    {"type": "player_joined", "player_id": user_id},
    exclude=user_id,
)
```

- [ ] **Step 4: Update gameStore with online players state**

Modify `frontend/src/stores/gameStore.ts` — add online players tracking:

```typescript
interface OnlinePlayer {
  player_id: string
  name: string
  x: number
  y: number
  direction: string
}

interface GameState {
  // ... existing fields ...
  onlinePlayers: Map<string, OnlinePlayer>

  // ... existing actions ...
  setOnlinePlayer: (p: OnlinePlayer) => void
  removeOnlinePlayer: (id: string) => void
  setOnlinePlayers: (players: OnlinePlayer[]) => void
}

export const useGameStore = create<GameState>((set) => ({
  // ... existing state ...
  onlinePlayers: new Map(),

  // ... existing actions ...
  setOnlinePlayer: (p) => set((s) => {
    const next = new Map(s.onlinePlayers)
    next.set(p.player_id, p)
    return { onlinePlayers: next }
  }),
  removeOnlinePlayer: (id) => set((s) => {
    const next = new Map(s.onlinePlayers)
    next.delete(id)
    return { onlinePlayers: next }
  }),
  setOnlinePlayers: (players) => set(() => {
    const map = new Map<string, OnlinePlayer>()
    players.forEach((p) => map.set(p.player_id, p))
    return { onlinePlayers: map }
  }),
}))
```

- [ ] **Step 5: Send position updates from frontend**

Modify `frontend/src/services/ws.ts` — add position sending + handle new message types:

```typescript
let lastSentPosition = { x: 0, y: 0 }
const POSITION_SEND_THRESHOLD = 4  // Only send if moved > 4px

export function sendPosition(x: number, y: number, direction: string) {
  const dx = x - lastSentPosition.x
  const dy = y - lastSentPosition.y
  if (Math.abs(dx) < POSITION_SEND_THRESHOLD && Math.abs(dy) < POSITION_SEND_THRESHOLD) return
  lastSentPosition = { x, y }
  sendWS({ type: 'move', x, y, direction })
}

// In the socket.onmessage handler, add:
if (data.type === 'player_moved') {
  useGameStore.getState().setOnlinePlayer(data)
}
if (data.type === 'player_left') {
  useGameStore.getState().removeOnlinePlayer(data.player_id)
}
if (data.type === 'online_players') {
  useGameStore.getState().setOnlinePlayers(data.players)
}
```

- [ ] **Step 6: Render other players in GameScene**

Modify `frontend/src/game/GameScene.ts` — add other player sprites:

```typescript
import { sendPosition } from '../services/ws'

// Class properties:
private otherPlayers: Map<string, { sprite: Phaser.Physics.Arcade.Sprite; label: Phaser.GameObjects.Text }> = new Map()

// In update(), after movement handling and before NPC proximity:

// Send position to server
const dir = l ? 'left' : r ? 'right' : u ? 'up' : d ? 'down' : 'down'
sendPosition(this.player.x, this.player.y, dir)

// Sync other players
const onlinePlayers = useGameStore.getState().onlinePlayers
const currentIds = new Set(onlinePlayers.keys())

// Remove players who left
for (const [id, { sprite, label }] of this.otherPlayers) {
  if (!currentIds.has(id)) {
    sprite.destroy()
    label.destroy()
    this.otherPlayers.delete(id)
  }
}

// Update or create other player sprites
for (const [id, data] of onlinePlayers) {
  const existing = this.otherPlayers.get(id)
  if (existing) {
    // Smooth interpolation to target position
    const lerpFactor = 0.15
    existing.sprite.x += (data.x - existing.sprite.x) * lerpFactor
    existing.sprite.y += (data.y - existing.sprite.y) * lerpFactor
    existing.label.setPosition(existing.sprite.x, existing.sprite.y - 32)

    // Play walk animation if moving
    const dx = Math.abs(data.x - existing.sprite.x)
    const dy = Math.abs(data.y - existing.sprite.y)
    if (dx > 2 || dy > 2) {
      existing.sprite.anims.play(`player-${data.direction}-walk`, true)
    } else {
      existing.sprite.anims.stop()
    }
  } else {
    // Create new player sprite
    const sprite = this.physics.add.sprite(data.x, data.y, 'player_atlas', 'down')
      .setSize(24, 24).setOffset(4, 8).setDepth(1).setAlpha(0.8)
    sprite.displayWidth = 36; sprite.scaleY = sprite.scaleX
    // Tint slightly to distinguish from local player
    sprite.setTint(0xaaccff)

    const label = this.add.text(data.x, data.y - 32, data.name || '?', {
      font: 'bold 11px system-ui', color: '#aaccff',
      backgroundColor: '#18181bcc', padding: { x: 4, y: 1 },
    }).setOrigin(0.5).setDepth(3)

    this.otherPlayers.set(id, { sprite, label })
  }
}
```

- [ ] **Step 7: Verify multi-player flow**

1. Open two browser tabs, both logged in as different users
2. Move in tab 1 — verify avatar appears in tab 2
3. Have tab 1 start chatting with a resident — verify tab 2 sees resident status change to chatting
4. Tab 2 tries to chat with same resident — verify error "Resident is busy"
5. Tab 1 ends chat — verify tab 2 sees resident status restore

- [ ] **Step 8: Commit**

```bash
git add backend/ frontend/
git commit -m "feat: multi-player awareness — position sync via WebSocket, other player rendering, resident chat locking"
```

---

## Self-Review Checklist

**Spec coverage (Plan 4 features):**
- [x] Daily login reward (5 SC/day) — Task 2 (`daily_reward_service.py`)
- [x] Resident search (name, tags, district) — Task 3 (`search.py` router + `SearchDropdown.tsx`)
- [x] PostgreSQL full-text search (tsvector) — Task 1 (migration) + Task 3 (router)
- [x] Search UI in TopNav — Task 3 (`SearchDropdown.tsx` + `TopNav.tsx`)
- [x] Central plaza bulletin board — Task 5 (`bulletin.py` + `BulletinBoard.tsx`)
- [x] Top 10 hot + 5 newest + conversation count — Task 5 (`/bulletin` endpoint)
- [x] Heat calculation cron (hourly) — Task 4 (`heat_service.py` + `heat_cron.py`)
- [x] Status transitions (popular >= 50, sleeping = 7d no conv) — Task 4 (`recalculate_heat`)
- [x] WebSocket broadcast of status changes — Task 4 (`heat_cron_loop`)
- [x] Creator passive income (1 SC per conversation) — Task 6 (`reward_creator_passive`)
- [x] Skill creation reward (50 SC for >= 2 star) — Task 6 (`reward_skill_creation`)
- [x] Coin animations/notifications — Task 6 (`CoinNotification.tsx`)
- [x] Multi-player avatar rendering — Task 7 (other player sprites in GameScene)
- [x] Position sync via WebSocket — Task 7 (`move` handler + `sendPosition`)
- [x] Resident chat locking (one player at a time) — Task 7 (`lock_resident`/`unlock_resident`)

**Design doc alignment:**
- [x] Economy section: daily login 5 SC, creator passive 1 SC, skill creation 50 SC
- [x] B3: PostgreSQL full-text search with tsvector
- [x] B4: WebSocket protocol extended with `move`, `player_moved`, `player_left`, `online_players`
- [x] C1: Multi-player awareness — see other avatars, no player-to-player chat, single-player lock on residents

**Placeholder scan:** No TBDs. All code blocks are complete.

**Type consistency:**
- `SearchResult` fields match `ResidentListItem` schema
- `BulletinResident` fields match `ResidentListItem` schema
- `OnlinePlayer` interface matches `player_moved` WebSocket payload
- `CoinNotif` handles both `coin_earned` and `daily_reward` message types
- Heat cron broadcast matches existing `resident_status` message format

**Test coverage:**
- `test_daily_reward.py`: 4 tests (first claim, double claim, next day claim, field existence)
- `test_search.py`: 6 tests (by name, by role, by district, empty query, no results, limit)
- `test_heat.py`: 5 tests (calculation, popular transition, sleeping transition, popular-to-idle, chatting skip)

**Dependencies between tasks:**
```
Task 1 (DB migration) ─┬─→ Task 2 (daily reward)
                       ├─→ Task 3 (search)
                       └─→ Task 4 (heat cron)
Task 4 ───────────────────→ Task 5 (bulletin board, uses heat data)
Task 2 + Task 4 ─────────→ Task 6 (coin notifications)
Tasks 1-6 ────────────────→ Task 7 (multi-player, extends ws handler)
```
