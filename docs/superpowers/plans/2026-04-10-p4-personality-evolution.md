# P4: Dynamic Personality Evolution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make resident personalities evolve over time — SBTI dimensions drift gradually through daily interactions and shift dramatically in response to critical events, with full history tracking and three-layer text synchronization.

**Architecture:** Two evolution modes: Drift (slow, triggered every 15-20 new event memories, adjusts 1-2 dimensions ±1) and Shift (fast, triggered by importance≥0.9 events, adjusts 2-3 dimensions ±2). A PersonalityGuard enforces rate limits. Changes are persisted in a personality_history table and trigger persona_md/soul_md text updates via LLM. The evolution system hooks into the existing MemoryService and AgentLoop.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Anthropic SDK (LLM evaluation), SBTI match_type() for type migration

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/app/models/personality_history.py` | PersonalityHistory ORM model |
| Create | `backend/app/personality/__init__.py` | Package init |
| Create | `backend/app/personality/guard.py` | PersonalityGuard — rate limits and constraint enforcement |
| Create | `backend/app/personality/prompts.py` | LLM prompt templates for drift/shift evaluation and text sync |
| Create | `backend/app/personality/evolution.py` | EvolutionService — core drift/shift logic |
| Create | `backend/tests/test_personality_history_model.py` | ORM model tests |
| Create | `backend/tests/test_personality_guard.py` | Guard constraint tests |
| Create | `backend/tests/test_personality_evolution.py` | Service tests with mocked LLM |
| Create | `backend/tests/test_evolution_integration.py` | Integration with MemoryService |
| Modify | `backend/app/main.py` | Import personality_history model for table creation |
| Modify | `backend/app/memory/service.py` | Trigger drift/shift checks after memory creation |
| Modify | `backend/app/ws/handler.py` | Broadcast resident_type_changed WS event |
| Modify | `frontend/src/components/profile/ResidentCard.tsx` | Flash animation on type change |
| Create | `backend/alembic/versions/006_add_personality_history.py` | Alembic migration |

---

### Task 1: PersonalityHistory ORM Model

**Files:**
- Create: `backend/app/models/personality_history.py`
- Create: `backend/tests/test_personality_history_model.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_personality_history_model.py`:

```python
import pytest
from datetime import datetime, UTC
from sqlalchemy import select
from app.models.personality_history import PersonalityHistory
from app.models.resident import Resident


@pytest.fixture
async def evolution_resident(db_session):
    r = Resident(
        id="evo-test-res",
        slug="evo-test-res",
        name="EvoResident",
        district="engineering",
        status="idle",
        ability_md="Can code",
        persona_md="Friendly",
        soul_md="Curious",
        meta_json={"sbti": {
            "type": "CTRL",
            "type_name": "拿捏者",
            "dimensions": {
                "S1": "H", "S2": "H", "S3": "H",
                "E1": "H", "E2": "M", "E3": "H",
                "A1": "M", "A2": "H", "A3": "H",
                "Ac1": "H", "Ac2": "H", "Ac3": "H",
                "So1": "M", "So2": "H", "So3": "M",
            },
        }},
    )
    db_session.add(r)
    await db_session.commit()
    return r


@pytest.mark.anyio
async def test_create_drift_history(db_session, evolution_resident):
    entry = PersonalityHistory(
        resident_id=evolution_resident.id,
        trigger_type="drift",
        changes_json={"So1": {"from": "M", "to": "H"}},
        old_type="CTRL",
        new_type="CTRL",
        reason="Consistent social engagement over 15 memories",
    )
    db_session.add(entry)
    await db_session.commit()

    result = await db_session.execute(
        select(PersonalityHistory).where(PersonalityHistory.resident_id == evolution_resident.id)
    )
    saved = result.scalar_one()
    assert saved.trigger_type == "drift"
    assert saved.changes_json["So1"]["from"] == "M"
    assert saved.changes_json["So1"]["to"] == "H"
    assert saved.old_type == "CTRL"
    assert saved.new_type == "CTRL"
    assert saved.reason is not None
    assert saved.id is not None
    assert saved.created_at is not None


@pytest.mark.anyio
async def test_create_shift_history_with_type_migration(db_session, evolution_resident):
    entry = PersonalityHistory(
        resident_id=evolution_resident.id,
        trigger_type="shift",
        trigger_memory_id="some-memory-id",
        changes_json={
            "E1": {"from": "H", "to": "L"},
            "E2": {"from": "M", "to": "L"},
            "So1": {"from": "M", "to": "L"},
        },
        old_type="CTRL",
        new_type="THIN-K",
        reason="Severe trust betrayal event triggered deep emotional withdrawal",
    )
    db_session.add(entry)
    await db_session.commit()

    result = await db_session.execute(
        select(PersonalityHistory).where(
            PersonalityHistory.resident_id == evolution_resident.id,
            PersonalityHistory.trigger_type == "shift",
        )
    )
    saved = result.scalar_one()
    assert saved.trigger_memory_id == "some-memory-id"
    assert saved.new_type == "THIN-K"
    assert len(saved.changes_json) == 3


@pytest.mark.anyio
async def test_nullable_trigger_memory_id(db_session, evolution_resident):
    """Drift entries have no trigger_memory_id."""
    entry = PersonalityHistory(
        resident_id=evolution_resident.id,
        trigger_type="drift",
        changes_json={"A1": {"from": "M", "to": "H"}},
        old_type="GOGO",
        new_type="GOGO",
        reason="Accumulated optimistic interactions",
    )
    db_session.add(entry)
    await db_session.commit()

    result = await db_session.execute(
        select(PersonalityHistory).where(PersonalityHistory.id == entry.id)
    )
    saved = result.scalar_one()
    assert saved.trigger_memory_id is None


@pytest.mark.anyio
async def test_multiple_history_entries_ordered(db_session, evolution_resident):
    """Multiple history entries should be retrievable in created_at order."""
    for i, dim in enumerate(["S1", "E2", "So1"]):
        entry = PersonalityHistory(
            resident_id=evolution_resident.id,
            trigger_type="drift",
            changes_json={dim: {"from": "M", "to": "H"}},
            old_type="CTRL",
            new_type="CTRL",
            reason=f"Change {i}",
        )
        db_session.add(entry)
    await db_session.commit()

    result = await db_session.execute(
        select(PersonalityHistory)
        .where(PersonalityHistory.resident_id == evolution_resident.id)
        .order_by(PersonalityHistory.created_at.asc())
    )
    entries = result.scalars().all()
    assert len(entries) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_personality_history_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.personality_history'`

- [ ] **Step 3: Create the PersonalityHistory model**

Create `backend/app/models/personality_history.py`:

```python
import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PersonalityHistory(Base):
    __tablename__ = "personality_history"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    resident_id: Mapped[str] = mapped_column(
        String, ForeignKey("residents.id"), index=True, nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(
        String(10), nullable=False  # "drift" or "shift"
    )
    # FK to memories.id — nullable because drift is not triggered by a single memory
    trigger_memory_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("memories.id"), nullable=True
    )
    # {"So1": {"from": "L", "to": "M"}, "E2": {"from": "M", "to": "H"}}
    changes_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    old_type: Mapped[str] = mapped_column(String(20), nullable=False)
    new_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_personality_history_resident_created", "resident_id", "created_at"),
        Index("ix_personality_history_trigger_type", "resident_id", "trigger_type"),
    )
```

- [ ] **Step 4: Register the model in main.py**

In `backend/app/main.py`, in the lifespan function after the existing model imports, add:

