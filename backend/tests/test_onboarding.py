import pytest
import random
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.user import User
from app.models.resident import Resident
from app.services.onboarding_service import (
    check_onboarding_needed,
    create_player_resident,
    load_preset_as_player,
    skip_onboarding,
    CENTRAL_PLAZA_X,
    CENTRAL_PLAZA_Y,
    SPAWN_RADIUS,
)


@pytest.mark.anyio
async def test_check_onboarding_needed_new_user(db_session):
    """New user with no player_resident_id needs onboarding."""
    user = User(name="New", email="new@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    result = await check_onboarding_needed(db_session, user.id)
    assert result["needs_onboarding"] is True
    assert result["player_resident_id"] is None


@pytest.mark.anyio
async def test_check_onboarding_not_needed(db_session):
    """User with existing player_resident_id does not need onboarding."""
    user = User(name="Existing", email="existing@test.com", player_resident_id="res-123")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    result = await check_onboarding_needed(db_session, user.id)
    assert result["needs_onboarding"] is False
    assert result["player_resident_id"] == "res-123"


@pytest.mark.anyio
async def test_create_player_resident_minimal(db_session):
    """Create a player resident with minimal info (skip flow)."""
    user = User(name="Player", email="player@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resident = await create_player_resident(
        db=db_session,
        user_id=user.id,
        name="Player",
        sprite_key="埃迪",
        reply_mode="auto",
        ability_md="",
        persona_md="",
        soul_md="",
    )

    assert resident.resident_type == "player"
    assert resident.sprite_key == "埃迪"
    assert resident.reply_mode == "auto"
    assert resident.creator_id == user.id

    # User should be updated with player_resident_id and spawn position
    await db_session.refresh(user)
    assert user.player_resident_id == resident.id
    assert user.last_x is not None
    assert user.last_y is not None


@pytest.mark.anyio
async def test_create_player_resident_spawn_near_plaza(db_session):
    """Spawn position should be within SPAWN_RADIUS of Central Plaza."""
    user = User(name="Spawner", email="spawner@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    random.seed(42)  # deterministic test
    resident = await create_player_resident(
        db=db_session,
        user_id=user.id,
        name="Spawner",
        sprite_key="亚当",
        reply_mode="manual",
    )

    await db_session.refresh(user)
    dx = abs(user.last_x - CENTRAL_PLAZA_X)
    dy = abs(user.last_y - CENTRAL_PLAZA_Y)
    assert dx <= SPAWN_RADIUS
    assert dy <= SPAWN_RADIUS


@pytest.mark.anyio
async def test_create_player_resident_with_skill_data(db_session):
    """Create player resident with full Skill data."""
    user = User(name="SkillUser", email="skill@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resident = await create_player_resident(
        db=db_session,
        user_id=user.id,
        name="SkillUser",
        sprite_key="简",
        reply_mode="auto",
        ability_md="# 能力档案\n全栈工程师",
        persona_md="# 人格档案\n友善、耐心",
        soul_md="# 灵魂档案\n追求卓越",
    )

    assert resident.ability_md == "# 能力档案\n全栈工程师"
    assert resident.persona_md == "# 人格档案\n友善、耐心"
    assert resident.soul_md == "# 灵魂档案\n追求卓越"


@pytest.mark.anyio
async def test_create_player_resident_duplicate_blocked(db_session):
    """Should raise if user already has a player resident."""
    user = User(name="Dup", email="dup@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    await create_player_resident(
        db=db_session, user_id=user.id, name="Dup",
        sprite_key="埃迪", reply_mode="auto",
    )

    with pytest.raises(ValueError, match="already has a player resident"):
        await create_player_resident(
            db=db_session, user_id=user.id, name="Dup2",
            sprite_key="亚当", reply_mode="auto",
        )


@pytest.mark.anyio
async def test_skip_onboarding(db_session):
    """skip_onboarding should create a default player resident."""
    user = User(name="Skipper", email="skipper@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    resident = await skip_onboarding(db_session, user.id)

    assert resident.resident_type == "player"
    assert resident.sprite_key == "埃迪"
    assert resident.name == "新居民"

    await db_session.refresh(user)
    assert user.player_resident_id == resident.id


@pytest.mark.anyio
async def test_load_preset_as_player(db_session):
    """load_preset_as_player should copy preset data to a new player resident."""
    # Create a user who will own the preset (creator_id is required)
    creator = User(name="Creator", email="creator@test.com")
    db_session.add(creator)
    await db_session.commit()
    await db_session.refresh(creator)

    # Create a preset resident (NPC)
    preset = Resident(
        slug="preset-scholar",
        name="Scholar",
        sprite_key="亚瑟",
        creator_id=creator.id,
        ability_md="# 能力档案\n博学多才",
        persona_md="# 人格档案\n沉稳睿智",
        soul_md="# 灵魂档案\n追求真理",
        resident_type="npc",
    )
    db_session.add(preset)
    await db_session.commit()

    # Create the player user
    player_user = User(name="PlayerFromPreset", email="preset-player@test.com")
    db_session.add(player_user)
    await db_session.commit()
    await db_session.refresh(player_user)

    resident = await load_preset_as_player(db_session, player_user.id, "preset-scholar")

    assert resident.resident_type == "player"
    assert resident.name == "Scholar"
    assert resident.sprite_key == "亚瑟"
    assert resident.ability_md == "# 能力档案\n博学多才"
    assert resident.creator_id == player_user.id

    await db_session.refresh(player_user)
    assert player_user.player_resident_id == resident.id


@pytest.mark.anyio
async def test_check_onboarding_user_not_found(db_session):
    """Should raise ValueError for non-existent user."""
    with pytest.raises(ValueError, match="not found"):
        await check_onboarding_needed(db_session, "nonexistent-id")
