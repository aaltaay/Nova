"""The A6 rules as pure functions over one symbol's minute bars (Bot-Trading-Plan.md section 2i).

``levels`` finds the day's supply and demand from hourly swings known before 09:30; ``run_day`` plays 09:30 onward
minute by minute: sweep, shift, fair value gap, a limit order, then stop / target / time exit. Prices only -- size and
costs belong to ``backtest.py``. Nothing reads a bar before its close.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

OPEN_MIN = 9 * 60 + 30
TICK = 0.01


@dataclass(frozen=True)
class Params:
    target_r: float = 2.0
    window_end: int = 10 * 60 + 30      # minutes after midnight ET; no new order or fill from here
    hour_strength: int = 2              # bars each side of an hourly swing
    minute_strength: int = 2            # bars each side of a 1-minute swing
    lookback: int = 10                  # prior sessions of hourly bars
    far_edge: bool = False              # enter at the gap's far edge instead of its near edge
    premium: bool = True                # the entry must sit in the better half of the leg

    @property
    def exit_min(self) -> int:
        return max(11 * 60, self.window_end + 30)


@dataclass(frozen=True)
class Trade:
    side: int            # +1 long, -1 short
    level: float
    placed_min: int
    fill_min: int
    entry: float
    stop: float
    target: float
    exit: float
    exit_min: int
    reason: str          # stop | target | time


def hourly(minute: np.ndarray, high: np.ndarray, low: np.ndarray, before: int | None = None):
    """Clock-aligned hourly highs and lows from minute bars (only bars with ``minute < before``)."""
    if before is not None:
        keep = minute < before
        minute, high, low = minute[keep], high[keep], low[keep]
    if not len(minute):
        return np.empty(0), np.empty(0)
    hour = minute // 60
    edges = np.flatnonzero(np.diff(hour)) + 1
    return np.maximum.reduceat(high, np.r_[0, edges]), np.minimum.reduceat(low, np.r_[0, edges])


def swing_highs(high: np.ndarray, k: int) -> np.ndarray:
    """Indices whose high is above the k bars before and not below the k bars after."""
    n = len(high)
    out = [i for i in range(k, n - k)
           if high[i] > high[i - k:i].max() and high[i] >= high[i + 1:i + k + 1].max()]
    return np.array(out, dtype=int)


def swing_lows(low: np.ndarray, k: int) -> np.ndarray:
    return swing_highs(-low, k)


def levels(hours_high: np.ndarray, hours_low: np.ndarray, open_price: float, k: int) -> tuple[float | None, float | None]:
    """(supply, demand): the nearest untaken hourly swing high above the open and swing low below it."""
    supply = demand = None
    for i in swing_highs(hours_high, k):
        if (hours_high[i + 1:] <= hours_high[i]).all() and hours_high[i] > open_price:
            supply = hours_high[i] if supply is None else min(supply, hours_high[i])
    for i in swing_lows(hours_low, k):
        if (hours_low[i + 1:] >= hours_low[i]).all() and hours_low[i] < open_price:
            demand = hours_low[i] if demand is None else max(demand, hours_low[i])
    return supply, demand


class _Side:
    """One side's sweep -> shift -> gap search. Written for the short side; the long side runs on negated prices."""

    def __init__(self, sign: int, level: float | None, swings: np.ndarray, k: int):
        self.sign, self.level, self.swings, self.k = sign, level, swings, k
        self.reset()

    def reset(self) -> None:
        self.extreme_idx = -1

    def order(self, j: int, hi: np.ndarray, lo: np.ndarray, cl: np.ndarray, p: Params):
        """At bar j's close: (entry, stop) in the side's own (short-oriented) prices, or None."""
        if self.level is None:
            return None
        if hi[j] > self.level and (self.extreme_idx < 0 or hi[j] > hi[self.extreme_idx]):
            self.extreme_idx = j
        x = self.extreme_idx
        if x < 0:
            return None
        ref = self.swings[(self.swings < x) & (self.swings + self.k < j)]
        if not len(ref) or cl[j] >= lo[ref[-1]]:
            return None
        middle = (hi[x] + lo[j]) / 2
        for m in range(j, x + 1, -1):
            if hi[m] < lo[m - 2]:
                edge = lo[m - 2] if p.far_edge else hi[m]
                if not p.premium or edge >= middle:
                    return edge, hi[x] + TICK
        return None


def run_day(minute: np.ndarray, o: np.ndarray, h: np.ndarray, low: np.ndarray, c: np.ndarray,
            supply: float | None, demand: float | None, p: Params) -> Trade | None:
    """Play one session from 09:30 with today's 04:00-20:00 minute bars; at most one filled trade."""
    k = p.minute_strength
    sides = {-1: _Side(-1, supply, swing_lows(low, k), k),
             +1: _Side(+1, None if demand is None else -demand, swing_lows(-h, k), k)}
    view = {-1: (h, low, c), +1: (-low, -h, -c)}
    working = None                      # (sign, entry, stop, target, level, placed_min)
    start = int(np.searchsorted(minute, OPEN_MIN))
    for j in range(start, len(minute)):
        t = minute[j]
        if working is not None:
            sign, entry, stop, target, level, placed = working
            if t >= p.window_end:
                working = None
            else:
                hi, lo, op = view[sign][0][j], view[sign][1][j], (o[j] if sign < 0 else -o[j])
                if hi >= entry:
                    fill = max(op, entry)
                    return _manage(minute, o, h, low, c, j, sign, fill, stop, target, level, placed, p)
                if lo <= target:
                    sides[sign].reset()
                    working = None
            if working is not None:
                continue
        if t >= p.window_end:
            break
        for sign, side in sides.items():
            hi, lo, cl = view[sign]
            got = side.order(j, hi, lo, cl, p)
            if got is not None and working is None:
                entry, stop = got
                working = (sign, entry, stop, entry - p.target_r * (stop - entry), side.level, int(t))
    return None


def _manage(minute, o, h, low, c, j, sign, fill, stop, target, level, placed, p: Params) -> Trade:
    """From the fill bar on, in short-oriented prices; the result is turned back into real prices."""
    def real(x: float) -> float:
        return x if sign < 0 else -x

    hi_all, lo_all, op_all = (h, low, o) if sign < 0 else (-low, -h, -o)
    exit_px, exit_min, reason = float(c[-1]), int(minute[-1]), "time"
    for i in range(j, len(minute)):
        if minute[i] >= p.exit_min:
            exit_px, exit_min, reason = float(c[i - 1]), int(minute[i - 1]), "time"
            break
        if hi_all[i] >= stop:
            worst = max(op_all[i], stop) if i > j else max(fill, stop)
            exit_px, exit_min, reason = real(worst), int(minute[i]), "stop"
            break
        if i > j and lo_all[i] <= target:
            exit_px, exit_min, reason = real(target), int(minute[i]), "target"
            break
    return Trade(side=sign, level=real(level), placed_min=placed, fill_min=int(minute[j]), entry=real(fill),
                 stop=real(stop), target=real(target), exit=float(exit_px), exit_min=exit_min, reason=reason)
