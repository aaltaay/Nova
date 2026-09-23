"""Synthetic one-minute bars for the setup scanner tests."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from setup_scanner.bars import Bar

ET = ZoneInfo("America/New_York")


def et_ts(hh: int, mm: int, day: str = "2026-09-21") -> float:
    y, mo, d = (int(x) for x in day.split("-"))
    return datetime(y, mo, d, hh, mm, tzinfo=ET).timestamp()


def base_morning(start_hh: int = 8, start_mm: int = 20, n: int = 40, price: float = 4.00) -> list[Bar]:
    """A quiet base: ``n`` bars oscillating a cent around ``price``."""
    t0 = et_ts(start_hh, start_mm)
    bars = []
    for i in range(n):
        wiggle = 0.01 if i % 2 else 0.0
        o = price + wiggle
        c = price + (0.01 - wiggle)
        bars.append(Bar(t0 + 60 * i, o, max(o, c) + 0.01, min(o, c) - 0.01, c, 5_000))
    return bars


def add(bars: list[Bar], o: float, h: float, lo: float, c: float, v: float = 50_000) -> list[Bar]:
    t = bars[-1].t + 60
    bars.append(Bar(t, o, h, lo, c, v))
    return bars


def leg_up(bars: list[Bar], closes: list[float], v: float = 80_000) -> list[Bar]:
    """Green candles closing at each value in ``closes``."""
    for c in closes:
        o = bars[-1].c
        add(bars, o, c + 0.01, o - 0.01, c, v)
    return bars
