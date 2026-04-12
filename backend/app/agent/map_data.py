"""Town map data: named locations, coordinates, and utility functions."""
from __future__ import annotations

import math
from typing import Any

LOCATIONS: dict[str, dict[str, Any]] = {
    # === Public Facilities ===
    "academy": {
        "name": "学院",
        "type": "public",
        "role": "growth",
        "bounds": (15, 18, 42, 34),
        "center": (28, 26),
        "entrance": (25, 18),
        "description": "小镇的学习中心，有多间教室和自习室",
        "boosted_actions": ["STUDY", "REFLECT"],
    },
    "tavern": {
        "name": "酒馆",
        "type": "public",
        "role": "social",
        "bounds": (72, 13, 83, 26),
        "center": (77, 19),
        "entrance": (72, 14),
        "description": "热闹的社交场所，居民们喜欢在这里聊天和交换消息",
        "boosted_actions": ["CHAT_RESIDENT", "GOSSIP"],
    },
    "cafe": {
        "name": "咖啡馆",
        "type": "public",
        "role": "casual_social",
        "bounds": (53, 14, 62, 26),
        "center": (57, 20),
        "entrance": (53, 14),
        "description": "安静的休闲场所，适合一对一的深度对话",
        "boosted_actions": ["CHAT_RESIDENT", "IDLE"],
    },
    "workshop": {
        "name": "工坊",
        "type": "public",
        "role": "production",
        "bounds": (108, 20, 124, 34),
        "center": (116, 27),
        "entrance": (108, 20),
        "description": "制造和修理物品的地方，工具和材料一应俱全",
        "boosted_actions": ["WORK"],
    },
    "library": {
        "name": "图书馆",
        "type": "public",
        "role": "knowledge",
        "bounds": (57, 43, 70, 53),
        "center": (63, 48),
        "entrance": (57, 43),
        "description": "藏书丰富的图书馆，适合研究和独处思考",
        "boosted_actions": ["STUDY", "REFLECT", "JOURNAL"],
    },
    "shop": {
        "name": "杂货铺",
        "type": "public",
        "role": "economy",
        "bounds": (75, 43, 93, 53),
        "center": (84, 48),
        "entrance": (75, 43),
        "description": "日用品和特色商品的交易场所",
        "boosted_actions": ["WORK", "OBSERVE"],
    },
    "town_hall": {
        "name": "市政厅",
        "type": "public",
        "role": "governance",
        "bounds": (106, 45, 132, 62),
        "center": (119, 53),
        "entrance": (106, 45),
        "description": "小镇的行政中心，处理公共事务和居民登记",
        "boosted_actions": ["WORK"],
    },
    # === Private Houses ===
    "house_a": {
        "name": "住宅A", "type": "private",
        "bounds": (65, 14, 69, 26), "center": (67, 20), "entrance": (65, 19),
        "capacity": 1,
    },
    "house_b": {
        "name": "住宅B", "type": "private",
        "bounds": (86, 13, 90, 25), "center": (88, 19), "entrance": (86, 18),
        "capacity": 1,
    },
    "house_c": {
        "name": "住宅C", "type": "private",
        "bounds": (93, 13, 97, 25), "center": (95, 19), "entrance": (93, 18),
        "capacity": 1,
    },
    "house_d": {
        "name": "住宅D", "type": "private",
        "bounds": (20, 59, 24, 70), "center": (22, 64), "entrance": (20, 65),
        "capacity": 1,
    },
    "house_e": {
        "name": "住宅E", "type": "private",
        "bounds": (27, 59, 33, 70), "center": (30, 64), "entrance": (28, 65),
        "capacity": 1,
    },
    "house_f": {
        "name": "住宅F", "type": "private",
        "bounds": (36, 59, 40, 70), "center": (38, 64), "entrance": (36, 65),
        "capacity": 1,
    },
    # === Apartments ===
    "apt_star": {
        "name": "星光公寓", "type": "apartment",
        "bounds": (51, 65, 62, 75), "center": (56, 70), "entrance": (54, 74),
        "capacity": 5,
    },
    "apt_moon": {
        "name": "月华公寓", "type": "apartment",
        "bounds": (69, 65, 80, 75), "center": (74, 70), "entrance": (72, 74),
        "capacity": 5,
    },
    "apt_dawn": {
        "name": "晨曦公寓", "type": "apartment",
        "bounds": (87, 65, 99, 75), "center": (93, 70), "entrance": (90, 74),
        "capacity": 5,
    },
    # === Outdoor Areas ===
    "north_path": {
        "name": "北林荫道", "type": "outdoor",
        "bounds": (15, 35, 135, 42), "center": (75, 38),
        "description": "连接北区建筑群的林荫步道",
    },
    "central_plaza": {
        "name": "中央广场", "type": "outdoor",
        "bounds": (55, 54, 95, 58), "center": (75, 56),
        "description": "小镇中心的开阔广场，居民们经常路过",
    },
    "south_lawn": {
        "name": "南草坪", "type": "outdoor",
        "bounds": (15, 76, 99, 83), "center": (57, 79),
        "description": "南部公寓之间的绿地，适合散步和休息",
    },
    "town_entrance": {
        "name": "小镇入口", "type": "outdoor",
        "bounds": (50, 85, 90, 99), "center": (70, 92),
        "description": "小镇南端的入口区域",
    },
}


