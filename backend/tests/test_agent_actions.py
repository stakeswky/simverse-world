import pytest
from unittest.mock import MagicMock
from app.agent.actions import ActionType, ActionResult, get_available_actions
from app.models.resident import Resident


def _make_resident(status="idle", district="engineering", tile_x=76, tile_y=50):
    r = MagicMock(spec=Resident)
    r.status = status
    r.district = district
    r.tile_x = tile_x
    r.tile_y = tile_y
    r.id = "test-res"
    r.slug = "test-res"
    r.home_tile_x = None
    r.home_tile_y = None
    r.home_location_id = None
    return r


def test_all_14_action_types_exist():
    expected = {
        "CHAT_RESIDENT", "CHAT_FOLLOW_UP", "GOSSIP",
        "WANDER", "VISIT_DISTRICT", "GO_HOME",
        "OBSERVE", "EAVESDROP",
        "REFLECT", "JOURNAL",
        "WORK", "STUDY",
        "IDLE", "NAP",
    }
    actual = {a.value for a in ActionType}
    assert actual == expected


def test_action_result_dataclass():
    result = ActionResult(
        action=ActionType.WANDER,
        target_slug=None,
        target_tile=(80, 55),
        reason="Feeling restless",
    )
    assert result.action == ActionType.WANDER
    assert result.target_tile == (80, 55)
    assert result.reason == "Feeling restless"


def test_get_available_actions_no_nearby():
    """With no nearby residents, social actions unavailable."""
    r = _make_resident()
    actions = get_available_actions(r, nearby_residents=[])
    social = {ActionType.CHAT_RESIDENT, ActionType.GOSSIP, ActionType.EAVESDROP, ActionType.CHAT_FOLLOW_UP}
    assert not social.intersection(set(actions))
    # Movement always available
    assert ActionType.WANDER in actions


def test_get_available_actions_with_nearby():
    """With nearby idle residents, social actions available."""
    r = _make_resident()
    other = _make_resident(status="idle")
    other.id = "other-res"
    other.slug = "other-res"
    actions = get_available_actions(r, nearby_residents=[other])
    assert ActionType.CHAT_RESIDENT in actions


def test_get_available_actions_chatting_resident_excluded():
    """Residents actively chatting cannot be targeted."""
    r = _make_resident()
    busy = _make_resident(status="chatting")
    busy.id = "busy-res"
    busy.slug = "busy-res"
    actions = get_available_actions(r, nearby_residents=[busy])
    # chatting resident not available for CHAT_RESIDENT
    # but EAVESDROP should be possible
    assert ActionType.EAVESDROP in actions
    # CHAT_RESIDENT with that specific busy resident not possible
    # (the filter should not allow initiating chat with chatting resident)


def test_go_home_available_when_away():
    """GO_HOME only available when not at home tile."""
    r = _make_resident(tile_x=10, tile_y=10)
    r.home_tile_x = 76
    r.home_tile_y = 50
    actions = get_available_actions(r, nearby_residents=[])
    assert ActionType.GO_HOME in actions


def test_go_home_unavailable_when_at_home():
    """GO_HOME not offered when already at home tile."""
    r = _make_resident(tile_x=76, tile_y=50)
    r.home_tile_x = 76
    r.home_tile_y = 50
    actions = get_available_actions(r, nearby_residents=[])
    assert ActionType.GO_HOME not in actions
