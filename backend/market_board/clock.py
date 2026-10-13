"""The Market page's clock (ADR 053): the ET trading date, the session's phase and bounds, the sessions behind.

The desk day starts at 04:00 ET: before then, and on a closed day, the page reads the last session. Early closes
(NYSE, 13:00 ET) end after-hours at 17:00. Holidays and early closes come from ``constants_nova_os``.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

from constants_nova_os import NOVA_OS_NYSE_EARLY_CLOSE_NAMES, NOVA_OS_NYSE_HOLIDAY_NAMES
from constants_scanner import (
    SESSION_AFTERHOURS_END_MIN_ET,
    SESSION_PREMARKET_START_MIN_ET,
    SESSION_RTH_CLOSE_MIN_ET,
    SESSION_RTH_OPEN_MIN_ET,
)

ET = ZoneInfo("America/New_York")
EARLY_CLOSE_MIN_ET = 13 * 60
EARLY_AFTER_HOURS_END_MIN_ET = 17 * 60


def et(now: float) -> datetime:
    return datetime.fromtimestamp(now, ET)


def at(day: date, minutes: int) -> float:
    """Epoch seconds of ``minutes`` after ET midnight on ``day``."""
    return datetime.combine(day, dtime(minutes // 60, minutes % 60), ET).timestamp()


def minute_of_day(ts: float) -> int:
    t = et(ts)
    return t.hour * 60 + t.minute


def is_open_day(day: date) -> bool:
    from sim.trading_day import last_open_day

    return last_open_day(day) == day


def close_minute(day: date) -> int:
    return EARLY_CLOSE_MIN_ET if day.isoformat() in NOVA_OS_NYSE_EARLY_CLOSE_NAMES else SESSION_RTH_CLOSE_MIN_ET


def after_hours_end_minute(day: date) -> int:
    early = day.isoformat() in NOVA_OS_NYSE_EARLY_CLOSE_NAMES
    return EARLY_AFTER_HOURS_END_MIN_ET if early else SESSION_AFTERHOURS_END_MIN_ET


def prior_open_day(day: date) -> date:
    d = day - timedelta(days=1)
    while not is_open_day(d):
        d -= timedelta(days=1)
    return d


def trading_date(now: float) -> date:
    """Today's session when it is open and past 04:00 ET, else the last session before now."""
    t = et(now)
    day = t.date()
    if is_open_day(day) and t.hour * 60 + t.minute >= SESSION_PREMARKET_START_MIN_ET:
        return day
    return prior_open_day(day)


def sessions_back(day: date, n: int) -> list[date]:
    """The ``n`` sessions ending at ``day`` (or the last session before it), oldest first."""
    if not is_open_day(day):
        day = prior_open_day(day)
    out = [day]
    while len(out) < n:
        out.append(prior_open_day(out[-1]))
    return list(reversed(out))


def phase(now: float) -> str:
    """``premarket`` | ``regular`` | ``after_hours`` | ``closed`` on the ET clock."""
    t = et(now)
    day = t.date()
    if not is_open_day(day):
        return "closed"
    m = t.hour * 60 + t.minute
    if SESSION_PREMARKET_START_MIN_ET <= m < SESSION_RTH_OPEN_MIN_ET:
        return "premarket"
    if SESSION_RTH_OPEN_MIN_ET <= m < close_minute(day):
        return "regular"
    if close_minute(day) <= m < after_hours_end_minute(day):
        return "after_hours"
    return "closed"


def _next(now: float) -> dict | None:
    day = et(now).date()
    for offset in range(15):
        d = day + timedelta(days=offset)
        if not is_open_day(d):
            continue
        for minutes, kind in ((SESSION_PREMARKET_START_MIN_ET, "premarket"), (SESSION_RTH_OPEN_MIN_ET, "open"),
                              (close_minute(d), "close"), (after_hours_end_minute(d), "after_hours_end")):
            when = at(d, minutes)
            if when > now:
                return {"kind": kind, "at": when}
    return None


def session(now: float) -> dict:
    """The wire's ``session`` block."""
    day = trading_date(now)
    today = et(now).date()
    holiday = NOVA_OS_NYSE_HOLIDAY_NAMES.get(today.isoformat())
    early = NOVA_OS_NYSE_EARLY_CLOSE_NAMES.get(day.isoformat())
    note = f"US stocks closed today ({holiday})" if holiday else (f"Early close at 13:00 ET ({early})" if early else None)
    return {
        "date": day.isoformat(),
        "phase": phase(now),
        "open_at": at(day, SESSION_RTH_OPEN_MIN_ET),
        "close_at": at(day, close_minute(day)),
        "next": _next(now),
        "holiday": note,
    }
