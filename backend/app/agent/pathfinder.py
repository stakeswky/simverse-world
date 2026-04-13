"""A* pathfinding for resident movement on the tilemap grid."""
import heapq
import json
import logging
from pathlib import Path

from app.agent.map_data import LOCATIONS

logger = logging.getLogger(__name__)

_walkable_tiles_cache: set[tuple[int, int]] | None = None

# Rectangular bounds for the overall walkable area
_WALKABLE_X_RANGE = range(14, 134)  # x=14..133
_WALKABLE_Y_RANGE = range(12, 100)  # y=12..99

_TILEMAP_PATH = Path(__file__).resolve().parents[3] / "frontend" / "public" / "assets" / "village" / "tilemap" / "tilemap.json"


def _load_collision_tiles() -> set[tuple[int, int]]:
    """Read the Collisions layer from tilemap.json and return blocked tile coordinates."""
    try:
        with open(_TILEMAP_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Could not load tilemap for collision data: %s", e)
        return set()

    map_width = data["width"]

    for layer in data["layers"]:
        if layer["name"] == "Collisions":
            coll_data = layer["data"]
            blocked: set[tuple[int, int]] = set()
            for y in _WALKABLE_Y_RANGE:
                for x in _WALKABLE_X_RANGE:
                    idx = y * map_width + x
                    if idx < len(coll_data) and coll_data[idx] != 0:
                        blocked.add((x, y))
            return blocked

    logger.warning("No 'Collisions' layer found in tilemap")
    return set()


def _get_forced_walkable() -> set[tuple[int, int]]:
    """Return tiles that must always be walkable (location entrances and centers)."""
    forced: set[tuple[int, int]] = set()
    for loc in LOCATIONS.values():
        if "entrance" in loc:
            forced.add(tuple(loc["entrance"]))
        if "center" in loc:
            forced.add(tuple(loc["center"]))
    return forced


def get_walkable_tiles() -> set[tuple[int, int]]:
    """Return the set of all walkable tile coordinates.

    Derives walkable tiles from the rectangular map bounds, subtracts
    collision-layer blocked tiles, and force-includes all location
    entrances and centers.
    """
    global _walkable_tiles_cache
    if _walkable_tiles_cache is not None:
        return _walkable_tiles_cache

    # Start with full rectangular area
    tiles: set[tuple[int, int]] = set()
    for x in _WALKABLE_X_RANGE:
        for y in _WALKABLE_Y_RANGE:
            tiles.add((x, y))

    # Subtract collision-layer blocked tiles
    blocked = _load_collision_tiles()
    if blocked:
        tiles -= blocked
        logger.info("Loaded %d collision tiles, effective walkable: %d", len(blocked), len(tiles))

    # Force-add location entrances and centers (always reachable)
    forced = _get_forced_walkable()
    tiles |= forced

    _walkable_tiles_cache = tiles
    return tiles


def reset_walkable_cache() -> None:
    """Reset cache (for testing)."""
    global _walkable_tiles_cache
    _walkable_tiles_cache = None


def find_path(
    from_tile: tuple[int, int],
    to_tile: tuple[int, int],
    walkable_tiles: frozenset[tuple[int, int]] | set[tuple[int, int]],
    max_steps: int = 500,
) -> list[tuple[int, int]] | None:
    """Find the shortest path from from_tile to to_tile using A*.

    Args:
        from_tile: (x, y) start tile
        to_tile:   (x, y) destination tile
        walkable_tiles: set of passable tiles
        max_steps: abort if path exceeds this length

    Returns:
        Ordered list of (x, y) tiles from start to end, or None if no path.
    """
    if from_tile == to_tile:
        return [from_tile]

    if to_tile not in walkable_tiles:
        return None

    def heuristic(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    open_heap: list[tuple[int, int, tuple[int, int]]] = []
    counter = 0
    heapq.heappush(open_heap, (heuristic(from_tile, to_tile), counter, from_tile))

    came_from: dict[tuple[int, int], tuple[int, int] | None] = {from_tile: None}
    g_score: dict[tuple[int, int], int] = {from_tile: 0}

    neighbors_4 = ((1, 0), (-1, 0), (0, 1), (0, -1))

    while open_heap:
        _, _, current = heapq.heappop(open_heap)

        if current == to_tile:
            path: list[tuple[int, int]] = []
            node: tuple[int, int] | None = current
            while node is not None:
                path.append(node)
                node = came_from[node]
            path.reverse()
            return path

        current_g = g_score[current]
        if current_g >= max_steps:
            return None

        for dx, dy in neighbors_4:
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor not in walkable_tiles:
                continue

            tentative_g = current_g + 1
            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + heuristic(neighbor, to_tile)
                counter += 1
                heapq.heappush(open_heap, (f, counter, neighbor))

    return None
