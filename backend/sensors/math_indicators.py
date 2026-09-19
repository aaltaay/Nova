"""Pure indicator math from OHLCV bars. No I/O. No trip levels."""
from __future__ import annotations

from typing import Any


def _closes(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["c"]) for b in bars]


def ema_series(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        return [None] * len(values)
    k = 2.0 / (period + 1)
    out: list[float | None] = []
    ema: float | None = None
    window: list[float] = []
    for value in values:
        window.append(value)
        if ema is None:
            if len(window) < period:
                out.append(None)
                continue
            ema = sum(window[-period:]) / period
            out.append(round(ema, 6))
            continue
        ema = value * k + ema * (1.0 - k)
        out.append(round(ema, 6))
    return out


def last_ema(bars: list[dict[str, Any]], period: int) -> dict[str, Any]:
    closes = _closes(bars)
    series = ema_series(closes, period)
    value = series[-1] if series else None
    return {
        "period": period,
        "value": value,
        "ready": value is not None,
        "bars": len(closes),
    }


def macd_from_closes(closes: list[float], fast: int, slow: int, signal: int) -> dict[str, Any]:
    fast_s = ema_series(closes, fast)
    slow_s = ema_series(closes, slow)
    macd_line: list[float | None] = []
    for a, b in zip(fast_s, slow_s, strict=True):
        if a is None or b is None:
            macd_line.append(None)
        else:
            macd_line.append(round(a - b, 6))
    filled = [x for x in macd_line if x is not None]
    signal_on_filled = ema_series(filled, signal)
    signal_line: list[float | None] = [None] * (len(macd_line) - len(filled)) + signal_on_filled
    last_macd = macd_line[-1] if macd_line else None
    last_signal = signal_line[-1] if signal_line else None
    hist = None
    if last_macd is not None and last_signal is not None:
        hist = round(last_macd - last_signal, 6)
    return {
        "macd": last_macd,
        "signal": last_signal,
        "histogram": hist,
        "ready": hist is not None,
        "bars": len(closes),
    }


def typical_price(bar: dict[str, Any]) -> float:
    return (float(bar["h"]) + float(bar["l"]) + float(bar["c"])) / 3.0


def session_vwap(bars: list[dict[str, Any]]) -> dict[str, Any]:
    num = 0.0
    den = 0.0
    running: list[float] = []
    for bar in bars:
        vol = float(bar.get("v") or 0)
        if vol <= 0:
            running.append(running[-1] if running else typical_price(bar))
            continue
        num += typical_price(bar) * vol
        den += vol
        running.append(num / den if den else typical_price(bar))
    value = running[-1] if running and den > 0 else None
    last = float(bars[-1]["c"]) if bars else None
    dist = None
    if value is not None and last is not None:
        dist = round(last - value, 6)
    return {
        "vwap": round(value, 6) if value is not None else None,
        "last": last,
        "distance": dist,
        "running": running,
    }


def slope_last(values: list[float], n: int) -> float | None:
    if n < 2 or len(values) < n:
        return None
    window = values[-n:]
    x_mean = (n - 1) / 2.0
    y_mean = sum(window) / n
    num = 0.0
    den = 0.0
    for i, y in enumerate(window):
        num += (i - x_mean) * (y - y_mean)
        den += (i - x_mean) ** 2
    if den == 0:
        return None
    return round(num / den, 8)


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0
