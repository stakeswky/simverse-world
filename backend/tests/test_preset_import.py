import pytest
from app.models.user import User
from app.models.resident import Resident


@pytest.mark.anyio
async def test_seed_presets_creates_residents(db_session):
    """Seeding presets should create 14 residents."""
    from seed.preset_characters import seed_presets

    # Create system user
    system_user = User(
        id="00000000-0000-0000-0000-000000000001",
        name="System",
        email="system@skills.world",
        soul_coin_balance=0,
    )
    db_session.add(system_user)
    await db_session.commit()

    count = await seed_presets(db_session)
    assert count == 14

    # Verify 萧炎 exists with correct data
    from sqlalchemy import select
    result = await db_session.execute(
        select(Resident).where(Resident.slug == "xiao-yan")
    )
    xiaoyan = result.scalar_one_or_none()
    assert xiaoyan is not None
    assert xiaoyan.name == "萧炎"
    assert xiaoyan.resident_type == "npc"
    assert "心智模型" in xiaoyan.ability_md or "能力" in xiaoyan.ability_md
    assert xiaoyan.meta_json["origin"] == "preset"
    assert xiaoyan.meta_json["is_preset"] is True
    assert xiaoyan.star_rating == 3
    assert xiaoyan.sprite_key == "克劳斯"
    assert xiaoyan.district == "free"


@pytest.mark.anyio
async def test_seed_presets_is_idempotent(db_session):
    """Running seed twice should not duplicate residents."""
    from seed.preset_characters import seed_presets

    system_user = User(
        id="00000000-0000-0000-0000-000000000001",
        name="System",
        email="system@skills.world",
        soul_coin_balance=0,
    )
    db_session.add(system_user)
    await db_session.commit()

    count1 = await seed_presets(db_session)
    count2 = await seed_presets(db_session)
    assert count1 == 14
    assert count2 == 0  # no new residents on second run
