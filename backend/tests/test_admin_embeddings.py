import pytest
from unittest.mock import AsyncMock, patch

from app.models.user import User
from app.models.resident import Resident
from app.models.memory import Memory


@pytest.fixture
async def admin_user(db_session):
    user = User(
        id="admin-1",
        email="admin@test.local",
        hashed_password="x",
        name="Admin",
        is_admin=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def admin_token(admin_user):
    from app.services.auth_service import create_token
    return create_token(admin_user.id)


@pytest.fixture
async def seed_memories(db_session, admin_user):
    resident = Resident(
        id="r-1",
        slug="r-1",
        name="Alice",
        district="engineering",
        status="idle",
        creator_id=admin_user.id,
        ability_md="", persona_md="", soul_md="",
        meta_json={},
    )
    db_session.add(resident)
    for i in range(3):
        db_session.add(Memory(
            id=f"mem-{i}",
            resident_id="r-1",
            type="event",
            content=f"event {i}",
            importance=0.5,
            source="chat_player",
            embedding=None,
        ))
    await db_session.commit()


@pytest.mark.anyio
async def test_reembed_all_requires_admin(client):
    resp = await client.post("/admin/embeddings/reembed-all")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_reembed_all_enqueues_and_returns_count(
    client, admin_token, seed_memories
):
    mock_provider = AsyncMock()
    mock_provider.name = "mock"
    mock_provider.embed = AsyncMock(return_value=[0.9] * 1024)
    mock_provider.embed_batch = AsyncMock(return_value=[[0.9] * 1024] * 100)

    with patch("app.routers.admin.embeddings.get_active_provider", new=AsyncMock(return_value=mock_provider)):
        resp = await client.post(
            "/admin/embeddings/reembed-all",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["candidate_count"] == 3


@pytest.mark.anyio
async def test_reembed_event_memories_actually_writes_embeddings(
    db_engine, db_session, admin_user
):
    """Directly exercise the background task with a patched session factory."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from app.routers.admin import embeddings as embeddings_module

    # Seed 3 event memories with embedding=None
    resident = Resident(
        id="r-direct",
        slug="r-direct",
        name="Bob",
        district="engineering",
        status="idle",
        creator_id=admin_user.id,
        ability_md="", persona_md="", soul_md="",
        meta_json={},
    )
    db_session.add(resident)
    for i in range(3):
        db_session.add(Memory(
            id=f"mem-direct-{i}",
            resident_id="r-direct",
            type="event",
            content=f"direct event {i}",
            importance=0.5,
            source="chat_player",
            embedding=None,
        ))
    await db_session.commit()

    # Mock provider returns a valid non-zero vector
    mock_provider = AsyncMock()
    mock_provider.name = "mock"
    mock_provider.dimensions = 1024
    mock_provider.embed_batch = AsyncMock(return_value=[[0.3] * 1024] * 3)

    # Use the test engine's session factory
    test_session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    with patch("app.routers.admin.embeddings.async_session", test_session_factory):
        await embeddings_module._reembed_event_memories(mock_provider)

    # Verify embeddings were written
    from sqlalchemy import select
    rows = (await db_session.execute(select(Memory).where(Memory.id.like("mem-direct-%")))).scalars().all()
    assert len(rows) == 3
    for m in rows:
        assert m.embedding == [0.3] * 1024, f"memory {m.id} not updated"


@pytest.mark.anyio
async def test_reembed_skips_zero_vectors(db_engine, db_session, admin_user):
    """Provider failures produce zero vectors; re-embed should skip them, not write."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from app.routers.admin import embeddings as embeddings_module

    resident = Resident(
        id="r-zero",
        slug="r-zero",
        name="Carol",
        district="engineering",
        status="idle",
        creator_id=admin_user.id,
        ability_md="", persona_md="", soul_md="",
        meta_json={},
    )
    db_session.add(resident)
    # Seed 2 memories: one with existing embedding, one without
    db_session.add(Memory(
        id="mem-zero-keep",
        resident_id="r-zero",
        type="event",
        content="keep me",
        importance=0.5,
        source="chat_player",
        embedding=[0.5] * 1024,  # existing good embedding
    ))
    db_session.add(Memory(
        id="mem-zero-none",
        resident_id="r-zero",
        type="event",
        content="also keep me",
        importance=0.5,
        source="chat_player",
        embedding=None,  # no embedding
    ))
    await db_session.commit()

    # Mock provider returns ALL zero vectors (simulating failure)
    mock_provider = AsyncMock()
    mock_provider.name = "mock"
    mock_provider.dimensions = 1024
    mock_provider.embed_batch = AsyncMock(return_value=[[0.0] * 1024, [0.0] * 1024])

    test_session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    with patch("app.routers.admin.embeddings.async_session", test_session_factory):
        await embeddings_module._reembed_event_memories(mock_provider)

    # Existing embedding must NOT have been overwritten with zeros
    from sqlalchemy import select
    m_keep = (await db_session.execute(
        select(Memory).where(Memory.id == "mem-zero-keep")
    )).scalar_one()
    assert m_keep.embedding == [0.5] * 1024

    m_none = (await db_session.execute(
        select(Memory).where(Memory.id == "mem-zero-none")
    )).scalar_one()
    assert m_none.embedding is None  # still None; zero vec was skipped
