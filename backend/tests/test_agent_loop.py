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
                with patch("app.agent.loop.settings") as mock_settings:
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
