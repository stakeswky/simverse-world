import pytest
from datetime import datetime, UTC
from sqlalchemy import select
from app.models.personality_history import PersonalityHistory
from app.models.resident import Resident


@pytest.fixture
async def evolution_resident(db_session):
    r = Resident(
        id="evo-test-res",
        slug="evo-test-res",
        name="EvoResident",
        district="engineering",
        status="idle",
        creator_id="test-user-id",
        ability_md="Can code",
        persona_md="Friendly",
        soul_md="Curious",
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


@pytest.mark.anyio
async def test_create_drift_history(db_session, evolution_resident):
    entry = PersonalityHistory(
        resident_id=evolution_resident.id,
        trigger_type="drift",
        changes_json={"So1": {"from": "M", "to": "H"}},
        old_type="CTRL",
        new_type="CTRL",
        reason="Consistent social engagement over 15 memories",
    )
    db_session.add(entry)
    await db_session.commit()

    result = await db_session.execute(
        select(PersonalityHistory).where(PersonalityHistory.resident_id == evolution_resident.id)
    )
    saved = result.scalar_one()
    assert saved.trigger_type == "drift"
    assert saved.changes_json["So1"]["from"] == "M"
    assert saved.changes_json["So1"]["to"] == "H"
    assert saved.old_type == "CTRL"
    assert saved.new_type == "CTRL"
    assert saved.reason is not None
    assert saved.id is not None
    assert saved.created_at is not None


@pytest.mark.anyio
async def test_create_shift_history_with_type_migration(db_session, evolution_resident):
    entry = PersonalityHistory(
        resident_id=evolution_resident.id,
        trigger_type="shift",
        trigger_memory_id="some-memory-id",
        changes_json={
            "E1": {"from": "H", "to": "L"},
            "E2": {"from": "M", "to": "L"},
            "So1": {"from": "M", "to": "L"},
        },
        old_type="CTRL",
        new_type="THIN-K",
        reason="Severe trust betrayal event triggered deep emotional withdrawal",
    )
    db_session.add(entry)
    await db_session.commit()

    result = await db_session.execute(
        select(PersonalityHistory).where(
            PersonalityHistory.resident_id == evolution_resident.id,
            PersonalityHistory.trigger_type == "shift",
        )
    )
    saved = result.scalar_one()
    assert saved.trigger_memory_id == "some-memory-id"
    assert saved.new_type == "THIN-K"
    assert len(saved.changes_json) == 3


@pytest.mark.anyio
async def test_nullable_trigger_memory_id(db_session, evolution_resident):
    """Drift entries have no trigger_memory_id."""
    entry = PersonalityHistory(
        resident_id=evolution_resident.id,
        trigger_type="drift",
        changes_json={"A1": {"from": "M", "to": "H"}},
        old_type="GOGO",
        new_type="GOGO",
        reason="Accumulated optimistic interactions",
    )
    db_session.add(entry)
    await db_session.commit()

    result = await db_session.execute(
        select(PersonalityHistory).where(PersonalityHistory.id == entry.id)
    )
    saved = result.scalar_one()
    assert saved.trigger_memory_id is None


@pytest.mark.anyio
async def test_multiple_history_entries_ordered(db_session, evolution_resident):
    """Multiple history entries should be retrievable in created_at order."""
    for i, dim in enumerate(["S1", "E2", "So1"]):
        entry = PersonalityHistory(
            resident_id=evolution_resident.id,
            trigger_type="drift",
            changes_json={dim: {"from": "M", "to": "H"}},
            old_type="CTRL",
            new_type="CTRL",
            reason=f"Change {i}",
        )
        db_session.add(entry)
    await db_session.commit()

    result = await db_session.execute(
        select(PersonalityHistory)
        .where(PersonalityHistory.resident_id == evolution_resident.id)
        .order_by(PersonalityHistory.created_at.asc())
    )
    entries = result.scalars().all()
    assert len(entries) == 3
