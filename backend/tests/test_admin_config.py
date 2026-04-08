import pytest
from app.services.config_service import ConfigService


@pytest.mark.anyio
async def test_get_config_group(db_session):
    """Should return defaults merged with DB values; DB values override defaults."""
    from app.routers.admin.system_config import _get_config_group, DEFAULT_CONFIGS

    svc = ConfigService(db_session)
    # Set a value that overrides the default for "llm.model"
    await svc.set("model", "claude-sonnet-4-20250514", group="llm", updated_by="admin")
    await svc.set("economy.signup_bonus", 100, group="economy", updated_by="admin")

    result = await _get_config_group(db_session, "llm")

    # DB value should override the default
    assert result["model"] == "claude-sonnet-4-20250514"
    # All default keys should be present
    for full_key in DEFAULT_CONFIGS["llm"]:
        short_key = full_key.removeprefix("llm.")
        assert short_key in result

    # SearXNG group should return defaults when DB is empty
    searxng_result = await _get_config_group(db_session, "searxng")
    assert "url" in searxng_result
    assert searxng_result["url"] == "http://100.93.72.102:58080"


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
