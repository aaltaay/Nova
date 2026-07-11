"""
Shared pure numeric indicators for setup-pattern detection.

No fetching, no state, no orders — just bar-list math reused by
bull_flag.py, abcd.py, and any future pattern module.
"""

from __future__ import annotations


def ema(values: list[float], period: int) -> list[float | None]:
    """Exponential moving average. Returns None for indices before `period`
    bars have accumulated (matches how most charting platforms plot EMA)."""
    if period <= 0 or not values:
        return [None] * len(values)

    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result

    multiplier = 2 / (period + 1)
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = (values[i] - prev) * multiplier + prev
        result[i] = prev
    return result


def is_green(bar: dict) -> bool:
    """A bullish candle: close >= open."""
    close = bar.get("c")
    open_ = bar.get("o")
    if close is None or open_ is None:
        return False
    return close >= open_


def is_red(bar: dict) -> bool:
    return not is_green(bar)


def closes(bars: list[dict]) -> list[float]:
    return [b.get("c") or 0.0 for b in bars]
