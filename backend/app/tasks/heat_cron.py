import asyncio
import logging
from app.database import async_session
from app.services.heat_service import recalculate_heat
from app.ws.manager import manager

logger = logging.getLogger(__name__)
HEAT_CRON_INTERVAL_SECONDS = 3600  # 1 hour


async def heat_cron_loop():
    """Background task: recalculate heat hourly, broadcast status changes."""
    while True:
        try:
            async with async_session() as db:
                changes = await recalculate_heat(db)
            for change in changes:
                await manager.broadcast({
                    "type": "resident_status",
                    "resident_slug": change["slug"],
                    "status": change["new_status"],
                    "heat": change["heat"],
                })
            if changes:
                logger.info(f"Heat cron: {len(changes)} status changes")
        except Exception as e:
            logger.error(f"Heat cron error: {e}")
        await asyncio.sleep(HEAT_CRON_INTERVAL_SECONDS)
