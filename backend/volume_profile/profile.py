"""Volume by price for one stretch of 1-minute bars: the histogram, its point of control and its value area. Pure.

The same method as ``frontend/src/volume_profile/volumeProfile.ts``: each bar's volume spread evenly over the rows its
high-low range covers; the POC the busiest row, a tie to the row nearest the middle; the value area grown from the POC
two rows at a time toward the heavier side until it holds ``VP_VALUE_AREA_PCT``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from constants_volume_profile import VP_MIN_ROW, VP_ROWS, VP_VALUE_AREA_PCT


@dataclass(frozen=True)
class Bar:
    t: float
    o: float
    h: float
    l: float  # noqa: E741 -- the bar's low, as on the wire
    c: float
    v: float


@dataclass(frozen=True)
class Profile:
    low: float
    high: float
    row_size: float
    up: tuple[float, ...]
    down: tuple[float, ...]
    total: float
    poc_row: int
    vah_row: int
    val_row: int
    bars: int

    @property
    def poc(self) -> float:
        return self.low + (self.poc_row + 0.5) * self.row_size

    @property
    def vah(self) -> float:
        return self.low + (self.vah_row + 1) * self.row_size

    @property
    def val(self) -> float:
        return self.low + self.val_row * self.row_size


def _point_of_control(rows: list[float]) -> int:
    mid = (len(rows) - 1) / 2
    best = 0
    for i in range(1, len(rows)):
        if rows[i] > rows[best] or (rows[i] == rows[best] and abs(i - mid) < abs(best - mid)):
            best = i
    return best


def _value_area(rows: list[float], poc: int, pct: float) -> tuple[int, int]:
    target = sum(rows) * pct / 100.0
    lo = hi = poc
    held = rows[poc]
    while held < target and (lo > 0 or hi < len(rows) - 1):
        above_n = min(2, len(rows) - 1 - hi)
        below_n = min(2, lo)
        above = sum(rows[hi + 1:hi + 1 + above_n])
        below = sum(rows[lo - below_n:lo])
        if above_n > 0 and (below_n == 0 or above >= below):
            hi += above_n
            held += above
        else:
            lo -= below_n
            held += below
    return lo, hi


def build(bars: Iterable[Bar], rows: int = VP_ROWS, value_area_pct: float = VP_VALUE_AREA_PCT) -> Profile | None:
    """The profile of ``bars``; None when none of them traded."""
    inside = [b for b in bars if b.v > 0 and b.h >= b.l and all(math.isfinite(x) for x in (b.o, b.h, b.l, b.c, b.v))]
    if not inside:
        return None
    low = min(b.l for b in inside)
    high = max(b.h for b in inside)
    row_size = max(VP_MIN_ROW, (high - low) / rows)
    n = max(1, math.ceil((high - low) / row_size - 1e-9))
    up = [0.0] * n
    down = [0.0] * n

    def row_of(price: float) -> int:
        return min(n - 1, max(0, math.floor((price - low) / row_size)))

    for b in inside:
        side = up if b.c >= b.o else down
        first, last = row_of(b.l), row_of(b.h)
        if first == last:
            side[first] += b.v
            continue
        span = b.h - b.l
        for r in range(first, last + 1):
            overlap = min(b.h, low + (r + 1) * row_size) - max(b.l, low + r * row_size)
            if overlap > 0:
                side[r] += b.v * overlap / span
    totals = [u + d for u, d in zip(up, down, strict=True)]
    poc = _point_of_control(totals)
    val_row, vah_row = _value_area(totals, poc, value_area_pct)
    return Profile(low=low, high=high, row_size=row_size, up=tuple(up), down=tuple(down), total=sum(totals),
                   poc_row=poc, vah_row=vah_row, val_row=val_row, bars=len(inside))
