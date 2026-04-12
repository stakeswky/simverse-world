"""Action type definitions and context-sensitive filtering for the agent loop."""
from dataclasses import dataclass
from enum import Enum


class ActionType(str, Enum):
    # Social
    CHAT_RESIDENT  = "CHAT_RESIDENT"
    CHAT_FOLLOW_UP = "CHAT_FOLLOW_UP"
    GOSSIP         = "GOSSIP"
    # Movement
    WANDER         = "WANDER"
    VISIT_DISTRICT = "VISIT_DISTRICT"
    GO_HOME        = "GO_HOME"
    # Observe
    OBSERVE        = "OBSERVE"
    EAVESDROP      = "EAVESDROP"
    # Self
    REFLECT        = "REFLECT"
    JOURNAL        = "JOURNAL"
    # Work
    WORK           = "WORK"
    STUDY          = "STUDY"
    # Rest
    IDLE           = "IDLE"
    NAP            = "NAP"


@dataclass
class ActionResult:
    """Parsed output from the LLM decision step."""
    action: ActionType
    target_slug: str | None        # Resident slug if social action
    target_tile: tuple[int, int] | None  # (x, y) destination if movement
    reason: str                    # LLM's one-sentence rationale


# Actions that require a nearby idle/walking resident as target
_SOCIAL_NEEDS_IDLE_TARGET = {ActionType.CHAT_RESIDENT, ActionType.GOSSIP, ActionType.CHAT_FOLLOW_UP}

# Actions that can target chatting residents (observer role)
_SOCIAL_OBSERVER = {ActionType.EAVESDROP}

# Actions always available
_ALWAYS_AVAILABLE = {ActionType.WANDER, ActionType.VISIT_DISTRICT, ActionType.OBSERVE,
                     ActionType.REFLECT, ActionType.JOURNAL, ActionType.WORK,
                     ActionType.STUDY, ActionType.IDLE, ActionType.NAP}


def get_available_actions(resident, nearby_residents: list) -> list[ActionType]:
    """Return the list of valid actions given current world context.

    Args:
        resident: Resident ORM object (current actor)
        nearby_residents: Resident ORM objects within interaction range

    Returns:
        Ordered list of ActionType values the LLM may choose from.
    """
    available: list[ActionType] = list(_ALWAYS_AVAILABLE)

    idle_nearby = [r for r in nearby_residents if r.status in ("idle", "walking") and r.id != resident.id]
    chatting_nearby = [r for r in nearby_residents if r.status in ("chatting", "socializing") and r.id != resident.id]

    if idle_nearby:
        available.extend(_SOCIAL_NEEDS_IDLE_TARGET)

    if chatting_nearby or idle_nearby:
        available.extend(_SOCIAL_OBSERVER)

    # GO_HOME: available when not already at home
    home_loc_id = getattr(resident, 'home_location_id', None)
    if home_loc_id:
        from app.agent.map_data import get_location_by_id
        home_loc = get_location_by_id(home_loc_id)
        if home_loc:
            entrance = home_loc["entrance"]
            if not (resident.tile_x == entrance[0] and resident.tile_y == entrance[1]):
                available.append(ActionType.GO_HOME)
    else:
        # Fallback to old home_tile_x/y
        home_x = resident.home_tile_x
        home_y = resident.home_tile_y
        if home_x is not None and home_y is not None:
            if not (resident.tile_x == home_x and resident.tile_y == home_y):
                available.append(ActionType.GO_HOME)

    # Deduplicate while preserving order
    seen: set[ActionType] = set()
    result: list[ActionType] = []
    for a in available:
        if a not in seen:
            seen.add(a)
            result.append(a)
    return result
