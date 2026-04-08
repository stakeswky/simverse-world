import pytest
from app.services.config_service import ConfigService


@pytest.mark.anyio
async def test_get_config_group(db_session):
    """Should return all entries in a config group."""
    from app.routers.admin.system_config import _get_config_group

    svc = ConfigService(db_session)
    await svc.set("llm.system_model", "claude-sonnet-4-20250514", group="llm", updated_by="admin")
    await svc.set("llm.system_temperature", 0.3, group="llm", updated_by="admin")
    await svc.set("economy.signup_bonus", 100, group="economy", updated_by="admin")

    result = await _get_config_group(db_session, "llm")
    assert result == {
        "llm.system_model": "claude-sonnet-4-20250514",
        "llm.system_temperature": 0.3,
    }


@pytest.mark.anyio
async def test_set_config_single(db_session):
    """Should update a single config entry."""
    from app.routers.admin.system_config import _set_config

    await _set_config(db_session, key="heat.popular_threshold", value=80,
                      group="heat", admin_id="admin-1")

    svc = ConfigService(db_session)
    val = await svc.get("heat.popular_threshold", default=50)
    assert val == 80


@pytest.mark.anyio
async def test_set_config_batch(db_session):
    """Should update multiple config entries at once."""
    from app.routers.admin.system_config import _set_config_batch

    updates = [
        {"key": "llm.system_model", "value": "claude-haiku-4-5-20251001", "group": "llm"},
        {"key": "llm.system_timeout", "value": 60, "group": "llm"},
    ]
    await _set_config_batch(db_session, updates, admin_id="admin-1")

    svc = ConfigService(db_session)
    assert await svc.get("llm.system_model") == "claude-haiku-4-5-20251001"
    assert await svc.get("llm.system_timeout") == 60


@pytest.mark.anyio
async def test_get_all_config_groups(db_session):
    """Should list all distinct config groups."""
    from app.routers.admin.system_config import _get_all_groups

    svc = ConfigService(db_session)
    await svc.set("llm.model", "x", group="llm", updated_by="a")
    await svc.set("economy.bonus", 1, group="economy", updated_by="a")
    await svc.set("heat.threshold", 50, group="heat", updated_by="a")

    groups = await _get_all_groups(db_session)
    assert set(groups) == {"llm", "economy", "heat"}
