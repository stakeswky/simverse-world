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
