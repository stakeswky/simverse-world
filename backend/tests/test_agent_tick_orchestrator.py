"""Integration test for the refactored tick.py orchestrator."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.actions import ActionType, ActionResult


def _make_resident(slug="test-r"):
    r = MagicMock()
    r.id = f"id-{slug}"
    r.slug = slug
    r.name = "Test"
    r.tile_x = 76
    r.tile_y = 50
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
    from app.agent.tick import resident_tick

    resident = _make_resident()
    db = AsyncMock()

    call_order = []

    class MockPhase:
        def __init__(self, name, set_action=False):
            self._name = name
            self._set_action = set_action

        async def execute(self, ctx):
            call_order.append(self._name)
            if self._set_action:
                ctx.action_result = ActionResult(
                    action=ActionType.IDLE, target_slug=None,
                    target_tile=None, reason="test",
                )
            return ctx

    mock_phases = [
        MockPhase("perceive"),
        MockPhase("plan"),
        MockPhase("decide", set_action=True),
        MockPhase("execute"),
        MockPhase("memorize"),
    ]

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

    class StopPhase:
        async def execute(self, ctx):
            call_order.append("perceive")
            ctx.skip_remaining = True
            return ctx

    class NeverPhase:
        async def execute(self, ctx):
            call_order.append("plan")
            return ctx

    with patch("app.agent.tick.registry") as mock_reg, \
         patch("app.agent.tick._over_daily_limit", return_value=False):
        mock_reg.get_phases.return_value = [StopPhase(), NeverPhase()]
        result = await resident_tick(db, resident)

    assert call_order == ["perceive"]
    assert result is None
