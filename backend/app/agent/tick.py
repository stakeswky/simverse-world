"""Resident tick: slim orchestrator calling plugin phases."""
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.actions import ActionResult
from app.agent.registry import registry
from app.agent.schemas import TickContext, get_world_time
from app.config import settings
from app.models.resident import Resident

logger = logging.getLogger(__name__)

_daily_counts: dict[str, int] = {}
_last_reset_date: str = ""


def _check_and_reset_daily_counts() -> None:
    global _last_reset_date
    today = datetime.now().strftime("%Y-%m-%d")
    if today != _last_reset_date:
        _daily_counts.clear()
        _last_reset_date = today


def _over_daily_limit(resident_id: str) -> bool:
    _check_and_reset_daily_counts()
    return _daily_counts.get(resident_id, 0) >= settings.agent_max_daily_actions


async def resident_tick(
    db: AsyncSession,
    resident: Resident,
) -> ActionResult | None:
    """Execute one autonomous tick for a resident via plugin chain."""
    if _over_daily_limit(resident.id):
        return None

    world_time, hour, schedule_phase = get_world_time()

    ctx = TickContext(
        db=db,
        resident=resident,
        world_time=world_time,
        hour=hour,
        schedule_phase=schedule_phase,
    )

    try:
        phases = registry.get_phases(resident)
    except RuntimeError as e:
        logger.error("Failed to load phases for %s: %s", resident.slug, e)
        return None

    for phase in phases:
        try:
            ctx = await phase.execute(ctx)
        except Exception as e:
            logger.warning("Phase failed for %s: %s", resident.slug, e)
            break
        if ctx.skip_remaining:
            break

    if ctx.action_result:
        _daily_counts[resident.id] = _daily_counts.get(resident.id, 0) + 1
        logger.debug("Resident %s ticked: %s -> %s",
                      resident.slug, ctx.action_result.action.value, ctx.action_result.reason)

    return ctx.action_result
