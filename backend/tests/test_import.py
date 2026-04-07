import pytest
import json
import io
import zipfile


@pytest.fixture
async def auth_headers(client):
    resp = await client.post("/auth/register", json={
        "name": "ImportUser", "email": "import@test.com", "password": "pass123"
    })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def seeded_user_residents(db_session, auth_headers, client):
    from app.models.resident import Resident
    me = await client.get("/users/me", headers=auth_headers)
    user_id = me.json()["id"]
    r = Resident(slug="existing-slug", name="已有居民", district="free", creator_id=user_id,
                 status="idle", heat=0, star_rating=1, sprite_key="梅",
                 tile_x=30, tile_y=65, token_cost_per_turn=1,
                 ability_md="", persona_md="", soul_md="", meta_json={})
    db_session.add(r)
    await db_session.commit()
    return [r]


@pytest.mark.anyio
async def test_import_skill_md(client, auth_headers):
    skill_content = """# Ability
## Professional
- Backend engineering expert with 10 years experience
- Distributed systems and high availability architectures

# Persona
## Layer 0: Core
- Methodical, calm under pressure, very detail-oriented

## Layer 2: Expression
- Uses analogies to explain complex technical systems

# Soul
## Values
- Reliability over speed always
- Engineering craftsmanship matters

## Background
- 8 years building payment systems at scale
"""
    files = {"file": ("SKILL.md", io.BytesIO(skill_content.encode()), "text/markdown")}
    data = {"name": "Payment Expert", "slug": "payment-expert"}
    resp = await client.post("/residents/import", headers=auth_headers, files=files, data=data)
    assert resp.status_code == 200
    result = resp.json()
    assert result["slug"] == "payment-expert"
    assert result["name"] == "Payment Expert"
    assert "Backend engineering" in result["ability_md"]
    assert "Methodical" in result["persona_md"]
    assert "Reliability" in result["soul_md"]
    assert result["star_rating"] >= 1


@pytest.mark.anyio
async def test_import_zip_three_layers(client, auth_headers):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ability.md", "# Ability\n## Professional\n- Frontend React expert with 5 years\n- CSS architecture and design systems\n\n## Creative\n- UI/UX design thinking specialist")
        zf.writestr("persona.md", "# Persona\n## Layer 0: Core\n- Detail-oriented perfectionist who never ships bugs\n\n## Layer 2: Expression\n- Visual thinker, draws diagrams for everything")
        zf.writestr("soul.md", "# Soul\n## Values\n- Beauty in simplicity is paramount\n\n## Experience\n- Redesigned 3 major enterprise products")
        zf.writestr("meta.json", json.dumps({"name": "Design Engineer", "profile": {"role": "Frontend"}}))
    buf.seek(0)

    files = {"file": ("resident.zip", buf, "application/zip")}
    data = {"name": "Design Engineer", "slug": "design-engineer"}
    resp = await client.post("/residents/import", headers=auth_headers, files=files, data=data)
    assert resp.status_code == 200
    result = resp.json()
    assert "React" in result["ability_md"]
    assert "perfectionist" in result["persona_md"]
    assert "Beauty" in result["soul_md"]


@pytest.mark.anyio
async def test_import_colleague_skill_format(client, auth_headers):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("work.md", "# Work Skill\n## Technical\n- Python backend and FastAPI expert\n- High performance systems design\n\n## Process\n- Code review champion and mentor")
        zf.writestr("persona.md", "# Persona\n## Layer 0: Core\n- Pragmatic and efficient problem solver\n\n## Layer 2: Expression\n- Direct communication, no fluff whatsoever")
    buf.seek(0)

    files = {"file": ("colleague.zip", buf, "application/zip")}
    data = {"name": "Backend Dev", "slug": "backend-dev"}
    resp = await client.post("/residents/import", headers=auth_headers, files=files, data=data)
    assert resp.status_code == 200
    result = resp.json()
    assert "Python backend" in result["ability_md"]
    assert "Pragmatic" in result["persona_md"]
    assert result["soul_md"] == ""


@pytest.mark.anyio
async def test_import_duplicate_slug(client, auth_headers, seeded_user_residents):
    files = {"file": ("SKILL.md", io.BytesIO(b"# Ability\nTest"), "text/markdown")}
    data = {"name": "Duplicate", "slug": "existing-slug"}
    resp = await client.post("/residents/import", headers=auth_headers, files=files, data=data)
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_import_requires_auth(client):
    files = {"file": ("SKILL.md", io.BytesIO(b"# Test"), "text/markdown")}
    data = {"name": "Test", "slug": "test-unauth"}
    resp = await client.post("/residents/import", files=files, data=data)
    assert resp.status_code == 401