def _find_location_in_bounds(x: int, y: int) -> tuple[str | None, dict | None]:
    """Return (loc_id, loc) if (x,y) falls within any location's bounds, else (None, None)."""
    for loc_id, loc in LOCATIONS.items():
        x1, y1, x2, y2 = loc["bounds"]
        if x1 <= x <= x2 and y1 <= y <= y2:
            return loc_id, loc
    return None, None


def get_location_at(x: int, y: int) -> dict | None:
    """Return location dict if (x,y) falls within any location's bounds."""
    _, loc = _find_location_in_bounds(x, y)
    return loc


def get_location_id_at(x: int, y: int) -> str | None:
    """Return location ID if (x,y) falls within any location's bounds."""
    loc_id, _ = _find_location_in_bounds(x, y)
    return loc_id


def get_location_by_id(loc_id: str) -> dict | None:
    """Lookup location by ID."""
    return LOCATIONS.get(loc_id)


def get_public_locations() -> list[dict]:
    """All public facilities."""
    return [loc for loc in LOCATIONS.values() if loc["type"] == "public"]


def get_housing_locations() -> list[dict]:
    """All private + apartment locations with capacity."""
    return [loc for loc in LOCATIONS.values() if loc["type"] in ("private", "apartment")]


def find_nearest_location(x: int, y: int, loc_type: str | None = None) -> tuple[str, dict] | None:
    """Find nearest location by center distance, optionally filtered by type."""
    best_id, best_loc, best_dist = None, None, float("inf")
    for loc_id, loc in LOCATIONS.items():
        if loc_type and loc["type"] != loc_type:
            continue
        cx, cy = loc["center"]
        dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        if dist < best_dist:
            best_id, best_loc, best_dist = loc_id, loc, dist
    if best_id is None:
        return None
    return best_id, best_loc


def format_location_list_for_prompt() -> str:
    """Format public locations + outdoor areas into a string for LLM prompts."""
    lines = []
    for loc_id, loc in LOCATIONS.items():
        if loc["type"] in ("private", "apartment"):
            continue
        x1, y1, x2, y2 = loc["bounds"]
        desc = loc.get("description", "")
        boosted = loc.get("boosted_actions", [])
        line = f"- {loc['name']}：{desc}"
        if boosted:
            line += f"（适合：{', '.join(boosted)}）"
        line += f" 入口坐标=({loc['entrance'][0]},{loc['entrance'][1]})" if "entrance" in loc else ""
        lines.append(line)
    return "\n".join(lines)


def get_valid_target_tile(loc_id: str) -> tuple[int, int] | None:
    """Return the entrance tile of a location for pathfinding."""
    loc = LOCATIONS.get(loc_id)
    if not loc:
        return None
    return loc.get("entrance", loc.get("center"))
