"""Sim session clock — 4:00–20:00 America/New_York, scrubbable, 1s playhead."""
from __future__ import annotations

import time as time_mod
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from constants_sim import SIM_SESSION_CLOSE_HOUR, SIM_SESSION_OPEN_HOUR
from sim.trading_day import last_trading_day

ET = ZoneInfo("America/New_York")

SESSION_OPEN = time(SIM_SESSION_OPEN_HOUR, 0)
SESSION_CLOSE = time(SIM_SESSION_CLOSE_HOUR, 0)
PRE_END = time(9, 30)
RTH_END = time(16, 0)

SESSION_SECONDS = (SIM_SESSION_CLOSE_HOUR - SIM_SESSION_OPEN_HOUR) * 60 * 60  # 04:00–20:00

# Optional YYYY-MM-DD for capture replay (None = wall calendar day).
_session_date: str | None = None
_resume_date: str | None = None

# Seconds from 04:00 ET (0 .. SESSION_SECONDS). None = follow wall clock clamped to session.
_scrub_second: float | None = None
# Wall monotonic when scrub position was last set (so playhead advances 1s / real second).
_scrub_anchor_mono: float | None = None
_paused_at: datetime | None = None
_window: tuple[time, time] | None = None


def set_window(start: str | None = None, end: str | None = None):
    global _window
    _window = (time.fromisoformat(start), time.fromisoformat(end)) if start and end else None


def session_seconds():
    start, end = session_bounds_on(_wall_et_now())
    return int((end - start).total_seconds())


def reset_for_tests() -> None:
    global _scrub_second, _scrub_anchor_mono, _session_date, _paused_at, _resume_date
    _scrub_second = None
    _scrub_anchor_mono = None
    _session_date = None
    _paused_at = None
    _resume_date = None
    set_window()


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
        # Weekend practice desk: a closed exchange day replays the last open one
        # at the same time of day, so real tickers have a session to read from.
        d = last_trading_day(day.astimezone(ET).date())
    opening, closing = _window or (SESSION_OPEN, SESSION_CLOSE)
    start = datetime.combine(d, opening, tzinfo=ET)
    end = datetime.combine(d, closing, tzinfo=ET)
    return start, end


def _wall_et_now() -> datetime:
    return datetime.now(ET)


def _clamp_sec(sec: float) -> float:
    return float(max(0.0, min(float(sec), float(session_seconds()))))


def _effective_scrub_second() -> float | None:
    """Scrub second including real-time playhead advance since last set."""
    if _scrub_second is None or _scrub_anchor_mono is None:
        return _scrub_second
    elapsed = time_mod.monotonic() - _scrub_anchor_mono
    return _clamp_sec(_scrub_second + elapsed)


def now_et() -> datetime:
    """Current sim time in ET (scrubbed playhead or wall, clamped into the session window)."""
    if _paused_at is not None:
        return _paused_at
    start, end = session_bounds_on(_wall_et_now())
    scrub = _effective_scrub_second()
    if scrub is not None:
        return start + timedelta(seconds=scrub)
    wall = _wall_et_now()
    if wall.date() != start.date():
        # Closed exchange day: the wall time of day on the replayed session date.
        wall = datetime.combine(start.date(), wall.timetz())
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


def scrub_to_minute(minute_from_open: int, *, notify: bool = True) -> dict[str, Any]:
    """UI scrubber is still minute-grained; playhead then advances per real second."""
    minute = int(max(0, min(int(minute_from_open), session_seconds() // 60)))
    return scrub_to_second(float(minute * 60), notify=notify)


def scrub_to_second(second_from_open: float, *, notify: bool = True) -> dict[str, Any]:
    global _scrub_second, _scrub_anchor_mono, _paused_at
    _scrub_second = _clamp_sec(second_from_open)
    _scrub_anchor_mono = time_mod.monotonic()
    if _paused_at is not None:
        start, _ = session_bounds_on(_paused_at)
        _paused_at = start + timedelta(seconds=_scrub_second)
    if notify:
        try:
            from sim import market as _market
            _market.rebuild_for_scrub()
        except Exception:
            pass
    return status_payload()


def keep_time_of_day(at: datetime, *, notify: bool = True) -> dict[str, Any]:
    """Place the playhead at ``at``'s Eastern clock time on the current session date.

    Used after the window/date changed (leaving historical replay); pause is kept.
    """
    global _paused_at
    start, _ = session_bounds_on(_wall_et_now())
    target = datetime.combine(start.date(), at.astimezone(ET).time(), tzinfo=ET)
    if _paused_at is not None:
        _paused_at = start  # re-date the frozen position; scrub places it below
    return scrub_to_second((target - start).total_seconds(), notify=notify)


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
        "session_date": start.date().isoformat(),
        "phase": phase(n),
        "session_open_et": start.isoformat(),
        "session_close_et": end.isoformat(),
        "minute_from_open": minute,
        "second_from_open": second,
        "minute_max": session_seconds() // 60,
        "second_max": session_seconds(),
        "scrubbed": _scrub_second is not None,
        "paused": is_paused(),
        "volume_mult": phase_volume_mult(n),
        "tick_interval_sec": phase_tick_interval_sec(n),
    }
