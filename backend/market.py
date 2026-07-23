"""
Eastern-time market session helpers.

Extracted from main.py (backend-modularity.mdc target layout). Behavior is
unchanged — same premarket/regular/after-hours boundaries used by the scan
loop to decide which discovery function runs.

Also owns Warrior-style pace RVOL (Daily Rate): today's volume ÷ expected
volume by this time of day.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from datetime import timedelta

from constants import (
    HOD_MOMO_RVOL_PACE_FLOOR,
    SESSION_AFTERHOURS_END_MIN_ET,
    SESSION_PREMARKET_START_MIN_ET,
    SESSION_RTH_CLOSE_MIN_ET,
    SESSION_RTH_OPEN_MIN_ET,
    SESSION_VOLUME_DAY_END_MIN_ET,
)

ET = ZoneInfo("America/New_York")


def now_et() -> datetime:
    return datetime.now(ET)


def session_key_et(now: datetime | None = None) -> str:
    """04:00 ET-anchored trading-session key (ISO date, ``YYYY-MM-DD``).

    Midnight–03:59 ET belongs to the *prior* completed session — a restart
    in that window must not fabricate a new morning scan or resurrect a
    stale prior-session snapshot as today's live table (ADR 008).
    """
    now = (now or now_et()).astimezone(ET)
    return (now - timedelta(hours=SESSION_PREMARKET_START_MIN_ET // 60)).date().isoformat()


def _et_at_minutes(now: datetime, minutes: int) -> datetime:
    """Same calendar day in ET, at the given minutes-from-midnight."""
    return now.replace(
        hour=minutes // 60,
        minute=minutes % 60,
        second=0,
        microsecond=0,
    )


def in_premarket() -> bool:
    now = now_et()
    start = _et_at_minutes(now, SESSION_PREMARKET_START_MIN_ET)
    open_ = _et_at_minutes(now, SESSION_RTH_OPEN_MIN_ET)
    return start <= now < open_


def in_market_hours() -> bool:
    now = now_et()
    open_ = _et_at_minutes(now, SESSION_RTH_OPEN_MIN_ET)
    close = _et_at_minutes(now, SESSION_RTH_CLOSE_MIN_ET)
    return open_ <= now < close


def in_after_hours() -> bool:
    now = now_et()
    start = _et_at_minutes(now, SESSION_RTH_CLOSE_MIN_ET)
    end = _et_at_minutes(now, SESSION_AFTERHOURS_END_MIN_ET)
    return start <= now < end


def volume_day_elapsed_fraction(now: datetime | None = None) -> float:
    """Fraction of the volume day (04:00–16:00 ET) elapsed, for pace RVOL.

    Warrior / Trade-Ideas "Relative Volume (Daily Rate)" compares cumulative
    volume to *expected* volume by this clock time, not raw daily/avg.
    Floor avoids divide-by-near-zero in the first minutes after 4:00.
    """
    now = now or now_et()
    start = _et_at_minutes(now, SESSION_PREMARKET_START_MIN_ET)
    end = _et_at_minutes(now, SESSION_VOLUME_DAY_END_MIN_ET)
    if now < start:
        return HOD_MOMO_RVOL_PACE_FLOOR
    if now >= end:
        return 1.0
    total = (end - start).total_seconds()
    if total <= 0:
        return 1.0
    frac = (now - start).total_seconds() / total
    return max(HOD_MOMO_RVOL_PACE_FLOOR, min(1.0, frac))


def pace_relative_volume(
    today_vol: float | None,
    avg_daily_vol: float | None,
    now: datetime | None = None,
) -> float | None:
    """Warrior-style Daily Rate RVOL: today_vol / (avg_daily_vol * elapsed_frac)."""
    if today_vol is None or avg_daily_vol is None:
        return None
    try:
        tv = float(today_vol)
        av = float(avg_daily_vol)
    except (TypeError, ValueError):
        return None
    if tv <= 0 or av <= 0:
        return None
    expected = av * volume_day_elapsed_fraction(now)
    if expected <= 0:
        return None
    return round(tv / expected, 2)
