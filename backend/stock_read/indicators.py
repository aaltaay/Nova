"""Numbers the read computes from stored one-minute bars (ADR 036). Pure.

A bar is ``{t: epoch seconds (the minute's start), o, h, l, c, v}``, oldest first, closed bars only
(the caller drops the forming minute). Every function answers ``None`` when the bars cannot say --
never a zero standing in for an unknown.
"""
from __future__ import annotations

import math
from datetime import datetime, time as dtime
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from constants_stock_read import (
    STOCK_READ_BACKSIDE_LOOK_BARS,
    STOCK_READ_BACKSIDE_TAIL_SHARE,
    STOCK_READ_ROUND_STEP,
)
from setup_scanner.series import ema

ET = ZoneInfo("America/New_York")
SESSION_START = dtime(4, 0)
REGULAR_OPEN = dtime(9, 30)
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
EPS = 1e-9


def et(ts: float) -> datetime:
    return datetime.fromtimestamp(float(ts), ET)


def session_of(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The newest session's bars from 04:00 ET (the chart's VWAP anchor)."""
    if not bars:
        return []
    start = datetime.combine(et(bars[-1]["t"]).date(), SESSION_START, ET).timestamp()
    return [b for b in bars if float(b["t"]) >= start]


def vwap(bars: list[dict[str, Any]]) -> float | None:
    num = den = 0.0
    for b in bars:
        v = float(b.get("v") or 0)
        if v > 0:
            num += (float(b["h"]) + float(b["l"]) + float(b["c"])) / 3.0 * v
            den += v
    return round(num / den, 4) if den > 0 else None


def macd_last(closes: list[float]) -> dict[str, float] | None:
    """The 12/26/9 MACD line, signal and histogram at the last close; None under 35 closes."""
    if len(closes) < MACD_SLOW + MACD_SIGNAL:
        return None
    fast, slow = ema(closes, MACD_FAST), ema(closes, MACD_SLOW)
    line = [a - b for a, b in zip(fast, slow, strict=True)]
    sig = ema(line, MACD_SIGNAL)
    return {"macd_line": round(line[-1], 6), "macd_signal": round(sig[-1], 6),
            "macd_hist": round(line[-1] - sig[-1], 6), "bars": len(closes)}


def ema_last(closes: list[float], n: int) -> float | None:
    return round(ema(closes, n)[-1], 4) if len(closes) >= n else None


def round_levels(price: float | None, step: float = STOCK_READ_ROUND_STEP) -> tuple[float | None, float | None]:
    """The nearest half / whole dollar strictly above and at-or-under ``price``."""
    if price is None or price <= 0:
        return None, None
    below = math.floor(price / step + EPS) * step
    above = below + step
    return round(above, 2), round(below, 2)


def levels(bars: list[dict[str, Any]], *, price: float | None, prev_close: float | None) -> dict[str, Any]:
    """The high of day (and when), the premarket high (04:00-09:30 of the bars' own day), the 09:30
    open (None before it printed), the session VWAP and the round numbers around the price."""
    day = session_of(bars)
    hod = None
    for b in day:
        if hod is None or float(b["h"]) >= hod["price"]:
            hod = {"price": round(float(b["h"]), 4), "ts": float(b["t"])}
    pre = [b for b in day if et(b["t"]).time() < REGULAR_OPEN]
    reg = [b for b in day if et(b["t"]).time() >= REGULAR_OPEN]
    above, below = round_levels(price)
    return {
        "hod": hod,
        "pmh": round(max(float(b["h"]) for b in pre), 4) if pre else None,
        "open": round(float(reg[0]["o"]), 4) if reg and et(reg[0]["t"]).time() < dtime(9, 31) else None,
        "prev_close": prev_close,
        "vwap": vwap(day),
        "round_above": above,
        "round_below": below,
    }


def volume_profile(bars: list[dict[str, Any]], n: int) -> dict[str, Any] | None:
    """Shares traded on green vs red candles over the last ``n`` (a doji counts for neither)."""
    look = [b for b in bars[-n:] if float(b.get("v") or 0) > 0]
    if not look:
        return None
    green = sum(float(b["v"]) for b in look if float(b["c"]) > float(b["o"]) + EPS)
    red = sum(float(b["v"]) for b in look if float(b["c"]) < float(b["o"]) - EPS)
    return {"green": int(green), "red": int(red), "bars": len(look)}


def median_range(bars: list[dict[str, Any]], n: int) -> float | None:
    rng = [float(b["h"]) - float(b["l"]) for b in bars[-n:]]
    return round(median(rng), 4) if rng else None


def manual_stop(bars: list[dict[str, Any]], entry: float, n: int) -> float | None:
    """A hand plan's stop: the lowest low of the last ``n`` closed candles, when it is under the entry."""
    lows = [float(b["l"]) for b in bars[-n:]]
    if not lows:
        return None
    low = min(lows)
    return round(low, 4) if low < entry - EPS else None


def backside(bars: list[dict[str, Any]]) -> list[str]:
    """Warnings the candles themselves give that the move may be done (descriptive, never a call):
    a topping tail on the high-of-day candle, that candle being the day's biggest volume and red,
    the 1-minute MACD histogram crossing under zero, and a candle closing under the one before."""
    day = session_of(bars)
    if len(day) < 2:
        return []
    out: list[str] = []
    look = day[-STOCK_READ_BACKSIDE_LOOK_BARS:]
    top = max(day, key=lambda b: float(b["h"]))
    if top in look:
        rng = float(top["h"]) - float(top["l"])
        wick = float(top["h"]) - max(float(top["o"]), float(top["c"]))
        if rng > EPS and wick / rng >= STOCK_READ_BACKSIDE_TAIL_SHARE - EPS:
            out.append(f"a topping tail on the high-of-day candle ({et(top['t']).strftime('%H:%M')})")
        biggest = max(day, key=lambda b: float(b.get("v") or 0))
        if biggest is top and float(top["c"]) < float(top["o"]) - EPS:
            out.append("the high-of-day candle is the day's biggest volume and closed red")
    closes = [float(b["c"]) for b in day]
    if len(closes) >= MACD_SLOW + MACD_SIGNAL + 1:
        now_h, before = macd_last(closes), macd_last(closes[:-1])
        if now_h and before and before["macd_hist"] > 0 >= now_h["macd_hist"]:
            out.append("the 1-minute MACD histogram crossed under zero")
    last, prev = day[-1], day[-2]
    if float(last["h"]) < float(prev["h"]) - EPS and float(last["c"]) < float(prev["l"]) - EPS:
        out.append("the last candle closed under the one before it")
    return out
