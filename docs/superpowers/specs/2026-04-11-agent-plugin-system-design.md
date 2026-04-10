# Agent Plugin System + Hierarchical Planning

> Date: 2026-04-11
> Status: Draft
> Branch: feat/p1-memory-system

## Overview

Refactor the monolithic `tick.py` into a YAML-driven plugin architecture, and add a hierarchical planning system (DailyGoal + HourlyPlan with importance scoring). Inspired by [OpenStory](https://github.com/ZJU-LLMs/OpenStory)'s Agent-Kernel plugin model, adapted to Skills-World's SBTI personality system.

### Goals

1. **Plugin architecture**: Each tick phase (perceive/plan/decide/execute/memorize) is an independent plugin class, loaded dynamically from YAML config via `importlib`.
2. **Hierarchical planning**: Residents generate a daily goal + time-slot plans each day, giving NPC behavior long-term coherence.
3. **Importance scoring**: Each planned action has an importance score (1-10) that controls whether the plan is strictly followed or can be interrupted.
4. **SBTI-driven profiles**: Different SBTI types map to different YAML configs (default/introvert/extravert), each with different plugin combinations and parameters.

### Non-Goals

- Distributed execution (Ray/Redis) -- we stay single-process asyncio
- Frontend changes for displaying daily plans (future work)
- Memory consolidation/compression (separate feature)
- Dynamic agent addition/removal at runtime (P2)

---

## 1. Plugin System Architecture

### 1.1 Directory Structure

```
backend/app/agent/
├── registry.py              # PluginRegistry: importlib dynamic loading
├── config_loader.py         # Parse YAML -> AgentConfig dataclass
├── tick.py                  # Slim orchestrator: load config -> run phase chain
├── loop.py                  # Unchanged, still calls tick.resident_tick()
├── schemas.py               # DailyGoal, HourlyPlan, ActionResult, TickContext
├── prompts.py               # Unchanged (plan-phase prompts live in plan plugin)
├── phases/
│   ├── __init__.py
│   ├── base.py              # PhasePlugin Protocol
│   ├── perceive/
│   │   ├── __init__.py
│   │   ├── basic.py         # BasicPerceivePlugin (extracted from tick.py)
│   │   └── social.py        # SocialPerceivePlugin (wider radius, relationship awareness)
│   ├── plan/
│   │   ├── __init__.py
│   │   └── basic.py         # BasicPlanPlugin (NEW: daily goal + hourly plans)
│   ├── decide/
│   │   ├── __init__.py
│   │   ├── basic.py         # BasicDecidePlugin (extracted from tick.py, plan-aware)
│   │   ├── cautious.py      # CautiousDecidePlugin (introvert: prefers solitude)
│   │   └── spontaneous.py   # SpontaneousDecidePlugin (extravert: easily distracted)
│   ├── execute/
│   │   ├── __init__.py
│   │   └── basic.py         # BasicExecutePlugin (extracted from tick.py)
│   └── memorize/
│       ├── __init__.py
│       ├── basic.py          # BasicMemorizePlugin (extracted from tick.py)
│       └── reflective.py     # ReflectiveMemorizePlugin (auto-reflect chance)
└── configs/
    ├── default.yaml
    ├── introvert.yaml
    └── extravert.yaml
```

### 1.2 Core Interface

```python
# phases/base.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class PhasePlugin(Protocol):
    async def execute(self, ctx: TickContext) -> TickContext:
        """Execute this phase, read/write TickContext and return it."""
        ...
```

All phases communicate through `TickContext`. Each plugin only reads/writes the fields it cares about.

### 1.3 PluginRegistry

```python
# registry.py
class PluginRegistry:
    _configs: dict[str, AgentConfig] = {}
    _phase_cache: dict[str, list[PhasePlugin]] = {}
    CONFIG_DIR = Path(__file__).parent / "configs"

    def load_all(self) -> None:
        """Scan configs/ dir at startup, load all YAML files."""

    def get_phases(self, resident: Resident) -> list[PhasePlugin]:
        """Get instantiated plugin chain for a resident (cached by config name)."""

    def _import_class(self, dotted_path: str) -> type:
        """'app.agent.phases.plan.basic.BasicPlanPlugin' -> class ref"""
```

### 1.4 Resident -> Config Mapping

```python
def resolve_config_name(resident: Resident) -> str:
    # 1. Explicit override in meta_json.agent_config
    # 2. Auto-map from SBTI dimensions:
    #    So1=L -> "introvert"
    #    So1=H + Ac3=H -> "extravert"
    #    else -> "default"
```

---

## 2. Hierarchical Planning System

### 2.1 Data Models

```python
# schemas.py

@dataclass
class DailyGoal:
    goal: str           # "Go to the library to research ancient texts"
    motivation: str     # "Recently developed a strong interest in history"
    created_at: str     # ISO datetime
    status: str         # "active" | "completed" | "abandoned"

@dataclass
class HourlyPlan:
    slot: int                    # 0-based slot index
    hour_range: tuple[int, int]  # (9, 12) means 9:00-12:00
    action: str                  # "STUDY"
    target: str | None           # target resident slug or None
    location: str | None         # target district name
    importance: int              # 1-10
    reason: str                  # one-sentence rationale
    status: str                  # "pending" | "executing" | "done" | "interrupted"

@dataclass
class DailySchedulePlan:
    goal: DailyGoal
    plans: list[HourlyPlan]
    generated_date: str          # "2026-04-11"
```

### 2.2 DB Changes (Resident Model)

Two new nullable JSON columns on `residents` table:

```python
daily_goal_json: Mapped[dict | None]   # DailyGoal serialized
daily_plans_json: Mapped[list | None]  # list[HourlyPlan] serialized
```

No separate table. Overwritten daily, no history needed.

### 2.3 Plan Generation (BasicPlanPlugin)

```
execute(ctx) flow:

1. Check if resident.daily_plans_json is stale (generated_date != today)
   ├── Stale -> call LLM to generate new DailyGoal + HourlyPlans
   └── Fresh -> skip generation

2. Find the HourlyPlan matching current time slot
   └── Write to ctx.current_plan (for decide phase)

3. Return ctx
```

LLM prompt inputs:
- SBTI type + persona_md (first 200 chars)
- Recent important memories (top 5 with importance > 0.5)
- Yesterday's event memory summary
- Top 3 relationship memories
- Wake/sleep hours from SBTI schedule
- Available action types

LLM outputs a single JSON with `goal` + `plans[]`.

### 2.4 Importance Scoring Semantics

| Score | Meaning | Example |
|-------|---------|---------|
| 1-3 | Daily routine, low plot impact | Rest, eat, idle, wander |
| 4-5 | Normal activity, some value | Visit a place, study, work |
| 6-7 | Important, drives narrative | Key conversation, decision |
| 8-10 | Critical event, major impact | Conflict, confession, turning point |

Constraints per day (enforced in plan prompt):
- Most slots should be 2-4
- Max 2-3 slots can be >= 6
- Social actions (CHAT_RESIDENT/GOSSIP) capped per config

---

## 3. TickContext Data Flow

```python
@dataclass
class TickContext:
    # Input (populated at tick start)
    db: AsyncSession
    resident: Resident
    world_time: str
    hour: int
    schedule_phase: str

    # Phase 1: Perceive
    nearby_residents: list[Resident]

    # Phase 2: Plan
    current_plan: HourlyPlan | None
    daily_goal: DailyGoal | None

    # Phase 3: Decide
    action_result: ActionResult | None
    plan_followed: bool

    # Phase 4: Execute
    new_tile: tuple[int, int] | None

    # Phase 5: Memorize
    memory_created: bool

    # Shared context
    memories: list[Memory]
    today_actions: list[str]
    available_actions: list[ActionType]

    # Control flow
    skip_remaining: bool          # Any phase can set True to skip rest
```

### Phase Data Flow Diagram

```
Perceive ──nearby_residents──> Plan ──current_plan──> Decide ──action_result──> Execute ──new_tile──> Memorize
                                     ──daily_goal──>         ──plan_followed──>                          │
                                                                                                         v
                                                                                                    Memory record
```

### Memory Retrieval Responsibility

The old `tick.py` had an explicit "retrieve" phase. In the new design:

- **PlanPlugin**: Fetches memories independently via `MemoryService(ctx.db)` when generating a new daily plan (only once per day). Does NOT write to `ctx.memories`.
- **DecidePlugin**: Fills `ctx.memories` and `ctx.today_actions` at the start of its `execute()`, before building the LLM prompt. This is the single source of truth for memory context in each tick.
- **MemorizePlugin**: Reads `ctx.action_result` to create new memories, does not read `ctx.memories`.

This avoids redundant DB queries — plan generation (rare) and per-tick decisions (frequent) each fetch only what they need.

### Orchestrator (slim tick.py)

```python
async def resident_tick(db, resident) -> ActionResult | None:
    if _over_daily_limit(resident.id): return None
    ctx = TickContext(db=db, resident=resident, ...)
    phases = registry.get_phases(resident)
    for phase in phases:
        ctx = await phase.execute(ctx)
        if ctx.skip_remaining: break
    if ctx.action_result: _increment_daily_count(resident.id)
    return ctx.action_result
```

---

## 4. Hybrid Plan Execution

The decide phase uses `interrupt_threshold` (from YAML config) to determine plan enforcement:

```
current_plan.importance >= interrupt_threshold:
    -> Force-execute planned action, skip LLM call
    -> plan.status = "executing"

current_plan.importance < interrupt_threshold:
    -> Inject plan as context hint in LLM prompt
    -> LLM may follow or deviate
    -> If deviated: plan.status = "interrupted"

No current_plan for this time slot:
    -> Free decision, normal LLM call
```

### Per-Config Behavior

| Config | Threshold | Effect |
|--------|-----------|--------|
| default | >= 6 | Moderate: follows important plans, flexible on routine |
| introvert | >= 5 | Strict: follows most plans, rarely interrupted |
| extravert | >= 8 | Loose: only follows critical plans, easily distracted |

---

## 5. YAML Configurations

### 5.1 default.yaml

```yaml
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

### 5.2 introvert.yaml

```yaml
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

### 5.3 extravert.yaml

```yaml
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

---

## 6. Migration Path

| Original File | Destination |
|---------------|-------------|
| `tick.py` _perceive() | `phases/perceive/basic.py` |
| `tick.py` decide logic + LLM call | `phases/decide/basic.py` |
| `tick.py` _execute_movement() | `phases/execute/basic.py` |
| `tick.py` memorize logic | `phases/memorize/basic.py` |
| `tick.py` parse_action_result() | `schemas.py` (utility) |
| `tick.py` _get_world_time() | `schemas.py` (utility) |
| `tick.py` daily_counts | Stays in tick.py orchestrator |
| `prompts.py` | Unchanged, decide plugins still import from it |
| `scheduler.py` | Unchanged, loop.py still imports from it |
| `actions.py` | Unchanged |
| `loop.py` | Add `registry.load_all()` at startup, rest unchanged |

### Backward Compatibility

- `resident_tick()` signature unchanged: `(db, resident) -> ActionResult | None`
- `AgentLoop._handle_action()` unchanged: consumes `ActionResult` as before
- WS broadcast messages unchanged (existing types preserved)
- New WS message type added: `resident_plan_generated`

---

## 7. Plugin Inventory

First batch: **9 plugin classes** to implement.

| Phase | Plugin | Complexity | Notes |
|-------|--------|------------|-------|
| Perceive | BasicPerceivePlugin | Low | Direct extract from tick.py |
| Perceive | SocialPerceivePlugin | Medium | Adds relationship lookup during perception |
| Plan | BasicPlanPlugin | High | New LLM call, JSON parsing, DB write |
| Decide | BasicDecidePlugin | Medium | Extract + add plan context injection |
| Decide | CautiousDecidePlugin | Medium | Extends Basic with social_reluctance prompt |
| Decide | SpontaneousDecidePlugin | Medium | Extends Basic with distraction_chance |
| Execute | BasicExecutePlugin | Low | Direct extract from tick.py |
| Memorize | BasicMemorizePlugin | Low | Direct extract from tick.py |
| Memorize | ReflectiveMemorizePlugin | Medium | Extends Basic with auto-reflect trigger |

Plus infrastructure: `registry.py`, `config_loader.py`, `schemas.py` (TickContext + plan types), Alembic migration.
