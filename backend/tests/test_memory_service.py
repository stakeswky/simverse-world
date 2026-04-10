import pytest
from datetime import datetime, UTC, timedelta
from app.models.memory import Memory
from app.models.resident import Resident
from app.memory.service import MemoryService


@pytest.fixture
async def resident(db_session):
    r = Resident(
        id="mem-test-res",
        slug="mem-test-res",
        name="TestResident",
        district="engineering",
        status="idle",
        creator_id="test-user-id",
        ability_md="Can code",
        persona_md="Friendly",
        soul_md="Curious",
        meta_json={"sbti": {"type": "CTRL", "type_name": "拿捏者", "dimensions": {
            "S1": "H", "S2": "H", "S3": "H",
            "E1": "H", "E2": "M", "E3": "H",
            "A1": "M", "A2": "H", "A3": "H",
            "Ac1": "H", "Ac2": "H", "Ac3": "H",
            "So1": "M", "So2": "H", "So3": "M",
        }}},
    )
    db_session.add(r)
    await db_session.commit()
    return r


@pytest.mark.anyio
async def test_add_event_memory(db_session, resident):
    svc = MemoryService(db_session)
    mem = await svc.add_memory(
        resident_id=resident.id,
        type="event",
        content="Discussed AI with a visitor",
        importance=0.6,
        source="chat_player",
    )
    assert mem.id is not None
    assert mem.type == "event"
    assert mem.resident_id == resident.id


@pytest.mark.anyio
async def test_get_memories_by_type(db_session, resident):
    svc = MemoryService(db_session)
    await svc.add_memory(resident.id, "event", "Event 1", 0.5, "chat_player")
    await svc.add_memory(resident.id, "event", "Event 2", 0.6, "chat_player")
    await svc.add_memory(resident.id, "reflection", "Reflection 1", 0.8, "reflection")

    events = await svc.get_memories(resident.id, type="event")
    assert len(events) == 2

    reflections = await svc.get_memories(resident.id, type="reflection")
    assert len(reflections) == 1


@pytest.mark.anyio
async def test_get_relationship_memory(db_session, resident):
    svc = MemoryService(db_session)
    await svc.add_memory(
        resident.id, "relationship", "A friendly engineer",
        0.5, "chat_player", related_user_id="user-1",
        metadata_json={"affinity": 0.3, "trust": 0.5, "tags": ["engineer"]},
    )

    rel = await svc.get_relationship(resident.id, user_id="user-1")
    assert rel is not None
    assert rel.metadata_json["affinity"] == 0.3

    no_rel = await svc.get_relationship(resident.id, user_id="user-999")
    assert no_rel is None


@pytest.mark.anyio
async def test_get_relationship_with_resident(db_session, resident):
    svc = MemoryService(db_session)
    await svc.add_memory(
        resident.id, "relationship", "A creative artist",
        0.5, "chat_resident", related_resident_id="other-res-1",
    )

    rel = await svc.get_relationship(resident.id, resident_id_target="other-res-1")
    assert rel is not None
    assert rel.content == "A creative artist"


@pytest.mark.anyio
async def test_update_relationship_memory(db_session, resident):
    svc = MemoryService(db_session)
    await svc.add_memory(
        resident.id, "relationship", "Initial impression",
        0.3, "chat_player", related_user_id="user-1",
    )

    await svc.update_relationship(
        resident.id, user_id="user-1",
        content="Updated: now a close friend",
        importance=0.7,
        metadata_json={"affinity": 0.8, "trust": 0.9, "tags": ["friend"]},
    )

    rel = await svc.get_relationship(resident.id, user_id="user-1")
    assert rel.content == "Updated: now a close friend"
    assert rel.importance == 0.7
    assert rel.metadata_json["affinity"] == 0.8


@pytest.mark.anyio
async def test_get_recent_reflections(db_session, resident):
    svc = MemoryService(db_session)
    for i in range(5):
        await svc.add_memory(resident.id, "reflection", f"Reflection {i}", 0.5 + i * 0.1, "reflection")

    top3 = await svc.get_recent_reflections(resident.id, limit=3)
    assert len(top3) == 3
    # Ordered by importance descending
    assert top3[0].importance >= top3[1].importance


@pytest.mark.anyio
async def test_count_recent_events(db_session, resident):
    svc = MemoryService(db_session)
    await svc.add_memory(resident.id, "event", "Event 1", 0.5, "chat_player")
    await svc.add_memory(resident.id, "event", "Event 2", 0.5, "chat_player")

    count = await svc.count_events_since_last_reflection(resident.id)
    assert count == 2


@pytest.mark.anyio
async def test_evict_old_memories(db_session, resident):
    svc = MemoryService(db_session)
    # Create 5 event memories with varying importance
    for i in range(5):
        mem = await svc.add_memory(resident.id, "event", f"Event {i}", 0.1 * (i + 1), "chat_player")
        # Manually set older timestamps for lower importance ones
        mem.created_at = datetime.now(UTC) - timedelta(days=30 - i)
        mem.last_accessed_at = datetime.now(UTC) - timedelta(days=30 - i)
    await db_session.commit()

    # Evict down to max 3
    evicted = await svc.evict_memories(resident.id, max_events=3)
    assert evicted == 2

    remaining = await svc.get_memories(resident.id, type="event")
    assert len(remaining) == 3
