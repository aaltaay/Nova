"""Each currency's move and strength from IBKR's spot midpoints (ADR 062). Pure: bars and quotes in, numbers out.

A pair is quoted as the market quotes it -- EUR/USD in dollars per euro, USD/JPY in yen per dollar -- and the currency's
own move against the dollar is the pair's move for the first, its inverse for the second. Strength is the currency
against an even mix of the other priced currencies; each pair between two of them is the ratio of their two dollar
rates (how cross rates are made), so it is arithmetic on IBKR's quotes, never an estimate. Bars are
``{t, open, high, low, close}`` (``t`` the bar's start) or daily rows ``{date, high, low, close}``.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

HOUR = 3600.0


def last_close_before(bars: Sequence[Mapping], end: float) -> float | None:
    """The close of the last bar that starts before ``end`` (a one-hour bar starting an hour before a day's start
    closes at it)."""
    found = None
    for bar in bars:
        if float(bar["t"]) >= end:
            break
        if bar.get("close"):
            found = float(bar["close"])
    return found


def pair_pct(now_level: float | None, open_level: float | None) -> float | None:
    if not now_level or not open_level:
        return None
    return (now_level / open_level - 1.0) * 100.0


def vs_usd(pct: float | None, per_usd: bool) -> float | None:
    """The currency's move against the dollar from its pair's: the same for EUR/USD, the inverse for USD/JPY."""
    if pct is None:
        return None
    return (1.0 / (1.0 + pct / 100.0) - 1.0) * 100.0 if per_usd else pct


def cross(a: float, b: float) -> float:
    """The move of the pair A/B from A's and B's moves against the dollar."""
    return ((1.0 + a / 100.0) / (1.0 + b / 100.0) - 1.0) * 100.0


def strengths(moves: Mapping[str, float]) -> dict[str, float]:
    """``{code: strength}`` -- each against an even mix of the others (the dollar's move against itself is 0)."""
    if len(moves) < 2:
        return {}
    return {a: sum(cross(moves[a], moves[b]) for b in moves if b != a) / (len(moves) - 1) for a in moves}


# -- the FX day, hour by hour -----------------------------------------------------------------------------------------
def day_from_bars(bars: Sequence[Mapping], day_from: float, day_to: float) -> dict:
    """The FX day in one pair's one-hour bars: ``{open, closes, high, low, last, last_t}`` -- ``open`` the close at the
    day's start, ``closes[h]`` the close of the bar starting in hour ``h`` (None without one), ``high`` / ``low`` over
    the day's bars, ``last`` its newest close."""
    closes: list[float | None] = [None] * 24
    high = low = last = last_t = None
    for bar in bars:
        t = float(bar["t"])
        if not day_from <= t < day_to or not bar.get("close"):
            continue
        h = int((t - day_from) // HOUR)
        closes[h] = float(bar["close"])
        hi, lo = bar.get("high") or bar["close"], bar.get("low") or bar["close"]
        high = hi if high is None else max(high, hi)
        low = lo if low is None else min(low, lo)
        last, last_t = float(bar["close"]), t
    return {"open": last_close_before(bars, day_from), "closes": closes, "high": high, "low": low, "last": last,
            "last_t": last_t}


def hour_levels(closes: Sequence[float | None], done: float, now_level: float | None, open_level: float) -> list:
    """Each hour's level at its end, for the hours begun: the bar's close, carried through an hour without one (the
    open before the first), the hour now forming at ``now_level`` when there is one."""
    begun = min(24, math.ceil(done))
    out: list[float] = []
    level = open_level
    for h in range(begun):
        if closes[h] is not None:
            level = float(closes[h])
        if h == begun - 1 and done < 24 and now_level:
            level = now_level
        out.append(level)
    return out


def strength_path(levels: Mapping[str, Sequence[float]], opens: Mapping[str, float], per_usd: Mapping[str, bool],
                  hours: int) -> list[dict[str, float]]:
    """``[{code: strength at the end of hour h}]`` for the hours begun; the dollar takes part at 0."""
    path = []
    for h in range(hours):
        moves = {"USD": 0.0}
        for code, lv in levels.items():
            level = lv[h] if h < len(lv) else (lv[-1] if lv else None)
            got = vs_usd(pair_pct(level, opens.get(code)), per_usd[code])
            if got is not None:
                moves[code] = got
        path.append(strengths(moves))
    return path


def changes(path: Sequence[Mapping[str, float]]) -> list[dict[str, float]]:
    """Each hour's strength change: the hour's strength minus the hour before's (0 before the day began)."""
    out, prev = [], {}
    for row in path:
        out.append({code: round(v - prev.get(code, 0.0), 4) for code, v in row.items()})
        prev = row
    return out


def block_change(path: Sequence[Mapping[str, float]], code: str, h0: int, h1: int) -> float | None:
    """A currency's strength change over hours ``h0`` to ``h1`` (exclusive): None for a block not begun."""
    if h0 >= len(path) or code not in path[-1]:
        return None
    end = path[min(h1, len(path)) - 1].get(code)
    start = path[h0 - 1].get(code, 0.0) if h0 > 0 else 0.0
    return None if end is None else round(end - start, 4)


# -- days -------------------------------------------------------------------------------------------------------------
def completed(rows: Sequence[Mapping], day_date: str, day_open: bool) -> list[Mapping]:
    """Daily rows of FX days that have ended: an open day's own row is still forming."""
    return [r for r in rows if (r.get("date") or "") < day_date or (not day_open and (r.get("date") or "") == day_date)]


def period_move(rows: Sequence[Mapping], days: int) -> dict | None:
    """The last completed close against the one ``days`` FX days before: ``{pct, open, rate, from, to}``."""
    closes = [r for r in rows if r.get("close")]
    if len(closes) <= days:
        return None
    last, base = closes[-1], closes[-1 - days]
    return {"pct": (last["close"] / base["close"] - 1.0) * 100.0, "open": base["close"], "rate": last["close"],
            "from": base["date"], "to": last["date"]}


def range_x(high: float | None, low: float | None, open_level: float | None, rows: Sequence[Mapping],
            days: int) -> float | None:
    """The FX day's range so far, as a share of its open, over the average range of the last ``days`` completed days
    as a share of their close. None with fewer than half those days."""
    if high is None or low is None or not open_level:
        return None
    normal = [(r["high"] - r["low"]) / r["close"] for r in list(rows)[-days:]
              if r.get("high") and r.get("low") and r.get("close")]
    if len(normal) < days / 2:
        return None
    avg = sum(normal) / len(normal)
    return round(((high - low) / open_level) / avg, 2) if avg > 0 else None
