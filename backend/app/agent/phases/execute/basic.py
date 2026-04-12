"""BasicExecutePlugin: handle movement and status changes."""
from __future__ import annotations

import logging
from typing import Any

from app.agent.actions import ActionType
from app.agent.map_data import get_valid_target_tile
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
            if action in movement_actions:
                # Resolve target tile
                target = ctx.action_result.target_tile
                if action == ActionType.GO_HOME:
                    # Use home_location_id entrance
                    home_loc_id = getattr(ctx.resident, 'home_location_id', None)
                    if home_loc_id:
                        target = get_valid_target_tile(home_loc_id)
                    elif ctx.resident.home_tile_x is not None:
                        target = (ctx.resident.home_tile_x, ctx.resident.home_tile_y)

                if target:
                    walkable = get_walkable_tiles()
                    path = find_path(
                        (ctx.resident.tile_x, ctx.resident.tile_y),
                        target,
                        walkable,
                    )
                    if path and len(path) >= 2:
                        next_tile = path[1]
                        ctx.resident.tile_x = next_tile[0]
                        ctx.resident.tile_y = next_tile[1]
                        ctx.resident.status = "walking"
                        ctx.new_tile = next_tile
                    else:
                        # Already at destination or unreachable — reset to idle
                        ctx.resident.status = "idle"
                        ctx.new_tile = (ctx.resident.tile_x, ctx.resident.tile_y)
                    await ctx.db.commit()
                else:
                    # No valid target — reset to idle
                    ctx.resident.status = "idle"
                    await ctx.db.commit()
            elif action in {ActionType.IDLE, ActionType.NAP, ActionType.REFLECT, ActionType.JOURNAL}:
                if ctx.resident.status not in ("chatting", "socializing"):
                    ctx.resident.status = "idle"
                    await ctx.db.commit()
        except Exception as e:
            logger.warning("Execute failed for %s: %s", ctx.resident.slug, e)

        return ctx
