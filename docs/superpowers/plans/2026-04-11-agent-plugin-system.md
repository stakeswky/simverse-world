# Agent Plugin System + Hierarchical Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the monolithic `tick.py` with a YAML-driven plugin architecture where each tick phase is an independent plugin class, and add a hierarchical planning system (DailyGoal + HourlyPlan) with importance-based hybrid execution.

**Architecture:** The 5-phase tick loop (perceive/plan/decide/execute/memorize) becomes a chain of `PhasePlugin` implementations loaded from YAML config via `importlib`. A `PluginRegistry` singleton caches plugin chains by config name. Different SBTI personality types map to different YAML configs (default/introvert/extravert), each specifying different plugin classes and parameters. A new `BasicPlanPlugin` generates daily goals + hourly plans via LLM once per day, and `DecidePlugin` variants use importance thresholds to determine whether to force-execute plans or allow LLM deviation.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.0 async, PyYAML, Alembic, pytest + pytest-asyncio

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/agent/schemas.py` | Create | `TickContext`, `DailyGoal`, `HourlyPlan`, `DailySchedulePlan` dataclasses + `parse_action_result()` + `get_world_time()` utilities |
| `backend/app/agent/phases/__init__.py` | Create | Empty package init |
| `backend/app/agent/phases/base.py` | Create | `PhasePlugin` Protocol definition |
| `backend/app/agent/phases/perceive/__init__.py` | Create | Empty |
| `backend/app/agent/phases/perceive/basic.py` | Create | `BasicPerceivePlugin` — extracted from `tick.py:_perceive()` |
| `backend/app/agent/phases/perceive/social.py` | Create | `SocialPerceivePlugin` — wider radius + relationship awareness |
| `backend/app/agent/phases/plan/__init__.py` | Create | Empty |
| `backend/app/agent/phases/plan/basic.py` | Create | `BasicPlanPlugin` — LLM daily goal + hourly plan generation |
| `backend/app/agent/phases/decide/__init__.py` | Create | Empty |
| `backend/app/agent/phases/decide/basic.py` | Create | `BasicDecidePlugin` — extracted from `tick.py` decide + plan-aware |
| `backend/app/agent/phases/decide/cautious.py` | Create | `CautiousDecidePlugin` — introvert variant |
| `backend/app/agent/phases/decide/spontaneous.py` | Create | `SpontaneousDecidePlugin` — extravert variant |
| `backend/app/agent/phases/execute/__init__.py` | Create | Empty |
| `backend/app/agent/phases/execute/basic.py` | Create | `BasicExecutePlugin` — extracted from `tick.py:_execute_movement()` |
| `backend/app/agent/phases/memorize/__init__.py` | Create | Empty |
| `backend/app/agent/phases/memorize/basic.py` | Create | `BasicMemorizePlugin` — extracted from `tick.py` memorize |
| `backend/app/agent/phases/memorize/reflective.py` | Create | `ReflectiveMemorizePlugin` — auto-reflect chance |
| `backend/app/agent/configs/default.yaml` | Create | Default agent config |
| `backend/app/agent/configs/introvert.yaml` | Create | Introvert agent config |
| `backend/app/agent/configs/extravert.yaml` | Create | Extravert agent config |
| `backend/app/agent/registry.py` | Create | `PluginRegistry` with YAML loading + `importlib` dynamic import + `resolve_config_name()` |
| `backend/app/agent/tick.py` | Modify | Slim down to orchestrator calling plugin chain |
| `backend/app/agent/loop.py` | Modify | Add `registry.load_all()` at startup |
| `backend/app/models/resident.py` | Modify | Add `daily_goal_json`, `daily_plans_json` columns |
| `backend/alembic/versions/007_add_daily_plan_fields.py` | Create | Migration for new Resident columns |
| `backend/tests/test_agent_schemas.py` | Create | Tests for schemas + utilities |
| `backend/tests/test_agent_registry.py` | Create | Tests for registry + config loading |
| `backend/tests/test_agent_phases.py` | Create | Tests for all phase plugins |
| `backend/tests/test_agent_tick_orchestrator.py` | Create | Integration test for new tick orchestrator |

---

### Task 1: Schemas + Utility Extraction

**Files:**
- Create: `backend/app/agent/schemas.py`
- Create: `backend/tests/test_agent_schemas.py`

- [ ] **Step 1: Write tests for `get_world_time` and `parse_action_result`**

```python
# backend/tests/test_agent_schemas.py
import pytest
from unittest.mock import patch
from datetime import datetime
from app.agent.schemas import get_world_time, parse_action_result, DailyGoal, HourlyPlan, TickContext


