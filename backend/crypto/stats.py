"""The Cryptos page's arithmetic (ADR 040), pure: aligned daily returns, beta, correlation, 16:00 ET prices.

A stock's session closes and a coin's 16:00 ET prices are paired by session date; returns run between
consecutive shared dates, so both sides of a pair always cover the same stretch (a date missing on either side
widens that pair's stretch for both, never for one).
"""
from __future__ import annotations

import math
from itertools import pairwise
from datetime import date, datetime, time as dtime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
# A series whose squared deviations sum to less than this does not move (daily returns near 1% sum to ~1e-3).
_FLAT = 1e-15


def aligned_returns(stock: dict[str, float], coin: dict[str, float], limit: int) -> tuple[list[float], list[float]]:
    """``(coin returns, stock returns)`` over the last ``limit`` consecutive shared dates' stretches."""
    dates = sorted(d for d in set(stock) & set(coin) if stock[d] > 0 and coin[d] > 0)
    xs: list[float] = []
    ys: list[float] = []
    for prev, cur in pairwise(dates):
        xs.append(coin[cur] / coin[prev] - 1)
        ys.append(stock[cur] / stock[prev] - 1)
    return xs[-limit:], ys[-limit:]


def beta(xs: list[float], ys: list[float], min_n: int) -> float | None:
    """The least-squares slope of ``ys`` on ``xs``; ``None`` under ``min_n`` pairs or a flat ``xs``."""
    n = len(xs)
    if n < min_n or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    var = sum((x - mx) ** 2 for x in xs)
    if var <= _FLAT:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / var


def corr(xs: list[float], ys: list[float], min_n: int) -> float | None:
    """Pearson's correlation; ``None`` under ``min_n`` pairs or when either side is flat."""
    n = len(xs)
    if n < min_n or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx * sx <= _FLAT or sy * sy <= _FLAT:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


def close_time(day: str) -> float:
    """16:00 ET on an ISO session date, as an epoch."""
    return datetime.combine(date.fromisoformat(day), dtime(16, 0), ET).timestamp()


def prices_at_close(hourly: list[dict], days: list[str]) -> dict[str, float]:
    """``{session date: the coin's price at 16:00 ET}`` from hourly candles -- the open of the hour that starts
    at 16:00, else the close of the hour that ends there; a date the series lacks is left out."""
    by_start = {c["t"]: c for c in hourly}
    out = {}
    for day in days:
        at = int(close_time(day))
        candle = by_start.get(at)
        price = candle["o"] if candle else (by_start[at - 3600]["c"] if at - 3600 in by_start else None)
        if price is not None and price > 0:
            out[day] = price
    return out


def pct_change(now: float | None, then: float | None) -> float | None:
    """``now`` against ``then`` in percent; ``None`` when either is unknown or ``then`` is not positive."""
    if now is None or then is None or then <= 0:
        return None
    return (now / then - 1) * 100
