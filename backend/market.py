"""
Eastern-time market session helpers.

Extracted from main.py (backend-modularity.mdc target layout). Behavior is
unchanged — same premarket/regular/after-hours boundaries used by the scan
loop to decide which discovery function runs.

Also owns momentum pace RVOL (Daily Rate): today's volume ÷ expected
volume by this time of day.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from datetime import timedelta

from constants import (
    HOD_MOMO_RVOL_PACE_FLOOR,
    NOVA_OS_NYSE_EARLY_CLOSE_MIN_ET,
    NOVA_OS_NYSE_EARLY_CLOSES,
    NOVA_OS_NYSE_HOLIDAYS,
    RVOL_VOLUME_CURVE_CUM_FRAC,
    SESSION_AFTERHOURS_END_MIN_ET,
    SESSION_PREMARKET_START_MIN_ET,
    SESSION_RTH_CLOSE_MIN_ET,
    SESSION_RTH_OPEN_MIN_ET,
)

ET = ZoneInfo("America/New_York")


def now_et() -> datetime:
    return datetime.now(ET)


def is_exchange_day(day: date) -> bool:
    """A weekday that is not an NYSE full-day holiday: a day with a trading session."""
    return day.weekday() < 5 and day.isoformat() not in NOVA_OS_NYSE_HOLIDAYS


def session_key_et(now: datetime | None = None) -> str:
    """04:00 ET-anchored trading-session key (ISO date, ``YYYY-MM-DD``).

    Midnight–03:59 ET belongs to the *prior* completed session — a restart
    in that window must not fabricate a new morning scan or resurrect a
    stale prior-session snapshot as today's live table (ADR 008).

    A weekend or holiday has no session of its own: it belongs to the last
    exchange day before it, so Saturday 04:00 is no rollover and Friday's
    boards stay Friday's until Monday 04:00 (operator report, 2026-10-17).
    """
    now = (now or now_et()).astimezone(ET)
    day = (now - timedelta(hours=SESSION_PREMARKET_START_MIN_ET // 60)).date()
    while not is_exchange_day(day):
        day -= timedelta(days=1)
    return day.isoformat()


def previous_exchange_day(day: date) -> date:
    """The exchange day strictly before ``day``: the walk back over weekends and NYSE holidays."""
    day -= timedelta(days=1)
    while not is_exchange_day(day):
        day -= timedelta(days=1)
    return day


def news_window_start(now: datetime | None = None) -> datetime:
    """Where the news for the trading session on screen begins: the previous exchange day's close (16:00 ET,
    13:00 on an NYSE early close).

    The session is ``session_key_et`` (04:00 ET, weekends and holidays walk back), not the calendar
    date: Monday premarket reads Friday's evening and the weekend's releases, the 16:00-20:00 earnings
    PRs stay on the session's boards after midnight, and Friday's boards keep their news all weekend.
    """
    session = date.fromisoformat(session_key_et(now))
    prior = previous_exchange_day(session)
    close_min = NOVA_OS_NYSE_EARLY_CLOSE_MIN_ET if prior.isoformat() in NOVA_OS_NYSE_EARLY_CLOSES else SESSION_RTH_CLOSE_MIN_ET
    return datetime.combine(prior, time(close_min // 60, close_min % 60), ET)


def news_window_start_param(now: datetime | None = None) -> str:
    """``news_window_start`` as Alpaca's news ``start``: RFC-3339 in UTC.

    Never a bare date: Alpaca reads ``2026-10-17`` as 00:00 UTC (probed 2026-10-19: earliest article
    00:40Z), which is 20:00 ET the evening before, not the ET day the caller meant.
    """
    return news_window_start(now).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _et_at_minutes(now: datetime, minutes: int) -> datetime:
    """Same calendar day in ET, at the given minutes-from-midnight."""
    return now.replace(
        hour=minutes // 60,
        minute=minutes % 60,
        second=0,
        microsecond=0,
    )


def in_premarket() -> bool:
    """04:00-09:30 ET on an exchange day. A weekend or holiday morning is closed, not premarket."""
    now = now_et()
    if not is_exchange_day(now.date()):
        return False
    start = _et_at_minutes(now, SESSION_PREMARKET_START_MIN_ET)
    open_ = _et_at_minutes(now, SESSION_RTH_OPEN_MIN_ET)
    return start <= now < open_


def in_market_hours() -> bool:
    """09:30-16:00 ET on an exchange day."""
    now = now_et()
    if not is_exchange_day(now.date()):
        return False
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
    """16:00-20:00 ET on an exchange day."""
    now = now_et()
    if not is_exchange_day(now.date()):
        return False
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
    if is_exchange_day(day):
        bounds =(_et_at_minutes(midnight, SESSION_PREMARKET_START_MIN_ET).timestamp(),
                  _et_at_minutes(midnight, SESSION_AFTERHOURS_END_MIN_ET).timestamp())
    _session_day = (midnight.timestamp(), datetime(nxt.year, nxt.month, nxt.day, tzinfo=ET).timestamp(),
                    bounds)
    return bounds


def in_trading_session(ts: float) -> bool:
    """True when ``ts`` falls inside an exchange day's 04:00-20:00 ET session (``trading_session_bounds``)."""
    bounds = trading_session_bounds(ts)
    return bounds is not None and bounds[0] <= ts < bounds[1]


def volume_curve_fraction(et_minute: float) -> float:
    """Share of a stock-day's 04:00-20:00 volume normally traded by ``et_minute`` (minutes after ET
    midnight, fractions allowed), interpolated on ``RVOL_VOLUME_CURVE_CUM_FRAC``."""
    knots = RVOL_VOLUME_CURVE_CUM_FRAC
    if not knots:
        return 0.0
    if et_minute <= knots[0][0]:
        return float(knots[0][1])
    if et_minute >= knots[-1][0]:
        return float(knots[-1][1])
    for (m0, f0), (m1, f1) in zip(knots, knots[1:], strict=False):
        if et_minute <= m1:
            return float(f1) if m1 == m0 else float(f0 + (et_minute - m0) / (m1 - m0) * (f1 - f0))
    return float(knots[-1][1])


def volume_day_elapsed_fraction(now: datetime | None = None) -> float:
    """Share of the day's volume expected by now, for pace RVOL.

    momentum / Trade-Ideas "Relative Volume (Daily Rate)" compares cumulative
    volume to *expected* volume by this clock time, not raw daily/avg. The
    expectation is the measured small-cap volume curve, not a straight line
    over 04:00-16:00: the line expected 36% of the day by 08:20 where small
    caps trade about 10%, so premarket RVOL read ~3.5x low.
    Floor avoids divide-by-near-zero in the first minutes after 4:00.
    """
    now = now or now_et()
    minute = now.hour * 60 + now.minute + now.second / 60.0
    return max(HOD_MOMO_RVOL_PACE_FLOOR, min(1.0, volume_curve_fraction(minute)))


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
