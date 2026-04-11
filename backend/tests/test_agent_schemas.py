import pytest
from app.agent.schemas import get_world_time, parse_action_result, DailyGoal, HourlyPlan


def test_parse_action_result_valid_json():
    raw = '{"action": "WANDER", "target_slug": null, "target_tile": [10, 20], "reason": "散步"}'
    result = parse_action_result(raw)
    assert result is not None
    assert result.action.value == "WANDER"
    assert result.target_tile == (10, 20)
    assert result.reason == "散步"


def test_parse_action_result_embedded_json():
    raw = '我决定去散步。 {"action": "IDLE", "target_slug": null, "target_tile": null, "reason": "休息"} 就这样吧。'
    result = parse_action_result(raw)
    assert result is not None
    assert result.action.value == "IDLE"


def test_parse_action_result_invalid():
    assert parse_action_result("no json here") is None
    assert parse_action_result('{"action": "INVALID_TYPE"}') is None


def test_daily_goal_dataclass():
    goal = DailyGoal(goal="研究古籍", motivation="好奇心驱使", created_at="2026-04-11T09:00:00", status="active")
    assert goal.goal == "研究古籍"
    assert goal.status == "active"


def test_hourly_plan_dataclass():
    plan = HourlyPlan(slot=0, hour_range=(7, 9), action="IDLE", target=None, location="home", importance=2, reason="早起休息", status="pending")
    assert plan.importance == 2
    assert plan.hour_range == (7, 9)
