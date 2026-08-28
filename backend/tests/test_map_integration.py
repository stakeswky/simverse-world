"""Integration tests for map-aware agent behavior.

Tests that verify map-data, prompts, and actions work together across modules.
"""
import io

import pytest
from unittest.mock import MagicMock
from sqlalchemy import select
from app.agent.map_data import LOCATIONS, get_location_at, assign_home
from app.agent.prompts import build_decision_prompt
from app.agent.actions import ActionType, get_available_actions
from app.models.resident import Resident


LEGACY_PLACEMENTS = {"engineering", "product", "free"}


@pytest.fixture
async def auth_headers(client):
    resp = await client.post("/auth/register", json={
        "name": "Map Import User",
        "email": "map-import@test.com",
        "password": "pass123",
    })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


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


def test_decide_prompt_includes_relationship_memories():
    """Remembered relationships now reach decide via the memories section.

    build_decision_prompt no longer takes a ``remembered_residents`` parameter
    (test-code drift): relationship knowledge is injected as ``memories``
    entries rendered verbatim under \u6700\u8fd1\u7684\u8bb0\u5fc6 as ``- [source] content``.
    """
    resident = _make_resident(tile_x=63, tile_y=48)
    memory = MagicMock()
    memory.source = "relationship"
    memory.content = "remote-friend \u662f\u8001\u670b\u53cb\uff0c\u804a\u5929\u5f88\u6295\u7f18\uff0c\u5e38\u7ea6\u5728\u9152\u9986"
    system, user = build_decision_prompt(
        resident=resident,
        schedule_phase="\u4e0a\u5348",
        world_time="10:00",
        nearby_residents=[],
        memories=[memory],
        today_actions=[],
        available_actions=[ActionType.VISIT_DISTRICT],
        max_daily_actions=20,
    )
    assert "\u6700\u8fd1\u7684\u8bb0\u5fc6" in user
    assert "[relationship]" in user
    assert "\u8001\u670b\u53cb\uff0c\u804a\u5929\u5f88\u6295\u7f18" in user
    assert "\u9152\u9986" in user


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
    """Simulate assigning every resident until the expanded town is full."""
    occupied = {}
    assignments = []
    for i in range(59):
        loc_id = assign_home(occupied=occupied)
        assert loc_id is not None, f"Resident {i+1} got no home"
        occupied[loc_id] = occupied.get(loc_id, 0) + 1
        assignments.append(loc_id)

    # First 6 get private houses
    assert assignments[:6] == ["house_a", "house_b", "house_c", "house_d", "house_e", "house_f"]
    assert assignments[6:21] == ["apt_star"] * 5 + ["apt_moon"] * 5 + ["apt_dawn"] * 5
    assert assignments[21:24] == ["house_g", "house_h", "house_i"]
    assert all(a.startswith("apt_") for a in assignments[24:])
    # The next resident should be the first one without a home.
    assert assign_home(occupied=occupied) is None


@pytest.mark.anyio
async def test_find_available_tile_uses_canonical_occupancy_bucket(db_session):
    """Legacy aliases must not select central-plaza slots while checking another bucket."""
    from app.services.resident_placement import _find_available_tile, LOCATION_TILE_SLOTS

    occupied_x, occupied_y = LOCATION_TILE_SLOTS["central_plaza"][0]
    db_session.add(
        Resident(
            slug="central-slot-1",
            name="Central Slot",
            district="central_plaza",
            creator_id="creator-1",
            tile_x=occupied_x,
            tile_y=occupied_y,
        )
    )
    await db_session.commit()

    location_id, next_x, next_y = await _find_available_tile(db_session, "engineering")
    assert location_id == "workshop"
    assert (next_x, next_y) != (occupied_x, occupied_y)


@pytest.mark.anyio
async def test_find_available_tile_skips_blocked_slots_and_uses_expansion(db_session, monkeypatch):
    """A full or blocked district falls back to a legal tile in a new district."""
    from app.services import resident_placement

    monkeypatch.setattr(resident_placement, "LOCATION_TILE_SLOTS", {
        "central_plaza": [(75, 56), (77, 56)],
        "east_gardens": [(150, 56)],
    })
    monkeypatch.setattr(resident_placement, "LOCATION_ALLOCATION_ORDER", (
        "central_plaza", "east_gardens",
    ))
    monkeypatch.setattr(resident_placement, "get_reachable_tiles", lambda: {(150, 56)})

    location_id, tile_x, tile_y = await resident_placement._find_available_tile(
        db_session,
        "central_plaza",
    )

    assert (location_id, tile_x, tile_y) == ("east_gardens", 150, 56)


