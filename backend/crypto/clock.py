"""The Cryptos page's clock (ADR 040), pure: US stock sessions, the last 16:00 ET close, the regions' market
hours, the 8-hour funding settlements, the crypto day, and options expiries.

Every answer is computed from the time given, in America/New_York for the stocks (the desk's NYSE holiday table
through ``sim.trading_day``; early closes are not modelled) and in each region's own zone for Asia and Europe.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

from constants import (
    SESSION_AFTERHOURS_END_MIN_ET,
    SESSION_PREMARKET_START_MIN_ET,
    SESSION_RTH_CLOSE_MIN_ET,
    SESSION_RTH_OPEN_MIN_ET,
)
from constants_crypto import CRYPTO_FUNDING_HOURS_UTC, CRYPTO_OPTIONS_EXPIRY_HOUR_UTC, CRYPTO_REGIONS

ET = ZoneInfo("America/New_York")
DAY = 86400
_STOCK_EVENTS = (
    (SESSION_PREMARKET_START_MIN_ET, "premarket", "US premarket opens"),
    (SESSION_RTH_OPEN_MIN_ET, "open", "US stocks open"),
    (SESSION_RTH_CLOSE_MIN_ET, "close", "US stocks close"),
    (SESSION_AFTERHOURS_END_MIN_ET, "after_hours_end", "US after-hours ends"),
)


def open_day(day: date) -> bool:
    """An exchange day (weekday, not an NYSE holiday)."""
    from sim.trading_day import last_open_day

    return last_open_day(day) == day


def _et(now: float) -> datetime:
    return datetime.fromtimestamp(now, ET)


def _at(day: date, minutes: int) -> float:
    return datetime.combine(day, dtime(minutes // 60, minutes % 60), ET).timestamp()


def stock_session(now: float) -> str:
    """``premarket`` | ``regular`` | ``after_hours`` | ``closed`` on the ET clock."""
    et = _et(now)
    if not open_day(et.date()):
        return "closed"
    m = et.hour * 60 + et.minute
    if SESSION_PREMARKET_START_MIN_ET <= m < SESSION_RTH_OPEN_MIN_ET:
        return "premarket"
    if SESSION_RTH_OPEN_MIN_ET <= m < SESSION_RTH_CLOSE_MIN_ET:
        return "regular"
    if SESSION_RTH_CLOSE_MIN_ET <= m < SESSION_AFTERHOURS_END_MIN_ET:
        return "after_hours"
    return "closed"


def bridge_phase(now: float) -> str:
    """The bridge column's name for now: the stock session, or ``overnight`` when stocks do not trade."""
    session = stock_session(now)
    return "overnight" if session == "closed" else session


def stock_next(now: float) -> dict:
    """The next stock-session boundary after ``now``: ``{kind, at, title}``."""
    day = _et(now).date()
    for offset in range(0, 15):
        d = day + timedelta(days=offset)
        if not open_day(d):
            continue
        for minutes, kind, title in _STOCK_EVENTS:
            at = _at(d, minutes)
            if at > now:
                return {"kind": kind, "at": at, "title": title}
    raise ValueError("no exchange day in the next two weeks")  # the holiday table would have to be wrong


def reference_close(now: float) -> tuple[float, str]:
    """``(epoch, ISO session date)`` of the last regular-session close at or before ``now``."""
    day = _et(now).date()
    if open_day(day) and now >= _at(day, SESSION_RTH_CLOSE_MIN_ET):
        return _at(day, SESSION_RTH_CLOSE_MIN_ET), day.isoformat()
    d = day - timedelta(days=1)
    while not open_day(d):
        d -= timedelta(days=1)
    return _at(d, SESSION_RTH_CLOSE_MIN_ET), d.isoformat()


def crypto_day_start(now: float) -> float:
    """The last 00:00 UTC: where the crypto day (and every exchange's daily candle) begins."""
    return float(int(now) - int(now) % DAY)


def next_funding(now: float) -> float:
    """The next 8-hour funding settlement (00:00 / 08:00 / 16:00 UTC) strictly after ``now``."""
    start = crypto_day_start(now)
    for day in (0, 1):
        for hour in CRYPTO_FUNDING_HOURS_UTC:
            at = start + day * DAY + hour * 3600
            if at > now:
                return at
    return start + DAY  # unreachable: 00:00 UTC tomorrow is always later


