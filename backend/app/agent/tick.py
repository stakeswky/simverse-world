"""Resident tick: 5-phase autonomous behavior cycle."""
import json
import logging
import re
from datetime import datetime, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.actions import ActionType, ActionResult, get_available_actions
from app.agent.pathfinder import get_walkable_tiles, find_path
from app.agent.prompts import build_decision_prompt
from app.config import settings
from app.llm.client import get_client
from app.memory.service import MemoryService
from app.models.resident import Resident

logger = logging.getLogger(__name__)

# Module-level daily action counters: {resident_id: count}
# Reset at midnight by the AgentLoop.
_daily_counts: dict[str, int] = {}
_last_reset_date: str = ""


def _get_world_time() -> tuple[str, int, str]:
    """Return (formatted_time, hour, schedule_phase).

    World time tracks real-world clock scaled by agent_time_scale.
    For MVP time_scale=1.0, world time == real time.
    """
    now = datetime.now()
    hour = now.hour
    formatted = now.strftime("%H:%M")

    if 5 <= hour < 9:
        phase = "清晨"
    elif 9 <= hour < 12:
        phase = "上午"
    elif 12 <= hour < 14:
        phase = "午后"
    elif 14 <= hour < 18:
        phase = "下午"
    elif 18 <= hour < 21:
        phase = "傍晚"
    elif 21 <= hour < 24:
        phase = "夜晚"
    else:
        phase = "深夜"
    return formatted, hour, phase


def _check_and_reset_daily_counts() -> None:
    """Reset action counts at midnight."""
    global _last_reset_date
    today = datetime.now().strftime("%Y-%m-%d")
    if today != _last_reset_date:
        _daily_counts.clear()
        _last_reset_date = today


