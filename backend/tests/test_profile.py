import pytest
from app.models.resident import Resident
from app.models.conversation import Conversation
from app.models.transaction import Transaction
from app.models.user import User


@pytest.fixture
async def auth_headers(client):
    resp = await client.post("/auth/register", json={
        "name": "ProfileUser", "email": "profile@test.com", "password": "pass123"
    })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def seeded_user_residents(db_session, auth_headers, client):
    """Seed 2 residents belonging to the test user."""
    # Get user id from /users/me
    me = await client.get("/users/me", headers=auth_headers)
    user_id = me.json()["id"]

    residents = [
        Resident(slug="test-r1", name="居民一", district="free", creator_id=user_id,
                 status="idle", heat=5, star_rating=2, sprite_key="梅",
                 tile_x=30, tile_y=65, token_cost_per_turn=1,
                 ability_md="能力", persona_md="人格", soul_md="灵魂",
                 meta_json={"role": "测试"}),
        Resident(slug="test-r2", name="居民二", district="engineering", creator_id=user_id,
                 status="idle", heat=10, star_rating=1, sprite_key="亚当",
                 tile_x=100, tile_y=52, token_cost_per_turn=1,
                 ability_md="能力2", persona_md="人格2", soul_md="灵魂2",
                 meta_json={"role": "测试2"}),
    ]
    for r in residents:
        db_session.add(r)
    await db_session.commit()
    return residents


@pytest.fixture
async def seeded_conversations(db_session, auth_headers, client, seeded_user_residents):
    me = await client.get("/users/me", headers=auth_headers)
    user_id = me.json()["id"]
    conv = Conversation(user_id=user_id, resident_id=seeded_user_residents[0].id,
                        turns=3, rating=4)
    db_session.add(conv)
    await db_session.commit()
    return [conv]


@pytest.fixture
async def seeded_transactions(db_session, auth_headers, client):
    me = await client.get("/users/me", headers=auth_headers)
    user_id = me.json()["id"]
    tx = Transaction(user_id=user_id, amount=-5, reason="chat:test")
    db_session.add(tx)
    await db_session.commit()
    return [tx]


@pytest.mark.anyio
async def test_list_my_residents_empty(client, auth_headers):
    resp = await client.get("/profile/residents", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_list_my_residents(client, auth_headers, seeded_user_residents):
    resp = await client.get("/profile/residents", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all("slug" in r and "star_rating" in r and "heat" in r for r in data)


@pytest.mark.anyio
async def test_list_my_conversations(client, auth_headers, seeded_conversations):
    resp = await client.get("/profile/conversations", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "resident_name" in data[0]
    assert "turns" in data[0]


@pytest.mark.anyio
async def test_list_my_conversations_pagination(client, auth_headers, seeded_conversations):
    resp = await client.get("/profile/conversations?limit=1&offset=0", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) <= 1


@pytest.mark.anyio
async def test_list_my_transactions(client, auth_headers, seeded_transactions):
    resp = await client.get("/profile/transactions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "amount" in data[0] and "reason" in data[0]


@pytest.mark.anyio
async def test_profile_requires_auth(client):
    for path in ["/profile/residents", "/profile/conversations", "/profile/transactions"]:
        resp = await client.get(path)
        assert resp.status_code == 401
