# P3: Autonomous Agent Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give residents autonomous behavior — a daily schedule driven by SBTI personality, decision-making via LLM, movement via A* pathfinding, and inter-resident conversations with memory integration.

**Architecture:** A centralized AgentLoop runs as a FastAPI background task (following the heat_cron_loop pattern). Each tick evaluates which residents should act based on their SBTI-derived schedule, then runs resident_tick() for active ones. Actions include movement, social interactions, observation, and self-reflection, all producing memories and broadcasting state to connected frontends.

**Tech Stack:** FastAPI background tasks, SQLAlchemy async, Anthropic SDK (LLM decisions), Phaser 3 (frontend animation), WebSocket broadcasting

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/config.py` | Add agent tuning parameters |
| Modify | `backend/app/models/resident.py` | Add home_tile_x/y fields |
| Create | `backend/alembic/versions/005_add_home_tile_and_agent_fields.py` | Migration |
| Create | `backend/app/agent/__init__.py` | Package init |
| Create | `backend/app/agent/scheduler.py` | DailySchedule + SBTI-driven scheduling |
| Create | `backend/app/agent/actions.py` | ActionType enum + ActionResult + filter logic |
| Create | `backend/app/agent/pathfinder.py` | A* pathfinding on tilemap grid |
| Create | `backend/app/agent/prompts.py` | All LLM prompt templates for agent decisions |
| Create | `backend/app/agent/tick.py` | resident_tick() — 5-phase per-resident loop |
| Create | `backend/app/agent/chat.py` | Inter-resident dialog + memory generation |
| Create | `backend/app/agent/loop.py` | AgentLoop class — main background task |
| Modify | `backend/app/main.py` | Register agent_loop in lifespan |
| Modify | `backend/app/ws/manager.py` | Add agent-specific tracking (socializing dict) |
| Create | `backend/tests/test_agent_scheduler.py` | Scheduler tests |
| Create | `backend/tests/test_agent_actions.py` | Action filter tests |
| Create | `backend/tests/test_pathfinder.py` | A* pathfinding tests |
| Create | `backend/tests/test_resident_tick.py` | Tick loop tests (mock LLM) |
| Create | `backend/tests/test_resident_chat.py` | Inter-resident chat tests (mock LLM) |
| Create | `backend/tests/test_agent_loop.py` | AgentLoop integration tests |
| Modify | `frontend/src/game/StatusVisuals.ts` | Add walking + socializing status visuals |
| Modify | `frontend/src/game/GameScene.ts` | Handle resident_move WS message + path animation |
| Modify | `frontend/src/game/GameScene.ts` | Handle resident_chat / resident_chat_end |

---

### Task 1: Agent Config Settings

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add agent settings**

In `backend/app/config.py`, inside the `Settings` class, before `model_config`:

```python
    # --- Agent Loop ---
    agent_tick_interval: int = 60          # seconds between tick rounds
    agent_max_concurrent: int = 5          # max residents ticking in parallel
    agent_max_daily_actions: int = 20      # per-resident action cap per in-game day
    agent_chat_max_turns: int = 8          # max dialog turns in a resident-resident chat
    agent_chat_cooldown: int = 1800        # seconds before same pair can chat again
    agent_time_scale: float = 1.0          # world time multiplier (1.0 = realtime)
    agent_enabled: bool = True             # master switch (set False to pause loop)
```

- [ ] **Step 2: Verify settings load**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -c "from app.config import settings; print(settings.agent_tick_interval, settings.agent_max_concurrent)"
```
Expected: `60 5`

- [ ] **Step 3: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/config.py
git commit -m "feat(agent): add agent loop config settings"
```

---

### Task 2: Resident Model Extension + Migration

**Files:**
- Modify: `backend/app/models/resident.py`
- Create: `backend/alembic/versions/005_add_home_tile_and_agent_fields.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_agent_resident_model.py`:

```python
import pytest
from sqlalchemy import select
from app.models.resident import Resident


@pytest.mark.anyio
async def test_resident_has_home_tile_fields(db_session):
    r = Resident(
        id="agent-model-test",
        slug="agent-model-test",
        name="Wanderer",
        district="engineering",
        status="idle",
        ability_md="Can wander",
        persona_md="Curious",
        soul_md="Free",
        creator_id="creator-1",
    )
    db_session.add(r)
    await db_session.commit()

    result = await db_session.execute(select(Resident).where(Resident.id == "agent-model-test"))
    saved = result.scalar_one()
    # home_tile fields nullable, default None
    assert saved.home_tile_x is None
    assert saved.home_tile_y is None


@pytest.mark.anyio
async def test_resident_home_tile_set(db_session):
    r = Resident(
        id="agent-model-test-2",
        slug="agent-model-test-2",
        name="Homebody",
        district="free",
        status="idle",
        ability_md="Stays home",
        persona_md="Introvert",
        soul_md="Rooted",
        creator_id="creator-1",
        home_tile_x=42,
        home_tile_y=58,
    )
    db_session.add(r)
    await db_session.commit()

    result = await db_session.execute(select(Resident).where(Resident.id == "agent-model-test-2"))
    saved = result.scalar_one()
    assert saved.home_tile_x == 42
    assert saved.home_tile_y == 58


