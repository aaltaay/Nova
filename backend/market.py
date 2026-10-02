"""
Eastern-time market session helpers.

Extracted from main.py (backend-modularity.mdc target layout). Behavior is
unchanged — same premarket/regular/after-hours boundaries used by the scan
loop to decide which discovery function runs.

Also owns momentum pace RVOL (Daily Rate): today's volume ÷ expected
volume by this time of day.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from datetime import timedelta

from constants import (
    HOD_MOMO_RVOL_PACE_FLOOR,
    NOVA_OS_NYSE_HOLIDAYS,
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


def regular_hours_at(when: datetime) -> bool:
    """Weekday, not an NYSE holiday, and 09:30 <= ET clock < 16:00.

    The only session that accepts an unpriced (market) order -- Nasdaq offers
    no unpriced orders in its extended sessions and IBKR holds an RTH-only MKT
    until the next open (``execution/session_gate.py``). ``when`` is an aware
    America/New_York datetime: the wall clock on Live and Paper, the replay
    playhead on Sim.
    """
    if when.weekday() >= 5:
        return False
    if when.date().isoformat() in NOVA_OS_NYSE_HOLIDAYS:
        return False
    minutes = when.hour * 60 + when.minute
    return SESSION_RTH_OPEN_MIN_ET <= minutes < SESSION_RTH_CLOSE_MIN_ET


def regular_session_opened_at(when: datetime) -> bool:
    """True once today's regular session has opened: an exchange day, ET clock >= 09:30.

    Before then there is no "today's open". IBKR's open tick (type 14) is the
    current session's open, and "before open will refer to previous day" --
    so in premarket, and all weekend, it is the previous session's open
    (``ibkr/open_tick.py``). ``when`` is an aware datetime.
    """
    when = when.astimezone(ET)
    if when.weekday() >= 5:
        return False
    if when.date().isoformat() in NOVA_OS_NYSE_HOLIDAYS:
        return False
    return when.hour * 60 + when.minute >= SESSION_RTH_OPEN_MIN_ET


def in_after_hours() -> bool:
    now = now_et()
    start = _et_at_minutes(now, SESSION_RTH_CLOSE_MIN_ET)
    end = _et_at_minutes(now, SESSION_AFTERHOURS_END_MIN_ET)
    return start <= now < end


# (midnight, next midnight, bounds) of the Eastern day asked about last: the L1 handlers ask on
# every tick, and a day's answer never changes.
_session_day: tuple[float, float, tuple[float, float] | None] | None = None


def trading_session_bounds(ts: float) -> tuple[float, float] | None:
    """Nova's trading session on ``ts``'s Eastern date: 04:00 and 20:00 ET as epoch seconds.

    ``None`` on a weekend or an NYSE holiday. The session is the extended day IBKR's US-stock
    bars cover -- premarket, regular hours, after hours -- and the only one Nova trades. After
    20:00 IBKR keeps the same SMART lines moving with its overnight session (20:00-03:50 ET, its
    OVERNIGHT venue): trades IBKR dates to the next trading day, which move the last while the
    day's volume and high stand still. They belong to no session of Nova's (2026-10-01: one
    200-share OM print at 20:48 read as a 12% leg on the Bots page). Early-close half-days are
    not modelled (``sim/trading_day.py``).
    """
    global _session_day
    cached = _session_day
    if cached is not None and cached[0] <= ts < cached[1]:
        return cached[2]
    day = datetime.fromtimestamp(ts, ET).date()
    midnight = datetime(day.year, day.month, day.day, tzinfo=ET)
    nxt = day + timedelta(days=1)
    bounds = None
    if day.weekday() < 5 and day.isoformat() not in NOVA_OS_NYSE_HOLIDAYS:
        bounds = (_et_at_minutes(midnight, SESSION_PREMARKET_START_MIN_ET).timestamp(),
                  _et_at_minutes(midnight, SESSION_AFTERHOURS_END_MIN_ET).timestamp())
    _session_day = (midnight.timestamp(), datetime(nxt.year, nxt.month, nxt.day, tzinfo=ET).timestamp(),
                    bounds)
    return bounds


def in_trading_session(ts: float) -> bool:
    """True when ``ts`` falls inside an exchange day's 04:00-20:00 ET session (``trading_session_bounds``)."""
    bounds = trading_session_bounds(ts)
    return bounds is not None and bounds[0] <= ts < bounds[1]


def volume_day_elapsed_fraction(now: datetime | None = None) -> float:
    """Fraction of the volume day (04:00–16:00 ET) elapsed, for pace RVOL.

    momentum / Trade-Ideas "Relative Volume (Daily Rate)" compares cumulative
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
    """momentum Daily Rate RVOL: today_vol / (avg_daily_vol * elapsed_frac)."""
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