@pytest.mark.anyio
async def test_find_available_tile_returns_reachable_tile(db_session):
    """Placement must never strand a resident on a walkable-but-unreachable island.

    central_plaza's first candidate slot (55, 54) is walkable but on a disconnected
    island; the old membership-only check handed it out and A* could never move that
    resident. The allocated tile must be pathable from the town hub.
    """
    from app.services.resident_placement import _find_available_tile
    from app.agent.pathfinder import get_walkable_tiles, find_path, reset_walkable_cache
    reset_walkable_cache()
    walkable = get_walkable_tiles()
    if (55, 54) not in walkable:
        pytest.skip("Tilemap not available in test environment")
    hub = tuple(LOCATIONS["central_plaza"]["center"])

    location_id, x, y = await _find_available_tile(db_session, "central_plaza")

    assert find_path(hub, (x, y), walkable) is not None, (
        f"Allocated tile ({x}, {y}) in {location_id} is unreachable from hub {hub}"
    )
    reset_walkable_cache()


@pytest.mark.anyio
async def test_find_available_tile_saturation_degrades_gracefully(db_session, monkeypatch):
    """When every district slot is occupied, fall back to a free reachable tile, not a crash.

    The saturation path used to raise RuntimeError, turning onboarding/forge into 500s.
    """
    from app.services import resident_placement

    monkeypatch.setattr(resident_placement, "LOCATION_TILE_SLOTS", {"central_plaza": [(75, 56)]})
    monkeypatch.setattr(resident_placement, "LOCATION_ALLOCATION_ORDER", ("central_plaza",))
    monkeypatch.setattr(resident_placement, "get_reachable_tiles", lambda: {(75, 56), (76, 56)})

    db_session.add(Resident(
        slug="occupier", name="Occupier", district="central_plaza",
        creator_id="creator-1", tile_x=75, tile_y=56,
    ))
    await db_session.commit()

    location_id, x, y = await resident_placement._find_available_tile(db_session, "central_plaza")

    # Only free reachable tile is (76, 56); must degrade to it instead of raising.
    assert (x, y) == (76, 56)


@pytest.mark.anyio
async def test_import_resident_emits_canonical_location_id(client, auth_headers):
    """Legacy multipart import places the resident in a canonical location.

    Regression spec for the /import route collision: the C1 soul-card JSON
    route once shadowed this multipart route (fixed by moving C1 to
    /import-card). SBTI's LLM client is mocked to its fail-open path so the
    pipeline runs offline.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    sbti_client = MagicMock()
    sbti_client.messages.create = AsyncMock(side_effect=RuntimeError("offline test"))
    with patch("app.services.sbti_service.get_client", return_value=sbti_client):
        skill_content = (
            "# Ability\n"
            "## Professional\n"
            "- Backend engineering expert with 10 years experience\n"
            "- Distributed systems and high availability architectures\n\n"
            "# Persona\n"
            "## Layer 0: Core\n"
            "- Methodical, calm under pressure, very detail-oriented\n\n"
            "# Soul\n"
            "- Build reliable systems and explain tradeoffs clearly\n"
        )
        files = {"file": ("SKILL.md", io.BytesIO(skill_content.encode()), "text/markdown")}
        data = {"name": "Canonical Import", "slug": "canonical-import"}

        resp = await client.post("/residents/import", headers=auth_headers, files=files, data=data)
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        detail = (await client.get("/residents/canonical-import")).json()

        assert payload["district"] == "workshop"
        assert payload["district"] not in LEGACY_PLACEMENTS
        x1, y1, x2, y2 = LOCATIONS["workshop"]["bounds"]
        assert x1 <= detail["tile_x"] <= x2
        assert y1 <= detail["tile_y"] <= y2


@pytest.mark.anyio
async def test_seed_creation_paths_use_canonical_location_ids(db_session):
    from seed.preset_characters import seed_presets
    from seed.seed_residents import SEED_DATA
    from app.models.user import User

    assert all(item["district"] not in LEGACY_PLACEMENTS for item in SEED_DATA)

    db_session.add(User(
        id="00000000-0000-0000-0000-000000000001",
        name="System",
        email="system@skills.world",
        soul_coin_balance=0,
    ))
    await db_session.commit()

    await seed_presets(db_session)
    residents = (await db_session.execute(select(Resident))).scalars().all()
    assert residents
    assert all(resident.district in LOCATIONS for resident in residents)
    assert all(resident.district not in LEGACY_PLACEMENTS for resident in residents)
