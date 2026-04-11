"""Tests for all phase plugins."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.schemas import TickContext, HourlyPlan, DailyGoal
from app.agent.actions import ActionType, ActionResult


def _make_resident(slug="test-resident", tile_x=76, tile_y=50, status="idle",
                   district="central", meta_json=None, name="Test"):
    r = MagicMock()
    r.id = f"id-{slug}"
    r.slug = slug
    r.name = name
    r.tile_x = tile_x
    r.tile_y = tile_y
    r.status = status
    r.district = district
    r.home_tile_x = 70
    r.home_tile_y = 45
    r.persona_md = "A friendly person."
    r.meta_json = meta_json or {"sbti": {"type": "CTRL", "type_name": "控制者", "dimensions": {"So1": "M", "Ac3": "M"}}}
    r.daily_goal_json = None
    r.daily_plans_json = None
    return r


def _make_ctx(resident=None, db=None, nearby=None):
    return TickContext(
        db=db or AsyncMock(),
        resident=resident or _make_resident(),
        world_time="10:00",
        hour=10,
        schedule_phase="上午",
        nearby_residents=nearby or [],
    )


@pytest.mark.anyio
async def test_basic_perceive_finds_nearby():
    from app.agent.phases.perceive.basic import BasicPerceivePlugin

    resident = _make_resident(tile_x=76, tile_y=50)
    nearby_r = _make_resident(slug="nearby", tile_x=80, tile_y=50)
    far_r = _make_resident(slug="far", tile_x=100, tile_y=100)

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [nearby_r, far_r]
    db.execute = AsyncMock(return_value=result_mock)

    plugin = BasicPerceivePlugin(params={"radius": 10})
    ctx = _make_ctx(resident=resident, db=db)
    ctx = await plugin.execute(ctx)

    assert len(ctx.nearby_residents) == 1
    assert ctx.nearby_residents[0].slug == "nearby"


@pytest.mark.anyio
async def test_basic_perceive_custom_radius():
    from app.agent.phases.perceive.basic import BasicPerceivePlugin

    resident = _make_resident(tile_x=76, tile_y=50)
    nearby_r = _make_resident(slug="nearby", tile_x=80, tile_y=50)

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [nearby_r]
    db.execute = AsyncMock(return_value=result_mock)

    plugin = BasicPerceivePlugin(params={"radius": 3})
    ctx = _make_ctx(resident=resident, db=db)
    ctx = await plugin.execute(ctx)

    assert len(ctx.nearby_residents) == 0


@pytest.mark.anyio
async def test_social_perceive_wider_radius():
    from app.agent.phases.perceive.social import SocialPerceivePlugin

    resident = _make_resident(tile_x=76, tile_y=50)
    mid_r = _make_resident(slug="mid", tile_x=88, tile_y=50)  # dist=12

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = [mid_r]
    db.execute = AsyncMock(return_value=result_mock)

    plugin = SocialPerceivePlugin(params={"radius": 14})
    ctx = _make_ctx(resident=resident, db=db)
    ctx = await plugin.execute(ctx)

    assert len(ctx.nearby_residents) == 1
    assert ctx.nearby_residents[0].slug == "mid"
