"""Clock-labeled session phase. Not a computed chop detector (that is sensor 17)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from constants_scanner import (
    SESSION_AFTERHOURS_END_MIN_ET,
    SESSION_PREMARKET_START_MIN_ET,
    SESSION_RTH_CLOSE_MIN_ET,
    SESSION_RTH_OPEN_MIN_ET,
)
from constants_sensors import (
    SESSION_MIDDAY_END_MIN_ET,
    SESSION_MORNING_MOMENTUM_END_MIN_ET,
    SESSION_OPEN_AUCTION_END_MIN_ET,
)
from market import ET, now_et


def minutes_et(now: datetime | None = None) -> int:
    stamp = (now or now_et()).astimezone(ET)
    return stamp.hour * 60 + stamp.minute


def classify_phase(mins: int) -> str:
    if SESSION_PREMARKET_START_MIN_ET <= mins < SESSION_RTH_OPEN_MIN_ET:
        return "pre-market"
    if SESSION_RTH_OPEN_MIN_ET <= mins < SESSION_OPEN_AUCTION_END_MIN_ET:
        return "open auction"
    if SESSION_OPEN_AUCTION_END_MIN_ET <= mins < SESSION_MORNING_MOMENTUM_END_MIN_ET:
        return "morning momentum"
    if SESSION_MORNING_MOMENTUM_END_MIN_ET <= mins < SESSION_MIDDAY_END_MIN_ET:
        return "midday chop"
    if SESSION_MIDDAY_END_MIN_ET <= mins < SESSION_RTH_CLOSE_MIN_ET:
        return "power hour"
    if SESSION_RTH_CLOSE_MIN_ET <= mins < SESSION_AFTERHOURS_END_MIN_ET:
        return "after-hours"
    return "closed"


def snapshot(now: datetime | None = None) -> dict[str, Any]:
    stamp = (now or now_et()).astimezone(ET)
    mins = stamp.hour * 60 + stamp.minute
    return {
        "phase": classify_phase(mins),
        "minutes_et": mins,
        "et": stamp.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "label_source": "clock",
        "note": (
            "Clock buckets from existing session constants. "
            "'midday chop' is a time-of-day label, not sensor 17."
        ),
    }