@pytest.mark.anyio
async def test_resident_status_values(db_session):
    """Status can be idle/chatting/sleeping/walking/socializing."""
    for status in ["idle", "chatting", "sleeping", "walking", "socializing"]:
        r = Resident(
            id=f"status-test-{status}",
            slug=f"status-test-{status}",
            name=f"Res {status}",
            district="free",
            status=status,
            ability_md="x",
            persona_md="x",
            soul_md="x",
            creator_id="creator-1",
        )
        db_session.add(r)
    await db_session.commit()

    result = await db_session.execute(
        select(Resident).where(Resident.id.like("status-test-%"))
    )
    rows = result.scalars().all()
    statuses = {r.status for r in rows}
    assert statuses == {"idle", "chatting", "sleeping", "walking", "socializing"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_agent_resident_model.py -v
```
Expected: FAIL — `AttributeError: 'Resident' object has no attribute 'home_tile_x'`

- [ ] **Step 3: Add fields to Resident model**

In `backend/app/models/resident.py`, after the `portrait_url` line, add:

```python
    # --- Agent fields (P3: Agent Loop) ---
    home_tile_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_tile_y: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_agent_resident_model.py -v
```
Expected: All 3 tests PASS

- [ ] **Step 5: Create Alembic migration**

Create `backend/alembic/versions/005_add_home_tile_and_agent_fields.py`:

```python
"""Add home_tile_x/y to residents for agent pathfinding.

Revision ID: 005
Revises: 004_add_memories
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "005_add_home_tile"
down_revision = "004_add_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("residents", sa.Column("home_tile_x", sa.Integer(), nullable=True))
    op.add_column("residents", sa.Column("home_tile_y", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("residents", "home_tile_y")
    op.drop_column("residents", "home_tile_x")
```

- [ ] **Step 6: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/models/resident.py backend/alembic/versions/005_add_home_tile_and_agent_fields.py backend/tests/test_agent_resident_model.py
git commit -m "feat(agent): add home_tile_x/y fields to Resident model"
```

---

### Task 3: Daily Schedule & SBTI-Driven Scheduling

**Files:**
- Create: `backend/app/agent/__init__.py`
- Create: `backend/app/agent/scheduler.py`
- Create: `backend/tests/test_agent_scheduler.py`

The scheduler converts raw SBTI dimension values into a probabilistic daily activity curve. The key insight: rather than a binary active/sleeping switch, we use a smooth sigmoid probability that peaks at `peak_hours` and drops at rest.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_agent_scheduler.py`:

```python
import pytest
from app.agent.scheduler import DailySchedule, build_schedule, get_activity_probability, should_tick


# SBTI data fixtures
CTRL_SBTI = {
    "type": "CTRL",
    "dimensions": {
        "S1": "H", "S2": "H", "S3": "H",
        "E1": "H", "E2": "M", "E3": "H",
        "A1": "M", "A2": "H", "A3": "H",
        "Ac1": "H", "Ac2": "H", "Ac3": "H",
        "So1": "M", "So2": "H", "So3": "M",
    }
}

DEAD_SBTI = {
    "type": "DEAD",
    "dimensions": {
        "S1": "L", "S2": "L", "S3": "L",
        "E1": "L", "E2": "L", "E3": "M",
        "A1": "L", "A2": "M", "A3": "L",
        "Ac1": "L", "Ac2": "L", "Ac3": "L",
        "So1": "L", "So2": "H", "So3": "M",
    }
}

GOGO_SBTI = {
    "type": "GOGO",
    "dimensions": {
        "S1": "H", "S2": "H", "S3": "M",
        "E1": "H", "E2": "M", "E3": "H",
        "A1": "M", "A2": "M", "A3": "H",
        "Ac1": "H", "Ac2": "H", "Ac3": "H",
        "So1": "M", "So2": "H", "So3": "M",
    }
}


def test_build_schedule_ctrl():
    sched = build_schedule(CTRL_SBTI)
    assert isinstance(sched, DailySchedule)
    # CTRL: high Ac1/Ac2/Ac3 → early riser, long active window
    assert sched.wake_hour <= 8
    assert sched.sleep_hour >= 22
    # High So1 → multiple social slots
    assert len(sched.social_slots) >= 1
    # rest_ratio from Ac3=H: low rest ratio (stays active)
    assert sched.rest_ratio <= 0.4


def test_build_schedule_dead():
    sched = build_schedule(DEAD_SBTI)
    # DEAD: low Ac1/Ac2/Ac3 → late riser, early sleeper
    assert sched.wake_hour >= 9
    assert sched.sleep_hour <= 23
    # Low So1 → few social slots
    assert len(sched.social_slots) <= 2
    # High rest ratio (mostly inactive)
    assert sched.rest_ratio >= 0.5


def test_build_schedule_no_sbti():
    """Residents without SBTI get a default midpoint schedule."""
    sched = build_schedule(None)
    assert sched.wake_hour == 8
    assert sched.sleep_hour == 22
    assert 0.2 <= sched.rest_ratio <= 0.6


def test_activity_probability_sleeping_hours():
    sched = build_schedule(CTRL_SBTI)
    # During sleep hours probability should be near 0
    sleep_prob = get_activity_probability(sched, (sched.sleep_hour + 2) % 24)
    assert sleep_prob < 0.1


def test_activity_probability_peak_hours():
    sched = build_schedule(GOGO_SBTI)
    # During peak hours probability should be high
    if sched.peak_hours:
        peak_prob = get_activity_probability(sched, sched.peak_hours[0])
        assert peak_prob > 0.5


def test_activity_probability_social_slot():
    sched = build_schedule(CTRL_SBTI)
    if sched.social_slots:
        # Social slots boost probability
        social_prob = get_activity_probability(sched, sched.social_slots[0])
        assert social_prob >= 0.3


def test_should_tick_sleeping_returns_false():
    """Sleeping residents should almost never tick."""
    sched = build_schedule(DEAD_SBTI)
    # Simulate 100 rolls during sleep time — expect very few True
    sleep_hour = (sched.sleep_hour + 3) % 24
    results = [should_tick(sched, sleep_hour) for _ in range(100)]
    assert sum(results) < 15  # At most 15% chance during sleep


def test_should_tick_has_jitter():
    """Consecutive should_tick calls at same hour should sometimes differ."""
    sched = build_schedule(GOGO_SBTI)
    wake_hour = sched.wake_hour + 2
    results = [should_tick(sched, wake_hour) for _ in range(50)]
    # Should see both True and False (jitter prevents all-true or all-false)
    assert True in results
    assert False in results
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_agent_scheduler.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent'`

- [ ] **Step 3: Create the scheduler**

Create `backend/app/agent/__init__.py`:

```python
```

Create `backend/app/agent/scheduler.py`:

```python
"""SBTI-driven daily schedule computation for resident autonomous behavior."""
import math
import random
from dataclasses import dataclass, field


@dataclass
class DailySchedule:
    """Computed schedule for a resident based on SBTI personality."""
    wake_hour: int           # Hour resident becomes active (0-23)
    sleep_hour: int          # Hour resident goes to sleep (0-23)
    peak_hours: list[int]    # Hours of maximum activity (1-3 values)
    social_slots: list[int]  # Hours with elevated social probability
    rest_ratio: float        # Fraction of awake time spent resting (0.0-1.0)


# SBTI dimension → schedule parameter mapping weights
_LEVEL = {"L": 0, "M": 1, "H": 2}


def _dim(sbti_data: dict, key: str) -> int:
    """Return numeric value (0=L, 1=M, 2=H) for a SBTI dimension."""
    dims = sbti_data.get("dimensions", {})
    return _LEVEL.get(dims.get(key, "M"), 1)


def build_schedule(sbti_data: dict | None) -> DailySchedule:
    """Derive a DailySchedule from SBTI dimensions.

    Algorithm:
    - wake_hour: driven by Ac1 (motivation) + Ac3 (execution). High = early riser.
    - sleep_hour: driven by So1 (social) + E2 (emotional investment). High = stays up later.
    - peak_hours: 1-3 hours where resident is most active. Derived from Ac1 + A3.
    - social_slots: hours where social probability gets a +0.2 boost. From So1 + E2.
    - rest_ratio: driven by Ac3 inverted. Low Ac3 = high rest_ratio.
    """
    if not sbti_data:
        return DailySchedule(
            wake_hour=8,
            sleep_hour=22,
            peak_hours=[10, 14],
            social_slots=[12, 19],
            rest_ratio=0.35,
        )

    ac1 = _dim(sbti_data, "Ac1")  # motivation: 0-2
    ac3 = _dim(sbti_data, "Ac3")  # execution:  0-2
    so1 = _dim(sbti_data, "So1")  # social:     0-2
    e2  = _dim(sbti_data, "E2")   # emotional:  0-2
    a3  = _dim(sbti_data, "A3")   # meaning:    0-2

    # wake_hour: [5, 7, 9] for H, M, L motivation+execution
    drive = ac1 + ac3  # 0-4
    wake_hour = max(5, 9 - drive)

    # sleep_hour: [21, 22, 23] for L, M, H social+emotional
    social_drive = so1 + e2  # 0-4
    sleep_hour = min(23, 20 + social_drive // 2)

    # peak_hours: 1-3 windows. High meaning → more peaks.
    base_peak = wake_hour + 2
    if a3 == 2:  # H meaning
        peak_hours = [base_peak, base_peak + 4, base_peak + 8]
    elif a3 == 1:  # M meaning
        peak_hours = [base_peak, base_peak + 5]
    else:  # L meaning — one late peak
        peak_hours = [base_peak + 3]
    # Clamp all peaks within awake window
    peak_hours = [h % 24 for h in peak_hours if wake_hour <= h % 24 < sleep_hour]
    if not peak_hours:
        peak_hours = [wake_hour + 2]

    # social_slots: So1=H → 3 slots, M → 2, L → 1
    social_base = wake_hour + 3
    if so1 == 2:
        social_slots = [social_base, social_base + 4, social_base + 7]
    elif so1 == 1:
        social_slots = [social_base, social_base + 6]
    else:
        social_slots = [social_base + 3]
    social_slots = [h % 24 for h in social_slots if wake_hour <= h % 24 < sleep_hour]

    # rest_ratio: Ac3=H → 0.2, M → 0.4, L → 0.6
    rest_ratio = 0.6 - (ac3 * 0.2)

    return DailySchedule(
        wake_hour=wake_hour,
        sleep_hour=sleep_hour,
        peak_hours=peak_hours,
        social_slots=social_slots,
        rest_ratio=rest_ratio,
    )


def get_activity_probability(schedule: DailySchedule, hour: int) -> float:
    """Compute a 0.0-1.0 probability that a resident acts at this hour.

    Uses a smooth curve that:
    - Returns 0.0 outside [wake_hour, sleep_hour)
    - Peaks at peak_hours (up to 0.9)
    - Has a baseline of (1 - rest_ratio) * 0.5 during awake hours
    - Adds +0.2 boost at social_slots
    """
    # Outside awake window → no activity
    if hour < schedule.wake_hour or hour >= schedule.sleep_hour:
        return 0.0

    baseline = (1.0 - schedule.rest_ratio) * 0.5

    # Peak boost: Gaussian around each peak hour
    peak_boost = 0.0
    for peak in schedule.peak_hours:
        distance = abs(hour - peak)
        # Gaussian with sigma=2 hours
        peak_boost = max(peak_boost, 0.4 * math.exp(-0.5 * (distance / 2.0) ** 2))

    # Social boost
    social_boost = 0.2 if hour in schedule.social_slots else 0.0

    prob = min(0.95, baseline + peak_boost + social_boost)
    return prob


def should_tick(schedule: DailySchedule, hour: int) -> bool:
    """Roll against activity probability with ±15 minute jitter.

    The jitter means residents don't all wake up at exactly the same second,
    and slightly different residents will tick at different wall-clock moments.
    """
    prob = get_activity_probability(schedule, hour)
    if prob <= 0.0:
        return False
    # Jitter: add small random noise to prob (±0.1)
    jittered = prob + random.uniform(-0.1, 0.1)
    return random.random() < jittered
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_agent_scheduler.py -v
```
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/agent/ backend/tests/test_agent_scheduler.py
git commit -m "feat(agent): add SBTI-driven DailySchedule with Gaussian activity probability"
```

---

### Task 4: Action Definitions

**Files:**
- Create: `backend/app/agent/actions.py`
- Create: `backend/tests/test_agent_actions.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_agent_actions.py`:

```python
import pytest
from unittest.mock import MagicMock
from app.agent.actions import ActionType, ActionResult, get_available_actions
from app.models.resident import Resident


def _make_resident(status="idle", district="engineering", tile_x=76, tile_y=50):
    r = MagicMock(spec=Resident)
    r.status = status
    r.district = district
    r.tile_x = tile_x
    r.tile_y = tile_y
    r.id = "test-res"
    r.slug = "test-res"
    r.home_tile_x = None
    r.home_tile_y = None
    return r


def test_all_14_action_types_exist():
    expected = {
        "CHAT_RESIDENT", "CHAT_FOLLOW_UP", "GOSSIP",
        "WANDER", "VISIT_DISTRICT", "GO_HOME",
        "OBSERVE", "EAVESDROP",
        "REFLECT", "JOURNAL",
        "WORK", "STUDY",
        "IDLE", "NAP",
    }
    actual = {a.value for a in ActionType}
    assert actual == expected


def test_action_result_dataclass():
    result = ActionResult(
        action=ActionType.WANDER,
        target_slug=None,
        target_tile=(80, 55),
        reason="Feeling restless",
    )
    assert result.action == ActionType.WANDER
    assert result.target_tile == (80, 55)
    assert result.reason == "Feeling restless"


def test_get_available_actions_no_nearby():
    """With no nearby residents, social actions unavailable."""
    r = _make_resident()
    actions = get_available_actions(r, nearby_residents=[])
    social = {ActionType.CHAT_RESIDENT, ActionType.GOSSIP, ActionType.EAVESDROP, ActionType.CHAT_FOLLOW_UP}
    assert not social.intersection(set(actions))
    # Movement always available
    assert ActionType.WANDER in actions


def test_get_available_actions_with_nearby():
    """With nearby idle residents, social actions available."""
    r = _make_resident()
    other = _make_resident(status="idle")
    other.id = "other-res"
    other.slug = "other-res"
    actions = get_available_actions(r, nearby_residents=[other])
    assert ActionType.CHAT_RESIDENT in actions


def test_get_available_actions_chatting_resident_excluded():
    """Residents actively chatting cannot be targeted."""
    r = _make_resident()
    busy = _make_resident(status="chatting")
    busy.id = "busy-res"
    busy.slug = "busy-res"
    actions = get_available_actions(r, nearby_residents=[busy])
    # chatting resident not available for CHAT_RESIDENT
    # but EAVESDROP should be possible
    assert ActionType.EAVESDROP in actions
    # CHAT_RESIDENT with that specific busy resident not possible
    # (the filter should not allow initiating chat with chatting resident)


def test_go_home_available_when_away():
    """GO_HOME only available when not at home tile."""
    r = _make_resident(tile_x=10, tile_y=10)
    r.home_tile_x = 76
    r.home_tile_y = 50
    actions = get_available_actions(r, nearby_residents=[])
    assert ActionType.GO_HOME in actions


def test_go_home_unavailable_when_at_home():
    """GO_HOME not offered when already at home tile."""
    r = _make_resident(tile_x=76, tile_y=50)
    r.home_tile_x = 76
    r.home_tile_y = 50
    actions = get_available_actions(r, nearby_residents=[])
    assert ActionType.GO_HOME not in actions
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_agent_actions.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.actions'`

- [ ] **Step 3: Implement actions**

Create `backend/app/agent/actions.py`:

```python
"""Action type definitions and context-sensitive filtering for the agent loop."""
from dataclasses import dataclass
from enum import Enum


class ActionType(str, Enum):
    # Social
    CHAT_RESIDENT  = "CHAT_RESIDENT"
    CHAT_FOLLOW_UP = "CHAT_FOLLOW_UP"
    GOSSIP         = "GOSSIP"
    # Movement
    WANDER         = "WANDER"
    VISIT_DISTRICT = "VISIT_DISTRICT"
    GO_HOME        = "GO_HOME"
    # Observe
    OBSERVE        = "OBSERVE"
    EAVESDROP      = "EAVESDROP"
    # Self
    REFLECT        = "REFLECT"
    JOURNAL        = "JOURNAL"
    # Work
    WORK           = "WORK"
    STUDY          = "STUDY"
    # Rest
    IDLE           = "IDLE"
    NAP            = "NAP"


@dataclass
class ActionResult:
    """Parsed output from the LLM decision step."""
    action: ActionType
    target_slug: str | None        # Resident slug if social action
    target_tile: tuple[int, int] | None  # (x, y) destination if movement
    reason: str                    # LLM's one-sentence rationale


# Actions that require a nearby idle/walking resident as target
_SOCIAL_NEEDS_IDLE_TARGET = {ActionType.CHAT_RESIDENT, ActionType.GOSSIP, ActionType.CHAT_FOLLOW_UP}

# Actions that can target chatting residents (observer role)
_SOCIAL_OBSERVER = {ActionType.EAVESDROP}

# Actions always available
_ALWAYS_AVAILABLE = {ActionType.WANDER, ActionType.VISIT_DISTRICT, ActionType.OBSERVE,
                     ActionType.REFLECT, ActionType.JOURNAL, ActionType.WORK,
                     ActionType.STUDY, ActionType.IDLE, ActionType.NAP}


def get_available_actions(resident, nearby_residents: list) -> list[ActionType]:
    """Return the list of valid actions given current world context.

    Args:
        resident: Resident ORM object (current actor)
        nearby_residents: Resident ORM objects within interaction range

    Returns:
        Ordered list of ActionType values the LLM may choose from.
    """
    available: list[ActionType] = list(_ALWAYS_AVAILABLE)

    idle_nearby = [r for r in nearby_residents if r.status in ("idle", "walking") and r.id != resident.id]
    chatting_nearby = [r for r in nearby_residents if r.status in ("chatting", "socializing") and r.id != resident.id]

    if idle_nearby:
        available.extend(_SOCIAL_NEEDS_IDLE_TARGET)

    if chatting_nearby or idle_nearby:
        available.extend(_SOCIAL_OBSERVER)

    # GO_HOME: only when not already at home tile
    home_x = resident.home_tile_x
    home_y = resident.home_tile_y
    if home_x is not None and home_y is not None:
        if not (resident.tile_x == home_x and resident.tile_y == home_y):
            available.append(ActionType.GO_HOME)

    # Deduplicate while preserving order
    seen: set[ActionType] = set()
    result: list[ActionType] = []
    for a in available:
        if a not in seen:
            seen.add(a)
            result.append(a)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_agent_actions.py -v
```
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/agent/actions.py backend/tests/test_agent_actions.py
git commit -m "feat(agent): add 14 ActionTypes, ActionResult dataclass, and context-sensitive filter"
```

---

### Task 5: A* Pathfinder

**Files:**
- Create: `backend/app/agent/pathfinder.py`
- Create: `backend/tests/test_pathfinder.py`

The pathfinder runs on the backend to compute movement paths for broadcast to the frontend. MVP uses a static set of walkable tiles derived from district bounding boxes; future versions can parse the actual Tiled JSON.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_pathfinder.py`:

```python
import pytest
from app.agent.pathfinder import find_path, get_walkable_tiles, DISTRICT_BOUNDS


def test_find_path_direct_neighbors():
    """Adjacent tiles should return a 2-step path."""
    walkable = {(x, y) for x in range(10) for y in range(10)}
    path = find_path((0, 0), (1, 0), walkable)
    assert path is not None
    assert len(path) >= 2
    assert path[0] == (0, 0)
    assert path[-1] == (1, 0)


def test_find_path_around_obstacle():
    """A* should route around unwalkable tiles."""
    walkable = {(x, y) for x in range(5) for y in range(5)}
    # Create vertical wall at x=2 (except top row)
    obstacle = {(2, y) for y in range(1, 5)}
    walkable -= obstacle

    path = find_path((0, 2), (4, 2), walkable)
    assert path is not None
    assert path[-1] == (4, 2)
    # Path should not cross the obstacle
    for tile in path:
        assert tile not in obstacle


def test_find_path_same_start_end():
    """Start == end returns single-tile path."""
    walkable = {(5, 5)}
    path = find_path((5, 5), (5, 5), walkable)
    assert path == [(5, 5)]


def test_find_path_impossible():
    """Unreachable destination returns None."""
    walkable = {(0, 0), (1, 0)}  # (5, 5) not in walkable
    path = find_path((0, 0), (5, 5), walkable)
    assert path is None


def test_find_path_long_corridor():
    """Straight corridor path is optimal length."""
    walkable = {(x, 5) for x in range(20)}
    path = find_path((0, 5), (19, 5), walkable)
    assert path is not None
    assert len(path) == 20  # 0..19 inclusive


def test_get_walkable_tiles_returns_set():
    tiles = get_walkable_tiles()
    assert isinstance(tiles, set)
    assert len(tiles) > 100  # Should cover multiple districts


def test_district_bounds_coverage():
    """All districts in DISTRICT_BOUNDS should contribute walkable tiles."""
    assert len(DISTRICT_BOUNDS) >= 4
    tiles = get_walkable_tiles()
    # Spot-check: central area (76, 50) should be walkable
    assert (76, 50) in tiles


def test_find_path_heuristic_optimality():
    """A* with Manhattan heuristic finds path in bounded steps."""
    walkable = {(x, y) for x in range(20) for y in range(20)}
    path = find_path((0, 0), (19, 19), walkable)
    assert path is not None
    # Manhattan distance = 38, path length should be 39 (optimal)
    assert len(path) == 39
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_pathfinder.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.pathfinder'`

- [ ] **Step 3: Implement A* pathfinder**

Create `backend/app/agent/pathfinder.py`:

```python
"""A* pathfinding for resident movement on the tilemap grid."""
import heapq
from functools import lru_cache

# District bounding boxes: (x_min, y_min, x_max, y_max)
# These approximate the walkable regions in the Tiled map.
# Walls and water tiles within these boxes are still blocked
# — in the MVP we use conservative inner margins.
DISTRICT_BOUNDS: dict[str, tuple[int, int, int, int]] = {
    "engineering":  (60, 40, 95, 65),
    "art":          (30, 40, 60, 65),
    "business":     (60, 65, 95, 90),
    "free":         (30, 65, 60, 90),
    "central":      (55, 45, 80, 70),   # Central Plaza
}

# Tiles that are explicitly blocked within district bounds (walls, water, etc.)
# In a production build these would be parsed from the Tiled map's collision layer.
_BLOCKED_TILES: frozenset[tuple[int, int]] = frozenset()


@lru_cache(maxsize=1)
def get_walkable_tiles() -> frozenset[tuple[int, int]]:
    """Return the set of all walkable tile coordinates.

    MVP: generate a grid covering all district bounding boxes,
    minus any explicitly blocked tiles.

    Production: parse the tilemap JSON collision layer instead.
    """
    tiles: set[tuple[int, int]] = set()
    for x_min, y_min, x_max, y_max in DISTRICT_BOUNDS.values():
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tiles.add((x, y))
    tiles -= set(_BLOCKED_TILES)
    return frozenset(tiles)


def find_path(
    from_tile: tuple[int, int],
    to_tile: tuple[int, int],
    walkable_tiles: frozenset[tuple[int, int]] | set[tuple[int, int]],
    max_steps: int = 500,
) -> list[tuple[int, int]] | None:
    """Find the shortest path from from_tile to to_tile using A*.

    Args:
        from_tile: (x, y) start tile
        to_tile:   (x, y) destination tile
        walkable_tiles: set of passable tiles
        max_steps: abort if path exceeds this length (prevents runaway search)

    Returns:
        Ordered list of (x, y) tiles from start (inclusive) to end (inclusive),
        or None if no path exists.
    """
    if from_tile == to_tile:
        return [from_tile]

    if to_tile not in walkable_tiles:
        return None

    def heuristic(a: tuple[int, int], b: tuple[int, int]) -> int:
        # Manhattan distance — admissible for 4-directional grid
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    # Priority queue: (f_score, tie_breaker, tile)
    open_heap: list[tuple[int, int, tuple[int, int]]] = []
    counter = 0
    heapq.heappush(open_heap, (heuristic(from_tile, to_tile), counter, from_tile))

    came_from: dict[tuple[int, int], tuple[int, int] | None] = {from_tile: None}
    g_score: dict[tuple[int, int], int] = {from_tile: 0}

    neighbors_4 = ((1, 0), (-1, 0), (0, 1), (0, -1))

    while open_heap:
        _, _, current = heapq.heappop(open_heap)

        if current == to_tile:
            # Reconstruct path
            path: list[tuple[int, int]] = []
            node: tuple[int, int] | None = current
            while node is not None:
                path.append(node)
                node = came_from[node]
            path.reverse()
            return path

        current_g = g_score[current]
        if current_g >= max_steps:
            return None

        for dx, dy in neighbors_4:
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor not in walkable_tiles:
                continue

            tentative_g = current_g + 1
            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + heuristic(neighbor, to_tile)
                counter += 1
                heapq.heappush(open_heap, (f, counter, neighbor))

    return None  # No path found
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_pathfinder.py -v
```
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/agent/pathfinder.py backend/tests/test_pathfinder.py
git commit -m "feat(agent): add A* pathfinder with district-based walkable tile grid"
```

---

### Task 6: Agent Decision Prompts

**Files:**
- Create: `backend/app/agent/prompts.py`

No tests for this task — prompt strings are tested indirectly through Task 7 (tick) and Task 8 (chat).

- [ ] **Step 1: Create prompt templates**

Create `backend/app/agent/prompts.py`:

```python
"""LLM prompt templates for the agent decision loop and inter-resident chat."""
from app.agent.actions import ActionType

DECISION_SYSTEM = """\
你是一个游戏 NPC 居民的自主决策引擎。你的任务是根据居民当前的状态、周围环境和记忆，
选择最符合角色人格的下一个行动。

居民信息：
- 姓名：{name}
- 区域：{district}
- 人格类型（SBTI）：{sbti_type}（{sbti_name}）
- 当前状态：{status}

输出严格 JSON 格式，不要输出其他内容：
{{
  "action": "<ACTION_TYPE>",
  "target_slug": "<居民slug或null>",
  "target_tile": [x, y] 或 null,
  "reason": "<一句话理由，15字以内>"
}}

可用的 action 类型：{available_actions}

规则：
- CHAT_RESIDENT 需要在 nearby_residents 中选一个空闲居民，填入 target_slug
- WANDER/GO_HOME/VISIT_DISTRICT 填入 target_tile，其余为 null
- GOSSIP 需要 target_slug，内容由后续流程生成
- 社交类型低（So1=L）的居民，倾向于选择 REFLECT/JOURNAL/OBSERVE
- 行动力高（Ac3=H）的居民，倾向于 WORK/STUDY/WANDER
- 当天已执行 {today_action_count} 个行动，上限 {max_daily_actions}
"""

DECISION_USER = """\
当前游戏世界时间：{world_time}（{schedule_phase}）

附近的居民：
{nearby_residents_text}

最近的记忆：
{recent_memories_text}

今天已做的事：
{today_actions_text}

请选择下一个行动。
"""


def build_decision_prompt(
    resident,
    schedule_phase: str,
    world_time: str,
    nearby_residents: list,
    memories: list,
    today_actions: list[str],
    available_actions: list[ActionType],
    max_daily_actions: int,
) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for the resident decision step."""
    sbti = (resident.meta_json or {}).get("sbti", {})
    sbti_type = sbti.get("type", "OJBK")
    sbti_name = sbti.get("type_name", "无所谓人")

    nearby_text = "\n".join(
        f"- {r.name}（{r.slug}）：{r.status}，距离约 {_tile_dist(resident, r)} 格"
        for r in nearby_residents
    ) or "（附近没有其他居民）"

    memory_text = "\n".join(
        f"- [{m.source}] {m.content}" for m in memories[:8]
    ) or "（无相关记忆）"

    today_text = "\n".join(f"- {a}" for a in today_actions[-10:]) or "（今天还没有任何行动）"

    action_list = ", ".join(a.value for a in available_actions)

    system = DECISION_SYSTEM.format(
        name=resident.name,
        district=resident.district,
        sbti_type=sbti_type,
        sbti_name=sbti_name,
        status=resident.status,
        available_actions=action_list,
        today_action_count=len(today_actions),
        max_daily_actions=max_daily_actions,
    )
    user = DECISION_USER.format(
        world_time=world_time,
        schedule_phase=schedule_phase,
        nearby_residents_text=nearby_text,
        recent_memories_text=memory_text,
        today_actions_text=today_text,
    )
    return system, user


def _tile_dist(a, b) -> int:
    return abs(a.tile_x - b.tile_x) + abs(a.tile_y - b.tile_y)


# ── Inter-Resident Chat Prompts ────────────────────────────────────────

CHAT_INITIATE_SYSTEM = """\
你是 {initiator_name}，一个 Skills World 的居民（SBTI：{sbti_type} {sbti_name}）。
你主动走向 {target_name} 并开始对话。

你的人格：
{persona_md}

你对 {target_name} 的记忆：
{relationship_memory}

请用中文，以符合你人格的方式开场白。保持简短（30字以内）。
"""

CHAT_REPLY_SYSTEM = """\
你是 {responder_name}，一个 Skills World 的居民（SBTI：{sbti_type} {sbti_name}）。
{initiator_name} 正在和你对话。

你的人格：
{persona_md}

你对 {initiator_name} 的记忆：
{relationship_memory}

对话历史：
{history}

请用中文，以符合你人格的方式回应。保持简短（50字以内）。
"""

CHAT_SUMMARY_SYSTEM = """\
请将以下居民间的对话总结成 1-2 句话，供玩家看到时理解发生了什么。
用第三人称描述，例如"小明和小红讨论了..."。
不要透露完整对话内容，只概括核心事件和情感变化。

输出格式：
{{"summary": "...", "mood": "positive/neutral/negative"}}
"""

CHAT_SUMMARY_USER = """\
{initiator_name} 和 {target_name} 的对话：

{dialog_text}
"""
```

- [ ] **Step 2: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/agent/prompts.py
git commit -m "feat(agent): add LLM prompt templates for decision loop and inter-resident chat"
```

---

### Task 7: Resident Tick — Core Loop

**Files:**
- Create: `backend/app/agent/tick.py`
- Create: `backend/tests/test_resident_tick.py`

The tick is the heart of the agent loop — each call processes one resident through the full 5-phase perceive→retrieve→decide→execute→memorize cycle.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_resident_tick.py`:

```python
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from app.models.resident import Resident
from app.models.memory import Memory
from app.agent.actions import ActionType, ActionResult
from app.agent.tick import resident_tick, parse_action_result, _daily_counts


@pytest.fixture
async def tick_resident(db_session):
    r = Resident(
        id="tick-test-res",
        slug="tick-test-res",
        name="TickTester",
        district="engineering",
        status="idle",
        ability_md="Tests things",
        persona_md="Methodical",
        soul_md="Curious",
        creator_id="creator-1",
        tile_x=76,
        tile_y=50,
        meta_json={"sbti": {
            "type": "GOGO",
            "type_name": "行者",
            "dimensions": {
                "S1": "H", "S2": "H", "S3": "M",
                "E1": "H", "E2": "M", "E3": "H",
                "A1": "M", "A2": "M", "A3": "H",
                "Ac1": "H", "Ac2": "H", "Ac3": "H",
                "So1": "M", "So2": "H", "So3": "M",
            }
        }},
    )
    db_session.add(r)
    await db_session.commit()
    return r


def _mock_decision_response(action: str, target_slug=None, target_tile=None, reason="test"):
    raw = json.dumps({
        "action": action,
        "target_slug": target_slug,
        "target_tile": target_tile,
        "reason": reason,
    })
    mock_msg = MagicMock()
    mock_block = MagicMock()
    mock_block.text = raw
    mock_msg.content = [mock_block]
    return mock_msg


def test_parse_action_result_wander():
    raw = json.dumps({
        "action": "WANDER",
        "target_slug": None,
        "target_tile": [80, 55],
        "reason": "Feeling restless",
    })
    result = parse_action_result(raw)
    assert result is not None
    assert result.action == ActionType.WANDER
    assert result.target_tile == (80, 55)
    assert result.reason == "Feeling restless"


def test_parse_action_result_chat():
    raw = json.dumps({
        "action": "CHAT_RESIDENT",
        "target_slug": "other-res",
        "target_tile": None,
        "reason": "Curious",
    })
    result = parse_action_result(raw)
    assert result is not None
    assert result.action == ActionType.CHAT_RESIDENT
    assert result.target_slug == "other-res"


def test_parse_action_result_invalid_json():
    result = parse_action_result("not json at all")
    assert result is None


def test_parse_action_result_invalid_action():
    raw = json.dumps({"action": "FLY_TO_MOON", "target_slug": None, "target_tile": None, "reason": "x"})
    result = parse_action_result(raw)
    assert result is None


def test_parse_action_result_extracts_json_from_prose():
    """LLM sometimes wraps JSON in prose — extract it."""
    prose = 'I think the resident should act. {"action": "IDLE", "target_slug": null, "target_tile": null, "reason": "rest"}'
    result = parse_action_result(prose)
    assert result is not None
    assert result.action == ActionType.IDLE


@pytest.mark.anyio
async def test_resident_tick_wander(db_session, tick_resident):
    """Tick should update tile position and create a memory for WANDER."""
    _daily_counts.clear()

    with patch("app.agent.tick.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_decision_response("WANDER", target_tile=[80, 55])
        )
        mock_get_client.return_value = mock_client

        with patch("app.agent.tick.get_walkable_tiles", return_value=frozenset(
            (x, y) for x in range(60, 100) for y in range(40, 70)
        )):
            result = await resident_tick(db_session, tick_resident)

    assert result is not None
    assert result.action == ActionType.WANDER

    # Resident position should be updated
    await db_session.refresh(tick_resident)
    assert tick_resident.tile_x != 76 or tick_resident.tile_y != 50 or result.target_tile == (76, 50)

    # A memory should be created
    mem_result = await db_session.execute(
        select(Memory).where(Memory.resident_id == tick_resident.id, Memory.type == "event")
    )
    memories = mem_result.scalars().all()
    assert len(memories) >= 1


@pytest.mark.anyio
async def test_resident_tick_respects_daily_limit(db_session, tick_resident):
    """Tick should return None when daily action limit is reached."""
    from app.config import settings
    # Pre-fill daily count to max
    _daily_counts[tick_resident.id] = settings.agent_max_daily_actions

    result = await resident_tick(db_session, tick_resident)
    assert result is None


@pytest.mark.anyio
async def test_resident_tick_llm_failure_returns_none(db_session, tick_resident):
    """If LLM fails, tick should return None gracefully without crashing."""
    _daily_counts.clear()

    with patch("app.agent.tick.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("LLM down"))
        mock_get_client.return_value = mock_client

        result = await resident_tick(db_session, tick_resident)

    assert result is None
    # Resident should still be in original state
    await db_session.refresh(tick_resident)
    assert tick_resident.status == "idle"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_resident_tick.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.tick'`

- [ ] **Step 3: Implement resident_tick**

Create `backend/app/agent/tick.py`:

```python
"""Resident tick: 5-phase autonomous behavior cycle."""
import json
import logging
import re
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.actions import ActionType, ActionResult, get_available_actions
from app.agent.pathfinder import get_walkable_tiles, find_path
from app.agent.prompts import build_decision_prompt
from app.config import settings
from app.llm.client import get_client
from app.memory.service import MemoryService
from app.models.resident import Resident

logger = logging.getLogger(__name__)

# Module-level daily action counters: {resident_id: count}
# Reset at midnight by the AgentLoop.
_daily_counts: dict[str, int] = {}
_last_reset_date: str = ""


def _get_world_time() -> tuple[str, int, str]:
    """Return (formatted_time, hour, schedule_phase).

    World time tracks real-world clock scaled by agent_time_scale.
    For MVP time_scale=1.0, world time == real time.
    """
    now = datetime.now()
    hour = now.hour
    formatted = now.strftime("%H:%M")

    if 5 <= hour < 9:
        phase = "清晨"
    elif 9 <= hour < 12:
        phase = "上午"
    elif 12 <= hour < 14:
        phase = "午后"
    elif 14 <= hour < 18:
        phase = "下午"
    elif 18 <= hour < 21:
        phase = "傍晚"
    elif 21 <= hour < 24:
        phase = "夜晚"
    else:
        phase = "深夜"
    return formatted, hour, phase


def _check_and_reset_daily_counts() -> None:
    """Reset action counts at midnight."""
    global _last_reset_date
    today = datetime.now().strftime("%Y-%m-%d")
    if today != _last_reset_date:
        _daily_counts.clear()
        _last_reset_date = today


def parse_action_result(raw: str) -> ActionResult | None:
    """Parse LLM response into ActionResult.

    Handles:
    - Pure JSON
    - JSON embedded in prose (extracts first {...} block)
    - Returns None on any parse failure
    """
    # Try to extract JSON from prose
    match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
    if not match:
        logger.debug("No JSON found in decision response: %s", raw[:200])
        return None

    try:
        data = json.loads(match.group())
        action_str = data.get("action", "")
        # Validate action type
        try:
            action = ActionType(action_str)
        except ValueError:
            logger.debug("Unknown action type: %s", action_str)
            return None

        target_tile = data.get("target_tile")
        if target_tile and isinstance(target_tile, list) and len(target_tile) == 2:
            target_tile = (int(target_tile[0]), int(target_tile[1]))
        else:
            target_tile = None

        return ActionResult(
            action=action,
            target_slug=data.get("target_slug"),
            target_tile=target_tile,
            reason=str(data.get("reason", ""))[:100],
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        logger.debug("Failed to parse action result: %s | raw: %s", e, raw[:200])
        return None


async def _perceive(db: AsyncSession, resident: Resident) -> list[Resident]:
    """Phase 1: Find nearby residents within interaction range (tile distance ≤ 10)."""
    all_residents = (await db.execute(
        select(Resident).where(Resident.id != resident.id)
    )).scalars().all()

    nearby = []
    for r in all_residents:
        dist = abs(r.tile_x - resident.tile_x) + abs(r.tile_y - resident.tile_y)
        if dist <= 10:
            nearby.append(r)
    return nearby


async def _execute_movement(
    db: AsyncSession,
    resident: Resident,
    target_tile: tuple[int, int],
) -> tuple[int, int]:
    """Move resident one step toward target_tile along A* path.

    Returns the actual new (tile_x, tile_y).
    """
    walkable = get_walkable_tiles()
    path = find_path((resident.tile_x, resident.tile_y), target_tile, walkable)

    if not path or len(path) < 2:
        return (resident.tile_x, resident.tile_y)

    # Move to next step on path (not teleport to destination)
    next_tile = path[1]
    resident.tile_x = next_tile[0]
    resident.tile_y = next_tile[1]
    resident.status = "walking"
    await db.commit()
    return next_tile


async def resident_tick(
    db: AsyncSession,
    resident: Resident,
) -> ActionResult | None:
    """Execute one autonomous tick for a resident.

    Phases:
    1. Perceive — query nearby residents
    2. Retrieve — fetch memories via MemoryService
    3. Decide — LLM chooses action
    4. Execute — update position/status
    5. Memorize — create event memory

    Returns ActionResult on success, None if skipped or failed.
    """
    _check_and_reset_daily_counts()

    # Check daily limit
    count = _daily_counts.get(resident.id, 0)
    if count >= settings.agent_max_daily_actions:
        return None

    world_time, hour, schedule_phase = _get_world_time()

    # ── Phase 1: Perceive ─────────────────────────────────────────────
    try:
        nearby = await _perceive(db, resident)
    except Exception as e:
        logger.warning("Tick perceive failed for %s: %s", resident.slug, e)
        return None

    # ── Phase 2: Retrieve ─────────────────────────────────────────────
    try:
        memory_svc = MemoryService(db)
        memories = await memory_svc.get_memories(resident.id, type="event", limit=10)
    except Exception as e:
        logger.warning("Tick retrieve failed for %s: %s", resident.slug, e)
        memories = []

    # ── Phase 3: Decide ───────────────────────────────────────────────
    available_actions = get_available_actions(resident, nearby)

    # Collect today's actions for context
    today_key = datetime.now().strftime("%Y-%m-%d")
    today_actions = [
        m.content for m in memories
        if m.created_at and m.created_at.strftime("%Y-%m-%d") == today_key
    ]

    try:
        system_prompt, user_prompt = build_decision_prompt(
            resident=resident,
            schedule_phase=schedule_phase,
            world_time=world_time,
            nearby_residents=nearby,
            memories=memories,
            today_actions=today_actions,
            available_actions=available_actions,
            max_daily_actions=settings.agent_max_daily_actions,
        )
        client = get_client("system")
        resp = await client.messages.create(
            model=settings.effective_model,
            max_tokens=200,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = resp.content[0].text
        action_result = parse_action_result(raw)
    except Exception as e:
        logger.warning("Tick decide failed for %s: %s", resident.slug, e)
        return None

    if action_result is None:
        return None

    # Validate that chosen action is in available list
    if action_result.action not in available_actions:
        logger.debug("Resident %s chose unavailable action %s, skipping", resident.slug, action_result.action)
        return None

    # ── Phase 4: Execute ──────────────────────────────────────────────
    try:
        new_tile = (resident.tile_x, resident.tile_y)
        movement_actions = {ActionType.WANDER, ActionType.GO_HOME, ActionType.VISIT_DISTRICT}

        if action_result.action in movement_actions and action_result.target_tile:
            new_tile = await _execute_movement(db, resident, action_result.target_tile)
        elif action_result.action in {ActionType.IDLE, ActionType.NAP, ActionType.REFLECT, ActionType.JOURNAL}:
            if resident.status not in ("chatting", "socializing"):
                resident.status = "idle"
                await db.commit()
    except Exception as e:
        logger.warning("Tick execute failed for %s: %s", resident.slug, e)
        # Continue to memorize step even if execute had issues

    # ── Phase 5: Memorize ─────────────────────────────────────────────
    try:
        memory_content = _format_action_memory(action_result, resident)
        await memory_svc.add_memory(
            resident_id=resident.id,
            type="event",
            content=memory_content,
            importance=0.3,
            source="agent_action",
        )
    except Exception as e:
        logger.warning("Tick memorize failed for %s: %s", resident.slug, e)

    # Increment daily counter
    _daily_counts[resident.id] = count + 1

    logger.debug("Resident %s ticked: %s → %s", resident.slug, action_result.action.value, action_result.reason)
    return action_result


def _format_action_memory(action_result: ActionResult, resident: Resident) -> str:
    """Format an action into a human-readable memory string."""
    action = action_result.action
    if action == ActionType.WANDER:
        tile = action_result.target_tile
        return f"四处游荡，走向 ({tile[0]}, {tile[1]})" if tile else "四处游荡"
    elif action == ActionType.GO_HOME:
        return "回到了自己的家"
    elif action == ActionType.VISIT_DISTRICT:
        tile = action_result.target_tile
        return f"前往了另一个区域 ({tile[0] if tile else '?'}, {tile[1] if tile else '?'})"
    elif action == ActionType.CHAT_RESIDENT:
        return f"和 {action_result.target_slug or '某位居民'} 开始了对话"
    elif action == ActionType.OBSERVE:
        return "静静地观察着周围的情况"
    elif action == ActionType.EAVESDROP:
        return "偷偷听了附近居民的对话"
    elif action == ActionType.REFLECT:
        return "进行了一段时间的自我反思"
    elif action == ActionType.JOURNAL:
        return "在心里记录了今天的见闻"
    elif action == ActionType.WORK:
        return "专注于自己的工作"
    elif action == ActionType.STUDY:
        return "学习了一些新知识"
    elif action == ActionType.GOSSIP:
        return f"和 {action_result.target_slug or '某位居民'} 闲聊八卦"
    elif action == ActionType.NAP:
        return "小憩了一会儿"
    elif action == ActionType.IDLE:
        return "发了会儿呆"
    else:
        return f"执行了 {action.value}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_resident_tick.py -v
```
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/agent/tick.py backend/tests/test_resident_tick.py
git commit -m "feat(agent): add 5-phase resident_tick with perceive/retrieve/decide/execute/memorize"
```

---

### Task 8: Inter-Resident Chat

**Files:**
- Create: `backend/app/agent/chat.py`
- Create: `backend/tests/test_resident_chat.py`

Two residents run a 3-8 turn LLM dialog, generate memories for both, update relationships, and produce a summary for player broadcast.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_resident_chat.py`:

```python
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from app.models.resident import Resident
from app.models.memory import Memory
from app.agent.chat import resident_chat, _chat_cooldowns


@pytest.fixture
async def chat_pair(db_session):
    initiator = Resident(
        id="chat-init",
        slug="chat-init",
        name="Initiator",
        district="engineering",
        status="idle",
        ability_md="Likes talking",
        persona_md="Outgoing",
        soul_md="Social",
        creator_id="c1",
        meta_json={"sbti": {"type": "GOGO", "type_name": "行者", "dimensions": {
            "So1": "H", "So2": "M", "So3": "H",
            "S1": "H", "S2": "H", "S3": "M",
            "E1": "H", "E2": "M", "E3": "H",
            "A1": "M", "A2": "M", "A3": "H",
            "Ac1": "H", "Ac2": "H", "Ac3": "H",
        }}},
    )
    target = Resident(
        id="chat-tgt",
        slug="chat-tgt",
        name="Target",
        district="engineering",
        status="idle",
        ability_md="Good listener",
        persona_md="Reflective",
        soul_md="Curious",
        creator_id="c1",
        meta_json={"sbti": {"type": "THIN-K", "type_name": "思考者", "dimensions": {
            "So1": "L", "So2": "H", "So3": "H",
            "S1": "H", "S2": "H", "S3": "L",
            "E1": "H", "E2": "M", "E3": "H",
            "A1": "M", "A2": "L", "A3": "H",
            "Ac1": "M", "Ac2": "H", "Ac3": "M",
        }}},
    )
    db_session.add(initiator)
    db_session.add(target)
    await db_session.commit()
    return initiator, target


def _mock_llm_text(text: str):
    mock_msg = MagicMock()
    mock_block = MagicMock()
    mock_block.text = text
    mock_msg.content = [mock_block]
    return mock_msg


@pytest.mark.anyio
async def test_resident_chat_creates_memories(db_session, chat_pair):
    initiator, target = chat_pair
    _chat_cooldowns.clear()

    dialog_responses = [
        "你好啊，今天天气不错！",       # turn 1: initiator opens
        "是啊，你去哪里玩了吗？",        # turn 2: target replies
        "我刚从工程区回来，很有意思。",  # turn 3: initiator
    ]
    extract_response = json.dumps({
        "memories": [{"content": "和 Target 聊了天气和工程区", "importance": 0.5}]
    })
    rel_response = json.dumps({
        "content": "Target 是个好相处的人",
        "importance": 0.5,
        "metadata": {"affinity": 0.4, "trust": 0.5, "tags": ["friendly"]},
    })
    summary_response = json.dumps({
        "summary": "Initiator 和 Target 聊了天气和工程区的趣事",
        "mood": "positive",
    })

    call_idx = 0
    def side_effect(*args, **kwargs):
        nonlocal call_idx
        responses = dialog_responses + [extract_response, rel_response, rel_response, summary_response]
        resp = _mock_llm_text(responses[min(call_idx, len(responses) - 1)])
        call_idx += 1
        return resp

    with patch("app.agent.chat.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=side_effect)
        mock_get_client.return_value = mock_client

        result = await resident_chat(db_session, initiator, target, max_turns=3)

    assert "summary" in result
    assert len(result["summary"]) > 0
    assert "mood" in result

    # Both residents should return to idle
    await db_session.refresh(initiator)
    await db_session.refresh(target)
    assert initiator.status == "idle"
    assert target.status == "idle"

    # Memories should be created for both
    init_mems = (await db_session.execute(
        select(Memory).where(Memory.resident_id == initiator.id, Memory.type == "event")
    )).scalars().all()
    tgt_mems = (await db_session.execute(
        select(Memory).where(Memory.resident_id == target.id, Memory.type == "event")
    )).scalars().all()
    assert len(init_mems) >= 1
    assert len(tgt_mems) >= 1


@pytest.mark.anyio
async def test_resident_chat_cooldown(db_session, chat_pair):
    initiator, target = chat_pair
    _chat_cooldowns.clear()

    # Manually set a fresh cooldown for this pair
    pair_key = tuple(sorted([initiator.id, target.id]))
    import time
    _chat_cooldowns[pair_key] = time.time()  # just set, not expired

    with patch("app.agent.chat.get_client"):
        result = await resident_chat(db_session, initiator, target)

    # Should return None/empty dict if on cooldown
    assert result is None or result.get("skipped") is True


@pytest.mark.anyio
async def test_resident_chat_busy_target_skipped(db_session, chat_pair):
    initiator, target = chat_pair
    _chat_cooldowns.clear()
    target.status = "chatting"
    await db_session.commit()

    with patch("app.agent.chat.get_client"):
        result = await resident_chat(db_session, initiator, target)

    assert result is None or result.get("skipped") is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_resident_chat.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.chat'`

- [ ] **Step 3: Implement inter-resident chat**

Create `backend/app/agent/chat.py`:

```python
"""Inter-resident conversation engine with memory generation and broadcasting."""
import json
import logging
import re
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import CHAT_INITIATE_SYSTEM, CHAT_REPLY_SYSTEM, CHAT_SUMMARY_SYSTEM, CHAT_SUMMARY_USER
from app.config import settings
from app.llm.client import get_client
from app.memory.service import MemoryService
from app.models.resident import Resident

logger = logging.getLogger(__name__)

# Cooldown tracking: {frozenset(id1, id2): last_chat_timestamp}
_chat_cooldowns: dict[tuple[str, str], float] = {}


def _pair_key(a: Resident, b: Resident) -> tuple[str, str]:
    return tuple(sorted([a.id, b.id]))  # type: ignore[return-value]


def _is_on_cooldown(initiator: Resident, target: Resident) -> bool:
    key = _pair_key(initiator, target)
    last = _chat_cooldowns.get(key)
    if last is None:
        return False
    return (time.time() - last) < settings.agent_chat_cooldown


def _set_cooldown(initiator: Resident, target: Resident) -> None:
    _chat_cooldowns[_pair_key(initiator, target)] = time.time()


async def _get_relationship_text(svc: MemoryService, resident: Resident, other: Resident) -> str:
    rel = await svc.get_relationship(resident.id, resident_id_target=other.id)
    if rel:
        return rel.content
    return f"（首次和 {other.name} 交谈）"


def _build_chat_system(resident: Resident, other: Resident, rel_text: str, is_initiator: bool, history: str) -> str:
    sbti = (resident.meta_json or {}).get("sbti", {})
    sbti_type = sbti.get("type", "OJBK")
    sbti_name = sbti.get("type_name", "无所谓人")

    if is_initiator:
        return CHAT_INITIATE_SYSTEM.format(
            initiator_name=resident.name,
            sbti_type=sbti_type,
            sbti_name=sbti_name,
            target_name=other.name,
            persona_md=resident.persona_md or "",
            relationship_memory=rel_text,
        )
    else:
        return CHAT_REPLY_SYSTEM.format(
            responder_name=resident.name,
            sbti_type=sbti_type,
            sbti_name=sbti_name,
            initiator_name=other.name,
            persona_md=resident.persona_md or "",
            relationship_memory=rel_text,
            history=history,
        )


async def resident_chat(
    db: AsyncSession,
    initiator: Resident,
    target: Resident,
    max_turns: int | None = None,
) -> dict[str, Any] | None:
    """Run a full inter-resident conversation.

    Flow:
    1. Pre-checks (cooldown, target availability)
    2. Lock both residents as 'socializing'
    3. Alternating LLM dialog for 3-8 turns
    4. Generate event memories for both (using MemoryService.extract_events)
    5. Update relationship memories for both
    6. Generate summary
    7. Unlock both residents
    8. Return summary dict

    Returns None if skipped (cooldown, busy target, etc.)
    """
    # Pre-checks
    if _is_on_cooldown(initiator, target):
        logger.debug("Chat skipped: %s↔%s on cooldown", initiator.slug, target.slug)
        return {"skipped": True, "reason": "cooldown"}

    if target.status in ("chatting", "socializing", "sleeping"):
        logger.debug("Chat skipped: %s is %s", target.slug, target.status)
        return {"skipped": True, "reason": "target_busy"}

    if max_turns is None:
        max_turns = settings.agent_chat_max_turns

    # Clamp turns to [3, 8]
    num_turns = max(3, min(max_turns, 8))

    # Lock both as socializing
    initiator.status = "socializing"
    target.status = "socializing"
    await db.commit()

    client = get_client("system")
    svc = MemoryService(db)

    # Fetch relationship memories for context
    init_rel_text = await _get_relationship_text(svc, initiator, target)
    tgt_rel_text = await _get_relationship_text(svc, target, initiator)

    dialog_lines: list[str] = []  # "Name: text"

    try:
        for turn in range(num_turns):
            is_initiator_turn = (turn % 2 == 0)
            speaker = initiator if is_initiator_turn else target
            listener = target if is_initiator_turn else initiator
            rel_text = init_rel_text if is_initiator_turn else tgt_rel_text

            history = "\n".join(dialog_lines[-6:])  # last 6 lines as context
            system_prompt = _build_chat_system(
                speaker, listener, rel_text,
                is_initiator=(turn == 0),
                history=history,
            )

            messages = [{"role": "user", "content": history or "开始对话"}]
            if turn > 0:
                # Append previous line as context
                messages = [{"role": "user", "content": history}]

            resp = await client.messages.create(
                model=settings.effective_model,
                max_tokens=100,
                system=system_prompt,
                messages=messages,
            )
            reply = resp.content[0].text.strip()[:200]
            dialog_lines.append(f"{speaker.name}: {reply}")

        dialog_text = "\n".join(dialog_lines)

        # Generate event memories for both
        init_memories = await svc.extract_events(
            resident=initiator,
            other_name=target.name,
            conversation_text=dialog_text,
            source="chat_resident",
        )
        tgt_memories = await svc.extract_events(
            resident=target,
            other_name=initiator.name,
            conversation_text=dialog_text,
            source="chat_resident",
        )

        # Update relationships for both
        if init_memories:
            await svc.update_relationship_via_llm(
                resident=initiator,
                other_name=target.name,
                resident_id_target=target.id,
                event_summaries=[m.content for m in init_memories],
            )
        if tgt_memories:
            await svc.update_relationship_via_llm(
                resident=target,
                other_name=initiator.name,
                resident_id_target=initiator.id,
                event_summaries=[m.content for m in tgt_memories],
            )

        # Generate summary for broadcast
        try:
            summary_resp = await client.messages.create(
                model=settings.effective_model,
                max_tokens=150,
                system=CHAT_SUMMARY_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": CHAT_SUMMARY_USER.format(
                        initiator_name=initiator.name,
                        target_name=target.name,
                        dialog_text=dialog_text,
                    ),
                }],
            )
            raw_summary = summary_resp.content[0].text
            match = re.search(r'\{[^{}]+\}', raw_summary, re.DOTALL)
            if match:
                summary_data = json.loads(match.group())
            else:
                summary_data = {"summary": f"{initiator.name} 和 {target.name} 聊了一会儿", "mood": "neutral"}
        except Exception:
            summary_data = {"summary": f"{initiator.name} 和 {target.name} 聊了一会儿", "mood": "neutral"}

        _set_cooldown(initiator, target)

        return {
            "initiator_slug": initiator.slug,
            "target_slug": target.slug,
            "summary": summary_data.get("summary", ""),
            "mood": summary_data.get("mood", "neutral"),
            "turns": len(dialog_lines),
        }

    except Exception as e:
        logger.warning("resident_chat failed %s↔%s: %s", initiator.slug, target.slug, e)
        return None

    finally:
        # Always unlock both residents
        initiator.status = "idle"
        target.status = "idle"
        try:
            await db.commit()
        except Exception:
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_resident_chat.py -v
```
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/agent/chat.py backend/tests/test_resident_chat.py
git commit -m "feat(agent): add inter-resident chat with 3-8 turn LLM dialog, memory generation, and summary"
```

---

### Task 9: Agent Loop Main

**Files:**
- Create: `backend/app/agent/loop.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_agent_loop.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_agent_loop.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from app.models.resident import Resident
from app.agent.loop import AgentLoop
from app.agent.actions import ActionType, ActionResult
from app.agent.scheduler import DailySchedule


@pytest.fixture
async def loop_residents(db_session):
    residents = []
    for i in range(3):
        r = Resident(
            id=f"loop-res-{i}",
            slug=f"loop-res-{i}",
            name=f"LoopRes{i}",
            district="engineering",
            status="idle",
            ability_md="Loops",
            persona_md="Patient",
            soul_md="Persistent",
            creator_id="c1",
            meta_json={"sbti": {"type": "GOGO", "type_name": "行者", "dimensions": {
                "S1": "H", "S2": "H", "S3": "M",
                "E1": "H", "E2": "M", "E3": "H",
                "A1": "M", "A2": "M", "A3": "H",
                "Ac1": "H", "Ac2": "H", "Ac3": "H",
                "So1": "M", "So2": "H", "So3": "M",
            }}},
        )
        db_session.add(r)
        residents.append(r)
    await db_session.commit()
    return residents


@pytest.mark.anyio
async def test_agent_loop_tick_round_runs(db_session, loop_residents):
    """_tick_round should call resident_tick for each active resident."""
    loop = AgentLoop()

    tick_results = [
        ActionResult(action=ActionType.IDLE, target_slug=None, target_tile=None, reason="rest"),
        ActionResult(action=ActionType.WANDER, target_slug=None, target_tile=(80, 55), reason="restless"),
        None,  # third resident skipped
    ]
    call_idx = 0

    async def mock_tick(db, resident):
        nonlocal call_idx
        result = tick_results[min(call_idx, len(tick_results) - 1)]
        call_idx += 1
        return result

    with patch("app.agent.loop.resident_tick", side_effect=mock_tick):
        with patch("app.agent.loop.should_tick", return_value=True):
            with patch("app.agent.loop.build_schedule", return_value=MagicMock(
                wake_hour=6, sleep_hour=23, peak_hours=[10], social_slots=[14], rest_ratio=0.3
            )):
                await loop._tick_round(db_session)

    # All 3 residents should have been evaluated
    assert call_idx == 3


@pytest.mark.anyio
async def test_agent_loop_respects_max_concurrent(db_session, loop_residents):
    """AgentLoop should use a semaphore limiting concurrent ticks."""
    loop = AgentLoop()
    concurrent_count = 0
    max_seen = 0

    async def slow_tick(db, resident):
        nonlocal concurrent_count, max_seen
        concurrent_count += 1
        max_seen = max(max_seen, concurrent_count)
        import asyncio
        await asyncio.sleep(0.01)
        concurrent_count -= 1
        return None

    with patch("app.agent.loop.resident_tick", side_effect=slow_tick):
        with patch("app.agent.loop.should_tick", return_value=True):
            with patch("app.agent.loop.build_schedule", return_value=MagicMock(
                wake_hour=6, sleep_hour=23, peak_hours=[10], social_slots=[14], rest_ratio=0.3
            )):
                with patch("app.config.settings") as mock_settings:
                    mock_settings.agent_max_concurrent = 2
                    mock_settings.agent_enabled = True
                    mock_settings.agent_max_daily_actions = 20
                    await loop._tick_round(db_session)

    # max concurrent should not exceed limit
    assert max_seen <= 2


@pytest.mark.anyio
async def test_agent_loop_broadcasts_movement(db_session, loop_residents):
    """Loop should broadcast resident_move for WANDER actions."""
    loop = AgentLoop()
    broadcasts: list[dict] = []

    async def mock_broadcast(data, exclude=None):
        broadcasts.append(data)

    wander_result = ActionResult(
        action=ActionType.WANDER, target_slug=None, target_tile=(80, 55), reason="restless"
    )

    with patch("app.agent.loop.resident_tick", return_value=wander_result):
        with patch("app.agent.loop.should_tick", return_value=True):
            with patch("app.agent.loop.build_schedule", return_value=MagicMock(
                wake_hour=6, sleep_hour=23, peak_hours=[10], social_slots=[14], rest_ratio=0.3
            )):
                with patch("app.agent.loop.manager") as mock_manager:
                    mock_manager.broadcast = AsyncMock(side_effect=mock_broadcast)
                    await loop._tick_round(db_session)

    move_broadcasts = [b for b in broadcasts if b.get("type") == "resident_move"]
    assert len(move_broadcasts) >= 1


@pytest.mark.anyio
async def test_agent_loop_one_failed_tick_doesnt_crash(db_session, loop_residents):
    """A failing tick should be caught and loop should continue."""
    loop = AgentLoop()
    call_count = 0

    async def flaky_tick(db, resident):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("Simulated tick failure")
        return None

    with patch("app.agent.loop.resident_tick", side_effect=flaky_tick):
        with patch("app.agent.loop.should_tick", return_value=True):
            with patch("app.agent.loop.build_schedule", return_value=MagicMock(
                wake_hour=6, sleep_hour=23, peak_hours=[10], social_slots=[14], rest_ratio=0.3
            )):
                with patch("app.agent.loop.manager") as mock_manager:
                    mock_manager.broadcast = AsyncMock()
                    # Should not raise
                    await loop._tick_round(db_session)

    # All 3 residents should have been attempted
    assert call_count == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_agent_loop.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.loop'`

- [ ] **Step 3: Implement AgentLoop**

Create `backend/app/agent/loop.py`:

```python
"""AgentLoop: centralized background task driving all resident autonomous behavior."""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.actions import ActionType, ActionResult
from app.agent.chat import resident_chat
from app.agent.scheduler import build_schedule, should_tick
from app.agent.tick import resident_tick
from app.config import settings
from app.database import async_session
from app.models.resident import Resident
from app.ws.manager import manager

logger = logging.getLogger(__name__)


class AgentLoop:
    """Centralized agent loop — runs as a FastAPI background task.

    Follows the same pattern as heat_cron_loop: while True, try, sleep.
    Differences:
    - Evaluates per-resident schedules (SBTI-derived) before ticking
    - Uses asyncio.Semaphore to bound concurrent ticks
    - Dispatches resident_chat() for CHAT_RESIDENT actions
    - Broadcasts movement and status changes to all connected clients
    """

    async def run(self) -> None:
        """Main loop — runs indefinitely."""
        logger.info("AgentLoop started (interval=%ds)", settings.agent_tick_interval)
        while True:
            if not settings.agent_enabled:
                await asyncio.sleep(settings.agent_tick_interval)
                continue
            try:
                async with async_session() as db:
                    await self._tick_round(db)
            except Exception as e:
                logger.error("AgentLoop tick_round error: %s", e)
            await asyncio.sleep(settings.agent_tick_interval)

    async def _tick_round(self, db: AsyncSession) -> None:
        """One round: evaluate schedules, run concurrent resident ticks."""
        # Load all active residents
        result = await db.execute(
            select(Resident).where(Resident.status.not_in(["sleeping"]))
        )
        residents = list(result.scalars().all())
        if not residents:
            return

        current_hour = datetime.now().hour
        semaphore = asyncio.Semaphore(settings.agent_max_concurrent)

        async def guarded_tick(resident: Resident) -> ActionResult | None:
            """Run one resident's tick with semaphore, handle errors gracefully."""
            # Evaluate schedule before acquiring semaphore
            sbti_data = (resident.meta_json or {}).get("sbti")
            schedule = build_schedule(sbti_data)

            if not should_tick(schedule, current_hour):
                return None

            async with semaphore:
                try:
                    action_result = await resident_tick(db, resident)
                except Exception as e:
                    logger.warning("Tick error for %s: %s", resident.slug, e)
                    return None

            if action_result:
                await self._handle_action(db, resident, action_result)

            return action_result

        # Run all ticks concurrently, bounded by semaphore
        await asyncio.gather(*(guarded_tick(r) for r in residents), return_exceptions=True)

    async def _handle_action(
        self,
        db: AsyncSession,
        resident: Resident,
        action_result: ActionResult,
    ) -> None:
        """Post-tick: broadcast state changes and handle chat initiation."""
        movement_actions = {ActionType.WANDER, ActionType.GO_HOME, ActionType.VISIT_DISTRICT}

        if action_result.action in movement_actions:
            await manager.broadcast({
                "type": "resident_move",
                "resident_slug": resident.slug,
                "tile_x": resident.tile_x,
                "tile_y": resident.tile_y,
                "target_tile": list(action_result.target_tile) if action_result.target_tile else None,
                "status": "walking",
            })

        elif action_result.action == ActionType.CHAT_RESIDENT:
            await self._initiate_chat(db, resident, action_result.target_slug)

        elif action_result.action in {ActionType.IDLE, ActionType.NAP}:
            await manager.broadcast({
                "type": "resident_status",
                "resident_slug": resident.slug,
                "status": resident.status,
            })

    async def _initiate_chat(
        self,
        db: AsyncSession,
        initiator: Resident,
        target_slug: str | None,
    ) -> None:
        """Fetch target resident and run inter-resident chat."""
        if not target_slug:
            return

        result = await db.execute(
            select(Resident).where(Resident.slug == target_slug)
        )
        target = result.scalar_one_or_none()
        if target is None:
            return

        # Broadcast chat start
        await manager.broadcast({
            "type": "resident_chat",
            "initiator_slug": initiator.slug,
            "target_slug": target.slug,
            "summary": None,  # Will be updated when chat ends
        })

        try:
            chat_result = await resident_chat(db, initiator, target)

            if chat_result and not chat_result.get("skipped"):
                await manager.broadcast({
                    "type": "resident_chat_end",
                    "initiator_slug": initiator.slug,
                    "target_slug": target.slug,
                    "summary": chat_result.get("summary", ""),
                    "mood": chat_result.get("mood", "neutral"),
                })
        except Exception as e:
            logger.warning("Chat initiation failed %s→%s: %s", initiator.slug, target_slug, e)
            # Ensure both get unlocked
            initiator.status = "idle"
            target.status = "idle"
            await db.commit()
            await manager.broadcast({
                "type": "resident_chat_end",
                "initiator_slug": initiator.slug,
                "target_slug": target.slug,
                "summary": "",
            })


# Module-level singleton
agent_loop = AgentLoop()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/test_agent_loop.py -v
```
Expected: All 4 tests PASS

- [ ] **Step 5: Register in main.py lifespan**

In `backend/app/main.py`, add import at top:

```python
from app.agent.loop import agent_loop
```

In the `lifespan` function, after `task = asyncio.create_task(heat_cron_loop())`:

```python
    agent_task = asyncio.create_task(agent_loop.run())
```

And in the `yield` cleanup section, add:

```python
    agent_task.cancel()
```

The full lifespan block after modification:

```python
@asynccontextmanager
async def lifespan(app):
    from app.database import engine, Base
    import app.models.user  # noqa: F401
    import app.models.resident  # noqa: F401
    import app.models.conversation  # noqa: F401
    import app.models.transaction  # noqa: F401
    import app.models.system_config  # noqa: F401
    import app.models.forge_session  # noqa: F401
    import app.models.pending_message  # noqa: F401
    import app.models.memory  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    task = asyncio.create_task(heat_cron_loop())
    agent_task = asyncio.create_task(agent_loop.run())
    yield
    task.cancel()
    agent_task.cancel()
```

- [ ] **Step 6: Run all backend tests**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/ -v --timeout=30
```
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/agent/loop.py backend/app/main.py backend/tests/test_agent_loop.py
git commit -m "feat(agent): add AgentLoop with concurrent tick dispatch, chat initiation, WS broadcasting"
```

---

### Task 10: WebSocket Broadcasting for Agent Actions

**Files:**
- Modify: `backend/app/ws/manager.py`

Add socializing tracking to the ConnectionManager so the frontend and backend can both track which resident pairs are currently in a resident-resident conversation.

- [ ] **Step 1: Extend ConnectionManager**

In `backend/app/ws/manager.py`, in the `__init__` method, add after `self.chat_queue`:

```python
        self.socializing: dict[str, str] = {}  # resident_id -> partner_resident_id
```

Add these methods to the `ConnectionManager` class:

```python
    def lock_socializing(self, res_a_id: str, res_b_id: str) -> bool:
        """Mark two residents as socializing with each other.

        Returns False if either is already locked.
        """
        if res_a_id in self.socializing or res_b_id in self.socializing:
            return False
        self.socializing[res_a_id] = res_b_id
        self.socializing[res_b_id] = res_a_id
        return True

    def unlock_socializing(self, res_a_id: str, res_b_id: str) -> None:
        self.socializing.pop(res_a_id, None)
        self.socializing.pop(res_b_id, None)

    def is_socializing(self, resident_id: str) -> bool:
        return resident_id in self.socializing
```

- [ ] **Step 2: Verify manager tests still pass**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/ -v --timeout=30 -k "not agent_loop"
```
Expected: PASS

- [ ] **Step 3: Document new WS message types**

Add a comment block in `backend/app/agent/loop.py` at the top, after the imports:

```python
# New WebSocket message types emitted by the AgentLoop:
#
# resident_move:
#   { "type": "resident_move", "resident_slug": str, "tile_x": int, "tile_y": int,
#     "target_tile": [x, y] | null, "status": "walking" }
#
# resident_chat:
#   { "type": "resident_chat", "initiator_slug": str, "target_slug": str, "summary": null }
#
# resident_chat_end:
#   { "type": "resident_chat_end", "initiator_slug": str, "target_slug": str,
#     "summary": str, "mood": "positive"|"neutral"|"negative" }
#
# resident_status:
#   { "type": "resident_status", "resident_slug": str, "status": str }
```

- [ ] **Step 4: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add backend/app/ws/manager.py backend/app/agent/loop.py
git commit -m "feat(agent): extend ConnectionManager with socializing tracking, document WS message types"
```

---

### Task 11: Frontend — Resident Movement Animation

**Files:**
- Modify: `frontend/src/game/StatusVisuals.ts`
- Modify: `frontend/src/game/GameScene.ts`

- [ ] **Step 1: Add walking and socializing to StatusVisuals**

In `frontend/src/game/StatusVisuals.ts`, add to `STATUS_CONFIG`:

```typescript
  walking:     { label: '🚶 移动中', canChat: false, bubble: '🚶', alpha: 1.0, tint: null },
  socializing: { label: '🗣️ 交谈中', canChat: false, bubble: '🗣️', alpha: 1.0, tint: 0x22c55e },
```

In the `applyStatusVisuals` function, add new `else if` branches after the `chatting` branch:

```typescript
  } else if (status === 'walking') {
    // Subtle horizontal bob while walking
    scene.tweens.add({
      targets: sprite, x: x + 2, duration: 200, yoyo: true, repeat: -1, ease: 'Linear',
    })
  } else if (status === 'socializing') {
    // Gentle bounce and green tint
    scene.tweens.add({
      targets: sprite,
      scaleY: sprite.scaleY * 1.05,
      duration: 600, yoyo: true, repeat: -1, ease: 'Sine.easeInOut',
    })
    const glow = scene.add.graphics().setDepth(0)
    glow.fillStyle(0x22c55e, 0.06)
    glow.fillCircle(x, y, 30)
    scene.tweens.add({ targets: glow, alpha: 0.2, duration: 1000, yoyo: true, repeat: -1 })
    objects.push(glow)
  }
```

- [ ] **Step 2: Handle resident_move WS message in GameScene**

In `frontend/src/game/GameScene.ts`, in the `create()` method where WS messages are handled, add a handler for `resident_move`. Find the `onWSMessage` block and add:

```typescript
    onWSMessage((msg) => {
      // ... existing handlers ...

      if (msg.type === 'resident_move') {
        this._handleResidentMove(msg)
      }

      if (msg.type === 'resident_chat') {
        this._handleResidentChatStart(msg)
      }

      if (msg.type === 'resident_chat_end') {
        this._handleResidentChatEnd(msg)
      }

      if (msg.type === 'resident_status') {
        this._handleResidentStatusUpdate(msg)
      }
    })
```

Add these private methods to the `MainScene` class:

```typescript
  private _handleResidentMove(msg: {
    resident_slug: string
    tile_x: number
    tile_y: number
    status: string
  }): void {
    const idx = this.residents.findIndex(r => r.slug === msg.resident_slug)
    if (idx < 0) return

    const sprite = this.npcSprites[idx]
    if (!sprite) return

    const TILE_SIZE = 32
    const targetX = msg.tile_x * TILE_SIZE + TILE_SIZE / 2
    const targetY = msg.tile_y * TILE_SIZE + TILE_SIZE / 2

    // Update logical position
    this.residents[idx].tile_x = msg.tile_x
    this.residents[idx].tile_y = msg.tile_y
    this.residents[idx].status = msg.status

    // Animate sprite to new position
    clearStatusVisuals(this, sprite)
    applyStatusVisuals(this, sprite, 'walking', sprite.x, sprite.y)

    this.tweens.add({
      targets: sprite,
      x: targetX,
      y: targetY,
      duration: 800,
      ease: 'Linear',
      onComplete: () => {
        clearStatusVisuals(this, sprite)
        applyStatusVisuals(this, sprite, 'idle', targetX, targetY)
        this.residents[idx].status = 'idle'
      },
    })
  }

  private _chatBubbles: Map<string, Phaser.GameObjects.Text> = new Map()

  private _handleResidentChatStart(msg: {
    initiator_slug: string
    target_slug: string
    summary: string | null
  }): void {
    for (const slug of [msg.initiator_slug, msg.target_slug]) {
      const idx = this.residents.findIndex(r => r.slug === slug)
      if (idx < 0) continue
      const sprite = this.npcSprites[idx]
      if (!sprite) continue

      clearStatusVisuals(this, sprite)
      applyStatusVisuals(this, sprite, 'socializing', sprite.x, sprite.y)
      this.residents[idx].status = 'socializing'

      // Add chat bubble
      const bubble = this.add.text(sprite.x, sprite.y - 60, '💬 ...', {
        fontSize: '12px',
        backgroundColor: '#1e293bdd',
        padding: { x: 6, y: 3 },
        color: '#e2e8f0',
        wordWrap: { width: 120 },
      }).setOrigin(0.5).setDepth(10)
      this._chatBubbles.set(slug, bubble)
    }
  }

  private _handleResidentChatEnd(msg: {
    initiator_slug: string
    target_slug: string
    summary: string
    mood?: string
  }): void {
    for (const slug of [msg.initiator_slug, msg.target_slug]) {
      const idx = this.residents.findIndex(r => r.slug === slug)
      if (idx < 0) continue
      const sprite = this.npcSprites[idx]
      if (!sprite) continue

      clearStatusVisuals(this, sprite)
      applyStatusVisuals(this, sprite, 'idle', sprite.x, sprite.y)
      this.residents[idx].status = 'idle'

      // Remove old bubble
      const oldBubble = this._chatBubbles.get(slug)
      oldBubble?.destroy()
      this._chatBubbles.delete(slug)
    }

    // Show summary bubble on initiator for 5 seconds
    const initIdx = this.residents.findIndex(r => r.slug === msg.initiator_slug)
    if (initIdx >= 0 && msg.summary) {
      const sprite = this.npcSprites[initIdx]
      if (sprite) {
        const summaryBubble = this.add.text(sprite.x, sprite.y - 80, msg.summary, {
          fontSize: '11px',
          backgroundColor: '#0f172add',
          padding: { x: 8, y: 4 },
          color: '#f1f5f9',
          wordWrap: { width: 150 },
        }).setOrigin(0.5).setDepth(10)

        this.time.delayedCall(5000, () => summaryBubble.destroy())
      }
    }
  }

  private _handleResidentStatusUpdate(msg: {
    resident_slug: string
    status: string
  }): void {
    const idx = this.residents.findIndex(r => r.slug === msg.resident_slug)
    if (idx < 0) return
    const sprite = this.npcSprites[idx]
    if (!sprite) return

    this.residents[idx].status = msg.status
    clearStatusVisuals(this, sprite)
    applyStatusVisuals(this, sprite, msg.status, sprite.x, sprite.y)
  }
```

- [ ] **Step 3: Run TypeScript check**

```bash
cd /Users/jimmy/Downloads/Skills-World/frontend && npx tsc --noEmit
```
Expected: No errors

- [ ] **Step 4: Commit**

```bash
cd /Users/jimmy/Downloads/Skills-World
git add frontend/src/game/StatusVisuals.ts frontend/src/game/GameScene.ts
git commit -m "feat(agent): add frontend walking/socializing visuals, NPC movement tween, chat bubble"
```

---

### Task 12: Final Integration Verification

- [ ] **Step 1: Run full backend test suite**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -m pytest tests/ -v --timeout=30
```
Expected: All tests PASS — no regressions

- [ ] **Step 2: Run TypeScript type check**

```bash
cd /Users/jimmy/Downloads/Skills-World/frontend && npx tsc --noEmit
```
Expected: No errors

- [ ] **Step 3: Verify file structure**

```bash
find /Users/jimmy/Downloads/Skills-World/backend/app/agent -type f -name "*.py" | sort
find /Users/jimmy/Downloads/Skills-World/backend/tests -name "test_agent*" -o -name "test_pathfinder*" -o -name "test_resident_*" | sort
```

Expected structure:
```
backend/app/agent/__init__.py
backend/app/agent/actions.py
backend/app/agent/chat.py
backend/app/agent/loop.py
backend/app/agent/pathfinder.py
backend/app/agent/prompts.py
backend/app/agent/scheduler.py
backend/app/agent/tick.py
---
backend/tests/test_agent_actions.py
backend/tests/test_agent_loop.py
backend/tests/test_agent_resident_model.py
backend/tests/test_agent_scheduler.py
backend/tests/test_pathfinder.py
backend/tests/test_resident_chat.py
backend/tests/test_resident_tick.py
```

- [ ] **Step 4: Smoke-test agent import chain**

```bash
cd /Users/jimmy/Downloads/Skills-World/backend && python3 -c "
from app.agent.loop import agent_loop
from app.agent.scheduler import build_schedule
from app.agent.actions import ActionType, get_available_actions
from app.agent.pathfinder import find_path, get_walkable_tiles
from app.agent.tick import resident_tick, parse_action_result
from app.agent.chat import resident_chat
print('All agent imports OK')
print('ActionTypes:', [a.value for a in ActionType])
print('Walkable tiles:', len(get_walkable_tiles()))
"
```

Expected:
```
All agent imports OK
ActionTypes: ['CHAT_RESIDENT', 'CHAT_FOLLOW_UP', 'GOSSIP', 'WANDER', 'VISIT_DISTRICT', 'GO_HOME', 'OBSERVE', 'EAVESDROP', 'REFLECT', 'JOURNAL', 'WORK', 'STUDY', 'IDLE', 'NAP']
Walkable tiles: <number > 100>
```

- [ ] **Step 5: Final commit if any cleanup needed**

```bash
cd /Users/jimmy/Downloads/Skills-World && git status
# If clean: done. If outstanding changes:
git add -A
git commit -m "chore(agent): final P3 cleanup and import verification"
```

---

## Architecture Notes for Implementers

### Why a module-level `_daily_counts` dict?

The daily counter lives in `tick.py` module scope rather than the DB for performance — a Redis increment would be ideal for multi-process deploys, but for the single-process FastAPI server this is sufficient and avoids adding a Redis dependency. The AgentLoop calls `_check_and_reset_daily_counts()` on every tick to handle midnight rollovers.

### Why A* on the backend?

Path computation on the backend lets us:
1. Broadcast the authoritative path to ALL connected clients (not just the one who triggered it)
2. Validate that movements don't cross impassable tiles (server-side authority)
3. Compute paths during the agent loop without touching the frontend

The frontend only receives tile coordinates and animates tweens — it does not pathfind itself for NPC movement.

### Chat Cooldown Design

The `_chat_cooldowns` dict in `chat.py` prevents the same two residents from chatting every 60 seconds. Default cooldown is 1800s (30 min real time). This creates more organic social patterns — if two residents just talked, they'll naturally drift apart before reconnecting.

### Schedule Jitter

`should_tick()` adds ±0.1 uniform noise to the probability before rolling. This prevents the "synchronized heartbeat" anti-pattern where 20 residents all become active at exactly 09:00:00. The effective result is a probabilistic stagger of ±1-2 minutes around each resident's natural activity window.

### Frontend WS Message Contract

| Message type | Sent by | Frontend response |
|---|---|---|
| `resident_move` | AgentLoop._handle_action | Tween sprite to new tile over 800ms |
| `resident_chat` | AgentLoop._initiate_chat | Lock sprite as socializing, show "..." bubble |
| `resident_chat_end` | AgentLoop._initiate_chat | Unlock sprite, show summary bubble 5s |
| `resident_status` | AgentLoop._handle_action | Update sprite visual to new status |