def parse_action_result(raw: str) -> ActionResult | None:
    """Parse LLM response into ActionResult.

    Handles:
    - Pure JSON
    - JSON embedded in prose (extracts first {...} block)
    - Returns None on any parse failure
    """
    # Try to extract JSON from prose
    match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
    if not match:
        logger.debug("No JSON found in decision response: %s", raw[:200])
        return None

    try:
        data = json.loads(match.group())
        action_str = data.get("action", "")
        # Validate action type
        try:
            action = ActionType(action_str)
        except ValueError:
            logger.debug("Unknown action type: %s", action_str)
            return None

        target_tile = data.get("target_tile")
        if target_tile and isinstance(target_tile, list) and len(target_tile) == 2:
            target_tile = (int(target_tile[0]), int(target_tile[1]))
        else:
            target_tile = None

        return ActionResult(
            action=action,
            target_slug=data.get("target_slug"),
            target_tile=target_tile,
            reason=str(data.get("reason", ""))[:100],
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        logger.debug("Failed to parse action result: %s | raw: %s", e, raw[:200])
        return None


async def _perceive(db: AsyncSession, resident: Resident) -> list[Resident]:
    """Phase 1: Find nearby residents within interaction range (tile distance <= 10)."""
    all_residents = (await db.execute(
        select(Resident).where(Resident.id != resident.id)
    )).scalars().all()

    nearby = []
    for r in all_residents:
        dist = abs(r.tile_x - resident.tile_x) + abs(r.tile_y - resident.tile_y)
        if dist <= 10:
            nearby.append(r)
    return nearby


async def _execute_movement(
    db: AsyncSession,
    resident: Resident,
    target_tile: tuple[int, int],
) -> tuple[int, int]:
    """Move resident one step toward target_tile along A* path.

    Returns the actual new (tile_x, tile_y).
    """
    walkable = get_walkable_tiles()
    path = find_path((resident.tile_x, resident.tile_y), target_tile, walkable)

    if not path or len(path) < 2:
        return (resident.tile_x, resident.tile_y)

    # Move to next step on path (not teleport to destination)
    next_tile = path[1]
    resident.tile_x = next_tile[0]
    resident.tile_y = next_tile[1]
    resident.status = "walking"
    await db.commit()
    return next_tile


async def resident_tick(
    db: AsyncSession,
    resident: Resident,
) -> ActionResult | None:
    """Execute one autonomous tick for a resident.

    Phases:
    1. Perceive — query nearby residents
    2. Retrieve — fetch memories via MemoryService
    3. Decide — LLM chooses action
    4. Execute — update position/status
    5. Memorize — create event memory

    Returns ActionResult on success, None if skipped or failed.
    """
    _check_and_reset_daily_counts()

    # Check daily limit
    count = _daily_counts.get(resident.id, 0)
    if count >= settings.agent_max_daily_actions:
        return None

    world_time, hour, schedule_phase = _get_world_time()

    # -- Phase 1: Perceive -------------------------------------------------
    try:
        nearby = await _perceive(db, resident)
    except Exception as e:
        logger.warning("Tick perceive failed for %s: %s", resident.slug, e)
        return None

    # -- Phase 2: Retrieve -------------------------------------------------
    try:
        memory_svc = MemoryService(db)
        memories = await memory_svc.get_memories(resident.id, type="event", limit=10)
    except Exception as e:
        logger.warning("Tick retrieve failed for %s: %s", resident.slug, e)
        memories = []

    # -- Phase 3: Decide ---------------------------------------------------
    available_actions = get_available_actions(resident, nearby)

    # Collect today's actions for context
    today_key = datetime.now().strftime("%Y-%m-%d")
    today_actions = [
        m.content for m in memories
        if m.created_at and m.created_at.strftime("%Y-%m-%d") == today_key
    ]

    try:
        system_prompt, user_prompt = build_decision_prompt(
            resident=resident,
            schedule_phase=schedule_phase,
            world_time=world_time,
            nearby_residents=nearby,
            memories=memories,
            today_actions=today_actions,
            available_actions=available_actions,
            max_daily_actions=settings.agent_max_daily_actions,
        )
        client = get_client("system")
        resp = await client.messages.create(
            model=settings.effective_model,
            max_tokens=200,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = resp.content[0].text
        action_result = parse_action_result(raw)
    except Exception as e:
        logger.warning("Tick decide failed for %s: %s", resident.slug, e)
        return None

    if action_result is None:
        return None

    # Validate that chosen action is in available list
    if action_result.action not in available_actions:
        logger.debug("Resident %s chose unavailable action %s, skipping", resident.slug, action_result.action)
        return None

    # -- Phase 4: Execute --------------------------------------------------
    try:
        new_tile = (resident.tile_x, resident.tile_y)
        movement_actions = {ActionType.WANDER, ActionType.GO_HOME, ActionType.VISIT_DISTRICT}

        if action_result.action in movement_actions and action_result.target_tile:
            new_tile = await _execute_movement(db, resident, action_result.target_tile)
        elif action_result.action in {ActionType.IDLE, ActionType.NAP, ActionType.REFLECT, ActionType.JOURNAL}:
            if resident.status not in ("chatting", "socializing"):
                resident.status = "idle"
                await db.commit()
    except Exception as e:
        logger.warning("Tick execute failed for %s: %s", resident.slug, e)
        # Continue to memorize step even if execute had issues

    # -- Phase 5: Memorize -------------------------------------------------
    try:
        memory_content = _format_action_memory(action_result, resident)
        await memory_svc.add_memory(
            resident_id=resident.id,
            type="event",
            content=memory_content,
            importance=0.3,
            source="agent_action",
        )
    except Exception as e:
        logger.warning("Tick memorize failed for %s: %s", resident.slug, e)

    # Increment daily counter
    _daily_counts[resident.id] = count + 1

    logger.debug("Resident %s ticked: %s -> %s", resident.slug, action_result.action.value, action_result.reason)
    return action_result


def _format_action_memory(action_result: ActionResult, resident: Resident) -> str:
    """Format an action into a human-readable memory string."""
    action = action_result.action
    if action == ActionType.WANDER:
        tile = action_result.target_tile
        return f"四处游荡，走向 ({tile[0]}, {tile[1]})" if tile else "四处游荡"
    elif action == ActionType.GO_HOME:
        return "回到了自己的家"
    elif action == ActionType.VISIT_DISTRICT:
        tile = action_result.target_tile
        return f"前往了另一个区域 ({tile[0] if tile else '?'}, {tile[1] if tile else '?'})"
    elif action == ActionType.CHAT_RESIDENT:
        return f"和 {action_result.target_slug or '某位居民'} 开始了对话"
    elif action == ActionType.OBSERVE:
        return "静静地观察着周围的情况"
    elif action == ActionType.EAVESDROP:
        return "偷偷听了附近居民的对话"
    elif action == ActionType.REFLECT:
        return "进行了一段时间的自我反思"
    elif action == ActionType.JOURNAL:
        return "在心里记录了今天的见闻"
    elif action == ActionType.WORK:
        return "专注于自己的工作"
    elif action == ActionType.STUDY:
        return "学习了一些新知识"
    elif action == ActionType.GOSSIP:
        return f"和 {action_result.target_slug or '某位居民'} 闲聊八卦"
    elif action == ActionType.NAP:
        return "小憩了一会儿"
    elif action == ActionType.IDLE:
        return "发了会儿呆"
    else:
        return f"执行了 {action.value}"
