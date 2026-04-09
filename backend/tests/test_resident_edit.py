import pytest
from app.models.resident import Resident
from app.models.user import User


@pytest.fixture
async def auth_headers(client):
    resp = await client.post("/auth/register", json={
        "name": "EditUser", "email": "edit@test.com", "password": "pass123"
    })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def auth_headers_other(client):
    resp = await client.post("/auth/register", json={
        "name": "OtherUser", "email": "other@test.com", "password": "pass123"
    })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def seeded_user_residents(db_session, auth_headers, client):
    me = await client.get("/users/me", headers=auth_headers)
    user_id = me.json()["id"]
    residents = [
        Resident(slug="edit-r1", name="编辑居民一", district="free", creator_id=user_id,
                 status="idle", heat=0, star_rating=1, sprite_key="梅",
                 tile_x=30, tile_y=65, token_cost_per_turn=1,
                 ability_md="# Ability\nOriginal", persona_md="# Persona\nOriginal",
                 soul_md="# Soul\nOriginal", meta_json={}),
    ]
    for r in residents:
        db_session.add(r)
    await db_session.commit()
    return residents


@pytest.mark.anyio
async def test_edit_resident_ability(client, auth_headers, seeded_user_residents):
    slug = seeded_user_residents[0].slug
    resp = await client.put(
        f"/residents/{slug}", headers=auth_headers,
        json={"ability_md": "# Updated Ability\nNew ability content"},
    )
    assert resp.status_code == 200
    assert resp.json()["ability_md"] == "# Updated Ability\nNew ability content"


@pytest.mark.anyio
async def test_edit_resident_creates_version(client, auth_headers, seeded_user_residents):
    slug = seeded_user_residents[0].slug
    await client.put(f"/residents/{slug}", headers=auth_headers,
                     json={"ability_md": "# V2"})
    resp = await client.get(f"/residents/{slug}/versions", headers=auth_headers)
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) >= 1
    assert versions[0]["version_number"] == 1


@pytest.mark.anyio
async def test_edit_resident_not_owner(client, auth_headers_other, seeded_user_residents):
    slug = seeded_user_residents[0].slug
    resp = await client.put(f"/residents/{slug}", headers=auth_headers_other,
                            json={"ability_md": "# Hacked"})
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_edit_resident_not_found(client, auth_headers):
    resp = await client.put("/residents/nonexistent", headers=auth_headers,
                            json={"ability_md": "# Test"})
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_version_history_max_10(client, auth_headers, seeded_user_residents):
    slug = seeded_user_residents[0].slug
    for i in range(12):
        await client.put(f"/residents/{slug}", headers=auth_headers,
                         json={"ability_md": f"# V{i+2}"})
    resp = await client.get(f"/residents/{slug}/versions", headers=auth_headers)
    assert len(resp.json()) <= 10
