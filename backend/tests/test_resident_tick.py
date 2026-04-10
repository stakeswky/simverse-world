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
