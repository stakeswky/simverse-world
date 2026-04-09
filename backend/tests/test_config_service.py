# tests/test_config_service.py
import pytest
from app.models.system_config import SystemConfig
from app.services.config_service import ConfigService


@pytest.mark.anyio
async def test_get_returns_default_when_no_db_entry(db_session):
    """Should return default value when config key not in DB."""
    svc = ConfigService(db_session)
    value = await svc.get("economy.signup_bonus", default=100)
    assert value == 100


@pytest.mark.anyio
async def test_get_returns_db_value_over_default(db_session):
    """DB value should override default."""
    config = SystemConfig(
        key="economy.signup_bonus",
        value="200",
        group="economy",
        updated_by="admin",
    )
    db_session.add(config)
    await db_session.commit()

    svc = ConfigService(db_session)
    value = await svc.get("economy.signup_bonus", default=100)
    assert value == 200


@pytest.mark.anyio
async def test_set_creates_new_entry(db_session):
    """set() should create a new config entry."""
    svc = ConfigService(db_session)
    await svc.set("economy.daily_reward", 10, group="economy", updated_by="admin-id")

    value = await svc.get("economy.daily_reward", default=5)
    assert value == 10


@pytest.mark.anyio
async def test_set_updates_existing_entry(db_session):
    """set() should update an existing config entry."""
    svc = ConfigService(db_session)
    await svc.set("economy.daily_reward", 10, group="economy", updated_by="admin-id")
    await svc.set("economy.daily_reward", 20, group="economy", updated_by="admin-id")

    value = await svc.get("economy.daily_reward", default=5)
    assert value == 20


@pytest.mark.anyio
async def test_get_group_returns_all_in_group(db_session):
    """get_group() should return all config entries for a group."""
    svc = ConfigService(db_session)
    await svc.set("economy.signup_bonus", 100, group="economy", updated_by="admin")
    await svc.set("economy.daily_reward", 5, group="economy", updated_by="admin")
    await svc.set("heat.popular_threshold", 50, group="heat", updated_by="admin")

    economy = await svc.get_group("economy")
    assert economy == {"economy.signup_bonus": 100, "economy.daily_reward": 5}
