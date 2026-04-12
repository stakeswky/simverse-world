import pytest
from app.agent.pathfinder import find_path, get_walkable_tiles


def test_find_path_direct_neighbors():
    """Adjacent tiles should return a 2-step path."""
    walkable = {(x, y) for x in range(10) for y in range(10)}
    path = find_path((0, 0), (1, 0), walkable)
    assert path is not None
    assert len(path) >= 2
    assert path[0] == (0, 0)
    assert path[-1] == (1, 0)


def test_find_path_around_obstacle():
    """A* should route around unwalkable tiles."""
    walkable = {(x, y) for x in range(5) for y in range(5)}
    # Create vertical wall at x=2 (except top row)
    obstacle = {(2, y) for y in range(1, 5)}
    walkable -= obstacle

    path = find_path((0, 2), (4, 2), walkable)
    assert path is not None
    assert path[-1] == (4, 2)
    # Path should not cross the obstacle
    for tile in path:
        assert tile not in obstacle


def test_find_path_same_start_end():
    """Start == end returns single-tile path."""
    walkable = {(5, 5)}
    path = find_path((5, 5), (5, 5), walkable)
    assert path == [(5, 5)]


def test_find_path_impossible():
    """Unreachable destination returns None."""
    walkable = {(0, 0), (1, 0)}  # (5, 5) not in walkable
    path = find_path((0, 0), (5, 5), walkable)
    assert path is None


def test_find_path_long_corridor():
    """Straight corridor path is optimal length."""
    walkable = {(x, 5) for x in range(20)}
    path = find_path((0, 5), (19, 5), walkable)
    assert path is not None
    assert len(path) == 20  # 0..19 inclusive


def test_get_walkable_tiles_returns_set():
    tiles = get_walkable_tiles()
    assert isinstance(tiles, set)
    assert len(tiles) > 100  # Should cover multiple districts


def test_locations_coverage():
    """All locations in map_data should contribute walkable tiles."""
    from app.agent.map_data import LOCATIONS
    assert len(LOCATIONS) >= 4
    tiles = get_walkable_tiles()
    # Spot-check: tavern entrance area should be walkable
    assert (72, 14) in tiles


def test_find_path_heuristic_optimality():
    """A* with Manhattan heuristic finds path in bounded steps."""
    walkable = {(x, y) for x in range(20) for y in range(20)}
    path = find_path((0, 0), (19, 19), walkable)
    assert path is not None
    # Manhattan distance = 38, path length should be 39 (optimal)
    assert len(path) == 39
