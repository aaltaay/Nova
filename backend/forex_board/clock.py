"""The FX day and the sessions on their own clocks (ADR 062). Pure but for the clock.

Forex trades from Sunday 17:00 to Friday 17:00 New York, each FX day running 17:00 to 17:00. The day shown is the one
trading now, or, over the weekend, Friday's. Its sessions hand over at the newest region's 08:00: Asia from the day's
start until London's 08:00, London until New York's 08:00, New York to the day's end. A city's own session is 08:00-17:00
on its clock, on its weekdays, while the FX day is open. Summer time moves each city's hours, never the rule.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

from constants_forex_board import FOREX_DAY_START_HOUR_ET, FOREX_SESSION_LOCAL, FOREX_SESSIONS, FOREX_TZ

ET = ZoneInfo(FOREX_TZ)
HOUR = 3600.0
_OPEN_STARTS = (6, 0, 1, 2, 3)          # an FX day starts at 17:00 ET on Sunday to Thursday


def _hm(text: str) -> dtime:
    h, m = text.split(":")
    return dtime(int(h), int(m))


def _at(day: date, hm: str, tz: str | ZoneInfo) -> float:
    zone = tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)
    return datetime.combine(day, _hm(hm), zone).timestamp()


def _start_on(day: date) -> float:
    return datetime.combine(day, dtime(FOREX_DAY_START_HOUR_ET), ET).timestamp()


def day(now: float) -> dict:
    """``{from, to, open, next_open_at, date}`` -- the FX day shown; ``date`` is the day it ends on (its name)."""
    t = datetime.fromtimestamp(now, ET)
    start = t.date() if t.hour >= FOREX_DAY_START_HOUR_ET else t.date() - timedelta(days=1)
    is_open = start.weekday() in _OPEN_STARTS
    while start.weekday() not in _OPEN_STARTS:           # the weekend shows Friday's day, Thursday 17:00 on
        start -= timedelta(days=1)
    frm = _start_on(start)
    end = start + timedelta(days=1)
    nxt = None
    if not is_open:
        ahead = t.date()
        while not (ahead.weekday() == 6 and _start_on(ahead) > now):
            ahead += timedelta(days=1)
        nxt = _start_on(ahead)
    return {"from": frm, "to": _start_on(end), "open": is_open, "next_open_at": nxt, "date": end.isoformat()}


def previous_day(fx: dict) -> dict:
    """The FX day before ``fx`` (Thursday's before Friday's, Friday's before Monday's)."""
    return day(fx["from"] - 1.0)          # a second before a day's start shows the one before it


def blocks(fx: dict) -> list[dict]:
    """The three hand-over sessions of the FX day: ``[{id, name, from, to}]``, each hour in one of them."""
    label = date.fromisoformat(fx["date"])
    london = _at(label, FOREX_SESSION_LOCAL[0], "Europe/London")
    new_york = _at(label, FOREX_SESSION_LOCAL[0], ET)
    edges = [fx["from"], max(fx["from"], min(london, fx["to"])), max(fx["from"], min(new_york, fx["to"])), fx["to"]]
    return [{"id": s["id"], "name": s["name"], "from": edges[i], "to": edges[i + 1]}
            for i, s in enumerate(FOREX_SESSIONS)]


def tracks(fx: dict) -> list[dict]:
    """The cities' own hours under Follow the sun, clipped to the FX day: ``[{id, name, from, to}]``."""
    label = date.fromisoformat(fx["date"])
    out = []
    for s in FOREX_SESSIONS:
        a = _at(label, FOREX_SESSION_LOCAL[0], s["track_from"])
        b = _at(label, FOREX_SESSION_LOCAL[1], s["track_to"])
        out.append({"id": s["id"], "name": s["name"], "from": max(a, fx["from"]), "to": min(b, fx["to"])})
    return out


def home(tz: str, now: float, fx: dict) -> dict:
    """A currency's home session: 08:00-17:00 in its city on a local weekday, while the FX day is open --
    ``{open, open_at, close_at, next_open_at}``."""
    zone = ZoneInfo(tz)
    local = datetime.fromtimestamp(now, zone).date()
    today = None
    if local.weekday() < 5:
        today = (_at(local, FOREX_SESSION_LOCAL[0], zone), _at(local, FOREX_SESSION_LOCAL[1], zone))
    is_open = bool(fx["open"] and today and today[0] <= now < today[1])
    nxt = None
    for ahead in range(9):
        d = local + timedelta(days=ahead)
        if d.weekday() >= 5:
            continue
        a = _at(d, FOREX_SESSION_LOCAL[0], zone)
        if a > now and day(a)["open"]:
            nxt = a
            break
    return {"open": is_open, "open_at": today[0] if today else None, "close_at": today[1] if today else None,
            "next_open_at": nxt}


def hour_of(t: float, fx: dict) -> int:
    """The hour of the FX day ``t`` falls in, 0 to 23 (outside: below 0 or above 23)."""
    return int((t - fx["from"]) // HOUR)


def hours_done(fx: dict, now: float) -> float:
    """How many hours of the FX day have passed (24 once it is over)."""
    return max(0.0, min(24.0, (min(now, fx["to"]) - fx["from"]) / HOUR))
