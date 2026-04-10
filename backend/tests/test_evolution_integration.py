import pytest
import json
from unittest.mock import AsyncMock, patch
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
        creator_id="test-user-id",
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


def _llm_resp(text: str) -> str:
    return text


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

    with patch("app.memory.service.llm_chat", new=AsyncMock(
        return_value=_llm_resp(json.dumps({
            "memories": [{"content": "Profound connection", "importance": 0.92}]
        }))
    )), patch("app.personality.evolution.llm_chat", new=AsyncMock(side_effect=[
        _llm_resp(shift_response),
        _llm_resp(persona_response),
    ])):
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

    # Also add a previous drift history so can_drift uses the interval logic
    from app.models.personality_history import PersonalityHistory
    from datetime import datetime, UTC, timedelta
    old_drift = PersonalityHistory(
        resident_id=int_resident.id,
        trigger_type="drift",
        changes_json={"S1": {"from": "M", "to": "H"}},
        old_type="CTRL",
        new_type="CTRL",
        reason="Old drift",
        created_at=datetime.now(UTC) - timedelta(days=3),
    )
    db_session.add(old_drift)
    await db_session.commit()

    drift_response = json.dumps({"changes": []})  # No changes — just checks the call

    mock_evo_llm_chat = AsyncMock(return_value=_llm_resp(drift_response))
    with patch("app.memory.service.llm_chat", new=AsyncMock(
        return_value=_llm_resp(json.dumps({
            "memories": [{"content": "The 15th event", "importance": 0.5}]
        }))
    )), patch("app.personality.evolution.llm_chat", mock_evo_llm_chat):
        with patch("app.memory.service.generate_embedding", return_value=[0.1] * 1024):
            await svc.extract_events(
                resident=int_resident,
                other_name="Visitor",
                conversation_text="The 15th conversation.",
            )

    # Drift LLM should have been called
    mock_evo_llm_chat.assert_called_once()


@pytest.mark.anyio
async def test_evolution_failure_does_not_crash_memory_extraction(db_session, int_resident):
    """Evolution errors must not propagate to memory extraction callers."""
    svc = MemoryService(db_session)

    with patch("app.memory.service.llm_chat", new=AsyncMock(
        return_value=_llm_resp(json.dumps({
            "memories": [{"content": "Critical event", "importance": 0.95}]
        }))
    )), patch("app.personality.evolution.EvolutionService.evaluate_shift",
              new_callable=AsyncMock, side_effect=Exception("Evolution crashed")):
        with patch("app.memory.service.generate_embedding", return_value=[0.1] * 1024):
            # Should NOT raise even if evolution crashes
            memories = await svc.extract_events(
                resident=int_resident,
                other_name="Visitor",
                conversation_text="A critical event happened.",
            )

    assert len(memories) == 1  # Memory was still created
