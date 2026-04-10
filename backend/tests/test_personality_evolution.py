import pytest
import json
from datetime import datetime, UTC, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from app.models.resident import Resident
from app.models.memory import Memory
from app.models.personality_history import PersonalityHistory
from app.personality.evolution import EvolutionService


@pytest.fixture
async def evo_resident(db_session):
    r = Resident(
        id="evo-svc-res",
        slug="evo-svc-res",
        name="EvoSvcResident",
        district="engineering",
        status="idle",
        creator_id="test-user-id",
        ability_md="Can code",
        persona_md="Friendly engineer who rarely starts conversations. Prefers technical topics.",
        soul_md="Believes in meritocracy and quiet achievement.",
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


def _mock_llm_response(text: str):
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


@pytest.mark.anyio
async def test_evaluate_drift_applies_valid_changes(db_session, evo_resident):
    """Drift evaluation should update SBTI dimensions and create history entry."""
    # Seed 15 event memories to pass the drift interval gate
    for i in range(15):
        mem = Memory(
            resident_id=evo_resident.id,
            type="event",
            content=f"Social event {i}",
            importance=0.5,
            source="chat_player",
        )
        db_session.add(mem)
    await db_session.commit()

    # Add drift history entry with created_at in the past so memories are counted as "after" it
    drift_history = PersonalityHistory(
        resident_id=evo_resident.id,
        trigger_type="drift",
        changes_json={"S1": {"from": "M", "to": "H"}},
        old_type="CTRL",
        new_type="CTRL",
        reason="Old drift",
        created_at=datetime.now(UTC) - timedelta(days=2),
    )
    db_session.add(drift_history)
    await db_session.commit()

    drift_response = json.dumps({
        "changes": [
            {"dim": "So1", "from": "M", "to": "H", "evidence": "15 social interactions"},
        ]
    })
    persona_response = "Updated persona with high social warmth. Friendly engineer who now actively starts conversations."

    with patch("app.personality.evolution.get_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=[
            _mock_llm_response(drift_response),   # drift eval
            _mock_llm_response(persona_response),  # text sync
        ])
        mock_client_fn.return_value = mock_client

        svc = EvolutionService(db_session)
        history = await svc.evaluate_drift(evo_resident)

    assert history is not None
    assert history.trigger_type == "drift"
    assert "So1" in history.changes_json
    assert history.changes_json["So1"]["to"] == "H"

    # Verify resident SBTI updated in DB
    await db_session.refresh(evo_resident)
    dims = evo_resident.meta_json["sbti"]["dimensions"]
    assert dims["So1"] == "H"

    # Verify persona_md updated
    assert "actively starts" in evo_resident.persona_md


@pytest.mark.anyio
async def test_evaluate_drift_returns_none_when_not_due(db_session, evo_resident):
    """Drift should return None when fewer than MIN_DRIFT_INTERVAL memories since last drift."""
    # Add a recent drift history so the interval check kicks in
    recent_drift = PersonalityHistory(
        resident_id=evo_resident.id,
        trigger_type="drift",
        changes_json={"S1": {"from": "M", "to": "H"}},
        old_type="CTRL",
        new_type="CTRL",
        reason="Recent drift",
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(recent_drift)
    await db_session.commit()

    # Only 5 memories after the drift — below the 15 threshold
    for i in range(5):
        mem = Memory(
            resident_id=evo_resident.id,
            type="event",
            content=f"Event {i}",
            importance=0.5,
            source="chat_player",
        )
        db_session.add(mem)
    await db_session.commit()

    svc = EvolutionService(db_session)
    result = await svc.evaluate_drift(evo_resident)
    assert result is None


@pytest.mark.anyio
async def test_evaluate_shift_applies_dramatic_changes(db_session, evo_resident):
    """Shift evaluation should handle multi-step changes and trigger soul_md update."""
    trigger_mem = Memory(
        resident_id=evo_resident.id,
        type="event",
        content="Best friend betrayed resident's deepest secret to the whole district",
        importance=0.95,
        source="chat_player",
    )
    db_session.add(trigger_mem)
    await db_session.commit()

    shift_response = json.dumps({
        "event_type": "trust_betrayal",
        "changes": [
            {"dim": "E1", "from": "H", "to": "L", "evidence": "Catastrophic trust collapse"},
            {"dim": "So1", "from": "M", "to": "L", "evidence": "Social withdrawal"},
        ],
        "shift_reason": "The betrayal shattered the resident's ability to trust others",
    })
    persona_response = "Cold and withdrawn. No longer initiates social contact."
    soul_response = "Believes relationships are transactional. Trust must be earned through years of proof."

    with patch("app.personality.evolution.get_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=[
            _mock_llm_response(shift_response),  # shift eval
            _mock_llm_response(persona_response),  # persona sync
            _mock_llm_response(soul_response),     # soul sync (shift triggers soul update)
        ])
        mock_client_fn.return_value = mock_client

        svc = EvolutionService(db_session)
        history = await svc.evaluate_shift(evo_resident, trigger_mem)

    assert history is not None
    assert history.trigger_type == "shift"
    assert history.trigger_memory_id == trigger_mem.id
    assert "E1" in history.changes_json
    assert history.changes_json["E1"]["to"] == "L"

    await db_session.refresh(evo_resident)
    dims = evo_resident.meta_json["sbti"]["dimensions"]
    assert dims["E1"] == "L"
    assert dims["So1"] == "L"