```python
    import app.models.personality_history  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_personality_history_model.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/models/personality_history.py backend/tests/test_personality_history_model.py backend/app/main.py
git commit -m "feat(personality): add PersonalityHistory ORM model for evolution audit trail"
```

---

### Task 2: PersonalityGuard

**Files:**
- Create: `backend/app/personality/__init__.py`
- Create: `backend/app/personality/guard.py`
- Create: `backend/tests/test_personality_guard.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_personality_guard.py`:

```python
import pytest
from datetime import datetime, UTC, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from app.personality.guard import PersonalityGuard
from app.models.personality_history import PersonalityHistory
from app.models.resident import Resident
from app.models.memory import Memory


@pytest.fixture
async def guard_resident(db_session):
    r = Resident(
        id="guard-test-res",
        slug="guard-test-res",
        name="GuardResident",
        district="engineering",
        status="idle",
        ability_md="Test",
        persona_md="Test",
        soul_md="Test",
        meta_json={"sbti": {
            "type": "CTRL",
            "type_name": "拿捏者",
            "dimensions": {
                "S1": "H", "S2": "H", "S3": "H",
                "E1": "H", "E2": "M", "E3": "H",
                "A1": "M", "A2": "H", "A3": "H",
                "Ac1": "H", "Ac2": "H", "Ac3": "H",
                "So1": "M", "So2": "H", "So3": "M",
            },
        }},
    )
    db_session.add(r)
    await db_session.commit()
    return r


# ── can_drift tests ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_can_drift_true_when_no_history(db_session, guard_resident):
    """No history → drift is allowed."""
    guard = PersonalityGuard()
    result = await guard.can_drift(guard_resident.id, db_session)
    assert result is True


@pytest.mark.anyio
async def test_can_drift_false_when_recent_drift(db_session, guard_resident):
    """If there was a drift in the last 14 memories, deny."""
    # Seed 10 event memories (below MIN_DRIFT_INTERVAL=15)
    for i in range(10):
        mem = Memory(
            resident_id=guard_resident.id,
            type="event",
            content=f"Event {i}",
            importance=0.5,
            source="chat_player",
        )
        db_session.add(mem)

    # Add a drift history entry dated now
    history = PersonalityHistory(
        resident_id=guard_resident.id,
        trigger_type="drift",
        changes_json={"S1": {"from": "M", "to": "H"}},
        old_type="CTRL",
        new_type="CTRL",
        reason="Previous drift",
        created_at=datetime.now(UTC),
    )
    db_session.add(history)
    await db_session.commit()

    guard = PersonalityGuard()
    result = await guard.can_drift(guard_resident.id, db_session)
    assert result is False


@pytest.mark.anyio
async def test_can_drift_true_when_enough_memories_since_last_drift(db_session, guard_resident):
    """If 15+ event memories since last drift, allow."""
    # Set drift history 1 day ago
    history = PersonalityHistory(
        resident_id=guard_resident.id,
        trigger_type="drift",
        changes_json={"S1": {"from": "M", "to": "H"}},
        old_type="CTRL",
        new_type="CTRL",
        reason="Old drift",
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(history)
    await db_session.commit()

    # Add 15 event memories after the drift history
    for i in range(15):
        mem = Memory(
            resident_id=guard_resident.id,
            type="event",
            content=f"Post-drift event {i}",
            importance=0.5,
            source="chat_player",
        )
        db_session.add(mem)
    await db_session.commit()

    guard = PersonalityGuard()
    result = await guard.can_drift(guard_resident.id, db_session)
    assert result is True


# ── can_shift tests ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_can_shift_true_when_no_history(db_session, guard_resident):
    guard = PersonalityGuard()
    result = await guard.can_shift(guard_resident.id, db_session)
    assert result is True


@pytest.mark.anyio
async def test_can_shift_false_within_cooldown(db_session, guard_resident):
    """Shift within 24h cooldown → denied."""
    history = PersonalityHistory(
        resident_id=guard_resident.id,
        trigger_type="shift",
        changes_json={"E1": {"from": "H", "to": "L"}},
        old_type="CTRL",
        new_type="THIN-K",
        reason="Recent shift",
        created_at=datetime.now(UTC) - timedelta(hours=12),  # 12h ago, within 24h
    )
    db_session.add(history)
    await db_session.commit()

    guard = PersonalityGuard()
    result = await guard.can_shift(guard_resident.id, db_session)
    assert result is False


@pytest.mark.anyio
async def test_can_shift_true_after_cooldown(db_session, guard_resident):
    """Shift 25h ago → cooldown expired, allowed."""
    history = PersonalityHistory(
        resident_id=guard_resident.id,
        trigger_type="shift",
        changes_json={"E1": {"from": "H", "to": "L"}},
        old_type="CTRL",
        new_type="THIN-K",
        reason="Old shift",
        created_at=datetime.now(UTC) - timedelta(hours=25),
    )
    db_session.add(history)
    await db_session.commit()

    guard = PersonalityGuard()
    result = await guard.can_shift(guard_resident.id, db_session)
    assert result is True


# ── validate_drift tests ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_validate_drift_clamps_to_max_dimensions(db_session, guard_resident):
    """Drift with 4 dimensions → clamped to MAX_DRIFT_PER_CYCLE=2."""
    guard = PersonalityGuard()
    changes = {
        "S1": {"from": "M", "to": "H"},
        "E1": {"from": "H", "to": "M"},
        "A1": {"from": "M", "to": "H"},
        "So1": {"from": "L", "to": "M"},
    }
    clamped = await guard.validate_drift(changes, guard_resident.id, db_session)
    assert len(clamped) <= 2


@pytest.mark.anyio
async def test_validate_drift_rejects_L_to_H_jump(db_session, guard_resident):
    """Drift cannot jump L→H (step=1 only)."""
    guard = PersonalityGuard()
    changes = {
        "S1": {"from": "L", "to": "H"},  # invalid: 2-step jump
        "E2": {"from": "M", "to": "H"},  # valid: 1-step
    }
    clamped = await guard.validate_drift(changes, guard_resident.id, db_session)
    # L→H change should be removed; E2 change should remain
    assert "S1" not in clamped
    assert "E2" in clamped


@pytest.mark.anyio
async def test_validate_shift_clamps_to_max_dimensions(db_session, guard_resident):
    """Shift with 5 dimensions → clamped to MAX_SHIFT_PER_EVENT=3."""
    guard = PersonalityGuard()
    changes = {
        "S1": {"from": "H", "to": "L"},
        "E1": {"from": "H", "to": "L"},
        "A1": {"from": "M", "to": "H"},
        "So1": {"from": "M", "to": "L"},
        "Ac1": {"from": "H", "to": "M"},
    }
    clamped = await guard.validate_shift(changes, guard_resident.id, db_session)
    assert len(clamped) <= 3


@pytest.mark.anyio
async def test_validate_shift_allows_L_to_H(db_session, guard_resident):
    """Shift CAN jump L→H (step=2 allowed)."""
    guard = PersonalityGuard()
    changes = {"E1": {"from": "L", "to": "H"}}
    clamped = await guard.validate_shift(changes, guard_resident.id, db_session)
    assert "E1" in clamped
    assert clamped["E1"]["to"] == "H"


# ── check_monthly_budget tests ────────────────────────────────────────────


@pytest.mark.anyio
async def test_check_monthly_budget_full_at_start(db_session, guard_resident):
    guard = PersonalityGuard()
    remaining = await guard.check_monthly_budget(guard_resident.id, db_session)
    assert remaining == PersonalityGuard.TOTAL_MONTHLY_CHANGE


@pytest.mark.anyio
async def test_check_monthly_budget_decreases_with_changes(db_session, guard_resident):
    # Add a drift that changed 2 dimensions
    history = PersonalityHistory(
        resident_id=guard_resident.id,
        trigger_type="drift",
        changes_json={
            "S1": {"from": "M", "to": "H"},
            "E2": {"from": "H", "to": "M"},
        },
        old_type="CTRL",
        new_type="CTRL",
        reason="Test drift",
        created_at=datetime.now(UTC),
    )
    db_session.add(history)
    await db_session.commit()

    guard = PersonalityGuard()
    remaining = await guard.check_monthly_budget(guard_resident.id, db_session)
    # Each dimension change counts as 1 toward the budget
    assert remaining == PersonalityGuard.TOTAL_MONTHLY_CHANGE - 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_personality_guard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.personality'`

