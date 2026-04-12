"""A* pathfinding for resident movement on the tilemap grid."""
import heapq

from app.agent.map_data import LOCATIONS

_walkable_tiles_cache: set[tuple[int, int]] | None = None


def get_walkable_tiles() -> set[tuple[int, int]]:
    """Return the set of all walkable tile coordinates.

    Derives walkable areas from LOCATIONS bounds, covering all named
    locations plus connecting corridors between them.
    """
    global _walkable_tiles_cache
    if _walkable_tiles_cache is not None:
        return _walkable_tiles_cache

    tiles: set[tuple[int, int]] = set()

    # All named location interiors are walkable
    for loc in LOCATIONS.values():
        x1, y1, x2, y2 = loc["bounds"]
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                tiles.add((x, y))

    # Full-area walkable zone connecting all three zones and outdoor areas.
    # Covers x=14..133, y=12..99 (includes town_entrance at y=85-99).
    for x in range(14, 134):
        for y in range(12, 100):
            tiles.add((x, y))

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
