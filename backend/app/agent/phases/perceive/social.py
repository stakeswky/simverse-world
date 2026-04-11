"""SocialPerceivePlugin: wider radius + relationship awareness."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.agent.schemas import TickContext
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
        except Exception as e:
            logger.warning("Social perceive failed for %s: %s", ctx.resident.slug, e)
            ctx.skip_remaining = True

        return ctx