- [ ] **Step 3: Create the package init and guard module**

Create `backend/app/personality/__init__.py`:

```python
```

Create `backend/app/personality/guard.py`:

```python
import logging
from datetime import datetime, UTC, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.personality_history import PersonalityHistory
from app.models.memory import Memory

logger = logging.getLogger(__name__)

# L/M/H ordering for step validation
_LEVEL_ORDER = {"L": 0, "M": 1, "H": 2}


def _step_distance(frm: str, to: str) -> int:
    """Absolute step distance between two L/M/H levels."""
    return abs(_LEVEL_ORDER.get(to, 1) - _LEVEL_ORDER.get(frm, 1))


class PersonalityGuard:
    """Enforces rate limits and validity constraints on personality evolution.

    All validate_* methods return a (possibly clamped/filtered) subset of
    the proposed changes dict. They never raise — callers get fewer changes,
    never an exception.
    """

    MAX_DRIFT_PER_CYCLE: int = 2
    MAX_SHIFT_PER_EVENT: int = 3
    DRIFT_STEP: int = 1        # max single-step distance for drift
    SHIFT_STEP: int = 2        # max single-step distance for shift (L→H allowed)
    MIN_DRIFT_INTERVAL: int = 15  # event memories required since last drift
    SHIFT_COOLDOWN_HOURS: int = 24
    TOTAL_MONTHLY_CHANGE: int = 8  # sum of all dimension changes per calendar month

    async def can_drift(self, resident_id: str, db: AsyncSession) -> bool:
        """Return True if enough event memories have accumulated since last drift."""
        # Find timestamp of most recent drift
        stmt = (
            select(PersonalityHistory.created_at)
            .where(
                PersonalityHistory.resident_id == resident_id,
                PersonalityHistory.trigger_type == "drift",
            )
            .order_by(PersonalityHistory.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        last_drift_at = result.scalar_one_or_none()

        # Count event memories since last drift (or all-time if no drift yet)
        count_stmt = select(func.count()).select_from(Memory).where(
            Memory.resident_id == resident_id,
            Memory.type == "event",
        )
        if last_drift_at is not None:
            count_stmt = count_stmt.where(Memory.created_at > last_drift_at)

        result = await db.execute(count_stmt)
        count = result.scalar_one()
        return count >= self.MIN_DRIFT_INTERVAL

    async def can_shift(self, resident_id: str, db: AsyncSession) -> bool:
        """Return True if 24h cooldown has elapsed since last shift."""
        stmt = (
            select(PersonalityHistory.created_at)
            .where(
                PersonalityHistory.resident_id == resident_id,
                PersonalityHistory.trigger_type == "shift",
            )
            .order_by(PersonalityHistory.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        last_shift_at = result.scalar_one_or_none()

        if last_shift_at is None:
            return True

        elapsed = datetime.now(UTC) - last_shift_at
        return elapsed >= timedelta(hours=self.SHIFT_COOLDOWN_HOURS)

    async def validate_drift(
        self,
        changes: dict[str, dict],
        resident_id: str,
        db: AsyncSession,
    ) -> dict[str, dict]:
        """Validate and clamp drift changes.

        Rules:
        - Remove any change where step distance > DRIFT_STEP (no L→H)
        - Keep at most MAX_DRIFT_PER_CYCLE dimensions
        """
        valid = {
            dim: change
            for dim, change in changes.items()
            if _step_distance(change["from"], change["to"]) <= self.DRIFT_STEP
        }
        if len(valid) > self.MAX_DRIFT_PER_CYCLE:
            # Keep the first N (LLM ordering reflects priority)
            keys = list(valid.keys())[: self.MAX_DRIFT_PER_CYCLE]
            valid = {k: valid[k] for k in keys}
        return valid

    async def validate_shift(
        self,
        changes: dict[str, dict],
        resident_id: str,
        db: AsyncSession,
    ) -> dict[str, dict]:
        """Validate and clamp shift changes.

        Rules:
        - All step distances allowed (L→H OK for shift)
        - Keep at most MAX_SHIFT_PER_EVENT dimensions
        """
        if len(changes) > self.MAX_SHIFT_PER_EVENT:
            keys = list(changes.keys())[: self.MAX_SHIFT_PER_EVENT]
            return {k: changes[k] for k in keys}
        return dict(changes)

    async def check_monthly_budget(
        self, resident_id: str, db: AsyncSession
    ) -> int:
        """Return remaining monthly dimension-change budget.

        Counts total dimension changes recorded in personality_history
        during the current calendar month.
        """
        from sqlalchemy import extract
        now = datetime.now(UTC)
        stmt = (
            select(PersonalityHistory.changes_json)
            .where(
                PersonalityHistory.resident_id == resident_id,
                extract("year", PersonalityHistory.created_at) == now.year,
                extract("month", PersonalityHistory.created_at) == now.month,
            )
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        used = sum(len(row) for row in rows if isinstance(row, dict))
        return max(0, self.TOTAL_MONTHLY_CHANGE - used)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_personality_guard.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/personality/ backend/tests/test_personality_guard.py
git commit -m "feat(personality): add PersonalityGuard with drift/shift rate limits and budget tracking"
```

---

### Task 3: Evolution Prompts

**Files:**
- Create: `backend/app/personality/prompts.py`

No standalone tests for this task — prompts are tested indirectly through Task 4 (EvolutionService tests).

- [ ] **Step 1: Create prompt templates**

Create `backend/app/personality/prompts.py`:

