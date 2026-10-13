"""Per-share arithmetic for a followed trade. Pure: no IBKR, no clock.

The feed has no position size, so P/L is per share and in percent points against the trader's average price.
Long: price minus average; short: average minus price. A window exit is a range, never one invented fill.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# What Nova will ask IBKR for: a US stock ticker as the feed reads it (letters, digits, a class dot).
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,5}(\.[A-Z])?$")


def priceable(symbol: str) -> bool:
    return bool(TICKER_RE.match(symbol or ""))


def pl_point(side: str, avg: float, price: float) -> dict[str, float]:
    per_share = price - avg if side == "long" else avg - price
    return {"per_share": round(per_share, 4), "pct": _pct(per_share, avg)}


def pl_range(side: str, avg: float, low: float, high: float) -> dict[str, float]:
    if side == "long":
        lo, hi = low - avg, high - avg
    else:
        lo, hi = avg - high, avg - low
    return {"low_per_share": round(lo, 4), "high_per_share": round(hi, 4),
            "low_pct": _pct(lo, avg), "high_pct": _pct(hi, avg)}


def _pct(per_share: float, avg: float) -> float:
    return round(per_share / avg * 100.0, 2) if avg > 0 else 0.0


def held(entry_ts: float, entry_since_ts: float | None, entry_known: bool,
         end_ts: float, end_since_ts: float | None = None) -> dict[str, float | None]:
    """``{min_sec, max_sec}`` from entry to ``end_ts`` (an exit, or now). Each ``*_since_ts`` opens a window
    before its time; ``max_sec`` is None when the entry time is not known (only a floor is)."""
    earliest_end = end_since_ts if end_since_ts is not None else end_ts
    min_sec = max(0.0, earliest_end - entry_ts)
    max_sec = None if not entry_known else max(0.0, end_ts - (entry_since_ts if entry_since_ts is not None else entry_ts))
    return {"min_sec": round(min_sec), "max_sec": None if max_sec is None else round(max_sec)}


def exit_at(trades: list[dict[str, Any]], at_ts: float) -> dict[str, float] | None:
    """The last price-setting trade at or before ``at_ts``'s second: ``{price, trade_ts}``, or None."""
    limit = float(int(at_ts))
    best = None
    for row in trades:
        if row.get("sets_price") and row["ts"] <= limit and (best is None or row["ts"] >= best["ts"]):
            best = row
    return None if best is None else {"price": float(best["price"]), "trade_ts": float(best["ts"])}


def range_from_trades(trades: list[dict[str, Any]], from_ts: float, to_ts: float) -> tuple[float, float] | None:
    """Lowest and highest price-setting trade from ``from_ts``'s second to ``to_ts``'s second, or None."""
    lo_sec, hi_sec = float(int(from_ts)), float(int(to_ts))
    prices = [float(r["price"]) for r in trades if r.get("sets_price") and lo_sec <= r["ts"] <= hi_sec]
    return (min(prices), max(prices)) if prices else None


def range_from_bars(bars: list[dict[str, Any]], from_ts: float, to_ts: float) -> tuple[float, float] | None:
    """Low and high of the 1-minute bars (``{t ISO, h, l, v}``) whose minute overlaps the window, or None."""
    lows, highs = [], []
    for bar in bars:
        start = bar_start(bar.get("t"))
        if start is None or start + 60 <= from_ts or start > to_ts or not bar.get("v"):
            continue
        lows.append(float(bar["l"]))
        highs.append(float(bar["h"]))
    return (min(lows), max(highs)) if lows else None


def bar_start(t: Any) -> float | None:
    if not isinstance(t, str):
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
