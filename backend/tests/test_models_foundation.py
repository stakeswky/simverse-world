import pytest
from app.models.user import User


@pytest.mark.anyio
async def test_user_new_fields_defaults(db_session):
    """Verify new User fields exist with correct defaults."""
    user = User(
        name="test",
        email="test@example.com",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.is_admin is False
    assert user.is_banned is False
    assert user.linuxdo_id is None
    assert user.linuxdo_trust_level is None
    assert user.player_resident_id is None
    assert user.last_x == 2432
    assert user.last_y == 1600
    assert user.settings_json == {}
    assert user.custom_llm_enabled is False
    assert user.custom_llm_api_format == "anthropic"
    assert user.custom_llm_api_key is None
    assert user.custom_llm_base_url is None
    assert user.custom_llm_model is None


from app.models.resident import Resident


@pytest.mark.anyio
async def test_resident_new_fields_defaults(db_session):
    """Verify new Resident fields exist with correct defaults."""
    # Need a user first (creator_id FK)
    user = User(name="creator", email="creator@test.com")
    db_session.add(user)
    await db_session.commit()

    resident = Resident(
        slug="test-resident",
        name="Test",
        creator_id=user.id,
    )
    db_session.add(resident)
    await db_session.commit()
    await db_session.refresh(resident)

    assert resident.resident_type == "npc"
    assert resident.reply_mode == "manual"
    assert resident.portrait_url is None


from app.models.system_config import SystemConfig


@pytest.mark.anyio
async def test_system_config_crud(db_session):
    """Verify SystemConfig model CRUD operations."""
    config = SystemConfig(
        key="economy.signup_bonus",
        value="100",
        group="economy",
        updated_by="admin-user-id",
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)

    assert config.key == "economy.signup_bonus"
    assert config.value == "100"
    assert config.group == "economy"
    assert config.updated_by == "admin-user-id"
    assert config.updated_at is not None

    # Update
    config.value = "200"
    await db_session.commit()
    await db_session.refresh(config)
    assert config.value == "200"


from app.models.forge_session import ForgeSession


@pytest.mark.anyio
async def test_forge_session_creation(db_session):
    """Verify ForgeSession model creation with JSON fields."""
    user = User(name="forger", email="forger@test.com")
    db_session.add(user)
    await db_session.commit()

    session = ForgeSession(
        user_id=user.id,
        character_name="萧炎",
        mode="deep",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    assert session.id is not None
    assert session.character_name == "萧炎"
    assert session.mode == "deep"
    assert session.status == "routing"
    assert session.current_stage == ""
    assert session.research_data == {}
    assert session.extraction_data == {}
    assert session.build_output == {}
    assert session.validation_report == {}
    assert session.refinement_log == {}