```python
"""LLM prompt templates for personality evolution (drift, shift, text sync)."""

# ── Drift evaluation ───────────────────────────────────────────────────────

DRIFT_EVAL_SYSTEM = """\
你是一个人格演化分析师。你的任务是分析一个居民最近的经历（事件记忆），判断哪些 SBTI 人格维度有足够证据支持微小变化。

## 规则
- 只分析有明确行为证据的维度
- 每次最多推荐 2 个维度
- 每个维度只能变化 1 步：L→M、M→H、H→M、M→L（不允许 L→H 或 H→L）
- 如果没有足够证据支持任何维度变化，返回空列表

## 输出格式
严格 JSON，不要输出其他内容：
{"changes": [{"dim": "So1", "from": "M", "to": "H", "evidence": "居民在过去15条记忆中多次主动发起社交"}]}

如果没有变化：{"changes": []}
"""

DRIFT_EVAL_USER = """\
居民：{resident_name}（SBTI 类型：{sbti_type}）

当前 15 维度评分：
{current_dimensions}

最近的事件记忆（按时间倒序）：
{recent_memories}

请分析哪些维度有明确的漂移证据。
"""

# ── Shift evaluation ───────────────────────────────────────────────────────

SHIFT_EVAL_SYSTEM = """\
你是一个人格剧变分析师。你的任务是分析一个高重要性事件对居民 SBTI 人格的冲击影响。

## 触发场景类型
- 深度共鸣（deep resonance）：某人真正理解了居民的内心世界
- 信任背叛（trust betrayal）：被信任的人伤害或出卖了居民
- 认知冲突（cognitive conflict）：遭遇与核心信念激烈冲突的观点
- 群体排斥/接纳（group rejection/acceptance）：被重要群体拒绝或接纳

## 规则
- 最多推荐 3 个维度
- 每个维度最多变化 2 步（允许 L→H 或 H→L）
- 只分析真正被这个事件冲击的维度

## 输出格式
严格 JSON：
{"event_type": "trust_betrayal", "changes": [{"dim": "E1", "from": "H", "to": "L", "evidence": "..."}], "shift_reason": "对方出卖了居民最深的秘密，彻底动摇了对他人的信任"}

如果事件影响不足以触发剧变：{"event_type": "none", "changes": [], "shift_reason": ""}
"""

SHIFT_EVAL_USER = """\
居民：{resident_name}（SBTI 类型：{sbti_type}）

当前 15 维度评分：
{current_dimensions}

触发事件（重要性：{importance}）：
{event_content}

请分析这个事件对居民人格的剧变影响。
"""

# ── Text synchronization ───────────────────────────────────────────────────

TEXT_SYNC_SYSTEM = """\
你是一个角色文档编辑器。你的任务是根据人格维度的变化，修改居民的人格描述文档（persona_md），使其反映新的人格状态。

## 规则
- 只修改与变化维度相关的段落
- 保留其他所有内容不变
- 文风与原文保持一致
- 修改要自然、符合叙事逻辑
- 如果是 shift（剧变），可以用更强烈的语气描述变化

## 输出格式
直接输出修改后的完整文档内容，不要加任何解释或标记。
"""

TEXT_SYNC_USER = """\
居民名字：{resident_name}
变化类型：{trigger_type}（drift=渐变，shift=剧变）
变化原因：{reason}

维度变化：
{changes_summary}

原始 persona_md 内容：
{original_text}

请输出修改后的 persona_md 内容。
"""

TEXT_SYNC_SOUL_SYSTEM = """\
你是一个角色文档编辑器。你的任务是根据重大人格剧变（shift），修改居民的灵魂描述文档（soul_md）中的核心价值部分。

## 规则
- soul_md 极少改变，只在 shift 事件后且核心价值维度（S3、A3）发生变化时修改
- 只修改与变化维度直接相关的内容
- 修改幅度要小而深刻，体现内心深处的转变
- 保留其他所有内容不变

## 输出格式
直接输出修改后的完整 soul_md 内容，不要加任何解释或标记。
"""

TEXT_SYNC_SOUL_USER = """\
居民名字：{resident_name}
剧变事件：{reason}

核心维度变化：
{changes_summary}

原始 soul_md 内容：
{original_text}

请输出修改后的 soul_md 内容（保守修改，只改动最核心的部分）。
"""


def format_dimensions(dimensions: dict[str, str]) -> str:
    """Format L/M/H dimension dict into a readable block for LLM prompts."""
    dim_labels = {
        "S1": "自尊自信", "S2": "自我清晰度", "S3": "核心价值",
        "E1": "依恋安全感", "E2": "情感投入度", "E3": "边界与依赖",
        "A1": "世界观倾向", "A2": "规则与灵活度", "A3": "人生意义感",
        "Ac1": "动机导向", "Ac2": "决策风格", "Ac3": "执行模式",
        "So1": "社交主动性", "So2": "人际边界感", "So3": "表达与真实度",
    }
    level_map = {"L": "低", "M": "中", "H": "高"}
    lines = []
    for code, label in dim_labels.items():
        val = dimensions.get(code, "M")
        lines.append(f"- {label}({code}): {level_map.get(val, '中')}({val})")
    return "\n".join(lines)


def format_changes_summary(changes_json: dict[str, dict]) -> str:
    """Format changes_json into a readable summary for text sync prompts."""
    dim_labels = {
        "S1": "自尊自信", "S2": "自我清晰度", "S3": "核心价值",
        "E1": "依恋安全感", "E2": "情感投入度", "E3": "边界与依赖",
        "A1": "世界观倾向", "A2": "规则与灵活度", "A3": "人生意义感",
        "Ac1": "动机导向", "Ac2": "决策风格", "Ac3": "执行模式",
        "So1": "社交主动性", "So2": "人际边界感", "So3": "表达与真实度",
    }
    level_map = {"L": "低", "M": "中", "H": "高"}
    lines = []
    for dim, change in changes_json.items():
        label = dim_labels.get(dim, dim)
        frm = level_map.get(change["from"], change["from"])
        to = level_map.get(change["to"], change["to"])
        lines.append(f"- {label}({dim}): {frm} → {to}")
    return "\n".join(lines)
```

- [ ] **Step 2: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/personality/prompts.py
git commit -m "feat(personality): add LLM prompt templates for drift/shift evaluation and text sync"
```

---

### Task 4: Evolution Service

**Files:**
- Create: `backend/app/personality/evolution.py`
- Create: `backend/tests/test_personality_evolution.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_personality_evolution.py`:

```python
import pytest
import json
from datetime import datetime, UTC, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from app.models.resident import Resident
from app.models.memory import Memory
from app.models.personality_history import PersonalityHistory
from app.personality.evolution import EvolutionService


@pytest.fixture
async def evo_resident(db_session):
    r = Resident(
        id="evo-svc-res",
        slug="evo-svc-res",
        name="EvoSvcResident",
        district="engineering",
        status="idle",
        ability_md="Can code",
        persona_md="Friendly engineer who rarely starts conversations. Prefers technical topics.",
        soul_md="Believes in meritocracy and quiet achievement.",
        meta_json={"sbti": {
            "type": "CTRL",
            "type_name": "拿捏者",
            "dimensions": {
                "S1": "H", "S2": "H", "S3": "H",
                "E1": "H", "E2": "M", "E3": "H",
                "A1": "M", "A2": "H", "A3": "H",
                "Ac1": "H", "Ac2": "H", "Ac3": "H",
                "So1": "M", "So2": "H", "So3": "M",
            },
        }},
    )
    db_session.add(r)
    await db_session.commit()
    return r


def _mock_llm_response(text: str):
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


@pytest.mark.anyio
async def test_evaluate_drift_applies_valid_changes(db_session, evo_resident):
    """Drift evaluation should update SBTI dimensions and create history entry."""
    # Seed 15 event memories to pass the drift interval gate
    for i in range(15):
        mem = Memory(
            resident_id=evo_resident.id,
            type="event",
            content=f"Social event {i}",
            importance=0.5,
            source="chat_player",
        )
        db_session.add(mem)
    await db_session.commit()

    drift_response = json.dumps({
        "changes": [
            {"dim": "So1", "from": "M", "to": "H", "evidence": "15 social interactions"},
        ]
    })
    persona_response = "Updated persona with high social warmth. Friendly engineer who now actively starts conversations."

    with patch("app.personality.evolution.get_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=[
            _mock_llm_response(drift_response),   # drift eval
            _mock_llm_response(persona_response),  # text sync
        ])
        mock_client_fn.return_value = mock_client

        svc = EvolutionService(db_session)
        history = await svc.evaluate_drift(evo_resident)

    assert history is not None
    assert history.trigger_type == "drift"
    assert "So1" in history.changes_json
    assert history.changes_json["So1"]["to"] == "H"

    # Verify resident SBTI updated in DB
    await db_session.refresh(evo_resident)
    dims = evo_resident.meta_json["sbti"]["dimensions"]
    assert dims["So1"] == "H"

    # Verify persona_md updated
    assert "actively starts" in evo_resident.persona_md


