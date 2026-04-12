from app.agent.map_data import (
    LOCATIONS,
    assign_home,
    get_location_at,
    get_location_id_at,
    get_location_by_id,
    get_public_locations,
    get_housing_locations,
    find_nearest_location,
    format_location_list_for_prompt,
    get_valid_target_tile,
)


def test_locations_has_all_entries():
    assert len(LOCATIONS) == 20
    assert "academy" in LOCATIONS
    assert "tavern" in LOCATIONS
    assert "house_a" in LOCATIONS
    assert "apt_star" in LOCATIONS
    assert "central_plaza" in LOCATIONS


def test_get_location_at_inside_library():
    loc = get_location_at(63, 48)
    assert loc is not None
    assert loc["name"] == "图书馆"


def test_get_location_at_outside():
    loc = get_location_at(0, 0)
    assert loc is None


def test_get_location_id_at():
    assert get_location_id_at(63, 48) == "library"
    assert get_location_id_at(0, 0) is None


def test_get_location_by_id():
    loc = get_location_by_id("tavern")
    assert loc is not None
    assert loc["name"] == "酒馆"
    assert get_location_by_id("nonexistent") is None


def test_get_public_locations():
    pubs = get_public_locations()
    assert len(pubs) == 7
    names = [p["name"] for p in pubs]
    assert "学院" in names
    assert "市政厅" in names


def test_get_housing_locations():
    houses = get_housing_locations()
    assert len(houses) == 9  # 6 private + 3 apartment
    total_cap = sum(h["capacity"] for h in houses)
    assert total_cap == 21  # 6*1 + 3*5


def test_find_nearest_location_public():
    loc_id, loc = find_nearest_location(60, 48)
    assert loc_id == "library"  # (63,48) center, dist=3


def test_find_nearest_location_filtered():
    loc_id, loc = find_nearest_location(60, 48, loc_type="public")
    assert loc_id == "library"
    loc_id2, _ = find_nearest_location(60, 48, loc_type="private")
    assert loc_id2 != "library"


def test_format_location_list_for_prompt():
    text = format_location_list_for_prompt()
    assert "学院" in text
    assert "酒馆" in text
    assert "图书馆" in text
    assert "住宅A" not in text  # private homes not listed


def test_get_valid_target_tile():
    tile = get_valid_target_tile("library")
    assert tile == (57, 43)  # entrance
    assert get_valid_target_tile("nonexistent") is None


def test_get_valid_target_tile_fallback_to_center():
    tile = get_valid_target_tile("central_plaza")
    assert tile == (75, 56)  # center, since no entrance


# ── Housing Assignment Tests ─────────────────────────────────────────


def test_assign_home_first_resident_gets_private():
    """First 6 residents get private houses."""
    loc_id = assign_home(occupied={})
    assert loc_id == "house_a"


def test_assign_home_respects_capacity():
    """Once private houses are full, assigns apartments."""
    occupied = {"house_a": 1, "house_b": 1, "house_c": 1,
                "house_d": 1, "house_e": 1, "house_f": 1}
    loc_id = assign_home(occupied=occupied)
    assert loc_id == "apt_star"


def test_assign_home_apartment_fills():
    """Apartments fill room by room."""
    occupied = {"house_a": 1, "house_b": 1, "house_c": 1,
                "house_d": 1, "house_e": 1, "house_f": 1,
                "apt_star": 5, "apt_moon": 3}
    loc_id = assign_home(occupied=occupied)
    assert loc_id == "apt_moon"  # still has capacity


def test_assign_home_partial_fill_skips_correctly():
    """When house_a is full, next resident gets house_b."""
    occupied = {"house_a": 1}
    loc_id = assign_home(occupied=occupied)
    assert loc_id == "house_b"


def test_assign_home_all_full():
    """When everything is full, returns None."""
    occupied = {"house_a": 1, "house_b": 1, "house_c": 1,
                "house_d": 1, "house_e": 1, "house_f": 1,
                "apt_star": 5, "apt_moon": 5, "apt_dawn": 5}
    loc_id = assign_home(occupied=occupied)
    assert loc_id is None
