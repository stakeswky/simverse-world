"""SocialPerceivePlugin: wider radius + relationship awareness."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.agent.schemas import TickContext
from app.memory.service import MemoryService
from app.models.resident import Resident

logger = logging.getLogger(__name__)


class SocialPerceivePlugin:
    def __init__(self, params: dict[str, Any] | None = None):
        params = params or {}
        self.radius: int = params.get("radius", 14)
        self.track_relationships: bool = params.get("track_relationships", False)

    async def execute(self, ctx: TickContext) -> TickContext:
        try:
            result = await ctx.db.execute(
                select(Resident).where(Resident.id != ctx.resident.id)
            )
            all_residents = result.scalars().all()

            nearby = []
            for r in all_residents:
                dist = abs(r.tile_x - ctx.resident.tile_x) + abs(r.tile_y - ctx.resident.tile_y)
                if dist <= self.radius:
                    nearby.append(r)

            ctx.nearby_residents = nearby

            # Tag known residents by checking relationship memories
            if self.track_relationships and nearby:
                await self._tag_known_residents(ctx)
        except Exception as e:
            logger.warning("Social perceive failed for %s: %s", ctx.resident.slug, e)
            ctx.skip_remaining = True

        return ctx

    async def _tag_known_residents(self, ctx: TickContext) -> None:
        """Check relationship memories for nearby residents, store in metadata."""
        try:
            memory_svc = MemoryService(ctx.db)
            known_ids: dict[str, str] = {}  # resident_id -> relationship content
            for r in ctx.nearby_residents:
                rel = await memory_svc.get_relationship(
                    ctx.resident.id, resident_id_target=r.id,
                )
                if rel:
                    known_ids[r.id] = rel.content
            if known_ids:
                # Store on TickContext for decide phase to use
                ctx.nearby_known = known_ids
                logger.debug("%s recognizes %d nearby residents",
                             ctx.resident.slug, len(known_ids))
        except Exception as e:
            logger.debug("Relationship lookup failed (non-fatal): %s", e)