@pytest.mark.anyio
async def test_evaluate_drift_returns_none_when_not_due(db_session, evo_resident):
    """Drift should return None when fewer than MIN_DRIFT_INTERVAL memories."""
    # Only 5 memories — below the 15 threshold
    for i in range(5):
        mem = Memory(
            resident_id=evo_resident.id,
            type="event",
            content=f"Event {i}",
            importance=0.5,
            source="chat_player",
        )
        db_session.add(mem)
    await db_session.commit()

    svc = EvolutionService(db_session)
    result = await svc.evaluate_drift(evo_resident)
    assert result is None


@pytest.mark.anyio
async def test_evaluate_shift_applies_dramatic_changes(db_session, evo_resident):
    """Shift evaluation should handle multi-step changes and trigger soul_md update."""
    trigger_mem = Memory(
        resident_id=evo_resident.id,
        type="event",
        content="Best friend betrayed resident's deepest secret to the whole district",
        importance=0.95,
        source="chat_player",
    )
    db_session.add(trigger_mem)
    await db_session.commit()

    shift_response = json.dumps({
        "event_type": "trust_betrayal",
        "changes": [
            {"dim": "E1", "from": "H", "to": "L", "evidence": "Catastrophic trust collapse"},
            {"dim": "So1", "from": "M", "to": "L", "evidence": "Social withdrawal"},
        ],
        "shift_reason": "The betrayal shattered the resident's ability to trust others",
    })
    persona_response = "Cold and withdrawn. No longer initiates social contact."
    soul_response = "Believes relationships are transactional. Trust must be earned through years of proof."

    with patch("app.personality.evolution.get_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=[
            _mock_llm_response(shift_response),  # shift eval
            _mock_llm_response(persona_response),  # persona sync
            _mock_llm_response(soul_response),     # soul sync (shift triggers soul update)
        ])
        mock_client_fn.return_value = mock_client

        svc = EvolutionService(db_session)
        history = await svc.evaluate_shift(evo_resident, trigger_mem)

    assert history is not None
    assert history.trigger_type == "shift"
    assert history.trigger_memory_id == trigger_mem.id
    assert "E1" in history.changes_json
    assert history.changes_json["E1"]["to"] == "L"

    await db_session.refresh(evo_resident)
    dims = evo_resident.meta_json["sbti"]["dimensions"]
    assert dims["E1"] == "L"
    assert dims["So1"] == "L"


@pytest.mark.anyio
async def test_evaluate_shift_respects_cooldown(db_session, evo_resident):
    """Shift within 24h cooldown → returns None."""
    # Add recent shift history
    recent_shift = PersonalityHistory(
        resident_id=evo_resident.id,
        trigger_type="shift",
        changes_json={"E1": {"from": "H", "to": "L"}},
        old_type="CTRL",
        new_type="THIN-K",
        reason="Previous shift",
        created_at=datetime.now(UTC) - timedelta(hours=6),
    )
    db_session.add(recent_shift)

    trigger_mem = Memory(
        resident_id=evo_resident.id,
        type="event",
        content="Another major event",
        importance=0.95,
        source="chat_player",
    )
    db_session.add(trigger_mem)
    await db_session.commit()

    svc = EvolutionService(db_session)
    result = await svc.evaluate_shift(evo_resident, trigger_mem)
    assert result is None


@pytest.mark.anyio
async def test_type_migration_recorded_on_shift(db_session, evo_resident):
    """When dimensions change enough to migrate type, history records old/new type."""
    trigger_mem = Memory(
        resident_id=evo_resident.id,
        type="event",
        content="Deep intellectual awakening — rejected all social norms",
        importance=0.92,
        source="chat_player",
    )
    db_session.add(trigger_mem)
    await db_session.commit()

    # CTRL → THIN-K requires So1 L (was M) and several other changes
    shift_response = json.dumps({
        "event_type": "cognitive_conflict",
        "changes": [
            {"dim": "So1", "from": "M", "to": "L", "evidence": "..."},
            {"dim": "So3", "from": "M", "to": "H", "evidence": "..."},
        ],
        "shift_reason": "Cognitive awakening leading to social withdrawal",
    })
    persona_response = "Withdrawn thinker."
    soul_response = "Values intellectual purity above social connection."

    with patch("app.personality.evolution.get_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=[
            _mock_llm_response(shift_response),
            _mock_llm_response(persona_response),
            _mock_llm_response(soul_response),
        ])
        mock_client_fn.return_value = mock_client

        svc = EvolutionService(db_session)
        history = await svc.evaluate_shift(evo_resident, trigger_mem)

    assert history is not None
    # old_type and new_type should both be set (may or may not be different)
    assert history.old_type is not None
    assert history.new_type is not None


