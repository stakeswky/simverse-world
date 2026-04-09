import pytest
from app.models.user import User
from app.models.resident import Resident


@pytest.mark.anyio
async def test_admin_list_residents_pagination(db_session):
    """Resident list should support pagination and search."""
    from app.routers.admin.residents import _list_residents

    user = User(name="creator", email="c@test.com", is_admin=True, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    for i in range(12):
        db_session.add(Resident(slug=f"r-{i}", name=f"Resident {i}", creator_id=user.id))
    await db_session.commit()

    residents, total = await _list_residents(db_session, offset=0, limit=5)
    assert len(residents) == 5
    assert total == 12


@pytest.mark.anyio
async def test_admin_list_residents_filter_district(db_session):
    """Should filter by district."""
    from app.routers.admin.residents import _list_residents

    user = User(name="cr", email="cr@test.com", is_admin=True, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    db_session.add(Resident(slug="eng-1", name="Eng", creator_id=user.id, district="engineering"))
    db_session.add(Resident(slug="prod-1", name="Prod", creator_id=user.id, district="product"))
    await db_session.commit()

    residents, total = await _list_residents(db_session, district="engineering")
    assert total == 1
    assert residents[0].district == "engineering"


@pytest.mark.anyio
async def test_admin_edit_resident_persona(db_session):
    """Admin can edit any resident's persona, not just own."""
    from app.routers.admin.residents import _edit_resident

    user = User(name="owner", email="owner@test.com", is_admin=False, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    r = Resident(slug="edit-me", name="Editable", creator_id=user.id,
                 ability_md="old", persona_md="old", soul_md="old")
    db_session.add(r)
    await db_session.commit()

    updated = await _edit_resident(db_session, r.id, ability_md="new ability", district="academy")
    assert updated.ability_md == "new ability"
    assert updated.district == "academy"
    assert updated.persona_md == "old"  # unchanged


@pytest.mark.anyio
async def test_admin_create_preset_resident(db_session):
    """Admin can create a preset character."""
    from app.routers.admin.residents import _create_preset

    preset = await _create_preset(
        db_session,
        slug="preset-sage",
        name="The Sage",
        district="academy",
        ability_md="# Wisdom",
        persona_md="# Ancient one",
        soul_md="",
        sprite_key="伊莎贝拉",
        tile_x=76,
        tile_y=50,
        resident_type="preset",
        reply_mode="auto",
        meta_json=None,
        creator_id="system",
    )
    assert preset.slug == "preset-sage"
    assert preset.resident_type == "preset"
    assert preset.creator_id == "system"


@pytest.mark.anyio
async def test_admin_batch_district(db_session):
    """Batch district change should update all specified residents."""
    from app.routers.admin.residents import _batch_update_district

    user = User(name="bc", email="bc@test.com", is_admin=True, is_banned=False)
    db_session.add(user)
    await db_session.commit()

    r1 = Resident(slug="b1", name="B1", creator_id=user.id, district="free")
    r2 = Resident(slug="b2", name="B2", creator_id=user.id, district="free")
    db_session.add_all([r1, r2])
    await db_session.commit()

    count = await _batch_update_district(db_session, [r1.id, r2.id], "engineering")
    assert count == 2

    await db_session.refresh(r1)
    await db_session.refresh(r2)
    assert r1.district == "engineering"
    assert r2.district == "engineering"
