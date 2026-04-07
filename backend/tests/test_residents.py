import pytest
from app.models.resident import Resident

@pytest.fixture
async def seeded_db(client, db_session):
    """Seed 5 demo residents into the test DB."""
    residents = [
        Resident(id="r1", slug="isabella", name="伊莎贝拉", district="free", status="idle",
                 heat=15, sprite_key="伊莎贝拉", tile_x=70, tile_y=42, star_rating=2,
                 creator_id="system", token_cost_per_turn=1,
                 ability_md="# 能力\n咖啡调制", persona_md="# 人格\n热情", soul_md="# 灵魂\n咖啡",
                 meta_json={"role": "咖啡店老板"}),
        Resident(id="r2", slug="klaus", name="克劳斯", district="engineering", status="popular",
                 heat=62, sprite_key="克劳斯", tile_x=58, tile_y=55, star_rating=3,
                 creator_id="system", token_cost_per_turn=1,
                 ability_md="# 能力\n研究", persona_md="# 人格\n严谨", soul_md="# 灵魂\n真理",
                 meta_json={"role": "研究员"}),
    ]
    for r in residents:
        db_session.add(r)
    await db_session.commit()
    return residents

@pytest.mark.anyio
async def test_list_residents_empty(client):
    resp = await client.get("/residents")
    assert resp.status_code == 200
    assert resp.json() == []

@pytest.mark.anyio
async def test_list_residents(client, seeded_db):
    resp = await client.get("/residents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["slug"] in ["isabella", "klaus"]

@pytest.mark.anyio
async def test_get_resident_by_slug(client, seeded_db):
    resp = await client.get("/residents/isabella")
    assert resp.status_code == 200
    assert resp.json()["name"] == "伊莎贝拉"
    assert resp.json()["status"] in ["idle", "sleeping", "popular", "chatting"]

@pytest.mark.anyio
async def test_get_resident_detail_fields(client, seeded_db):
    resp = await client.get("/residents/isabella")
    data = resp.json()
    assert "ability_md" in data
    assert "persona_md" in data
    assert "soul_md" in data

@pytest.mark.anyio
async def test_get_resident_not_found(client):
    resp = await client.get("/residents/nonexistent")
    assert resp.status_code == 404
