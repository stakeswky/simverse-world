"""A* pathfinding for resident movement on the tilemap grid."""
import heapq

# District bounding boxes: (x_min, y_min, x_max, y_max)
# These approximate the walkable regions in the Tiled map.
# Walls and water tiles within these boxes are still blocked
# — in the MVP we use conservative inner margins.
DISTRICT_BOUNDS: dict[str, tuple[int, int, int, int]] = {
    "engineering":  (60, 40, 95, 65),
    "art":          (30, 40, 60, 65),
    "business":     (60, 65, 95, 90),
    "free":         (30, 65, 60, 90),
    "central":      (55, 45, 80, 70),   # Central Plaza
}

# Tiles that are explicitly blocked within district bounds (walls, water, etc.)
# In a production build these would be parsed from the Tiled map's collision layer.
_BLOCKED_TILES: frozenset[tuple[int, int]] = frozenset()


_walkable_tiles_cache: set[tuple[int, int]] | None = None


def get_walkable_tiles() -> set[tuple[int, int]]:
    """Return the set of all walkable tile coordinates.

    MVP: generate a grid covering all district bounding boxes,
    minus any explicitly blocked tiles.

    Production: parse the tilemap JSON collision layer instead.
    """
    global _walkable_tiles_cache
    if _walkable_tiles_cache is not None:
        return _walkable_tiles_cache

    tiles: set[tuple[int, int]] = set()
    for x_min, y_min, x_max, y_max in DISTRICT_BOUNDS.values():
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                tiles.add((x, y))
    tiles -= set(_BLOCKED_TILES)
    _walkable_tiles_cache = tiles
    return tiles


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
        max_steps: abort if path exceeds this length (prevents runaway search)

    Returns:
        Ordered list of (x, y) tiles from start (inclusive) to end (inclusive),
        or None if no path exists.
    """
    if from_tile == to_tile:
        return [from_tile]

    if to_tile not in walkable_tiles:
        return None

    def heuristic(a: tuple[int, int], b: tuple[int, int]) -> int:
        # Manhattan distance — admissible for 4-directional grid
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    # Priority queue: (f_score, tie_breaker, tile)
    open_heap: list[tuple[int, int, tuple[int, int]]] = []
    counter = 0
    heapq.heappush(open_heap, (heuristic(from_tile, to_tile), counter, from_tile))

    came_from: dict[tuple[int, int], tuple[int, int] | None] = {from_tile: None}
    g_score: dict[tuple[int, int], int] = {from_tile: 0}

    neighbors_4 = ((1, 0), (-1, 0), (0, 1), (0, -1))

    while open_heap:
        _, _, current = heapq.heappop(open_heap)

        if current == to_tile:
            # Reconstruct path
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

    return None  # No path found
