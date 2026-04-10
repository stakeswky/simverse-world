"""SBTI-driven daily schedule computation for resident autonomous behavior."""
import math
import random
from dataclasses import dataclass, field


@dataclass
class DailySchedule:
    """Computed schedule for a resident based on SBTI personality."""
    wake_hour: int           # Hour resident becomes active (0-23)
    sleep_hour: int          # Hour resident goes to sleep (0-23)
    peak_hours: list[int]    # Hours of maximum activity (1-3 values)
    social_slots: list[int]  # Hours with elevated social probability
    rest_ratio: float        # Fraction of awake time spent resting (0.0-1.0)


# SBTI dimension → schedule parameter mapping weights
_LEVEL = {"L": 0, "M": 1, "H": 2}


def _dim(sbti_data: dict, key: str) -> int:
    """Return numeric value (0=L, 1=M, 2=H) for a SBTI dimension."""
    dims = sbti_data.get("dimensions", {})
    return _LEVEL.get(dims.get(key, "M"), 1)


def build_schedule(sbti_data: dict | None) -> DailySchedule:
    """Derive a DailySchedule from SBTI dimensions.

    Algorithm:
    - wake_hour: driven by Ac1 (motivation) + Ac3 (execution). High = early riser.
    - sleep_hour: driven by So1 (social) + E2 (emotional investment). High = stays up later.
    - peak_hours: 1-3 hours where resident is most active. Derived from Ac1 + A3.
    - social_slots: hours where social probability gets a +0.2 boost. From So1 + E2.
    - rest_ratio: driven by Ac3 inverted. Low Ac3 = high rest_ratio.
    """
    if not sbti_data:
        return DailySchedule(
            wake_hour=8,
            sleep_hour=22,
            peak_hours=[10, 14],
            social_slots=[12, 19],
            rest_ratio=0.35,
        )

    ac1 = _dim(sbti_data, "Ac1")  # motivation: 0-2
    ac3 = _dim(sbti_data, "Ac3")  # execution:  0-2
    so1 = _dim(sbti_data, "So1")  # social:     0-2
    e2  = _dim(sbti_data, "E2")   # emotional:  0-2
    a3  = _dim(sbti_data, "A3")   # meaning:    0-2

    # wake_hour: [5, 7, 9] for H, M, L motivation+execution
    drive = ac1 + ac3  # 0-4
    wake_hour = max(5, 9 - drive)

    # sleep_hour: [21, 22, 23] for L, M, H social+emotional
    # social_drive: 0-4; use (social_drive+1)//2 so M+M (=2) → +1 → 21, not 21
    # Mapping: 0→20, 1→21, 2→21, 3→22, 4→22 → use (social_drive+1)//2
    # Better: 0→21, 1-2→22, 3-4→23
    social_drive = so1 + e2  # 0-4
    if social_drive == 0:
        sleep_hour = 21
    elif social_drive <= 2:
        sleep_hour = 22
    else:
        sleep_hour = 23

    # peak_hours: 1-3 windows. High meaning → more peaks.
    base_peak = wake_hour + 2
    if a3 == 2:  # H meaning
        peak_hours = [base_peak, base_peak + 4, base_peak + 8]
    elif a3 == 1:  # M meaning
        peak_hours = [base_peak, base_peak + 5]
    else:  # L meaning — one late peak
        peak_hours = [base_peak + 3]
    # Clamp all peaks within awake window
    peak_hours = [h % 24 for h in peak_hours if wake_hour <= h % 24 < sleep_hour]
    if not peak_hours:
        peak_hours = [wake_hour + 2]

    # social_slots: So1=H → 3 slots, M → 2, L → 1
    social_base = wake_hour + 3
    if so1 == 2:
        social_slots = [social_base, social_base + 4, social_base + 7]
    elif so1 == 1:
        social_slots = [social_base, social_base + 6]
    else:
        social_slots = [social_base + 3]
    social_slots = [h % 24 for h in social_slots if wake_hour <= h % 24 < sleep_hour]

    # rest_ratio: Ac3=H → 0.2, M → 0.4, L → 0.6
    rest_ratio = 0.6 - (ac3 * 0.2)

    return DailySchedule(
        wake_hour=wake_hour,
        sleep_hour=sleep_hour,
        peak_hours=peak_hours,
        social_slots=social_slots,
        rest_ratio=rest_ratio,
    )


def get_activity_probability(schedule: DailySchedule, hour: int) -> float:
    """Compute a 0.0-1.0 probability that a resident acts at this hour.

    Uses a smooth curve that:
    - Returns 0.0 outside [wake_hour, sleep_hour)
    - Peaks at peak_hours (up to 0.9)
    - Has a baseline of (1 - rest_ratio) * 0.5 during awake hours
    - Adds +0.2 boost at social_slots
    """
    # Outside awake window → no activity (unless debug override)
    from app.config import settings
    if getattr(settings, 'agent_debug_always_active', False):
        return 0.8  # Debug mode: always active
    if hour < schedule.wake_hour or hour >= schedule.sleep_hour:
        return 0.0

    baseline = (1.0 - schedule.rest_ratio) * 0.5

    # Peak boost: Gaussian around each peak hour
    peak_boost = 0.0
    for peak in schedule.peak_hours:
        distance = abs(hour - peak)
        # Gaussian with sigma=2 hours
        peak_boost = max(peak_boost, 0.4 * math.exp(-0.5 * (distance / 2.0) ** 2))

    # Social boost
    social_boost = 0.2 if hour in schedule.social_slots else 0.0

    prob = min(0.95, baseline + peak_boost + social_boost)
    return prob


def should_tick(schedule: DailySchedule, hour: int) -> bool:
    """Roll against activity probability with ±15 minute jitter.

    The jitter means residents don't all wake up at exactly the same second,
    and slightly different residents will tick at different wall-clock moments.
    """
    prob = get_activity_probability(schedule, hour)
    if prob <= 0.0:
        return False
    # Jitter: add small random noise to prob (±0.1)
    jittered = prob + random.uniform(-0.1, 0.1)
    return random.random() < jittered
