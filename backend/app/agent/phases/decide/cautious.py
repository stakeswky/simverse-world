"""CautiousDecidePlugin: introvert variant — prefers solitude, resists social interruption."""
from __future__ import annotations

import logging
import random
from typing import Any

from app.agent.actions import ActionType, ActionResult
from app.agent.phases.decide.basic import BasicDecidePlugin
from app.agent.schemas import TickContext

logger = logging.getLogger(__name__)


class CautiousDecidePlugin(BasicDecidePlugin):
    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        params = params or {}
        self.social_reluctance: bool = params.get("social_reluctance", True)

    async def _llm_decide(self, ctx: TickContext):
        result = await super()._llm_decide(ctx)

        if result and self.social_reluctance:
            social_actions = {ActionType.CHAT_RESIDENT, ActionType.GOSSIP, ActionType.CHAT_FOLLOW_UP}
            if result.action in social_actions:
                plan = ctx.current_plan
                if plan and plan.action not in ("CHAT_RESIDENT", "GOSSIP", "CHAT_FOLLOW_UP"):
                    if random.random() < 0.5:
                        logger.debug("Cautious %s resisted social action", ctx.resident.slug)
                        result = ActionResult(
                            action=ActionType.OBSERVE,
                            target_slug=None,
                            target_tile=None,
                            reason="不太想社交",
                        )

        return result
