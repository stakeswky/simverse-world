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
