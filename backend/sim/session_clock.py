"""Sim session clock — 6:00–18:00 America/New_York, scrubbable."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

SESSION_OPEN = time(6, 0)
SESSION_CLOSE = time(18, 0)
PRE_END = time(9, 30)
RTH_END = time(16, 0)

# Minutes from 06:00 ET within the session window (0 .. 12*60).
_scrub_minute: int | None = None  # None = follow wall clock clamped to session


def reset_for_tests() -> None:
    global _scrub_minute
    _scrub_minute = None


def session_bounds_on(day: datetime) -> tuple[datetime, datetime]:
    d = day.astimezone(ET).date()
    start = datetime.combine(d, SESSION_OPEN, tzinfo=ET)
    end = datetime.combine(d, SESSION_CLOSE, tzinfo=ET)
    return start, end


def _wall_et_now() -> datetime:
    return datetime.now(ET)


def now_et() -> datetime:
    """Current sim time in ET (scrubbed or wall, clamped into today's 6–18)."""
    start, end = session_bounds_on(_wall_et_now())
    if _scrub_minute is not None:
        return start + timedelta(minutes=max(0, min(_scrub_minute, 12 * 60)))
    wall = _wall_et_now()
    if wall < start:
        return start
    if wall > end:
        return end
    return wall


def phase(at: datetime | None = None) -> str:
    t = (at or now_et()).timetz().replace(tzinfo=None)
    # compare as time
    tt = (at or now_et()).time()
    if tt < PRE_END:
        return "premarket"
    if tt < RTH_END:
        return "rth"
    return "postmarket"


def phase_volume_mult(at: datetime | None = None) -> float:
    p = phase(at)
    if p == "premarket":
        return 0.45
    if p == "rth":
        return 1.0
    return 0.55


def phase_tick_interval_sec(at: datetime | None = None) -> float:
    p = phase(at)
    if p == "rth":
        return 0.08
    if p == "premarket":
        return 0.15
    return 0.12


def scrub_to_minute(minute_from_open: int) -> dict[str, Any]:
    global _scrub_minute
    _scrub_minute = int(max(0, min(int(minute_from_open), 12 * 60)))
    return status_payload()


def clear_scrub() -> dict[str, Any]:
    global _scrub_minute
    _scrub_minute = None
    return status_payload()


def status_payload() -> dict[str, Any]:
    n = now_et()
    start, end = session_bounds_on(n)
    minute = int((n - start).total_seconds() // 60)
    return {
        "sim_time_et": n.isoformat(),
        "phase": phase(n),
        "session_open_et": start.isoformat(),
        "session_close_et": end.isoformat(),
        "minute_from_open": minute,
        "minute_max": 12 * 60,
        "scrubbed": _scrub_minute is not None,
        "volume_mult": phase_volume_mult(n),
        "tick_interval_sec": phase_tick_interval_sec(n),
    }
