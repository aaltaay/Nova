"""Sim session clock — 6:00–18:00 America/New_York, scrubbable, 1s playhead."""
from __future__ import annotations

import time as time_mod
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

SESSION_OPEN = time(6, 0)
SESSION_CLOSE = time(18, 0)
PRE_END = time(9, 30)
RTH_END = time(16, 0)

SESSION_SECONDS = 12 * 60 * 60  # 06:00–18:00

# Optional YYYY-MM-DD for capture replay (None = wall calendar day).
_session_date: str | None = None
_resume_date: str | None = None

# Seconds from 06:00 ET (0 .. SESSION_SECONDS). None = follow wall clock clamped to session.
_scrub_second: float | None = None
# Wall monotonic when scrub position was last set (so playhead advances 1s / real second).
_scrub_anchor_mono: float | None = None
_paused_at: datetime | None = None


def reset_for_tests() -> None:
    global _scrub_second, _scrub_anchor_mono, _session_date, _paused_at, _resume_date
    _scrub_second = None
    _scrub_anchor_mono = None
    _session_date = None
    _paused_at = None
    _resume_date = None


def set_session_date(date_yyyy_mm_dd: str | None) -> None:
    global _session_date, _resume_date
    raw = (date_yyyy_mm_dd or "").strip() or None
    _session_date = raw
    _resume_date = None


def session_bounds_on(day: datetime) -> tuple[datetime, datetime]:
    date_override = _session_date or _resume_date
    if date_override:
        from datetime import date as _date
        y, m, dd = (int(x) for x in date_override.split("-"))
        d = _date(y, m, dd)
    else:
        d = day.astimezone(ET).date()
    start = datetime.combine(d, SESSION_OPEN, tzinfo=ET)
    end = datetime.combine(d, SESSION_CLOSE, tzinfo=ET)
    return start, end


def _wall_et_now() -> datetime:
    return datetime.now(ET)


def _clamp_sec(sec: float) -> float:
    return float(max(0.0, min(float(sec), float(SESSION_SECONDS))))


def _effective_scrub_second() -> float | None:
    """Scrub second including real-time playhead advance since last set."""
    if _scrub_second is None or _scrub_anchor_mono is None:
        return _scrub_second
    elapsed = time_mod.monotonic() - _scrub_anchor_mono
    return _clamp_sec(_scrub_second + elapsed)


def now_et() -> datetime:
    """Current sim time in ET (scrubbed playhead or wall, clamped into today's 6–18)."""
    if _paused_at is not None:
        return _paused_at
    start, end = session_bounds_on(_wall_et_now())
    scrub = _effective_scrub_second()
    if scrub is not None:
        return start + timedelta(seconds=scrub)
    wall = _wall_et_now()
    if wall < start:
        return start
    if wall > end:
        return end
    return wall


def is_paused() -> bool:
    return _paused_at is not None


def set_paused(paused: bool) -> dict[str, Any]:
    """Freeze exactly here, or resume here without catching up to wall time."""
    global _paused_at, _scrub_second, _scrub_anchor_mono, _resume_date
    if paused and _paused_at is None:
        _paused_at = now_et()
    elif not paused and _paused_at is not None:
        frozen = _paused_at
        # Keep the paused day even if wall midnight passed in the meantime.
        _resume_date = frozen.date().isoformat()
        start, _ = session_bounds_on(frozen)
        _scrub_second = (frozen - start).total_seconds()
        _scrub_anchor_mono = time_mod.monotonic()
        _paused_at = None
    return status_payload()


def phase(at: datetime | None = None) -> str:
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
    """UI scrubber is still minute-grained; playhead then advances per real second."""
    minute = int(max(0, min(int(minute_from_open), 12 * 60)))
    return scrub_to_second(float(minute * 60))


def scrub_to_second(second_from_open: float) -> dict[str, Any]:
    global _scrub_second, _scrub_anchor_mono, _paused_at
    _scrub_second = _clamp_sec(second_from_open)
    _scrub_anchor_mono = time_mod.monotonic()
    if _paused_at is not None:
        start, _ = session_bounds_on(_paused_at)
        _paused_at = start + timedelta(seconds=_scrub_second)
    try:
        from sim import market as _market

        _market.rebuild_for_scrub()
    except Exception:
        pass
    return status_payload()


def clear_scrub() -> dict[str, Any]:
    global _scrub_second, _scrub_anchor_mono, _paused_at, _resume_date
    _paused_at = None
    _resume_date = None
    _scrub_second = None
    _scrub_anchor_mono = None
    try:
        from sim import market as _market

        _market.rebuild_for_scrub()
    except Exception:
        pass
    return status_payload()


def status_payload() -> dict[str, Any]:
    n = now_et()
    start, end = session_bounds_on(n)
    elapsed = (n - start).total_seconds()
    minute = int(elapsed // 60)
    second = int(elapsed)
    return {
        "sim_time_et": n.isoformat(),
        "phase": phase(n),
        "session_open_et": start.isoformat(),
        "session_close_et": end.isoformat(),
        "minute_from_open": minute,
        "second_from_open": second,
        "minute_max": 12 * 60,
        "second_max": SESSION_SECONDS,
        "scrubbed": _scrub_second is not None,
        "paused": is_paused(),
        "volume_mult": phase_volume_mult(n),
        "tick_interval_sec": phase_tick_interval_sec(n),
    }
