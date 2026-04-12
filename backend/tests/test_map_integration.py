"""Integration tests for map-aware agent behavior.

Tests that verify map-data, prompts, and actions work together across modules.
"""
import pytest
from unittest.mock import MagicMock
from app.agent.map_data import LOCATIONS, get_location_at, assign_home
from app.agent.prompts import build_decision_prompt
from app.agent.actions import ActionType, get_available_actions


def _make_resident(slug="test", tile_x=63, tile_y=48, home_location_id="house_a"):
    r = MagicMock()
    r.id = "res-1"
    r.slug = slug
    r.name = "Test"
    r.tile_x = tile_x
    r.tile_y = tile_y
    r.status = "idle"
    r.district = "central"
    r.home_tile_x = None
    r.home_tile_y = None
    r.home_location_id = home_location_id
    r.persona_md = "Friendly."
    r.meta_json = {"sbti": {"type": "CTRL", "type_name": "\u63a7\u5236\u8005", "dimensions": {"So1": "M", "Ac3": "M"}}}
    return r


def test_decide_prompt_includes_location():
    """Decide prompt should mention the NPC's current location."""
    r = _make_resident(tile_x=63, tile_y=48)  # Inside library
    system, user = build_decision_prompt(
        resident=r, schedule_phase="\u4e0a\u5348", world_time="10:00",
        nearby_residents=[], memories=[], today_actions=[],
        available_actions=[ActionType.STUDY], max_daily_actions=20,
    )
    assert "\u56fe\u4e66\u9986" in system


def test_decide_prompt_shows_boost():
    """Library should boost STUDY/REFLECT/JOURNAL."""
    r = _make_resident(tile_x=63, tile_y=48)
    system, _ = build_decision_prompt(
        resident=r, schedule_phase="\u4e0a\u5348", world_time="10:00",
        nearby_residents=[], memories=[], today_actions=[],
        available_actions=[ActionType.STUDY], max_daily_actions=20,
    )
    assert "STUDY" in system
    assert "REFLECT" in system


def test_go_home_uses_location_id():
    """GO_HOME should be available based on home_location_id entrance."""
    r = _make_resident(tile_x=63, tile_y=48, home_location_id="house_a")
    # house_a entrance is (65, 19), NPC is at (63, 48) -- not home
    actions = get_available_actions(r, [])
    assert ActionType.GO_HOME in actions


def test_go_home_not_available_when_at_home():
    """GO_HOME unavailable when at home entrance."""
    r = _make_resident(tile_x=65, tile_y=19, home_location_id="house_a")
    actions = get_available_actions(r, [])
    assert ActionType.GO_HOME not in actions


def test_full_housing_assignment_flow():
    """Simulate assigning 21 residents to fill all housing."""
    occupied = {}
    assignments = []
    for i in range(21):
        loc_id = assign_home(occupied=occupied)
        assert loc_id is not None, f"Resident {i+1} got no home"
        occupied[loc_id] = occupied.get(loc_id, 0) + 1
        assignments.append(loc_id)

    # First 6 get private houses
    assert assignments[:6] == ["house_a", "house_b", "house_c", "house_d", "house_e", "house_f"]
    # Next 15 fill apartments
    assert all(a.startswith("apt_") for a in assignments[6:])
    # 22nd should be None
    assert assign_home(occupied=occupied) is None
