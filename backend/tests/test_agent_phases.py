"""Tests for agent phase plugins."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agent.actions import ActionType
from app.agent.schemas import TickContext, HourlyPlan


def _make_resident(slug="test-resident"):
    r = MagicMock()
    r.id = "res-1"
    r.slug = slug
    r.name = "Test Resident"
    r.district = "engineering"
    r.status = "idle"
    r.tile_x = 10
    r.tile_y = 10
    r.home_tile_x = 5
    r.home_tile_y = 5
    r.meta_json = {"sbti": {"type": "GOGO", "type_name": "行者", "dimensions": {
        "S1": "H", "S2": "H", "S3": "M",
        "E1": "H", "E2": "M", "E3": "H",
        "A1": "M", "A2": "M", "A3": "H",
        "Ac1": "H", "Ac2": "H", "Ac3": "H",
        "So1": "M", "So2": "H", "So3": "M",
    }}}
    return r


def _make_ctx():
    db = AsyncMock()
    resident = _make_resident()
    ctx = TickContext(
        db=db,
        resident=resident,
        world_time="10:00",
        hour=10,
        schedule_phase="上午",
        nearby_residents=[],
        current_plan=None,
        available_actions=[ActionType.WORK, ActionType.IDLE, ActionType.WANDER, ActionType.OBSERVE],
    )
    return ctx


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

    with patch("app.agent.phases.decide.basic.MemoryService") as MockMS:
        mock_svc = AsyncMock()
        mock_svc.get_memories = AsyncMock(return_value=[])
        MockMS.return_value = mock_svc

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

    with patch("app.agent.phases.decide.basic.llm_chat") as mock_llm, \
         patch("app.agent.phases.decide.basic.MemoryService") as MockMS:
        mock_llm.return_value = '{"action": "WANDER", "target_slug": null, "target_tile": [80, 50], "reason": "出去走走"}'
        mock_svc = AsyncMock()
        mock_svc.get_memories = AsyncMock(return_value=[])
        MockMS.return_value = mock_svc

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

    with patch("app.agent.phases.decide.basic.llm_chat") as mock_llm, \
         patch("app.agent.phases.decide.basic.MemoryService") as MockMS:
        mock_llm.return_value = '{"action": "IDLE", "target_slug": null, "target_tile": null, "reason": "发呆"}'
        mock_svc = AsyncMock()
        mock_svc.get_memories = AsyncMock(return_value=[])
        MockMS.return_value = mock_svc

        plugin = BasicDecidePlugin(params={"interrupt_threshold": 6, "plan_adherence_hint": True})
        ctx = await plugin.execute(ctx)

    assert ctx.action_result is not None
    assert ctx.action_result.action == ActionType.IDLE


# ── Plan Tests ───────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_basic_plan_generates_plan_when_stale():
    from app.agent.phases.plan.basic import BasicPlanPlugin

    ctx = _make_ctx()
    resident = ctx.resident
    resident.daily_plans_json = None
    resident.daily_goal_json = None
    resident.persona_md = "A curious learner."

    llm_response = '{"goal": {"goal": "学习新技能", "motivation": "好奇心驱使"}, "plans": [{"slot": 0, "hour_range": [7, 9], "action": "IDLE", "target": null, "location": "home", "importance": 2, "reason": "起床"}, {"slot": 1, "hour_range": [9, 11], "action": "STUDY", "target": null, "location": "library", "importance": 5, "reason": "学习"}, {"slot": 2, "hour_range": [11, 13], "action": "IDLE", "target": null, "location": "home", "importance": 2, "reason": "午餐"}]}'

    with patch("app.agent.phases.plan.basic.llm_chat", return_value=llm_response), \
         patch("app.agent.phases.plan.basic.MemoryService") as MockMS, \
         patch("app.agent.phases.plan.basic.manager") as mock_mgr:
        mock_svc = AsyncMock()
        mock_svc.get_memories = AsyncMock(return_value=[])
        MockMS.return_value = mock_svc
        mock_mgr.broadcast = AsyncMock()

        plugin = BasicPlanPlugin(params={"hourly_slots": 3, "max_social_slots": 1, "max_high_importance": 1})
        ctx = await plugin.execute(ctx)

    assert resident.daily_goal_json is not None
    assert resident.daily_goal_json["goal"] == "学习新技能"
    assert resident.daily_plans_json is not None
    assert len(resident.daily_plans_json["plans"]) == 3


@pytest.mark.anyio
async def test_basic_plan_skips_when_fresh():
    from app.agent.phases.plan.basic import BasicPlanPlugin
    from datetime import datetime as dt

    ctx = _make_ctx()
    resident = ctx.resident
    today = dt.now().strftime("%Y-%m-%d")
    resident.daily_goal_json = {"goal": "existing", "motivation": "test", "created_at": "now", "status": "active"}
    resident.daily_plans_json = {
        "generated_date": today,
        "plans": [
            {"slot": 0, "hour_range": [7, 9], "action": "IDLE", "target": None, "location": "home", "importance": 2, "reason": "休息", "status": "pending"},
        ],
    }
    ctx.hour = 8

    plugin = BasicPlanPlugin(params={"hourly_slots": 1})
    ctx = await plugin.execute(ctx)

    assert ctx.current_plan is not None
    assert ctx.current_plan.action == "IDLE"


@pytest.mark.anyio
async def test_basic_plan_broadcasts_on_generation():
    from app.agent.phases.plan.basic import BasicPlanPlugin

    ctx = _make_ctx()
    resident = ctx.resident
    resident.daily_plans_json = None
    resident.daily_goal_json = None
    resident.persona_md = "A friendly person."

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