def next_expiry(now: float) -> tuple[float, bool]:
    """``(epoch, monthly)``: the next Friday 08:00 UTC options expiry; monthly on a month's last Friday."""
    d = datetime.fromtimestamp(now, timezone.utc).date()
    for offset in range(0, 15):
        day = d + timedelta(days=offset)
        if day.weekday() != 4:
            continue
        at = datetime(day.year, day.month, day.day, CRYPTO_OPTIONS_EXPIRY_HOUR_UTC, tzinfo=timezone.utc).timestamp()
        if at > now:
            return at, (day + timedelta(days=7)).month != day.month
    raise ValueError("no Friday in two weeks")


def _region_windows(region: dict, around: date) -> list[tuple[float, float]]:
    """The region's weekday sessions on local dates around ``around``, as epochs."""
    otz, oh, om = region["open"]
    ctz, ch, cm = region["close"]
    out = []
    for offset in (-1, 0, 1):
        local = around + timedelta(days=offset)
        if local.weekday() >= 5:
            continue
        start = datetime(local.year, local.month, local.day, oh, om, tzinfo=ZoneInfo(otz)).timestamp()
        end = datetime(local.year, local.month, local.day, ch, cm, tzinfo=ZoneInfo(ctz)).timestamp()
        if end > start:
            out.append((start, end))
    return out


def regions_open(now: float) -> dict[str, bool]:
    """Which markets are in their hours now: Asia, Europe and the US regular session."""
    day = _et(now).date()
    out = {r["id"]: any(a <= now < b for a, b in _region_windows(r, day)) for r in CRYPTO_REGIONS}
    out["us"] = stock_session(now) == "regular"
    return out


def lanes(now: float) -> dict[str, list[list[int]]]:
    """The 24/7 clock's lanes for today's ET date, as ``[from, to]`` minutes after ET midnight.

    ``asia`` and ``europe`` from each region's own clock; ``premarket`` / ``regular`` / ``after_hours`` on an
    exchange day (empty otherwise); ``funding`` the settlement times as ``[m, m]``.
    """
    day = _et(now).date()
    start = datetime.combine(day, dtime(0), ET).timestamp()
    end = datetime.combine(day + timedelta(days=1), dtime(0), ET).timestamp()

    def minutes(ts: float) -> int:
        return int(round((ts - start) / 60))

    out: dict[str, list[list[int]]] = {}
    for region in CRYPTO_REGIONS:
        spans = [[minutes(max(a, start)), minutes(min(b, end))] for a, b in _region_windows(region, day)
                 if b > start and a < end]
        out[region["id"]] = sorted(s for s in spans if s[1] > s[0])
    stocks = open_day(day)
    out["premarket"] = [[SESSION_PREMARKET_START_MIN_ET, SESSION_RTH_OPEN_MIN_ET]] if stocks else []
    out["regular"] = [[SESSION_RTH_OPEN_MIN_ET, SESSION_RTH_CLOSE_MIN_ET]] if stocks else []
    out["after_hours"] = [[SESSION_RTH_CLOSE_MIN_ET, SESSION_AFTERHOURS_END_MIN_ET]] if stocks else []
    funding = []
    utc_day = crypto_day_start(start)
    for day_offset in (0, 1):
        for hour in CRYPTO_FUNDING_HOURS_UTC:
            at = utc_day + day_offset * DAY + hour * 3600
            if start <= at < end:
                funding.append([minutes(at), minutes(at)])
    out["funding"] = sorted(funding)
    return out


def clock(now: float) -> dict:
    """The board's ``clock`` block (AGENTS.md section 3, "The Cryptos page")."""
    day_start = crypto_day_start(now)
    return {
        "now": now,
        "stock_session": stock_session(now),
        "stock_next": {k: v for k, v in stock_next(now).items() if k != "title"},
        "crypto_day_start": day_start,
        "crypto_day_start_et": datetime.fromtimestamp(day_start, ET).strftime("%H:%M"),
        "regions": regions_open(now),
        "next_funding": next_funding(now),
        "lanes": lanes(now),
    }
