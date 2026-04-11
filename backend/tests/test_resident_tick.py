import pytest
import json
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from app.models.resident import Resident
from app.models.memory import Memory
from app.agent.actions import ActionType, ActionResult
from app.agent.tick import resident_tick, _daily_counts
from app.agent.schemas import parse_action_result


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
    return json.dumps({
        "action": action,
        "target_slug": target_slug,
        "target_tile": target_tile,
        "reason": reason,
    })


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
async def test_resident_tick_via_plugin_chain(db_session, tick_resident):
    """Tick should run plugin chain and return action result."""
    _daily_counts.clear()

    class MockPhase:
        def __init__(self, set_action=False):
            self._set_action = set_action
        async def execute(self, ctx):
            if self._set_action:
                ctx.action_result = ActionResult(
                    action=ActionType.IDLE, target_slug=None,
                    target_tile=None, reason="test",
                )
            return ctx

    with patch("app.agent.tick.registry") as mock_reg:
        mock_reg.get_phases.return_value = [
            MockPhase(), MockPhase(set_action=True), MockPhase(),
        ]
        result = await resident_tick(db_session, tick_resident)

    assert result is not None
    assert result.action == ActionType.IDLE


@pytest.mark.anyio
async def test_resident_tick_respects_daily_limit(db_session, tick_resident):
    """Tick should return None when daily action limit is reached."""
    from app.config import settings
    _daily_counts[tick_resident.id] = settings.agent_max_daily_actions

    result = await resident_tick(db_session, tick_resident)
    assert result is None


@pytest.mark.anyio
async def test_resident_tick_phase_failure_returns_none(db_session, tick_resident):
    """If a phase raises, tick should stop gracefully."""
    _daily_counts.clear()

    class FailPhase:
        async def execute(self, ctx):
            raise Exception("phase error")

    with patch("app.agent.tick.registry") as mock_reg:
        mock_reg.get_phases.return_value = [FailPhase()]
        result = await resident_tick(db_session, tick_resident)

    assert result is None
