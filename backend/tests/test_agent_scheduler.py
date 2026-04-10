import pytest
from app.agent.scheduler import DailySchedule, build_schedule, get_activity_probability, should_tick


# SBTI data fixtures
CTRL_SBTI = {
    "type": "CTRL",
    "dimensions": {
        "S1": "H", "S2": "H", "S3": "H",
        "E1": "H", "E2": "M", "E3": "H",
        "A1": "M", "A2": "H", "A3": "H",
        "Ac1": "H", "Ac2": "H", "Ac3": "H",
        "So1": "M", "So2": "H", "So3": "M",
    }
}

DEAD_SBTI = {
    "type": "DEAD",
    "dimensions": {
        "S1": "L", "S2": "L", "S3": "L",
        "E1": "L", "E2": "L", "E3": "M",
        "A1": "L", "A2": "M", "A3": "L",
        "Ac1": "L", "Ac2": "L", "Ac3": "L",
        "So1": "L", "So2": "H", "So3": "M",
    }
}

GOGO_SBTI = {
    "type": "GOGO",
    "dimensions": {
        "S1": "H", "S2": "H", "S3": "M",
        "E1": "H", "E2": "M", "E3": "H",
        "A1": "M", "A2": "M", "A3": "H",
        "Ac1": "H", "Ac2": "H", "Ac3": "H",
        "So1": "M", "So2": "H", "So3": "M",
    }
}


def test_build_schedule_ctrl():
    sched = build_schedule(CTRL_SBTI)
    assert isinstance(sched, DailySchedule)
    # CTRL: high Ac1/Ac2/Ac3 → early riser, long active window
    assert sched.wake_hour <= 8
    assert sched.sleep_hour >= 22
    # High So1 → multiple social slots
    assert len(sched.social_slots) >= 1
    # rest_ratio from Ac3=H: low rest ratio (stays active)
    assert sched.rest_ratio <= 0.4


def test_build_schedule_dead():
    sched = build_schedule(DEAD_SBTI)
    # DEAD: low Ac1/Ac2/Ac3 → late riser, early sleeper
    assert sched.wake_hour >= 9
    assert sched.sleep_hour <= 23
    # Low So1 → few social slots
    assert len(sched.social_slots) <= 2
    # High rest ratio (mostly inactive)
    assert sched.rest_ratio >= 0.5


def test_build_schedule_no_sbti():
    """Residents without SBTI get a default midpoint schedule."""
    sched = build_schedule(None)
    assert sched.wake_hour == 8
    assert sched.sleep_hour == 22
    assert 0.2 <= sched.rest_ratio <= 0.6


def test_activity_probability_sleeping_hours():
    sched = build_schedule(CTRL_SBTI)
    # During sleep hours probability should be near 0
    sleep_prob = get_activity_probability(sched, (sched.sleep_hour + 2) % 24)
    assert sleep_prob < 0.1


def test_activity_probability_peak_hours():
    sched = build_schedule(GOGO_SBTI)
    # During peak hours probability should be high
    if sched.peak_hours:
        peak_prob = get_activity_probability(sched, sched.peak_hours[0])
        assert peak_prob > 0.5


def test_activity_probability_social_slot():
    sched = build_schedule(CTRL_SBTI)
    if sched.social_slots:
        # Social slots boost probability
        social_prob = get_activity_probability(sched, sched.social_slots[0])
        assert social_prob >= 0.3


def test_should_tick_sleeping_returns_false():
    """Sleeping residents should almost never tick."""
    sched = build_schedule(DEAD_SBTI)
    # Simulate 100 rolls during sleep time — expect very few True
    sleep_hour = (sched.sleep_hour + 3) % 24
    results = [should_tick(sched, sleep_hour) for _ in range(100)]
    assert sum(results) < 15  # At most 15% chance during sleep


def test_should_tick_has_jitter():
    """Consecutive should_tick calls at same hour should sometimes differ."""
    sched = build_schedule(GOGO_SBTI)
    wake_hour = sched.wake_hour + 2
    results = [should_tick(sched, wake_hour) for _ in range(50)]
    # Should see both True and False (jitter prevents all-true or all-false)
    assert True in results
    assert False in results
