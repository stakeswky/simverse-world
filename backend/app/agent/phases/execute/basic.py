"""BasicExecutePlugin: handle movement and status changes."""
from __future__ import annotations

import logging
from typing import Any

from app.agent.actions import ActionType
from app.agent.pathfinder import get_walkable_tiles, find_path
from app.agent.schemas import TickContext

logger = logging.getLogger(__name__)


class BasicExecutePlugin:
    def __init__(self, params: dict[str, Any] | None = None):
        params = params or {}
        self.max_steps: int = params.get("max_steps_per_tick", 1)

    async def execute(self, ctx: TickContext) -> TickContext:
        if ctx.action_result is None:
            return ctx

        action = ctx.action_result.action
        movement_actions = {ActionType.WANDER, ActionType.GO_HOME, ActionType.VISIT_DISTRICT}

        try:
            if action in movement_actions and ctx.action_result.target_tile:
                walkable = get_walkable_tiles()
                path = find_path(
                    (ctx.resident.tile_x, ctx.resident.tile_y),
                    ctx.action_result.target_tile,
                    walkable,
                )
                if path and len(path) >= 2:
                    next_tile = path[1]
                    ctx.resident.tile_x = next_tile[0]
                    ctx.resident.tile_y = next_tile[1]
                    ctx.resident.status = "walking"
                    ctx.new_tile = next_tile
                    await ctx.db.commit()
                else:
                    ctx.new_tile = (ctx.resident.tile_x, ctx.resident.tile_y)
            elif action in {ActionType.IDLE, ActionType.NAP, ActionType.REFLECT, ActionType.JOURNAL}:
                if ctx.resident.status not in ("chatting", "socializing"):
                    ctx.resident.status = "idle"
                    await ctx.db.commit()
        except Exception as e:
            logger.warning("Execute failed for %s: %s", ctx.resident.slug, e)

        return ctx
