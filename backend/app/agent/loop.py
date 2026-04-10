"""AgentLoop: centralized background task driving all resident autonomous behavior."""
# New WebSocket message types emitted by the AgentLoop:
#
# resident_move:
#   { "type": "resident_move", "resident_slug": str, "tile_x": int, "tile_y": int,
#     "target_tile": [x, y] | null, "status": "walking" }
#
# resident_chat:
#   { "type": "resident_chat", "initiator_slug": str, "target_slug": str, "summary": null }
#
# resident_chat_end:
#   { "type": "resident_chat_end", "initiator_slug": str, "target_slug": str,
#     "summary": str, "mood": "positive"|"neutral"|"negative" }
#
# resident_status:
#   { "type": "resident_status", "resident_slug": str, "status": str }
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.actions import ActionType, ActionResult
from app.agent.chat import resident_chat
from app.agent.scheduler import build_schedule, should_tick
from app.agent.tick import resident_tick
from app.config import settings
from app.database import async_session
from app.models.resident import Resident
from app.ws.manager import manager

logger = logging.getLogger(__name__)


class AgentLoop:
    """Centralized agent loop — runs as a FastAPI background task.

    Follows the same pattern as heat_cron_loop: while True, try, sleep.
    Differences:
    - Evaluates per-resident schedules (SBTI-derived) before ticking
    - Uses asyncio.Semaphore to bound concurrent ticks
    - Dispatches resident_chat() for CHAT_RESIDENT actions
    - Broadcasts movement and status changes to all connected clients
    """

    async def run(self) -> None:
        """Main loop — runs indefinitely."""
        logger.info("AgentLoop started (interval=%ds)", settings.agent_tick_interval)
        while True:
            if not settings.agent_enabled:
                await asyncio.sleep(settings.agent_tick_interval)
                continue
            try:
                async with async_session() as db:
                    await self._tick_round(db)
            except Exception as e:
                logger.error("AgentLoop tick_round error: %s", e)
            await asyncio.sleep(settings.agent_tick_interval)

    async def _tick_round(self, db: AsyncSession) -> None:
        """One round: evaluate schedules, run concurrent resident ticks."""
        # Load all active residents
        result = await db.execute(
            select(Resident).where(Resident.status.not_in(["sleeping"]))
        )
        residents = list(result.scalars().all())
        if not residents:
            return

        current_hour = datetime.now().hour
        semaphore = asyncio.Semaphore(settings.agent_max_concurrent)

        async def guarded_tick(resident: Resident) -> ActionResult | None:
            """Run one resident's tick with semaphore, handle errors gracefully."""
            # Evaluate schedule before acquiring semaphore
            sbti_data = (resident.meta_json or {}).get("sbti")
            schedule = build_schedule(sbti_data)

            if not should_tick(schedule, current_hour):
                return None

            async with semaphore:
                try:
                    action_result = await resident_tick(db, resident)
                except Exception as e:
                    logger.warning("Tick error for %s: %s", resident.slug, e)
                    return None

            if action_result:
                await self._handle_action(db, resident, action_result)

            return action_result

        # Run all ticks concurrently, bounded by semaphore
        await asyncio.gather(*(guarded_tick(r) for r in residents), return_exceptions=True)

    async def _handle_action(
        self,
        db: AsyncSession,
        resident: Resident,
        action_result: ActionResult,
    ) -> None:
        """Post-tick: broadcast state changes and handle chat initiation."""
        movement_actions = {ActionType.WANDER, ActionType.GO_HOME, ActionType.VISIT_DISTRICT}

        if action_result.action in movement_actions:
            await manager.broadcast({
                "type": "resident_move",
                "resident_slug": resident.slug,
                "tile_x": resident.tile_x,
                "tile_y": resident.tile_y,
                "target_tile": list(action_result.target_tile) if action_result.target_tile else None,
                "status": "walking",
            })

        elif action_result.action == ActionType.CHAT_RESIDENT:
            await self._initiate_chat(db, resident, action_result.target_slug)

        elif action_result.action in {ActionType.IDLE, ActionType.NAP}:
            await manager.broadcast({
                "type": "resident_status",
                "resident_slug": resident.slug,
                "status": resident.status,
            })

    async def _initiate_chat(
        self,
        db: AsyncSession,
        initiator: Resident,
        target_slug: str | None,
    ) -> None:
        """Fetch target resident and run inter-resident chat."""
        if not target_slug:
            return

        result = await db.execute(
            select(Resident).where(Resident.slug == target_slug)
        )
        target = result.scalar_one_or_none()
        if target is None:
            return

        # Broadcast chat start
        await manager.broadcast({
            "type": "resident_chat",
            "initiator_slug": initiator.slug,
            "target_slug": target.slug,
            "summary": None,  # Will be updated when chat ends
        })

        try:
            chat_result = await resident_chat(db, initiator, target)

            if chat_result and not chat_result.get("skipped"):
                await manager.broadcast({
                    "type": "resident_chat_end",
                    "initiator_slug": initiator.slug,
                    "target_slug": target.slug,
                    "summary": chat_result.get("summary", ""),
                    "mood": chat_result.get("mood", "neutral"),
                })
        except Exception as e:
            logger.warning("Chat initiation failed %s->%s: %s", initiator.slug, target_slug, e)
            # Ensure both get unlocked
            initiator.status = "idle"
            target.status = "idle"
            await db.commit()
            await manager.broadcast({
                "type": "resident_chat_end",
                "initiator_slug": initiator.slug,
                "target_slug": target.slug,
                "summary": "",
            })


# Module-level singleton
agent_loop = AgentLoop()
