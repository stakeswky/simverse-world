"""ReflectiveMemorizePlugin: extends BasicMemorizePlugin with auto-reflect chance."""
from __future__ import annotations

import logging
import random
from typing import Any

from app.agent.phases.memorize.basic import BasicMemorizePlugin, format_action_memory
from app.agent.schemas import TickContext
from app.memory.service import MemoryService

logger = logging.getLogger(__name__)


class ReflectiveMemorizePlugin(BasicMemorizePlugin):
    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        params = params or {}
        self.auto_reflect_chance: float = params.get("auto_reflect_chance", 0.15)
        self.reflection_depth: str = params.get("reflection_depth", "normal")

    async def execute(self, ctx: TickContext) -> TickContext:
        ctx = await super().execute(ctx)

        if ctx.memory_created and random.random() < self.auto_reflect_chance:
            try:
                memory_svc = MemoryService(ctx.db)
                reflections = await memory_svc.generate_reflections(ctx.resident)
                if reflections:
                    logger.info(
                        "Auto-reflection triggered for %s: %d reflections",
                        ctx.resident.slug, len(reflections),
                    )
            except Exception as e:
                logger.warning("Auto-reflection failed for %s: %s", ctx.resident.slug, e)

        return ctx
