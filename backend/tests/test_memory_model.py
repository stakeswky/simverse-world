import pytest
from datetime import datetime, UTC
from sqlalchemy import select
from app.models.memory import Memory


@pytest.mark.anyio
async def test_create_event_memory(db_session):
    mem = Memory(
        resident_id="res-1",
        type="event",
        content="Talked with player about AI ethics",
        importance=0.7,
        source="chat_player",
    )
    db_session.add(mem)
    await db_session.commit()

    result = await db_session.execute(select(Memory).where(Memory.resident_id == "res-1"))
    saved = result.scalar_one()
    assert saved.type == "event"
    assert saved.content == "Talked with player about AI ethics"
    assert saved.importance == 0.7
    assert saved.source == "chat_player"
    assert saved.id is not None
    assert saved.created_at is not None
    assert saved.last_accessed_at is not None


@pytest.mark.anyio
async def test_create_relationship_memory(db_session):
    mem = Memory(
        resident_id="res-1",
        type="relationship",
        content="First meeting, they are an engineer who likes cats",
        importance=0.5,
        source="chat_player",
        related_user_id="user-1",
        metadata_json={"affinity": 0.3, "trust": 0.5, "tags": ["engineer", "cat-lover"]},
    )
    db_session.add(mem)
    await db_session.commit()

    result = await db_session.execute(
        select(Memory).where(Memory.related_user_id == "user-1")
    )
    saved = result.scalar_one()
    assert saved.type == "relationship"
    assert saved.metadata_json["affinity"] == 0.3


@pytest.mark.anyio
async def test_create_reflection_memory(db_session):
    mem = Memory(
        resident_id="res-1",
        type="reflection",
        content="People in the engineering district seem too busy to chat",
        importance=0.8,
        source="reflection",
    )
    db_session.add(mem)
    await db_session.commit()

    result = await db_session.execute(
        select(Memory).where(Memory.type == "reflection")
    )
    saved = result.scalar_one()
    assert saved.source == "reflection"
    assert saved.importance == 0.8


@pytest.mark.anyio
async def test_memory_nullable_fields(db_session):
    mem = Memory(
        resident_id="res-1",
        type="event",
        content="Observed two residents chatting",
        importance=0.3,
        source="observation",
    )
    db_session.add(mem)
    await db_session.commit()

    result = await db_session.execute(select(Memory).where(Memory.id == mem.id))
    saved = result.scalar_one()
    assert saved.related_resident_id is None
    assert saved.related_user_id is None
    assert saved.media_url is None
    assert saved.media_summary is None
    assert saved.embedding is None