def test_get_world_time_morning():
    with patch("app.agent.schemas.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 11, 9, 30)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        formatted, hour, phase = get_world_time()
        assert hour == 9
        assert phase == "上午"
        assert formatted == "09:30"


def test_get_world_time_evening():
    with patch("app.agent.schemas.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 4, 11, 19, 0)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        formatted, hour, phase = get_world_time()
        assert hour == 19
        assert phase == "傍晚"


def test_parse_action_result_valid_json():
    raw = '{"action": "WANDER", "target_slug": null, "target_tile": [10, 20], "reason": "散步"}'
    result = parse_action_result(raw)
    assert result is not None
    assert result.action.value == "WANDER"
    assert result.target_tile == (10, 20)
    assert result.reason == "散步"


def test_parse_action_result_embedded_json():
    raw = '我决定去散步。 {"action": "IDLE", "target_slug": null, "target_tile": null, "reason": "休息"} 就这样吧。'
    result = parse_action_result(raw)
    assert result is not None
    assert result.action.value == "IDLE"


def test_parse_action_result_invalid():
    assert parse_action_result("no json here") is None
    assert parse_action_result('{"action": "INVALID_TYPE"}') is None


def test_daily_goal_dataclass():
    goal = DailyGoal(goal="研究古籍", motivation="好奇心驱使", created_at="2026-04-11T09:00:00", status="active")
    assert goal.goal == "研究古籍"
    assert goal.status == "active"


def test_hourly_plan_dataclass():
    plan = HourlyPlan(slot=0, hour_range=(7, 9), action="IDLE", target=None, location="home", importance=2, reason="早起休息", status="pending")
    assert plan.importance == 2
    assert plan.hour_range == (7, 9)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_agent_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.schemas'`

- [ ] **Step 3: Create `schemas.py` with dataclasses and extracted utilities**

```python
# backend/app/agent/schemas.py
"""Data models and utility functions for the agent plugin system."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from app.agent.actions import ActionType, ActionResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.memory import Memory
    from app.models.resident import Resident

logger = logging.getLogger(__name__)


# ── Hierarchical Planning Models ──────────────────────────────────────

@dataclass
class DailyGoal:
    """Resident's daily long-term goal."""
    goal: str
    motivation: str
    created_at: str
    status: str = "active"  # active | completed | abandoned


@dataclass
class HourlyPlan:
    """A single time-slot plan within a day."""
    slot: int
    hour_range: tuple[int, int]
    action: str
    target: str | None
    location: str | None
    importance: int
    reason: str
    status: str = "pending"  # pending | executing | done | interrupted


@dataclass
class DailySchedulePlan:
    """Complete daily schedule."""
    goal: DailyGoal
    plans: list[HourlyPlan]
    generated_date: str


# ── TickContext ────────────────────────────────────────────────────────

@dataclass
class TickContext:
    """Shared context passed between phase plugins during a tick."""
    # Input (populated at tick start)
    db: AsyncSession
    resident: Resident
    world_time: str
    hour: int
    schedule_phase: str

    # Phase 1: Perceive
    nearby_residents: list[Resident] = field(default_factory=list)

    # Phase 2: Plan
    current_plan: HourlyPlan | None = None
    daily_goal: DailyGoal | None = None

    # Phase 3: Decide
    action_result: ActionResult | None = None
    plan_followed: bool = True

    # Phase 4: Execute
    new_tile: tuple[int, int] | None = None

    # Phase 5: Memorize
    memory_created: bool = False

    # Shared context
    memories: list[Memory] = field(default_factory=list)
    today_actions: list[str] = field(default_factory=list)
    available_actions: list[ActionType] = field(default_factory=list)

    # Control flow
    skip_remaining: bool = False


# ── Utility functions (extracted from tick.py) ─────────────────────────

def get_world_time() -> tuple[str, int, str]:
    """Return (formatted_time, hour, schedule_phase)."""
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


def parse_action_result(raw: str) -> ActionResult | None:
    """Parse LLM response into ActionResult."""
    match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
    if not match:
        logger.debug("No JSON found in decision response: %s", raw[:200])
        return None

    try:
        data = json.loads(match.group())
        action_str = data.get("action", "")
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_agent_schemas.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/agent/schemas.py tests/test_agent_schemas.py
git commit -m "feat(agent): add schemas.py with TickContext, DailyGoal, HourlyPlan and extracted utilities"
```

---

### Task 2: PhasePlugin Protocol + Package Structure

**Files:**
- Create: `backend/app/agent/phases/__init__.py`
- Create: `backend/app/agent/phases/base.py`
- Create: `backend/app/agent/phases/perceive/__init__.py`
- Create: `backend/app/agent/phases/plan/__init__.py`
- Create: `backend/app/agent/phases/decide/__init__.py`
- Create: `backend/app/agent/phases/execute/__init__.py`
- Create: `backend/app/agent/phases/memorize/__init__.py`

- [ ] **Step 1: Create the directory structure and base protocol**

```python
# backend/app/agent/phases/__init__.py
# (empty)
```

```python
# backend/app/agent/phases/base.py
"""Base protocol for all agent phase plugins."""
from __future__ import annotations
from typing import Protocol, runtime_checkable, Any
from app.agent.schemas import TickContext


@runtime_checkable
class PhasePlugin(Protocol):
    """All phase plugins implement this interface."""

    async def execute(self, ctx: TickContext) -> TickContext:
        """Execute this phase, read/write TickContext and return it."""
        ...
```

Create empty `__init__.py` files in each subdirectory:
- `backend/app/agent/phases/perceive/__init__.py`
- `backend/app/agent/phases/plan/__init__.py`
- `backend/app/agent/phases/decide/__init__.py`
- `backend/app/agent/phases/execute/__init__.py`
- `backend/app/agent/phases/memorize/__init__.py`

- [ ] **Step 2: Write a quick smoke test for the protocol**

```python
# Add to backend/tests/test_agent_schemas.py (append at bottom)

from app.agent.phases.base import PhasePlugin


def test_phase_plugin_protocol():
    """A class with an async execute method satisfies PhasePlugin."""
    class DummyPlugin:
        async def execute(self, ctx):
            return ctx

    assert isinstance(DummyPlugin(), PhasePlugin)
```

- [ ] **Step 3: Run test**

Run: `cd backend && python3 -m pytest tests/test_agent_schemas.py::test_phase_plugin_protocol -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
cd backend && git add app/agent/phases/
git add tests/test_agent_schemas.py
git commit -m "feat(agent): add PhasePlugin protocol and phases package structure"
```

---

### Task 3: YAML Configs + Registry + Config Loader

**Files:**
- Create: `backend/app/agent/configs/default.yaml`
- Create: `backend/app/agent/configs/introvert.yaml`
- Create: `backend/app/agent/configs/extravert.yaml`
- Create: `backend/app/agent/registry.py`
- Create: `backend/tests/test_agent_registry.py`

- [ ] **Step 1: Write tests for registry**

```python
# backend/tests/test_agent_registry.py
import pytest
from pathlib import Path
from app.agent.registry import PluginRegistry, AgentConfig, resolve_config_name


def _make_resident_stub(agent_config=None, so1="M", ac3="M"):
    """Minimal resident-like object for testing."""
    class R:
        meta_json = {
            "sbti": {"dimensions": {"So1": so1, "Ac3": ac3}}
        }
    if agent_config:
        R.meta_json["agent_config"] = agent_config
    return R()


def test_load_all_finds_yaml_configs():
    reg = PluginRegistry()
    reg.load_all()
    assert "default" in reg._configs
    assert "introvert" in reg._configs
    assert "extravert" in reg._configs


def test_config_has_expected_phases():
    reg = PluginRegistry()
    reg.load_all()
    cfg = reg._configs["default"]
    assert cfg.phase_order == ["perceive", "plan", "decide", "execute", "memorize"]
    assert "perceive" in cfg.phases
    assert "plugin" in cfg.phases["perceive"]


def test_resolve_config_explicit_override():
    r = _make_resident_stub(agent_config="introvert")
    assert resolve_config_name(r) == "introvert"


def test_resolve_config_introvert_from_sbti():
    r = _make_resident_stub(so1="L")
    assert resolve_config_name(r) == "introvert"


def test_resolve_config_extravert_from_sbti():
    r = _make_resident_stub(so1="H", ac3="H")
    assert resolve_config_name(r) == "extravert"


def test_resolve_config_default_fallback():
    r = _make_resident_stub(so1="M", ac3="M")
    assert resolve_config_name(r) == "default"


def test_resolve_config_no_sbti():
    class R:
        meta_json = None
    assert resolve_config_name(R()) == "default"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_agent_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.registry'`

- [ ] **Step 3: Create the three YAML config files**

```yaml
# backend/app/agent/configs/default.yaml
name: default
description: Standard resident behavior, balanced across all dimensions

phase_order: [perceive, plan, decide, execute, memorize]

phases:
  perceive:
    plugin: app.agent.phases.perceive.basic.BasicPerceivePlugin
    params:
      radius: 10

  plan:
    plugin: app.agent.phases.plan.basic.BasicPlanPlugin
    params:
      plan_interval_hours: 24
      hourly_slots: 7
      max_social_slots: 2
      max_high_importance: 2

  decide:
    plugin: app.agent.phases.decide.basic.BasicDecidePlugin
    params:
      interrupt_threshold: 6
      plan_adherence_hint: true

  execute:
    plugin: app.agent.phases.execute.basic.BasicExecutePlugin
    params:
      max_steps_per_tick: 1

  memorize:
    plugin: app.agent.phases.memorize.basic.BasicMemorizePlugin
    params:
      base_importance: 0.3
      plan_deviation_boost: 0.2
```

```yaml
# backend/app/agent/configs/introvert.yaml
name: introvert
description: Introverted residents (So1=L), prefer solitude and deep thinking

phase_order: [perceive, plan, decide, execute, memorize]

phases:
  perceive:
    plugin: app.agent.phases.perceive.basic.BasicPerceivePlugin
    params:
      radius: 6

  plan:
    plugin: app.agent.phases.plan.basic.BasicPlanPlugin
    params:
      plan_interval_hours: 24
      hourly_slots: 5
      max_social_slots: 1
      max_high_importance: 1
      preferred_actions:
        - REFLECT:3
        - JOURNAL:3
        - STUDY:2
        - OBSERVE:2
        - WORK:2
        - CHAT_RESIDENT:0.5

  decide:
    plugin: app.agent.phases.decide.cautious.CautiousDecidePlugin
    params:
      interrupt_threshold: 5
      plan_adherence_hint: true
      social_reluctance: true
      interrupt_only_for:
        - high_importance_encounter
        - urgent_event

  execute:
    plugin: app.agent.phases.execute.basic.BasicExecutePlugin
    params:
      max_steps_per_tick: 1

  memorize:
    plugin: app.agent.phases.memorize.reflective.ReflectiveMemorizePlugin
    params:
      base_importance: 0.3
      plan_deviation_boost: 0.3
      auto_reflect_chance: 0.15
      reflection_depth: deep
```

```yaml
# backend/app/agent/configs/extravert.yaml
name: extravert
description: Extraverted residents (So1=H, Ac3=H), social and spontaneous

phase_order: [perceive, plan, decide, execute, memorize]

phases:
  perceive:
    plugin: app.agent.phases.perceive.social.SocialPerceivePlugin
    params:
      radius: 14
      track_relationships: true

  plan:
    plugin: app.agent.phases.plan.basic.BasicPlanPlugin
    params:
      plan_interval_hours: 24
      hourly_slots: 9
      max_social_slots: 4
      max_high_importance: 3
      preferred_actions:
        - CHAT_RESIDENT:3
        - GOSSIP:3
        - WANDER:2
        - VISIT_DISTRICT:2
        - WORK:1
        - REFLECT:0.3

  decide:
    plugin: app.agent.phases.decide.spontaneous.SpontaneousDecidePlugin
    params:
      interrupt_threshold: 8
      plan_adherence_hint: true
      social_eagerness: true
      distraction_chance: 0.3

  execute:
    plugin: app.agent.phases.execute.basic.BasicExecutePlugin
    params:
      max_steps_per_tick: 1

  memorize:
    plugin: app.agent.phases.memorize.basic.BasicMemorizePlugin
    params:
      base_importance: 0.25
      plan_deviation_boost: 0.1
```

- [ ] **Step 4: Create `registry.py`**

```python
# backend/app/agent/registry.py
"""Plugin registry: YAML config loading + importlib dynamic plugin instantiation."""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from app.agent.phases.base import PhasePlugin
    from app.models.resident import Resident

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent / "configs"


@dataclass
class AgentConfig:
    """Parsed representation of a YAML agent config."""
    name: str
    description: str
    phase_order: list[str]
    phases: dict[str, dict[str, Any]]


def _parse_yaml(path: Path) -> AgentConfig:
    """Parse a single YAML config file into AgentConfig."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return AgentConfig(
        name=data["name"],
        description=data.get("description", ""),
        phase_order=data["phase_order"],
        phases=data["phases"],
    )


def _import_class(dotted_path: str) -> type:
    """Dynamically import a class from a dotted module path.

    Example: 'app.agent.phases.perceive.basic.BasicPerceivePlugin' -> class
    """
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def resolve_config_name(resident: Resident) -> str:
    """Determine which YAML config to use for a resident.

    Priority:
    1. Explicit override in meta_json.agent_config
    2. Auto-map from SBTI dimensions
    3. Fallback to 'default'
    """
    meta = resident.meta_json or {}

    # 1. Explicit override
    explicit = meta.get("agent_config")
    if explicit:
        return explicit

    # 2. SBTI auto-map
    sbti = meta.get("sbti", {})
    dims = sbti.get("dimensions", {})
    so1 = dims.get("So1", "M")
    ac3 = dims.get("Ac3", "M")

    if so1 == "L":
        return "introvert"
    elif so1 == "H" and ac3 == "H":
        return "extravert"

    return "default"


class PluginRegistry:
    """Singleton registry that loads YAML configs and instantiates plugin chains."""

    def __init__(self):
        self._configs: dict[str, AgentConfig] = {}
        self._phase_cache: dict[str, list[PhasePlugin]] = {}

    def load_all(self) -> None:
        """Scan configs/ directory and load all YAML files."""
        self._configs.clear()
        self._phase_cache.clear()
        for yaml_file in sorted(CONFIG_DIR.glob("*.yaml")):
            try:
                config = _parse_yaml(yaml_file)
                self._configs[config.name] = config
                logger.info("Loaded agent config: %s (%s)", config.name, yaml_file.name)
            except Exception as e:
                logger.error("Failed to load agent config %s: %s", yaml_file, e)

    def get_phases(self, resident: Resident) -> list[PhasePlugin]:
        """Get the instantiated plugin chain for a resident (cached by config name)."""
        config_name = resolve_config_name(resident)

        if config_name not in self._phase_cache:
            config = self._configs.get(config_name)
            if config is None:
                config = self._configs.get("default")
            if config is None:
                raise RuntimeError("No agent configs loaded. Call registry.load_all() first.")
            self._phase_cache[config_name] = self._build_phases(config)

        return self._phase_cache[config_name]

    def _build_phases(self, config: AgentConfig) -> list[PhasePlugin]:
        """Instantiate plugin classes for each phase in order."""
        phases = []
        for phase_name in config.phase_order:
            phase_def = config.phases[phase_name]
            plugin_path = phase_def["plugin"]
            params = phase_def.get("params", {})
            cls = _import_class(plugin_path)
            instance = cls(params=params)
            phases.append(instance)
            logger.debug("Instantiated %s for phase '%s'", cls.__name__, phase_name)
        return phases


# Module-level singleton
registry = PluginRegistry()
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python3 -m pytest tests/test_agent_registry.py -v`
Expected: All 7 tests PASS

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/agent/registry.py app/agent/configs/
git add tests/test_agent_registry.py
git commit -m "feat(agent): add PluginRegistry with YAML config loading and dynamic import"
```

---

### Task 4: BasicPerceivePlugin + SocialPerceivePlugin

**Files:**
- Create: `backend/app/agent/phases/perceive/basic.py`
- Create: `backend/app/agent/phases/perceive/social.py`
- Create: `backend/tests/test_agent_phases.py`

- [ ] **Step 1: Write tests for perceive plugins**

```python
# backend/tests/test_agent_phases.py
"""Tests for all phase plugins."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.schemas import TickContext, HourlyPlan, DailyGoal
from app.agent.actions import ActionType, ActionResult


def _make_resident(slug="test-resident", tile_x=76, tile_y=50, status="idle",
                   district="central", meta_json=None, name="Test"):
    """Create a minimal Resident-like mock."""
    r = MagicMock()
    r.id = f"id-{slug}"
    r.slug = slug
    r.name = name
    r.tile_x = tile_x
    r.tile_y = tile_y
    r.status = status
    r.district = district
    r.home_tile_x = 70
    r.home_tile_y = 45
    r.persona_md = "A friendly person."
    r.meta_json = meta_json or {"sbti": {"type": "CTRL", "type_name": "控制者", "dimensions": {"So1": "M", "Ac3": "M"}}}
    r.daily_goal_json = None
    r.daily_plans_json = None
    return r


def _make_ctx(resident=None, db=None, nearby=None):
    """Create a TickContext for testing."""
    return TickContext(
        db=db or AsyncMock(),
        resident=resident or _make_resident(),
        world_time="10:00",
        hour=10,
        schedule_phase="上午",
        nearby_residents=nearby or [],
    )


# ── Perceive Tests ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_basic_perceive_finds_nearby():
    from app.agent.phases.perceive.basic import BasicPerceivePlugin

    resident = _make_resident(tile_x=76, tile_y=50)
    nearby_r = _make_resident(slug="nearby", tile_x=80, tile_y=50)  # dist=4
    far_r = _make_resident(slug="far", tile_x=100, tile_y=100)      # dist=74

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [nearby_r, far_r]
    db.execute = AsyncMock(return_value=result_mock)

    plugin = BasicPerceivePlugin(params={"radius": 10})
    ctx = _make_ctx(resident=resident, db=db)
    ctx = await plugin.execute(ctx)

    assert len(ctx.nearby_residents) == 1
    assert ctx.nearby_residents[0].slug == "nearby"


@pytest.mark.anyio
async def test_basic_perceive_custom_radius():
    from app.agent.phases.perceive.basic import BasicPerceivePlugin

    resident = _make_resident(tile_x=76, tile_y=50)
    nearby_r = _make_resident(slug="nearby", tile_x=80, tile_y=50)  # dist=4

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [nearby_r]
    db.execute = AsyncMock(return_value=result_mock)

    plugin = BasicPerceivePlugin(params={"radius": 3})  # dist=4 > radius=3
    ctx = _make_ctx(resident=resident, db=db)
    ctx = await plugin.execute(ctx)

    assert len(ctx.nearby_residents) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_agent_phases.py::test_basic_perceive_finds_nearby -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement BasicPerceivePlugin**

```python
# backend/app/agent/phases/perceive/basic.py
"""BasicPerceivePlugin: find nearby residents within radius."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.agent.schemas import TickContext
from app.models.resident import Resident

logger = logging.getLogger(__name__)


class BasicPerceivePlugin:
    """Find residents within Manhattan distance radius."""

    def __init__(self, params: dict[str, Any] | None = None):
        params = params or {}
        self.radius: int = params.get("radius", 10)

    async def execute(self, ctx: TickContext) -> TickContext:
        try:
            result = await ctx.db.execute(
                select(Resident).where(Resident.id != ctx.resident.id)
            )
            all_residents = result.scalars().all()

            nearby = []
            for r in all_residents:
                dist = abs(r.tile_x - ctx.resident.tile_x) + abs(r.tile_y - ctx.resident.tile_y)
                if dist <= self.radius:
                    nearby.append(r)

            ctx.nearby_residents = nearby
        except Exception as e:
            logger.warning("Perceive failed for %s: %s", ctx.resident.slug, e)
            ctx.skip_remaining = True

        return ctx
```

- [ ] **Step 4: Implement SocialPerceivePlugin**

```python
# backend/app/agent/phases/perceive/social.py
"""SocialPerceivePlugin: wider radius + relationship awareness."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.agent.schemas import TickContext
from app.models.resident import Resident

logger = logging.getLogger(__name__)


class SocialPerceivePlugin:
    """Perceive with wider radius. Optionally tag known residents."""

    def __init__(self, params: dict[str, Any] | None = None):
        params = params or {}
        self.radius: int = params.get("radius", 14)
        self.track_relationships: bool = params.get("track_relationships", False)

    async def execute(self, ctx: TickContext) -> TickContext:
        try:
            result = await ctx.db.execute(
                select(Resident).where(Resident.id != ctx.resident.id)
            )
            all_residents = result.scalars().all()

            nearby = []
            for r in all_residents:
                dist = abs(r.tile_x - ctx.resident.tile_x) + abs(r.tile_y - ctx.resident.tile_y)
                if dist <= self.radius:
                    nearby.append(r)

            ctx.nearby_residents = nearby
        except Exception as e:
            logger.warning("Social perceive failed for %s: %s", ctx.resident.slug, e)
            ctx.skip_remaining = True

        return ctx
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python3 -m pytest tests/test_agent_phases.py -v -k perceive`
Expected: All perceive tests PASS

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/agent/phases/perceive/
git add tests/test_agent_phases.py
git commit -m "feat(agent): add BasicPerceivePlugin and SocialPerceivePlugin"
```

---

### Task 5: BasicExecutePlugin + BasicMemorizePlugin + ReflectiveMemorizePlugin

**Files:**
- Create: `backend/app/agent/phases/execute/basic.py`
- Create: `backend/app/agent/phases/memorize/basic.py`
- Create: `backend/app/agent/phases/memorize/reflective.py`
- Modify: `backend/tests/test_agent_phases.py`

- [ ] **Step 1: Add tests for execute + memorize plugins**

```python
# Append to backend/tests/test_agent_phases.py

# ── Execute Tests ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_basic_execute_movement():
    from app.agent.phases.execute.basic import BasicExecutePlugin

    resident = _make_resident(tile_x=76, tile_y=50)
    ctx = _make_ctx(resident=resident)
    ctx.action_result = ActionResult(
        action=ActionType.WANDER,
        target_slug=None,
        target_tile=(80, 50),
        reason="散步",
    )

    with patch("app.agent.phases.execute.basic.get_walkable_tiles") as mock_wt, \
         patch("app.agent.phases.execute.basic.find_path") as mock_fp:
        mock_wt.return_value = {(76,50),(77,50),(78,50),(79,50),(80,50)}
        mock_fp.return_value = [(76,50),(77,50),(78,50),(79,50),(80,50)]
        plugin = BasicExecutePlugin(params={"max_steps_per_tick": 1})
        ctx = await plugin.execute(ctx)

    assert ctx.new_tile == (77, 50)
    assert resident.tile_x == 77


@pytest.mark.anyio
async def test_basic_execute_idle():
    from app.agent.phases.execute.basic import BasicExecutePlugin

    resident = _make_resident(status="idle")
    ctx = _make_ctx(resident=resident)
    ctx.action_result = ActionResult(
        action=ActionType.IDLE, target_slug=None, target_tile=None, reason="休息",
    )

    plugin = BasicExecutePlugin(params={})
    ctx = await plugin.execute(ctx)

    assert resident.status == "idle"


@pytest.mark.anyio
async def test_basic_execute_skips_when_no_action():
    from app.agent.phases.execute.basic import BasicExecutePlugin

    ctx = _make_ctx()
    ctx.action_result = None

    plugin = BasicExecutePlugin(params={})
    ctx = await plugin.execute(ctx)

    assert ctx.new_tile is None


# ── Memorize Tests ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_basic_memorize_creates_memory():
    from app.agent.phases.memorize.basic import BasicMemorizePlugin

    ctx = _make_ctx()
    ctx.action_result = ActionResult(
        action=ActionType.WANDER, target_slug=None, target_tile=(80, 50), reason="散步",
    )

    with patch("app.agent.phases.memorize.basic.MemoryService") as MockMS:
        mock_svc = AsyncMock()
        MockMS.return_value = mock_svc
        plugin = BasicMemorizePlugin(params={"base_importance": 0.3, "plan_deviation_boost": 0.2})
        ctx = await plugin.execute(ctx)

    mock_svc.add_memory.assert_called_once()
    call_kwargs = mock_svc.add_memory.call_args
    assert call_kwargs[1]["importance"] == 0.3
    assert ctx.memory_created is True


@pytest.mark.anyio
async def test_basic_memorize_boosts_importance_on_plan_deviation():
    from app.agent.phases.memorize.basic import BasicMemorizePlugin

    ctx = _make_ctx()
    ctx.action_result = ActionResult(
        action=ActionType.CHAT_RESIDENT, target_slug="alice", target_tile=None, reason="聊天",
    )
    ctx.plan_followed = False

    with patch("app.agent.phases.memorize.basic.MemoryService") as MockMS:
        mock_svc = AsyncMock()
        MockMS.return_value = mock_svc
        plugin = BasicMemorizePlugin(params={"base_importance": 0.3, "plan_deviation_boost": 0.2})
        ctx = await plugin.execute(ctx)

    call_kwargs = mock_svc.add_memory.call_args
    assert call_kwargs[1]["importance"] == pytest.approx(0.5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_agent_phases.py -v -k "execute or memorize"`
Expected: FAIL

- [ ] **Step 3: Implement BasicExecutePlugin**

```python
# backend/app/agent/phases/execute/basic.py
"""BasicExecutePlugin: handle movement and status changes."""
from __future__ import annotations

import logging
from typing import Any

from app.agent.actions import ActionType
from app.agent.pathfinder import get_walkable_tiles, find_path
from app.agent.schemas import TickContext

logger = logging.getLogger(__name__)


class BasicExecutePlugin:
    def __init__(self, params: dict[str, Any] | None = None):
        params = params or {}
        self.max_steps: int = params.get("max_steps_per_tick", 1)

    async def execute(self, ctx: TickContext) -> TickContext:
        if ctx.action_result is None:
            return ctx

        action = ctx.action_result.action
        movement_actions = {ActionType.WANDER, ActionType.GO_HOME, ActionType.VISIT_DISTRICT}

        try:
            if action in movement_actions and ctx.action_result.target_tile:
                walkable = get_walkable_tiles()
                path = find_path(
                    (ctx.resident.tile_x, ctx.resident.tile_y),
                    ctx.action_result.target_tile,
                    walkable,
                )
                if path and len(path) >= 2:
                    next_tile = path[1]
                    ctx.resident.tile_x = next_tile[0]
                    ctx.resident.tile_y = next_tile[1]
                    ctx.resident.status = "walking"
                    ctx.new_tile = next_tile
                    await ctx.db.commit()
                else:
                    ctx.new_tile = (ctx.resident.tile_x, ctx.resident.tile_y)
            elif action in {ActionType.IDLE, ActionType.NAP, ActionType.REFLECT, ActionType.JOURNAL}:
                if ctx.resident.status not in ("chatting", "socializing"):
                    ctx.resident.status = "idle"
                    await ctx.db.commit()
        except Exception as e:
            logger.warning("Execute failed for %s: %s", ctx.resident.slug, e)

        return ctx
```

- [ ] **Step 4: Implement BasicMemorizePlugin**

```python
# backend/app/agent/phases/memorize/basic.py
"""BasicMemorizePlugin: create event memory from action result."""
from __future__ import annotations

import logging
from typing import Any

from app.agent.actions import ActionType
from app.agent.schemas import TickContext
from app.memory.service import MemoryService

logger = logging.getLogger(__name__)


def format_action_memory(action_result, resident) -> str:
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


class BasicMemorizePlugin:
    def __init__(self, params: dict[str, Any] | None = None):
        params = params or {}
        self.base_importance: float = params.get("base_importance", 0.3)
        self.plan_deviation_boost: float = params.get("plan_deviation_boost", 0.2)

    async def execute(self, ctx: TickContext) -> TickContext:
        if ctx.action_result is None:
            return ctx

        importance = self.base_importance
        if not ctx.plan_followed:
            importance += self.plan_deviation_boost

        try:
            memory_content = format_action_memory(ctx.action_result, ctx.resident)
            memory_svc = MemoryService(ctx.db)
            await memory_svc.add_memory(
                resident_id=ctx.resident.id,
                type="event",
                content=memory_content,
                importance=importance,
                source="agent_action",
            )
            ctx.memory_created = True
        except Exception as e:
            logger.warning("Memorize failed for %s: %s", ctx.resident.slug, e)

        return ctx
```

- [ ] **Step 5: Implement ReflectiveMemorizePlugin**

```python
# backend/app/agent/phases/memorize/reflective.py
"""ReflectiveMemorizePlugin: extends BasicMemorizePlugin with auto-reflect chance."""
from __future__ import annotations

import logging
import random
from typing import Any

from app.agent.phases.memorize.basic import BasicMemorizePlugin, format_action_memory
from app.agent.schemas import TickContext
from app.memory.service import MemoryService

logger = logging.getLogger(__name__)


class ReflectiveMemorizePlugin(BasicMemorizePlugin):
    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        params = params or {}
        self.auto_reflect_chance: float = params.get("auto_reflect_chance", 0.15)
        self.reflection_depth: str = params.get("reflection_depth", "normal")

    async def execute(self, ctx: TickContext) -> TickContext:
        # First do normal memorize
        ctx = await super().execute(ctx)

        # Then maybe trigger a reflection
        if ctx.memory_created and random.random() < self.auto_reflect_chance:
            try:
                memory_svc = MemoryService(ctx.db)
                reflections = await memory_svc.generate_reflections(ctx.resident)
                if reflections:
                    logger.info(
                        "Auto-reflection triggered for %s: %d reflections",
                        ctx.resident.slug, len(reflections),
                    )
            except Exception as e:
                logger.warning("Auto-reflection failed for %s: %s", ctx.resident.slug, e)

        return ctx
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python3 -m pytest tests/test_agent_phases.py -v -k "execute or memorize"`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd backend && git add app/agent/phases/execute/ app/agent/phases/memorize/
git add tests/test_agent_phases.py
git commit -m "feat(agent): add BasicExecutePlugin, BasicMemorizePlugin, ReflectiveMemorizePlugin"
```

---

### Task 6: BasicDecidePlugin + Cautious + Spontaneous Variants

**Files:**
- Create: `backend/app/agent/phases/decide/basic.py`
- Create: `backend/app/agent/phases/decide/cautious.py`
- Create: `backend/app/agent/phases/decide/spontaneous.py`
- Modify: `backend/tests/test_agent_phases.py`

- [ ] **Step 1: Add tests for decide plugins**

```python
# Append to backend/tests/test_agent_phases.py

# ── Decide Tests ─────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_basic_decide_force_executes_high_importance_plan():
    from app.agent.phases.decide.basic import BasicDecidePlugin

    ctx = _make_ctx()
    ctx.current_plan = HourlyPlan(
        slot=3, hour_range=(9, 12), action="WORK",
        target=None, location="office", importance=7,
        reason="重要工作", status="pending",
    )
    ctx.available_actions = [ActionType.WORK, ActionType.IDLE, ActionType.WANDER]

    plugin = BasicDecidePlugin(params={"interrupt_threshold": 6, "plan_adherence_hint": True})
    ctx = await plugin.execute(ctx)

    assert ctx.action_result is not None
    assert ctx.action_result.action == ActionType.WORK
    assert ctx.plan_followed is True
    assert ctx.current_plan.status == "executing"


@pytest.mark.anyio
async def test_basic_decide_low_importance_calls_llm():
    from app.agent.phases.decide.basic import BasicDecidePlugin

    ctx = _make_ctx()
    ctx.current_plan = HourlyPlan(
        slot=0, hour_range=(7, 9), action="IDLE",
        target=None, location="home", importance=3,
        reason="早起休息", status="pending",
    )
    ctx.available_actions = [ActionType.IDLE, ActionType.WANDER, ActionType.OBSERVE]

    with patch("app.agent.phases.decide.basic.llm_chat") as mock_llm:
        mock_llm.return_value = '{"action": "WANDER", "target_slug": null, "target_tile": [80, 50], "reason": "出去走走"}'
        plugin = BasicDecidePlugin(params={"interrupt_threshold": 6, "plan_adherence_hint": True})
        ctx = await plugin.execute(ctx)

    assert ctx.action_result is not None
    assert ctx.action_result.action == ActionType.WANDER
    assert ctx.plan_followed is False
    assert ctx.current_plan.status == "interrupted"


@pytest.mark.anyio
async def test_basic_decide_no_plan_calls_llm():
    from app.agent.phases.decide.basic import BasicDecidePlugin

    ctx = _make_ctx()
    ctx.current_plan = None
    ctx.available_actions = [ActionType.IDLE, ActionType.WANDER]

    with patch("app.agent.phases.decide.basic.llm_chat") as mock_llm:
        mock_llm.return_value = '{"action": "IDLE", "target_slug": null, "target_tile": null, "reason": "发呆"}'
        plugin = BasicDecidePlugin(params={"interrupt_threshold": 6, "plan_adherence_hint": True})
        ctx = await plugin.execute(ctx)

    assert ctx.action_result is not None
    assert ctx.action_result.action == ActionType.IDLE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_agent_phases.py -v -k decide`
Expected: FAIL

- [ ] **Step 3: Implement BasicDecidePlugin**

```python
# backend/app/agent/phases/decide/basic.py
"""BasicDecidePlugin: decide next action, plan-aware with hybrid execution."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.agent.actions import ActionType, ActionResult, get_available_actions
from app.agent.prompts import build_decision_prompt
from app.agent.schemas import TickContext, parse_action_result
from app.config import settings
from app.llm.client import chat as llm_chat
from app.memory.service import MemoryService

logger = logging.getLogger(__name__)


class BasicDecidePlugin:
    def __init__(self, params: dict[str, Any] | None = None):
        params = params or {}
        self.interrupt_threshold: int = params.get("interrupt_threshold", 6)
        self.plan_adherence_hint: bool = params.get("plan_adherence_hint", True)

    async def execute(self, ctx: TickContext) -> TickContext:
        # Compute available actions
        ctx.available_actions = get_available_actions(ctx.resident, ctx.nearby_residents)

        # Retrieve memories for context
        await self._load_memories(ctx)

        plan = ctx.current_plan

        # Case 1: High-importance plan → force execute
        if plan and plan.importance >= self.interrupt_threshold:
            result = self._force_execute_plan(plan, ctx)
            if result:
                ctx.action_result = result
                ctx.plan_followed = True
                plan.status = "executing"
                return ctx

        # Case 2 & 3: Low-importance plan or no plan → call LLM
        try:
            action_result = await self._llm_decide(ctx)
        except Exception as e:
            logger.warning("Decide LLM failed for %s: %s", ctx.resident.slug, e)
            ctx.skip_remaining = True
            return ctx

        if action_result is None:
            ctx.skip_remaining = True
            return ctx

        # Validate action is available
        if action_result.action not in ctx.available_actions:
            logger.debug("Resident %s chose unavailable action %s", ctx.resident.slug, action_result.action)
            ctx.skip_remaining = True
            return ctx

        ctx.action_result = action_result

        # Check if LLM followed the plan
        if plan:
            try:
                planned_action = ActionType(plan.action)
                if action_result.action == planned_action:
                    ctx.plan_followed = True
                    plan.status = "executing"
                else:
                    ctx.plan_followed = False
                    plan.status = "interrupted"
            except ValueError:
                ctx.plan_followed = False

        return ctx

    def _force_execute_plan(self, plan, ctx: TickContext) -> ActionResult | None:
        """Build ActionResult directly from plan without LLM call."""
        try:
            action = ActionType(plan.action)
        except ValueError:
            logger.warning("Invalid action in plan: %s", plan.action)
            return None

        if action not in ctx.available_actions:
            return None

        return ActionResult(
            action=action,
            target_slug=plan.target,
            target_tile=None,
            reason=plan.reason[:100],
        )

    async def _llm_decide(self, ctx: TickContext) -> ActionResult | None:
        """Call LLM for decision, optionally injecting plan context."""
        today_key = datetime.now().strftime("%Y-%m-%d")
        today_actions = [
            m.content for m in ctx.memories
            if m.created_at and m.created_at.strftime("%Y-%m-%d") == today_key
        ]
        ctx.today_actions = today_actions

        system_prompt, user_prompt = build_decision_prompt(
            resident=ctx.resident,
            schedule_phase=ctx.schedule_phase,
            world_time=ctx.world_time,
            nearby_residents=ctx.nearby_residents,
            memories=ctx.memories,
            today_actions=today_actions,
            available_actions=ctx.available_actions,
            max_daily_actions=settings.agent_max_daily_actions,
        )

        # Inject plan hint if available
        if ctx.current_plan and self.plan_adherence_hint:
            plan = ctx.current_plan
            hint = f"\n\n你原本计划在这个时段 {plan.action}（{plan.reason}），但你可以根据当前情况改变主意。"
            user_prompt += hint

        raw = await llm_chat(system_prompt, [{"role": "user", "content": user_prompt}], max_tokens=200)
        return parse_action_result(raw)

    async def _load_memories(self, ctx: TickContext) -> None:
        """Load memories into ctx for decision prompt."""
        try:
            memory_svc = MemoryService(ctx.db)
            ctx.memories = await memory_svc.get_memories(ctx.resident.id, type="event", limit=10)
        except Exception as e:
            logger.warning("Memory retrieval failed for %s: %s", ctx.resident.slug, e)
            ctx.memories = []
```

- [ ] **Step 4: Implement CautiousDecidePlugin**

```python
# backend/app/agent/phases/decide/cautious.py
"""CautiousDecidePlugin: introvert variant — prefers solitude, resists social interruption."""
from __future__ import annotations

import logging
from typing import Any

from app.agent.actions import ActionType
from app.agent.phases.decide.basic import BasicDecidePlugin
from app.agent.schemas import TickContext

logger = logging.getLogger(__name__)


class CautiousDecidePlugin(BasicDecidePlugin):
    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        params = params or {}
        self.social_reluctance: bool = params.get("social_reluctance", True)

    async def _llm_decide(self, ctx: TickContext):
        """Override to inject social reluctance hint."""
        result = await super()._llm_decide(ctx)

        # If the LLM chose a social action and social_reluctance is on,
        # there's a chance to downgrade to a solo action
        if result and self.social_reluctance:
            social_actions = {ActionType.CHAT_RESIDENT, ActionType.GOSSIP, ActionType.CHAT_FOLLOW_UP}
            if result.action in social_actions:
                # Check if the plan says to be social; if not, resist
                plan = ctx.current_plan
                if plan and plan.action not in ("CHAT_RESIDENT", "GOSSIP", "CHAT_FOLLOW_UP"):
                    import random
                    if random.random() < 0.5:
                        from app.agent.actions import ActionResult
                        logger.debug("Cautious %s resisted social action", ctx.resident.slug)
                        result = ActionResult(
                            action=ActionType.OBSERVE,
                            target_slug=None,
                            target_tile=None,
                            reason="不太想社交",
                        )

        return result
```

- [ ] **Step 5: Implement SpontaneousDecidePlugin**

```python
# backend/app/agent/phases/decide/spontaneous.py
"""SpontaneousDecidePlugin: extravert variant — easily distracted, social-eager."""
from __future__ import annotations

import logging
import random
from typing import Any

from app.agent.actions import ActionType, ActionResult
from app.agent.phases.decide.basic import BasicDecidePlugin
from app.agent.schemas import TickContext

logger = logging.getLogger(__name__)


class SpontaneousDecidePlugin(BasicDecidePlugin):
    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        params = params or {}
        self.social_eagerness: bool = params.get("social_eagerness", True)
        self.distraction_chance: float = params.get("distraction_chance", 0.3)

    async def execute(self, ctx: TickContext) -> TickContext:
        # Chance to completely ignore plan and go free
        if ctx.current_plan and random.random() < self.distraction_chance:
            logger.debug("Spontaneous %s ignoring plan (distraction)", ctx.resident.slug)
            ctx.current_plan = None

        # If social eagerness and idle residents nearby, bias toward chat
        if self.social_eagerness and ctx.nearby_residents:
            idle_nearby = [r for r in ctx.nearby_residents
                          if r.status in ("idle", "walking")]
            if idle_nearby and random.random() < 0.4:
                target = random.choice(idle_nearby)
                ctx.action_result = ActionResult(
                    action=ActionType.CHAT_RESIDENT,
                    target_slug=target.slug,
                    target_tile=None,
                    reason="想聊天",
                )
                ctx.plan_followed = False
                if ctx.current_plan:
                    ctx.current_plan.status = "interrupted"
                # Still need to load memories for context
                await self._load_memories(ctx)
                return ctx

        return await super().execute(ctx)
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python3 -m pytest tests/test_agent_phases.py -v -k decide`
Expected: All decide tests PASS

- [ ] **Step 7: Commit**

```bash
cd backend && git add app/agent/phases/decide/
git add tests/test_agent_phases.py
git commit -m "feat(agent): add BasicDecidePlugin, CautiousDecidePlugin, SpontaneousDecidePlugin"
```

---

### Task 7: BasicPlanPlugin (LLM Daily Plan Generation)

**Files:**
- Create: `backend/app/agent/phases/plan/basic.py`
- Modify: `backend/tests/test_agent_phases.py`

- [ ] **Step 1: Add tests for plan plugin**

```python
# Append to backend/tests/test_agent_phases.py

# ── Plan Tests ───────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_basic_plan_generates_plan_when_stale():
    from app.agent.phases.plan.basic import BasicPlanPlugin

    resident = _make_resident()
    resident.daily_plans_json = None
    resident.daily_goal_json = None

    ctx = _make_ctx(resident=resident)

    llm_response = '''{
        "goal": {"goal": "学习新技能", "motivation": "好奇心驱使"},
        "plans": [
            {"slot": 0, "hour_range": [7, 9], "action": "IDLE", "target": null, "location": "home", "importance": 2, "reason": "起床"},
            {"slot": 1, "hour_range": [9, 11], "action": "STUDY", "target": null, "location": "library", "importance": 5, "reason": "学习"},
            {"slot": 2, "hour_range": [11, 13], "action": "IDLE", "target": null, "location": "home", "importance": 2, "reason": "午餐"}
        ]
    }'''

    with patch("app.agent.phases.plan.basic.llm_chat", return_value=llm_response), \
         patch("app.agent.phases.plan.basic.MemoryService") as MockMS:
        mock_svc = AsyncMock()
        mock_svc.get_memories = AsyncMock(return_value=[])
        MockMS.return_value = mock_svc

        plugin = BasicPlanPlugin(params={"hourly_slots": 3, "max_social_slots": 1, "max_high_importance": 1})
        ctx = await plugin.execute(ctx)

    assert resident.daily_goal_json is not None
    assert resident.daily_goal_json["goal"] == "学习新技能"
    assert resident.daily_plans_json is not None
    assert len(resident.daily_plans_json["plans"]) == 3


@pytest.mark.anyio
async def test_basic_plan_skips_when_fresh():
    from app.agent.phases.plan.basic import BasicPlanPlugin
    from datetime import datetime

    resident = _make_resident()
    today = datetime.now().strftime("%Y-%m-%d")
    resident.daily_goal_json = {"goal": "existing", "motivation": "test", "created_at": "now", "status": "active"}
    resident.daily_plans_json = {
        "generated_date": today,
        "plans": [
            {"slot": 0, "hour_range": [7, 9], "action": "IDLE", "target": None, "location": "home", "importance": 2, "reason": "休息", "status": "pending"},
        ],
    }

    ctx = _make_ctx(resident=resident, db=AsyncMock())
    ctx.hour = 8  # within slot 0's range

    plugin = BasicPlanPlugin(params={"hourly_slots": 1})
    ctx = await plugin.execute(ctx)

    assert ctx.current_plan is not None
    assert ctx.current_plan.action == "IDLE"


@pytest.mark.anyio
async def test_basic_plan_sets_current_plan_for_matching_slot():
    from app.agent.phases.plan.basic import BasicPlanPlugin
    from datetime import datetime

    resident = _make_resident()
    today = datetime.now().strftime("%Y-%m-%d")
    resident.daily_goal_json = {"goal": "test", "motivation": "test", "created_at": "now", "status": "active"}
    resident.daily_plans_json = {
        "generated_date": today,
        "plans": [
            {"slot": 0, "hour_range": [7, 9], "action": "IDLE", "target": None, "location": "home", "importance": 2, "reason": "休息", "status": "pending"},
            {"slot": 1, "hour_range": [9, 12], "action": "WORK", "target": None, "location": "office", "importance": 6, "reason": "工作", "status": "pending"},
        ],
    }

    ctx = _make_ctx(resident=resident)
    ctx.hour = 10  # within slot 1's range

    plugin = BasicPlanPlugin(params={"hourly_slots": 2})
    ctx = await plugin.execute(ctx)

    assert ctx.current_plan is not None
    assert ctx.current_plan.action == "WORK"
    assert ctx.current_plan.importance == 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_agent_phases.py -v -k plan`
Expected: FAIL

- [ ] **Step 3: Implement BasicPlanPlugin**

```python
# backend/app/agent/phases/plan/basic.py
"""BasicPlanPlugin: generate daily goal + hourly plans via LLM."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.agent.actions import ActionType
from app.agent.scheduler import build_schedule
from app.agent.schemas import TickContext, DailyGoal, HourlyPlan
from app.config import settings
from app.llm.client import chat as llm_chat
from app.memory.service import MemoryService

logger = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = """\
你是一个游戏 NPC 的日程规划器。根据居民的性格和记忆，生成今天的目标和分时段行动计划。

居民信息：
- 姓名：{name}
- 人格类型（SBTI）：{sbti_type}（{sbti_name}）
- 性格描述：{persona_snippet}

活跃时段：{wake_hour}:00 - {sleep_hour}:00，共 {slot_count} 个时段

可选行动：{action_types}

约束：
- importance 1-10，大部分为 2-4，最多 {max_high_importance} 个时段 >= 6
- 社交行动（CHAT_RESIDENT/GOSSIP）最多 {max_social_slots} 个时段
- 以第一人称自然表达目标，不要生硬的开头
{preferred_actions_hint}

输出严格 JSON，不要其他文字：
{{
  "goal": {{"goal": "今日目标描述", "motivation": "动机"}},
  "plans": [
    {{"slot": 0, "hour_range": [{start_0}, {end_0}], "action": "ACTION_TYPE", "target": null, "location": "地点", "importance": 3, "reason": "原因"}},
    ...
  ]
}}
"""

PLAN_USER_PROMPT = """\
最近的重要记忆：
{recent_memories}

最近的关系：
{relationships}

请生成今天的目标和 {slot_count} 个时段的计划。
"""


class BasicPlanPlugin:
    def __init__(self, params: dict[str, Any] | None = None):
        params = params or {}
        self.plan_interval_hours: int = params.get("plan_interval_hours", 24)
        self.hourly_slots: int = params.get("hourly_slots", 7)
        self.max_social_slots: int = params.get("max_social_slots", 2)
        self.max_high_importance: int = params.get("max_high_importance", 2)
        self.preferred_actions: list[str] = params.get("preferred_actions", [])

    async def execute(self, ctx: TickContext) -> TickContext:
        today = datetime.now().strftime("%Y-%m-%d")

        # Check if plans are stale
        plans_data = ctx.resident.daily_plans_json
        is_fresh = (
            plans_data
            and isinstance(plans_data, dict)
            and plans_data.get("generated_date") == today
        )

        if not is_fresh:
            try:
                await self._generate_plan(ctx, today)
            except Exception as e:
                logger.warning("Plan generation failed for %s: %s", ctx.resident.slug, e)
                return ctx

        # Load daily goal into context
        goal_data = ctx.resident.daily_goal_json
        if goal_data:
            ctx.daily_goal = DailyGoal(
                goal=goal_data.get("goal", ""),
                motivation=goal_data.get("motivation", ""),
                created_at=goal_data.get("created_at", ""),
                status=goal_data.get("status", "active"),
            )

        # Find current time slot
        plans_data = ctx.resident.daily_plans_json
        if plans_data and "plans" in plans_data:
            for p in plans_data["plans"]:
                hr = p.get("hour_range", [0, 0])
                if hr[0] <= ctx.hour < hr[1]:
                    ctx.current_plan = HourlyPlan(
                        slot=p["slot"],
                        hour_range=tuple(hr),
                        action=p["action"],
                        target=p.get("target"),
                        location=p.get("location"),
                        importance=p["importance"],
                        reason=p.get("reason", ""),
                        status=p.get("status", "pending"),
                    )
                    break

        return ctx

    async def _generate_plan(self, ctx: TickContext, today: str) -> None:
        """Call LLM to generate daily plan."""
        resident = ctx.resident
        sbti = (resident.meta_json or {}).get("sbti", {})
        schedule = build_schedule(sbti)

        # Compute time slots
        awake_hours = schedule.sleep_hour - schedule.wake_hour
        slot_duration = max(1, awake_hours // self.hourly_slots)
        slots_info = []
        for i in range(self.hourly_slots):
            start = schedule.wake_hour + i * slot_duration
            end = min(start + slot_duration, schedule.sleep_hour)
            if start >= schedule.sleep_hour:
                break
            slots_info.append((i, start, end))

        # Fetch memories for context
        memory_svc = MemoryService(ctx.db)
        recent = await memory_svc.get_memories(resident.id, type="event", limit=5)
        rels = await memory_svc.get_memories(resident.id, type="relationship", limit=3)

        recent_text = "\n".join(f"- {m.content}" for m in recent) or "（无）"
        rels_text = "\n".join(f"- {m.content}" for m in rels) or "（无）"

        action_types = ", ".join(a.value for a in ActionType)

        preferred_hint = ""
        if self.preferred_actions:
            preferred_hint = "- 偏好行为权重：" + ", ".join(self.preferred_actions)

        system_prompt = PLAN_SYSTEM_PROMPT.format(
            name=resident.name,
            sbti_type=sbti.get("type", "OJBK"),
            sbti_name=sbti.get("type_name", "无所谓人"),
            persona_snippet=(resident.persona_md or "")[:200],
            wake_hour=schedule.wake_hour,
            sleep_hour=schedule.sleep_hour,
            slot_count=len(slots_info),
            action_types=action_types,
            max_high_importance=self.max_high_importance,
            max_social_slots=self.max_social_slots,
            preferred_actions_hint=preferred_hint,
            start_0=slots_info[0][1] if slots_info else 7,
            end_0=slots_info[0][2] if slots_info else 9,
        )

        user_prompt = PLAN_USER_PROMPT.format(
            recent_memories=recent_text,
            relationships=rels_text,
            slot_count=len(slots_info),
        )

        raw = await llm_chat(system_prompt, [{"role": "user", "content": user_prompt}], max_tokens=600)

        # Parse JSON response
        start_idx = raw.find('{')
        end_idx = raw.rfind('}') + 1
        if start_idx == -1 or end_idx <= start_idx:
            raise ValueError(f"No JSON in plan response: {raw[:200]}")

        data = json.loads(raw[start_idx:end_idx])

        # Store goal
        goal = data.get("goal", {})
        resident.daily_goal_json = {
            "goal": goal.get("goal", "无目标"),
            "motivation": goal.get("motivation", ""),
            "created_at": datetime.now().isoformat(),
            "status": "active",
        }

        # Store plans with status field
        plans = data.get("plans", [])
        for p in plans:
            p["status"] = "pending"

        resident.daily_plans_json = {
            "generated_date": today,
            "plans": plans,
        }

        await ctx.db.commit()
        logger.info("Generated daily plan for %s: %s (%d slots)",
                     resident.slug, goal.get("goal", "?"), len(plans))
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_agent_phases.py -v -k plan`
Expected: All plan tests PASS

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/agent/phases/plan/
git add tests/test_agent_phases.py
git commit -m "feat(agent): add BasicPlanPlugin with LLM daily goal + hourly plan generation"
```

---

### Task 8: DB Migration + Resident Model Update

**Files:**
- Modify: `backend/app/models/resident.py`
- Create: `backend/alembic/versions/007_add_daily_plan_fields.py`

- [ ] **Step 1: Add fields to Resident model**

Add these two lines after `home_tile_y` in `backend/app/models/resident.py:42`:

```python
    # --- Agent Planning (Plugin System) ---
    daily_goal_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    daily_plans_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 2: Create Alembic migration**

```python
# backend/alembic/versions/007_add_daily_plan_fields.py
"""Add daily_goal_json and daily_plans_json to residents for hierarchical planning.

Revision ID: 007_daily_plans
Revises: 006_add_personality_history
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa

revision = "007_daily_plans"
down_revision = "006_add_personality_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("residents", sa.Column("daily_goal_json", sa.JSON(), nullable=True))
    op.add_column("residents", sa.Column("daily_plans_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("residents", "daily_plans_json")
    op.drop_column("residents", "daily_goal_json")
```

- [ ] **Step 3: Verify model loads**

Run: `cd backend && python3 -c "from app.models.resident import Resident; print('OK')" `
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd backend && git add app/models/resident.py alembic/versions/007_add_daily_plan_fields.py
git commit -m "feat(agent): add daily_goal_json and daily_plans_json to Resident model"
```

---

### Task 9: Rewrite tick.py as Orchestrator + Wire into loop.py

**Files:**
- Modify: `backend/app/agent/tick.py`
- Modify: `backend/app/agent/loop.py`
- Create: `backend/tests/test_agent_tick_orchestrator.py`

- [ ] **Step 1: Write integration test for new tick orchestrator**

```python
# backend/tests/test_agent_tick_orchestrator.py
"""Integration test for the refactored tick.py orchestrator."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.actions import ActionType, ActionResult


def _make_resident(slug="test-r", tile_x=76, tile_y=50):
    r = MagicMock()
    r.id = f"id-{slug}"
    r.slug = slug
    r.name = "Test"
    r.tile_x = tile_x
    r.tile_y = tile_y
    r.status = "idle"
    r.district = "central"
    r.home_tile_x = 70
    r.home_tile_y = 45
    r.persona_md = "Friendly."
    r.meta_json = {"sbti": {"type": "CTRL", "type_name": "控制者", "dimensions": {"So1": "M", "Ac3": "M"}}}
    r.daily_goal_json = None
    r.daily_plans_json = None
    return r


@pytest.mark.anyio
async def test_tick_orchestrator_runs_all_phases():
    """Verify the orchestrator calls each phase in sequence."""
    from app.agent.tick import resident_tick

    resident = _make_resident()
    db = AsyncMock()

    # Mock the registry to return simple phases
    mock_phases = []
    call_order = []
    for name in ["perceive", "plan", "decide", "execute", "memorize"]:
        phase = AsyncMock()
        async def make_exec(n, p):
            async def _exec(ctx):
                call_order.append(n)
                if n == "decide":
                    ctx.action_result = ActionResult(
                        action=ActionType.IDLE, target_slug=None,
                        target_tile=None, reason="test",
                    )
                return ctx
            p.execute = _exec
        await make_exec(name, phase)
        mock_phases.append(phase)

    with patch("app.agent.tick.registry") as mock_reg, \
         patch("app.agent.tick._over_daily_limit", return_value=False):
        mock_reg.get_phases.return_value = mock_phases
        result = await resident_tick(db, resident)

    assert call_order == ["perceive", "plan", "decide", "execute", "memorize"]
    assert result is not None
    assert result.action == ActionType.IDLE


@pytest.mark.anyio
async def test_tick_orchestrator_respects_daily_limit():
    from app.agent.tick import resident_tick

    resident = _make_resident()
    db = AsyncMock()

    with patch("app.agent.tick._over_daily_limit", return_value=True):
        result = await resident_tick(db, resident)

    assert result is None


@pytest.mark.anyio
async def test_tick_orchestrator_stops_on_skip_remaining():
    from app.agent.tick import resident_tick

    resident = _make_resident()
    db = AsyncMock()

    call_order = []

    phase1 = AsyncMock()
    async def exec1(ctx):
        call_order.append("perceive")
        ctx.skip_remaining = True
        return ctx
    phase1.execute = exec1

    phase2 = AsyncMock()
    async def exec2(ctx):
        call_order.append("plan")
        return ctx
    phase2.execute = exec2

    with patch("app.agent.tick.registry") as mock_reg, \
         patch("app.agent.tick._over_daily_limit", return_value=False):
        mock_reg.get_phases.return_value = [phase1, phase2]
        result = await resident_tick(db, resident)

    assert call_order == ["perceive"]
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_agent_tick_orchestrator.py -v`
Expected: FAIL (old tick.py doesn't have `registry` import)

- [ ] **Step 3: Rewrite `tick.py` as slim orchestrator**

```python
# backend/app/agent/tick.py
"""Resident tick: slim orchestrator calling plugin phases."""
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.actions import ActionResult
from app.agent.registry import registry
from app.agent.schemas import TickContext, get_world_time
from app.config import settings
from app.models.resident import Resident

logger = logging.getLogger(__name__)

# Module-level daily action counters: {resident_id: count}
_daily_counts: dict[str, int] = {}
_last_reset_date: str = ""


def _check_and_reset_daily_counts() -> None:
    """Reset action counts at midnight."""
    global _last_reset_date
    today = datetime.now().strftime("%Y-%m-%d")
    if today != _last_reset_date:
        _daily_counts.clear()
        _last_reset_date = today


def _over_daily_limit(resident_id: str) -> bool:
    """Check if resident has exceeded daily action limit."""
    _check_and_reset_daily_counts()
    return _daily_counts.get(resident_id, 0) >= settings.agent_max_daily_actions


async def resident_tick(
    db: AsyncSession,
    resident: Resident,
) -> ActionResult | None:
    """Execute one autonomous tick for a resident via plugin chain.

    Loads the appropriate plugin chain for this resident's SBTI config,
    then runs each phase in sequence passing TickContext through.

    Returns ActionResult on success, None if skipped or failed.
    """
    if _over_daily_limit(resident.id):
        return None

    world_time, hour, schedule_phase = get_world_time()

    ctx = TickContext(
        db=db,
        resident=resident,
        world_time=world_time,
        hour=hour,
        schedule_phase=schedule_phase,
    )

    try:
        phases = registry.get_phases(resident)
    except RuntimeError as e:
        logger.error("Failed to load phases for %s: %s", resident.slug, e)
        return None

    for phase in phases:
        try:
            ctx = await phase.execute(ctx)
        except Exception as e:
            logger.warning("Phase failed for %s: %s", resident.slug, e)
            break
        if ctx.skip_remaining:
            break

    if ctx.action_result:
        _daily_counts[resident.id] = _daily_counts.get(resident.id, 0) + 1
        logger.debug("Resident %s ticked: %s -> %s",
                      resident.slug, ctx.action_result.action.value, ctx.action_result.reason)

    return ctx.action_result
```

- [ ] **Step 4: Add `registry.load_all()` to `loop.py` startup**

In `backend/app/agent/loop.py`, add the registry import and initialization:

```python
# At the top of loop.py, add import:
from app.agent.registry import registry

# In AgentLoop.run(), add registry init before the while loop:
    async def run(self) -> None:
        """Main loop — runs indefinitely."""
        registry.load_all()
        logger.info("AgentLoop started (interval=%ds, %d agent configs loaded)",
                     settings.agent_tick_interval, len(registry._configs))
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
```

- [ ] **Step 5: Run orchestrator tests**

Run: `cd backend && python3 -m pytest tests/test_agent_tick_orchestrator.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Run ALL existing tests to verify backward compat**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: All tests PASS (existing tests in `test_agent_scheduler.py`, `test_agent_actions.py`, `test_agent_loop.py` should still pass since `resident_tick()` signature is unchanged)

- [ ] **Step 7: Commit**

```bash
cd backend && git add app/agent/tick.py app/agent/loop.py tests/test_agent_tick_orchestrator.py
git commit -m "feat(agent): rewrite tick.py as plugin orchestrator, wire registry into AgentLoop"
```

---

### Task 10: WS Broadcast for Plan Generation + Final Integration Test

**Files:**
- Modify: `backend/app/agent/phases/plan/basic.py`
- Modify: `backend/tests/test_agent_phases.py`

- [ ] **Step 1: Add WS broadcast to BasicPlanPlugin after plan generation**

In `backend/app/agent/phases/plan/basic.py`, add broadcast after plan is stored in `_generate_plan()`:

```python
# At the top, add import:
from app.ws.manager import manager

# At the end of _generate_plan(), after the db.commit(), add:
        # Broadcast plan generation event
        try:
            top_plan = max(plans, key=lambda p: p.get("importance", 0)) if plans else None
            await manager.broadcast({
                "type": "resident_plan_generated",
                "resident_slug": resident.slug,
                "goal": goal.get("goal", ""),
                "plan_count": len(plans),
                "top_plan": {
                    "action": top_plan["action"],
                    "importance": top_plan["importance"],
                    "hour_range": top_plan.get("hour_range", []),
                } if top_plan else None,
            })
        except Exception as e:
            logger.debug("Plan broadcast failed (non-fatal): %s", e)
```

- [ ] **Step 2: Add test for broadcast**

```python
# Append to backend/tests/test_agent_phases.py

@pytest.mark.anyio
async def test_basic_plan_broadcasts_on_generation():
    from app.agent.phases.plan.basic import BasicPlanPlugin

    resident = _make_resident()
    resident.daily_plans_json = None
    resident.daily_goal_json = None

    ctx = _make_ctx(resident=resident)

    llm_response = '{"goal": {"goal": "test", "motivation": "test"}, "plans": [{"slot": 0, "hour_range": [7, 9], "action": "IDLE", "target": null, "location": "home", "importance": 3, "reason": "rest"}]}'

    with patch("app.agent.phases.plan.basic.llm_chat", return_value=llm_response), \
         patch("app.agent.phases.plan.basic.MemoryService") as MockMS, \
         patch("app.agent.phases.plan.basic.manager") as mock_mgr:
        mock_svc = AsyncMock()
        mock_svc.get_memories = AsyncMock(return_value=[])
        MockMS.return_value = mock_svc
        mock_mgr.broadcast = AsyncMock()

        plugin = BasicPlanPlugin(params={"hourly_slots": 1, "max_social_slots": 1, "max_high_importance": 1})
        ctx = await plugin.execute(ctx)

    mock_mgr.broadcast.assert_called_once()
    broadcast_data = mock_mgr.broadcast.call_args[0][0]
    assert broadcast_data["type"] == "resident_plan_generated"
    assert broadcast_data["resident_slug"] == resident.slug
```

- [ ] **Step 3: Run test**

Run: `cd backend && python3 -m pytest tests/test_agent_phases.py::test_basic_plan_broadcasts_on_generation -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Run type check**

Run: `cd backend && python3 -m py_compile app/agent/tick.py && python3 -m py_compile app/agent/registry.py && python3 -m py_compile app/agent/schemas.py && echo "OK"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd backend && git add app/agent/phases/plan/basic.py tests/test_agent_phases.py
git commit -m "feat(agent): add WS broadcast for plan generation events"
```

---

## Execution Summary

| Task | Description | Estimated Effort |
|------|-------------|-----------------|
| 1 | Schemas + utility extraction | 15 min |
| 2 | PhasePlugin protocol + package structure | 10 min |
| 3 | YAML configs + registry + config loader | 25 min |
| 4 | BasicPerceivePlugin + SocialPerceivePlugin | 15 min |
| 5 | BasicExecutePlugin + memorize plugins | 20 min |
| 6 | Decide plugins (Basic + Cautious + Spontaneous) | 30 min |
| 7 | BasicPlanPlugin (LLM daily plan generation) | 30 min |
| 8 | DB migration + Resident model update | 10 min |
| 9 | Rewrite tick.py + wire loop.py | 20 min |
| 10 | WS broadcast + final integration | 15 min |

**Total: ~10 tasks, ~190 minutes**

**Dependencies:** Tasks 1-2 are foundations. Task 3 depends on Task 2. Tasks 4-7 depend on Tasks 1-2 but are independent of each other. Task 8 is independent. Task 9 depends on all of 1-8. Task 10 depends on 7 and 9.