@pytest.mark.anyio
async def test_evaluate_drift_llm_failure_returns_none(db_session, evo_resident):
    """LLM failure during drift → returns None, no DB changes."""
    for i in range(15):
        mem = Memory(
            resident_id=evo_resident.id,
            type="event",
            content=f"Event {i}",
            importance=0.5,
            source="chat_player",
        )
        db_session.add(mem)
    await db_session.commit()

    with patch("app.personality.evolution.get_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("LLM down"))
        mock_client_fn.return_value = mock_client

        svc = EvolutionService(db_session)
        result = await svc.evaluate_drift(evo_resident)

    assert result is None
    # Verify no history was created
    hist_result = await db_session.execute(
        select(PersonalityHistory).where(PersonalityHistory.resident_id == evo_resident.id)
    )
    assert hist_result.scalars().first() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_personality_evolution.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.personality.evolution'`

- [ ] **Step 3: Implement EvolutionService**

Create `backend/app/personality/evolution.py`:

```python
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.llm.client import get_client
from app.config import settings
from app.models.resident import Resident
from app.models.memory import Memory
from app.models.personality_history import PersonalityHistory
from app.personality.guard import PersonalityGuard
from app.personality.prompts import (
    DRIFT_EVAL_SYSTEM,
    DRIFT_EVAL_USER,
    SHIFT_EVAL_SYSTEM,
    SHIFT_EVAL_USER,
    TEXT_SYNC_SYSTEM,
    TEXT_SYNC_USER,
    TEXT_SYNC_SOUL_SYSTEM,
    TEXT_SYNC_SOUL_USER,
    format_dimensions,
    format_changes_summary,
)
from app.services.sbti_service import match_type

logger = logging.getLogger(__name__)

# Soul-relevant dimensions — only these trigger soul_md update on shift
_SOUL_DIMENSIONS = {"S3", "A3"}


class EvolutionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.guard = PersonalityGuard()

    async def evaluate_drift(self, resident: Resident) -> PersonalityHistory | None:
        """Check if drift is due and evaluate which dimensions should drift.

        Returns PersonalityHistory entry if drift occurred, else None.
        Non-blocking: exceptions are caught and logged.
        """
        try:
            # Guard check: enough memories since last drift?
            if not await self.guard.can_drift(resident.id, self.db):
                return None

            # Check monthly budget
            budget = await self.guard.check_monthly_budget(resident.id, self.db)
            if budget <= 0:
                logger.info("Drift skipped for %s: monthly budget exhausted", resident.id)
                return None

            sbti = (resident.meta_json or {}).get("sbti", {})
            dimensions = sbti.get("dimensions", {})
            sbti_type = sbti.get("type", "UNKNOWN")

            # Retrieve recent event memories
            stmt = (
                select(Memory)
                .where(Memory.resident_id == resident.id, Memory.type == "event")
                .order_by(Memory.created_at.desc())
                .limit(20)
            )
            result = await self.db.execute(stmt)
            recent_mems = result.scalars().all()

            if not recent_mems:
                return None

            mem_text = "\n".join(
                f"- [{m.importance:.1f}] {m.content}" for m in recent_mems
            )

            client = get_client("system")
            resp = await client.messages.create(
                model=settings.effective_model,
                max_tokens=400,
                system=DRIFT_EVAL_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": DRIFT_EVAL_USER.format(
                        resident_name=resident.name,
                        sbti_type=sbti_type,
                        current_dimensions=format_dimensions(dimensions),
                        recent_memories=mem_text,
                    ),
                }],
            )
            raw = self._extract_text(resp)
            data = json.loads(raw)
            changes_list = data.get("changes", [])

            if not changes_list:
                return None

            # Build changes dict
            proposed = {
                item["dim"]: {"from": item["from"], "to": item["to"]}
                for item in changes_list
                if item.get("dim") and item.get("from") and item.get("to")
            }

            # Guard validation (clamp, step check)
            validated = await self.guard.validate_drift(proposed, resident.id, self.db)
            if not validated:
                return None

            # Clamp by monthly budget
            if len(validated) > budget:
                keys = list(validated.keys())[:budget]
                validated = {k: validated[k] for k in keys}

            reason = "; ".join(
                item.get("evidence", "") for item in changes_list
                if item["dim"] in validated
            )

            return await self._apply_changes(
                resident=resident,
                changes=validated,
                trigger_type="drift",
                trigger_memory_id=None,
                reason=reason,
            )

        except Exception as e:
            logger.warning("Drift evaluation failed for %s: %s", resident.id, e)
            return None

    async def evaluate_shift(
        self, resident: Resident, trigger_memory: Memory
    ) -> PersonalityHistory | None:
        """Evaluate dramatic personality shift triggered by a high-importance event.

        Returns PersonalityHistory entry if shift occurred, else None.
        Non-blocking: exceptions are caught and logged.
        """
        try:
            if not await self.guard.can_shift(resident.id, self.db):
                logger.info("Shift skipped for %s: 24h cooldown active", resident.id)
                return None

            budget = await self.guard.check_monthly_budget(resident.id, self.db)
            if budget <= 0:
                logger.info("Shift skipped for %s: monthly budget exhausted", resident.id)
                return None

            sbti = (resident.meta_json or {}).get("sbti", {})
            dimensions = sbti.get("dimensions", {})
            sbti_type = sbti.get("type", "UNKNOWN")

            client = get_client("system")
            resp = await client.messages.create(
                model=settings.effective_model,
                max_tokens=500,
                system=SHIFT_EVAL_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": SHIFT_EVAL_USER.format(
                        resident_name=resident.name,
                        sbti_type=sbti_type,
                        current_dimensions=format_dimensions(dimensions),
                        importance=trigger_memory.importance,
                        event_content=trigger_memory.content,
                    ),
                }],
            )
            raw = self._extract_text(resp)
            data = json.loads(raw)
            changes_list = data.get("changes", [])
            shift_reason = data.get("shift_reason", "")

            if not changes_list or data.get("event_type") == "none":
                return None

            proposed = {
                item["dim"]: {"from": item["from"], "to": item["to"]}
                for item in changes_list
                if item.get("dim") and item.get("from") and item.get("to")
            }

            validated = await self.guard.validate_shift(proposed, resident.id, self.db)
            if not validated:
                return None

            if len(validated) > budget:
                keys = list(validated.keys())[:budget]
                validated = {k: validated[k] for k in keys}

            return await self._apply_changes(
                resident=resident,
                changes=validated,
                trigger_type="shift",
                trigger_memory_id=trigger_memory.id,
                reason=shift_reason,
            )

        except Exception as e:
            logger.warning("Shift evaluation failed for %s: %s", resident.id, e)
            return None

    async def _apply_changes(
        self,
        resident: Resident,
        changes: dict[str, dict],
        trigger_type: str,
        trigger_memory_id: str | None,
        reason: str,
    ) -> PersonalityHistory:
        """Apply validated dimension changes, re-match type, sync text, record history."""
        sbti = dict((resident.meta_json or {}).get("sbti", {}))
        dimensions = dict(sbti.get("dimensions", {}))
        old_type = sbti.get("type", "UNKNOWN")

        # Apply dimension changes
        for dim, change in changes.items():
            dimensions[dim] = change["to"]

        # Re-match SBTI type
        new_type_result = match_type(dimensions)
        new_type = new_type_result["type"]

        # Update resident SBTI in meta_json
        updated_sbti = dict(sbti)
        updated_sbti["dimensions"] = dimensions
        updated_sbti["type"] = new_type
        updated_sbti["type_name"] = new_type_result["type_name"]
        updated_sbti["similarity"] = new_type_result["similarity"]

        updated_meta = dict(resident.meta_json or {})
        updated_meta["sbti"] = updated_sbti
        resident.meta_json = updated_meta

        # Sync text layers
        await self._sync_text(resident, changes, reason, trigger_type)

        # Record history
        history = PersonalityHistory(
            resident_id=resident.id,
            trigger_type=trigger_type,
            trigger_memory_id=trigger_memory_id,
            changes_json=changes,
            old_type=old_type,
            new_type=new_type,
            reason=reason,
        )
        self.db.add(history)
        await self.db.commit()
        await self.db.refresh(resident)
        await self.db.refresh(history)

        if old_type != new_type:
            logger.info(
                "Type migration: %s → %s for resident %s",
                old_type, new_type, resident.id,
            )

        return history

    async def _sync_text(
        self,
        resident: Resident,
        changes: dict[str, dict],
        reason: str,
        trigger_type: str,
    ) -> None:
        """LLM-rewrite affected sections of persona_md (always) and soul_md (shift only).

        Failures are silently logged — text sync is best-effort.
        """
        changes_summary = format_changes_summary(changes)

        try:
            client = get_client("system")

            # Always sync persona_md
            resp = await client.messages.create(
                model=settings.effective_model,
                max_tokens=800,
                system=TEXT_SYNC_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": TEXT_SYNC_USER.format(
                        resident_name=resident.name,
                        trigger_type=trigger_type,
                        reason=reason,
                        changes_summary=changes_summary,
                        original_text=resident.persona_md or "",
                    ),
                }],
            )
            new_persona = self._extract_text(resp).strip()
            if new_persona:
                resident.persona_md = new_persona

        except Exception as e:
            logger.warning("persona_md sync failed for %s: %s", resident.id, e)

        # Only sync soul_md on shift AND if soul-relevant dimensions changed
        if trigger_type == "shift":
            soul_dims_changed = set(changes.keys()) & _SOUL_DIMENSIONS
            if soul_dims_changed:
                try:
                    client = get_client("system")
                    resp = await client.messages.create(
                        model=settings.effective_model,
                        max_tokens=500,
                        system=TEXT_SYNC_SOUL_SYSTEM,
                        messages=[{
                            "role": "user",
                            "content": TEXT_SYNC_SOUL_USER.format(
                                resident_name=resident.name,
                                reason=reason,
                                changes_summary=changes_summary,
                                original_text=resident.soul_md or "",
                            ),
                        }],
                    )
                    new_soul = self._extract_text(resp).strip()
                    if new_soul:
                        resident.soul_md = new_soul

                except Exception as e:
                    logger.warning("soul_md sync failed for %s: %s", resident.id, e)

    @staticmethod
    def _extract_text(response) -> str:
        """Extract text from LLM response, skipping ThinkingBlocks."""
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_personality_evolution.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/personality/evolution.py backend/tests/test_personality_evolution.py
git commit -m "feat(personality): add EvolutionService with drift/shift evaluation and three-layer text sync"
```

---

### Task 5: Wire Evolution into Memory System

**Files:**
- Modify: `backend/app/memory/service.py`
- Modify: `backend/app/ws/handler.py`
- Create: `backend/tests/test_evolution_integration.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/test_evolution_integration.py`:

```python
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock, call
from sqlalchemy import select
from app.models.resident import Resident
from app.models.memory import Memory
from app.models.personality_history import PersonalityHistory
from app.memory.service import MemoryService


@pytest.fixture
async def int_resident(db_session):
    r = Resident(
        id="int-evo-res",
        slug="int-evo-res",
        name="IntEvoResident",
        district="engineering",
        status="idle",
        ability_md="Can code",
        persona_md="Quiet and technical.",
        soul_md="Values precision.",
        meta_json={"sbti": {
            "type": "CTRL",
            "type_name": "拿捏者",
            "dimensions": {
                "S1": "H", "S2": "H", "S3": "H",
                "E1": "H", "E2": "M", "E3": "H",
                "A1": "M", "A2": "H", "A3": "H",
                "Ac1": "H", "Ac2": "H", "Ac3": "H",
                "So1": "M", "So2": "H", "So3": "M",
            },
        }},
    )
    db_session.add(r)
    await db_session.commit()
    return r


def _llm_resp(text: str):
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


@pytest.mark.anyio
async def test_high_importance_memory_triggers_shift_check(db_session, int_resident):
    """Adding a memory with importance >= 0.9 should attempt shift evaluation."""
    svc = MemoryService(db_session)

    shift_response = json.dumps({
        "event_type": "deep_resonance",
        "changes": [{"dim": "E2", "from": "M", "to": "H", "evidence": "Deep connection"}],
        "shift_reason": "Profound emotional resonance",
    })
    persona_response = "Now deeply emotionally engaged with others."

    with patch("app.memory.service.get_client") as mock_extract_client, \
         patch("app.personality.evolution.get_client") as mock_evo_client:

        mock_extract = AsyncMock()
        mock_extract.messages.create = AsyncMock(return_value=_llm_resp(json.dumps({
            "memories": [{"content": "Profound connection", "importance": 0.92}]
        })))
        mock_extract_client.return_value = mock_extract

        mock_evo = AsyncMock()
        mock_evo.messages.create = AsyncMock(side_effect=[
            _llm_resp(shift_response),
            _llm_resp(persona_response),
        ])
        mock_evo_client.return_value = mock_evo

        with patch("app.memory.service.generate_embedding", return_value=[0.1] * 1024):
            memories = await svc.extract_events(
                resident=int_resident,
                other_name="Visitor",
                conversation_text="We had a profound conversation about life.",
            )

    # The memory with importance=0.92 should exist
    assert len(memories) == 1
    assert memories[0].importance >= 0.9


@pytest.mark.anyio
async def test_drift_check_triggered_after_15_memories(db_session, int_resident):
    """After accumulating 15 event memories, drift evaluation should be called."""
    svc = MemoryService(db_session)

    # Pre-seed 14 memories directly
    for i in range(14):
        db_session.add(Memory(
            resident_id=int_resident.id,
            type="event",
            content=f"Prior event {i}",
            importance=0.5,
            source="chat_player",
        ))
    await db_session.commit()

    drift_response = json.dumps({"changes": []})  # No changes — just checks the call

    with patch("app.memory.service.get_client") as mock_extract_client, \
         patch("app.personality.evolution.get_client") as mock_evo_client:

        mock_extract = AsyncMock()
        mock_extract.messages.create = AsyncMock(return_value=_llm_resp(json.dumps({
            "memories": [{"content": "The 15th event", "importance": 0.5}]
        })))
        mock_extract_client.return_value = mock_extract

        mock_evo = AsyncMock()
        mock_evo.messages.create = AsyncMock(return_value=_llm_resp(drift_response))
        mock_evo_client.return_value = mock_evo

        with patch("app.memory.service.generate_embedding", return_value=[0.1] * 1024):
            await svc.extract_events(
                resident=int_resident,
                other_name="Visitor",
                conversation_text="The 15th conversation.",
            )

    # Drift LLM should have been called
    mock_evo.messages.create.assert_called_once()


@pytest.mark.anyio
async def test_evolution_failure_does_not_crash_memory_extraction(db_session, int_resident):
    """Evolution errors must not propagate to memory extraction callers."""
    svc = MemoryService(db_session)

    with patch("app.memory.service.get_client") as mock_extract_client, \
         patch("app.personality.evolution.EvolutionService.evaluate_shift",
               new_callable=AsyncMock, side_effect=Exception("Evolution crashed")):

        mock_extract = AsyncMock()
        mock_extract.messages.create = AsyncMock(return_value=_llm_resp(json.dumps({
            "memories": [{"content": "Critical event", "importance": 0.95}]
        })))
        mock_extract_client.return_value = mock_extract

        with patch("app.memory.service.generate_embedding", return_value=[0.1] * 1024):
            # Should NOT raise even if evolution crashes
            memories = await svc.extract_events(
                resident=int_resident,
                other_name="Visitor",
                conversation_text="A critical event happened.",
            )

    assert len(memories) == 1  # Memory was still created
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_evolution_integration.py -v`
Expected: FAIL — integration hooks not yet wired

- [ ] **Step 3: Modify MemoryService to trigger evolution checks**

In `backend/app/memory/service.py`, add the import at the top (alongside existing imports):

```python
from app.personality.evolution import EvolutionService
```

Modify the `extract_events` method — after the memories loop, add evolution hooks:

```python
        # Evolution hooks (non-blocking)
        if memories and resident is not None:
            evo = EvolutionService(self.db)

            # Check for shift on any high-importance memory
            high_importance = [m for m in memories if m.importance >= 0.9]
            if high_importance:
                try:
                    await evo.evaluate_shift(resident, high_importance[0])
                except Exception as e:
                    logger.warning("Shift evaluation error (non-fatal): %s", e)

            # Check drift trigger: count total events since last drift
            total_events = await self.count_events_since_last_reflection(resident.id)
            if total_events >= 15:
                try:
                    await evo.evaluate_drift(resident)
                except Exception as e:
                    logger.warning("Drift evaluation error (non-fatal): %s", e)

        return memories
```

Note: The `extract_events` method signature must accept the `resident` object (not just `resident_id`). Verify the existing signature already accepts `resident: Resident`. If the existing implementation uses `resident_id` as a string, update the signature to accept the full resident object (it already does based on P1 plan).

- [ ] **Step 4: Modify ws/handler.py to broadcast type change events**

In `backend/app/ws/handler.py`, in the `_extract_chat_memories` helper function, after calling `extract_events` and `update_relationship_via_llm`, add:

```python
            # Check for personality type change and broadcast
            await db.refresh(resident)
            new_sbti = (resident.meta_json or {}).get("sbti", {})
            new_type = new_sbti.get("type")
            old_type = original_sbti_type  # capture before memory extraction

            if new_type and old_type and new_type != old_type:
                from app.ws.manager import manager
                await manager.broadcast_to_resident_viewers(
                    resident_id,
                    {
                        "type": "resident_type_changed",
                        "resident_id": resident_id,
                        "old_type": old_type,
                        "new_type": new_type,
                        "type_name": new_sbti.get("type_name", ""),
                    },
                )
```

Before the memory extraction logic, capture the original type:

```python
            original_sbti_type = (resident.meta_json or {}).get("sbti", {}).get("type")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_evolution_integration.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Run full test suite for regressions**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/memory/service.py backend/app/ws/handler.py backend/tests/test_evolution_integration.py
git commit -m "feat(personality): wire evolution drift/shift checks into MemoryService and WS broadcast"
```

---

### Task 6: Frontend Type Change Notification

**Files:**
- Modify: `frontend/src/components/profile/ResidentCard.tsx`

- [ ] **Step 1: Add flash animation state to ResidentCard**

Read the current file at `frontend/src/components/profile/ResidentCard.tsx`.

Replace the entire file content with the following updated version that handles `resident_type_changed` WS events with a flash animation on the SBTI label:

```tsx
import { useEffect, useRef, useState } from 'react'

interface SbtiInfo {
  type: string
  type_name: string
}

interface ResidentCardProps {
  resident: {
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
    meta_json: { role?: string; sbti?: SbtiInfo } | null
  }
  onEdit: (slug: string) => void
  /** Optional: pass the latest WS message so ResidentCard can react to type changes */
  lastWsMessage?: { type: string; resident_id: string; new_type: string; type_name: string } | null
}

const STATUS_LABELS: Record<string, string> = {
  idle: '🟢 空闲',
  chatting: '💬 对话中',
  sleeping: '💤 沉睡',
  popular: '🔥 热门',
}

export function ResidentCard({ resident, onEdit, lastWsMessage }: ResidentCardProps) {
  const [isFlashing, setIsFlashing] = useState(false)
  const [displayedType, setDisplayedType] = useState<SbtiInfo | undefined>(
    resident.meta_json?.sbti ?? undefined
  )
  const flashTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // React to resident_type_changed WS messages
  useEffect(() => {
    if (
      lastWsMessage?.type === 'resident_type_changed' &&
      lastWsMessage.resident_id === resident.id
    ) {
      setDisplayedType({ type: lastWsMessage.new_type, type_name: lastWsMessage.type_name })
      setIsFlashing(true)

      if (flashTimeoutRef.current) {
        clearTimeout(flashTimeoutRef.current)
      }
      flashTimeoutRef.current = setTimeout(() => {
        setIsFlashing(false)
      }, 1500)
    }
  }, [lastWsMessage, resident.id])

  // Sync displayed type with prop updates (e.g. after page reload)
  useEffect(() => {
    if (resident.meta_json?.sbti) {
      setDisplayedType(resident.meta_json.sbti)
    }
  }, [resident.meta_json?.sbti?.type])

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (flashTimeoutRef.current) clearTimeout(flashTimeoutRef.current)
    }
  }, [])

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px',
      background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 12,
    }}>
      <div style={{
        width: 48, height: 48, background: 'var(--bg-input)', borderRadius: 8,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 24, flexShrink: 0,
      }}>🧑‍💻</div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontWeight: 700, fontSize: 14 }}>{resident.name}</span>
          <span style={{ fontSize: 12 }}>{'⭐'.repeat(resident.star_rating)}</span>
          {displayedType && (
            <span
              style={{
                fontSize: 10,
                padding: '1px 6px',
                borderRadius: 4,
                background: isFlashing ? 'var(--accent-alt, #fd79a8)' : 'var(--accent, #6c5ce7)',
                color: '#fff',
                fontWeight: 600,
                letterSpacing: 0.5,
                transition: 'background 0.3s ease',
                transform: isFlashing ? 'scale(1.15)' : 'scale(1)',
                display: 'inline-block',
              }}
              title={displayedType.type_name}
            >
              {displayedType.type}
            </span>
          )}
        </div>

        <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 2 }}>
          {resident.meta_json?.role ?? ''} · {resident.district}
        </div>

        <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 11, color: 'var(--text-secondary)' }}>
          <span>{STATUS_LABELS[resident.status] ?? resident.status}</span>
          <span>🔥 {resident.heat}</span>
          <span>💬 {resident.total_conversations}</span>
          {resident.avg_rating > 0 && <span>⭐ {resident.avg_rating.toFixed(1)}</span>}
        </div>
      </div>

      <button
        onClick={() => onEdit(resident.slug)}
        style={{
          background: 'var(--bg-input)', border: '1px solid var(--border)',
          color: 'var(--text-secondary)', padding: '6px 14px', borderRadius: 6,
          fontSize: 12, cursor: 'pointer', flexShrink: 0,
        }}
      >
        编辑
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Run TypeScript type check**

Run: `cd /Users/jimmy/Downloads/Skills-World/frontend && npx tsc --noEmit 2>&1 | head -30`
Expected: No errors related to ResidentCard.tsx

- [ ] **Step 3: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add frontend/src/components/profile/ResidentCard.tsx
git commit -m "feat(personality): add SBTI type flash animation on resident_type_changed WS event"
```

---

### Task 7: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/006_add_personality_history.py`

- [ ] **Step 1: Create the migration**

Create `backend/alembic/versions/006_add_personality_history.py`:

```python
"""Add personality_history table for evolution audit trail.

Revision ID: 006_add_personality_history
Revises: 005 (or the latest migration before this one)
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "006_add_personality_history"
down_revision = "005"  # Update to actual previous revision ID
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personality_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "resident_id",
            sa.String(),
            sa.ForeignKey("residents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trigger_type", sa.String(10), nullable=False),
        sa.Column(
            "trigger_memory_id",
            sa.String(),
            sa.ForeignKey("memories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("changes_json", sa.JSON(), nullable=False),
        sa.Column("old_type", sa.String(20), nullable=False),
        sa.Column("new_type", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_personality_history_resident_created",
        "personality_history",
        ["resident_id", "created_at"],
    )
    op.create_index(
        "ix_personality_history_trigger_type",
        "personality_history",
        ["resident_id", "trigger_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_personality_history_trigger_type")
    op.drop_index("ix_personality_history_resident_created")
    op.drop_table("personality_history")
```

Note: Update `down_revision` to match the actual latest migration revision in your alembic chain (check `backend/alembic/versions/` for the most recent file).

- [ ] **Step 2: Verify migration syntax**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m py_compile alembic/versions/006_add_personality_history.py && echo "Syntax OK"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/alembic/versions/006_add_personality_history.py
git commit -m "feat(personality): add Alembic migration for personality_history table"
```

---

### Task 8: Final Integration Verification

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS — no regressions

- [ ] **Step 2: Run TypeScript type check**

Run: `cd /Users/jimmy/Downloads/Skills-World/frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Verify file structure**

Run:
```bash
find /Users/jimmy/Downloads/Skills-World/backend/app/personality -type f -name "*.py" | sort
find /Users/jimmy/Downloads/Skills-World/backend/tests -name "*personality*" -o -name "*evolution*" | sort
```

Expected:
```
backend/app/personality/__init__.py
backend/app/personality/evolution.py
backend/app/personality/guard.py
backend/app/personality/prompts.py
---
backend/tests/test_evolution_integration.py
backend/tests/test_personality_evolution.py
backend/tests/test_personality_guard.py
backend/tests/test_personality_history_model.py
```

- [ ] **Step 4: Verify py_compile for all new modules**

Run:
```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m py_compile \
  app/models/personality_history.py \
  app/personality/__init__.py \
  app/personality/guard.py \
  app/personality/prompts.py \
  app/personality/evolution.py \
  alembic/versions/006_add_personality_history.py \
  && echo "All files compile OK"
```

Expected: `All files compile OK`

- [ ] **Step 5: Final commit if any cleanup needed**

```bash
cd /Users/jimmy/Downloads/Skills-World
git status
# Commit any uncommitted changes
git add -A && git commit -m "chore(personality): final cleanup for P4 personality evolution system"
```
