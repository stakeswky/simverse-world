"""BasicMemorizePlugin: create event memory from action result."""
from __future__ import annotations

import logging
from typing import Any

from app.agent.actions import ActionType
from app.agent.map_data import get_location_at
from app.agent.schemas import TickContext
from app.memory.service import MemoryService

logger = logging.getLogger(__name__)


def format_action_memory(action_result, resident) -> str:
    """Format an action into a human-readable memory string with location."""
    loc = get_location_at(resident.tile_x, resident.tile_y)
    loc_name = loc["name"] if loc else "户外"

    action = action_result.action
    if action == ActionType.WANDER:
        return f"在{loc_name}附近四处游荡"
    elif action == ActionType.GO_HOME:
        return "回到了自己的家"
    elif action == ActionType.VISIT_DISTRICT:
        return f"前往了{loc_name}"
    elif action == ActionType.CHAT_RESIDENT:
        return f"在{loc_name}和 {action_result.target_slug or '某位居民'} 聊天"
    elif action == ActionType.OBSERVE:
        return f"在{loc_name}静静地观察着周围的情况"
    elif action == ActionType.EAVESDROP:
        return f"在{loc_name}偷偷听了附近居民的对话"
    elif action == ActionType.REFLECT:
        return f"在{loc_name}进行了一段时间的自我反思"
    elif action == ActionType.JOURNAL:
        return f"在{loc_name}记录了今天的见闻"
    elif action == ActionType.WORK:
        return f"在{loc_name}专注于工作"
    elif action == ActionType.STUDY:
        return f"在{loc_name}学习了一些新知识"
    elif action == ActionType.GOSSIP:
        return f"在{loc_name}和 {action_result.target_slug or '某位居民'} 闲聊八卦"
    elif action == ActionType.NAP:
        return f"在{loc_name}小憩了一会儿"
    elif action == ActionType.IDLE:
        return f"在{loc_name}发了会儿呆"
    else:
        return f"在{loc_name}执行了 {action.value}"


class BasicMemorizePlugin:
    def __init__(self, params: dict[str, Any] | None = None):
        params = params or {}
        self.base_importance: float = params.get("base_importance", 0.3)
        self.plan_deviation_boost: float = params.get("plan_deviation_boost", 0.2)

    async def execute(self, ctx: TickContext) -> TickContext:
        if ctx.action_result is None:
            return ctx

        importance = self.base_importance
        if not ctx.plan_followed:
            importance += self.plan_deviation_boost

        try:
            memory_content = format_action_memory(ctx.action_result, ctx.resident)
            memory_svc = MemoryService(ctx.db)
            await memory_svc.add_memory(
                resident_id=ctx.resident.id,
                type="event",
                content=memory_content,
                importance=importance,
                source="agent_action",
            )
            ctx.memory_created = True
        except Exception as e:
            logger.warning("Memorize failed for %s: %s", ctx.resident.slug, e)

        return ctx
