"""Each market's sessions on its own clock (ADR 060): its regular hours in its own time zone, its trading weekdays
(Tadawul trades Sunday to Thursday), a lunch pause as two segments, and -- for the US -- Nova's NYSE calendar
(holidays and early closes, ``market_board.clock``). Other markets' holidays are not known: by the clock they open.

A session is ``(date, [(start, end), ...])`` in epoch seconds, the date the market's own. Pure but for the clock.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

from constants_global_board import GLOBAL_MARKETS, GLOBAL_US_ETF_SESSION, GLOBAL_US_TZ, MON_FRI

Session = tuple[date, list[tuple[float, float]]]
_SEARCH_DAYS = 15
# A country ETF's session: the US regular session on Nova's NYSE calendar.
US_ETF = {"id": "us_etf", "tz": GLOBAL_US_TZ, "days": MON_FRI, "segments": GLOBAL_US_ETF_SESSION,
          "calendar": "nyse"}


def by_id(market_id: str) -> Mapping | None:
    return next((m for m in GLOBAL_MARKETS if m["id"] == market_id), None)


def _zone(m: Mapping) -> ZoneInfo:
    return ZoneInfo(m["tz"])


def _hm(text: str) -> dtime:
    hour, minute = text.split(":")
    return dtime(int(hour), int(minute))


def local_date(m: Mapping, now: float) -> date:
    return datetime.fromtimestamp(now, _zone(m)).date()


def is_trading_day(m: Mapping, day: date) -> bool:
    if day.weekday() not in m["days"]:
        return False
    if m["calendar"] == "nyse":
        from market_board import clock

        return clock.is_open_day(day)
    return True


def is_holiday(m: Mapping, day: date) -> bool:
    """A weekday the market's calendar says is closed (only the NYSE calendar knows any)."""
    return day.weekday() in m["days"] and not is_trading_day(m, day)


def segments_on(m: Mapping, day: date) -> list[tuple[float, float]]:
    """The day's session segments, oldest first; ``[]`` on a day the market does not trade."""
    if not is_trading_day(m, day):
        return []
    zone = _zone(m)
    out = [(datetime.combine(day, _hm(a), zone).timestamp(), datetime.combine(day, _hm(b), zone).timestamp())
           for a, b in m["segments"]]
    if m["calendar"] == "nyse":
        from market_board import clock

        close = clock.at(day, clock.close_minute(day))   # an early close (13:00 ET) ends the day sooner
        out = [(a, min(b, close)) for a, b in out if a < close]
    return out


def session_on_or_before(m: Mapping, day: date) -> Session | None:
    """The latest session on ``day`` or before it."""
    for back in range(_SEARCH_DAYS):
        d = day - timedelta(days=back)
        segs = segments_on(m, d)
        if segs:
            return d, segs
    return None


def shown(m: Mapping, now: float) -> Session | None:
    """Today's session once it has opened, else the last one."""
    today = local_date(m, now)
    segs = segments_on(m, today)
    if segs and now >= segs[0][0]:
        return today, segs
    return session_on_or_before(m, today - timedelta(days=1))


def previous(m: Mapping, session: Session) -> Session | None:
    return session_on_or_before(m, session[0] - timedelta(days=1))


def next_open_at(m: Mapping, now: float) -> float | None:
    today = local_date(m, now)
    for ahead in range(_SEARCH_DAYS):
        for start, _end in segments_on(m, today + timedelta(days=ahead)):
            if start > now:
                return start
    return None


def state(m: Mapping, now: float) -> str:
    """``open`` inside a segment, ``break`` between two segments of today's session, ``holiday`` on a weekday the
    calendar closes, else ``closed``."""
    today = local_date(m, now)
    segs = segments_on(m, today)
    if not segs:
        return "holiday" if is_holiday(m, today) else "closed"
    if any(a <= now < b for a, b in segs):
        return "open"
    if segs[0][0] <= now < segs[-1][1]:
        return "break"
    return "closed"


def sessions_since(m: Mapping, start: float, now: float) -> list[tuple[float, float]]:
    """Every session segment that overlaps ``[start, now]``, oldest first."""
    first = local_date(m, start) - timedelta(days=1)
    last = local_date(m, now)
    out: list[tuple[float, float]] = []
    d = first
    while d <= last:
        out.extend((a, b) for a, b in segments_on(m, d) if b > start and a <= now)
        d += timedelta(days=1)
    return out


def session_view(m: Mapping, now: float) -> dict:
    """The wire's ``session`` block."""
    got = shown(m, now)
    segs = got[1] if got else []
    return {
        "date": got[0].isoformat() if got else None,
        "state": state(m, now),
        "open_at": segs[0][0] if segs else None,
        "close_at": segs[-1][1] if segs else None,
        "segments": [[a, b] for a, b in segs],
        "next_open_at": next_open_at(m, now),
        "calendar": m["calendar"],
    }
