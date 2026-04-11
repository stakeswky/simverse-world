"""SpontaneousDecidePlugin: extravert variant — easily distracted, social-eager."""
from __future__ import annotations

import logging
import random
from typing import Any

from app.agent.actions import ActionType, ActionResult, get_available_actions
from app.agent.phases.decide.basic import BasicDecidePlugin
from app.agent.schemas import TickContext

logger = logging.getLogger(__name__)


class SpontaneousDecidePlugin(BasicDecidePlugin):
    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        params = params or {}
        self.social_eagerness: bool = params.get("social_eagerness", True)
        self.distraction_chance: float = params.get("distraction_chance", 0.3)

    async def execute(self, ctx: TickContext) -> TickContext:
        if ctx.current_plan and random.random() < self.distraction_chance:
            logger.debug("Spontaneous %s ignoring plan (distraction)", ctx.resident.slug)
            ctx.current_plan = None

        if self.social_eagerness and ctx.nearby_residents:
            idle_nearby = [r for r in ctx.nearby_residents
                          if r.status in ("idle", "walking")]
            if idle_nearby and random.random() < 0.4:
                target = random.choice(idle_nearby)
                ctx.available_actions = get_available_actions(ctx.resident, ctx.nearby_residents)
                await self._load_memories(ctx)
                ctx.action_result = ActionResult(
                    action=ActionType.CHAT_RESIDENT,
                    target_slug=target.slug,
                    target_tile=None,
                    reason="想聊天",
                )
                ctx.plan_followed = False
                if ctx.current_plan:
                    ctx.current_plan.status = "interrupted"
                return ctx

        return await super().execute(ctx)