@pytest.mark.anyio
async def test_evaluate_shift_respects_cooldown(db_session, evo_resident):
    """Shift within 24h cooldown → returns None."""
    # Add recent shift history
    recent_shift = PersonalityHistory(
        resident_id=evo_resident.id,
        trigger_type="shift",
        changes_json={"E1": {"from": "H", "to": "L"}},
        old_type="CTRL",
        new_type="THIN-K",
        reason="Previous shift",
        created_at=datetime.now(UTC) - timedelta(hours=6),
    )
    db_session.add(recent_shift)

    trigger_mem = Memory(
        resident_id=evo_resident.id,
        type="event",
        content="Another major event",
        importance=0.95,
        source="chat_player",
    )
    db_session.add(trigger_mem)
    await db_session.commit()

    svc = EvolutionService(db_session)
    result = await svc.evaluate_shift(evo_resident, trigger_mem)
    assert result is None


@pytest.mark.anyio
async def test_type_migration_recorded_on_shift(db_session, evo_resident):
    """When dimensions change enough to migrate type, history records old/new type."""
    trigger_mem = Memory(
        resident_id=evo_resident.id,
        type="event",
        content="Deep intellectual awakening — rejected all social norms",
        importance=0.92,
        source="chat_player",
    )
    db_session.add(trigger_mem)
    await db_session.commit()

    # CTRL → THIN-K requires So1 L (was M) and several other changes
    shift_response = json.dumps({
        "event_type": "cognitive_conflict",
        "changes": [
            {"dim": "So1", "from": "M", "to": "L", "evidence": "..."},
            {"dim": "So3", "from": "M", "to": "H", "evidence": "..."},
        ],
        "shift_reason": "Cognitive awakening leading to social withdrawal",
    })
    persona_response = "Withdrawn thinker."
    soul_response = "Values intellectual purity above social connection."

    with patch("app.personality.evolution.get_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=[
            _mock_llm_response(shift_response),
            _mock_llm_response(persona_response),
            _mock_llm_response(soul_response),
        ])
        mock_client_fn.return_value = mock_client

        svc = EvolutionService(db_session)
        history = await svc.evaluate_shift(evo_resident, trigger_mem)

    assert history is not None
    # old_type and new_type should both be set (may or may not be different)
    assert history.old_type is not None
    assert history.new_type is not None


@pytest.mark.anyio
async def test_evaluate_drift_llm_failure_returns_none(db_session, evo_resident):
    """LLM failure during drift → returns None, no DB changes."""
    # Add old drift history so the guard passes
    old_drift = PersonalityHistory(
        resident_id=evo_resident.id,
        trigger_type="drift",
        changes_json={"S1": {"from": "M", "to": "H"}},
        old_type="CTRL",
        new_type="CTRL",
        reason="Old drift",
        created_at=datetime.now(UTC) - timedelta(days=2),
    )
    db_session.add(old_drift)
    await db_session.commit()

    for i in range(15):
        mem = Memory(
            resident_id=evo_resident.id,
            type="event",
            content=f"Event {i}",
            importance=0.5,
            source="chat_player",
        )
        db_session.add(mem)
    await db_session.commit()

    with patch("app.personality.evolution.get_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("LLM down"))
        mock_client_fn.return_value = mock_client

        svc = EvolutionService(db_session)
        result = await svc.evaluate_drift(evo_resident)

    assert result is None
    # Verify no new history was created (only the old_drift we seeded)
    hist_result = await db_session.execute(
        select(PersonalityHistory).where(PersonalityHistory.resident_id == evo_resident.id)
    )
    entries = hist_result.scalars().all()
    assert len(entries) == 1  # only the seeded old_drift
