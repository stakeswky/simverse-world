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
