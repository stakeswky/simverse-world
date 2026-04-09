import pytest
from app.models.user import User
from app.models.resident import Resident


@pytest.fixture
async def seeded_db(db_session):
    """Seed demo residents matching the 5 NPCs."""
    user = User(id="search-creator", name="SearchCreator", email="search@test.com", soul_coin_balance=0)
    db_session.add(user)
    await db_session.flush()

    residents = [
        Resident(slug="isabella", name="伊莎贝拉", district="free", creator_id="search-creator",
                 status="idle", heat=15, star_rating=2, sprite_key="伊莎贝拉",
                 tile_x=70, tile_y=42, token_cost_per_turn=1,
                 ability_md="", persona_md="", soul_md="",
                 meta_json={"role": "咖啡店老板"}),
        Resident(slug="klaus", name="克劳斯", district="engineering", creator_id="search-creator",
                 status="popular", heat=62, star_rating=3, sprite_key="克劳斯",
                 tile_x=58, tile_y=55, token_cost_per_turn=1,
                 ability_md="", persona_md="", soul_md="",
                 meta_json={"role": "研究员"}),
    ]
    for r in residents:
        db_session.add(r)
    await db_session.commit()
    return residents


@pytest.mark.anyio
async def test_search_by_name(client, seeded_db):
    resp = await client.get("/search?q=伊莎贝拉")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert any(r["name"] == "伊莎贝拉" for r in results)


@pytest.mark.anyio
async def test_search_by_role(client, seeded_db):
    resp = await client.get("/search?q=研究员")
    assert resp.status_code == 200
    results = resp.json()
    assert any(r["name"] == "克劳斯" for r in results)


@pytest.mark.anyio
async def test_search_by_district(client, seeded_db):
    resp = await client.get("/search?q=engineering")
    assert resp.status_code == 200
    results = resp.json()
    assert any(r["district"] == "engineering" for r in results)


@pytest.mark.anyio
async def test_search_empty_query(client):
    resp = await client.get("/search?q=")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_search_no_results(client, seeded_db):
    resp = await client.get("/search?q=xyznonexistent")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_search_limit(client, seeded_db):
    resp = await client.get("/search?q=a&limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) <= 3
