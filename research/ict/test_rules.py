"""The A6 rules on hand-built bars. Run: py -3 -m pytest research/ict/test_rules.py -q"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rules import Params, levels, run_day, swing_highs  # noqa: E402

M = lambda hh, mm: hh * 60 + mm  # noqa: E731

# 09:31 sweeps 101, 09:32 displaces, 09:33 closes under the 09:20 swing low and leaves a gap (09:33 high 100.5 under
# the 09:31 low 100.8). Leg 101.2 -> 99.6, middle 100.4, so the near edge 100.5 is in the top half.
OPEN_BARS = [
    (M(9, 30), 100.0, 100.6, 100.0, 100.5),
    (M(9, 31), 100.5, 101.2, 100.8, 101.0),
    (M(9, 32), 101.0, 101.05, 100.0, 100.1),
    (M(9, 33), 100.1, 100.5, 99.6, 99.7),
    (M(9, 34), 99.7, 100.2, 99.5, 100.0),
    (M(9, 35), 100.0, 100.55, 99.9, 100.3),
]


def short_day(last_bar):
    bars = [(m, 100.0, 100.0, 99.8 if m == M(9, 20) else 100.0, 100.0) for m in range(M(4, 0), M(9, 30))]
    bars += OPEN_BARS + [last_bar] + [(M(9, 37) + i, 99.5, 99.6, 99.4, 99.5) for i in range(5)]
    a = np.array(bars, dtype=float)
    return a[:, 0].astype(int), a[:, 1], a[:, 2], a[:, 3], a[:, 4]


def mirror(minute, o, h, low, c):
    return minute, 200 - o, 200 - low, 200 - h, 200 - c


def test_swing_high_needs_two_lower_before_and_none_higher_after():
    assert list(swing_highs(np.array([1, 2, 5, 3, 4, 1, 0.5]), 2)) == [2]
    assert list(swing_highs(np.array([1, 2, 5, 6, 4, 1]), 2)) == [3]


def test_levels_take_the_nearest_untaken_swing_each_side():
    hours_high = np.array([10, 11, 15, 12, 11, 13, 12, 11, 10.5, 10.4])
    hours_low = hours_high - 1
    supply, demand = levels(hours_high, hours_low, open_price=10.6, k=2)
    assert supply == 13          # 15 is further; both untaken, nearest wins
    assert demand is None or demand < 10.6


def test_textbook_short_hits_its_target():
    day = short_day((M(9, 36), 100.3, 100.4, 99.0, 99.1))
    trade = run_day(*day, supply=101.0, demand=None, p=Params())
    assert trade is not None
    assert (trade.side, trade.reason, trade.fill_min, trade.placed_min) == (-1, "target", M(9, 35), M(9, 33))
    assert trade.entry == pytest.approx(100.5)
    assert trade.stop == pytest.approx(101.21)
    assert trade.exit == pytest.approx(100.5 - 2 * 0.71)


def test_the_mirror_image_is_a_long_with_the_same_numbers():
    day = mirror(*short_day((M(9, 36), 100.3, 100.4, 99.0, 99.1)))
    trade = run_day(*day, supply=None, demand=99.0, p=Params())
    assert trade is not None
    assert (trade.side, trade.reason) == (1, "target")
    assert trade.entry == pytest.approx(99.5)
    assert trade.exit == pytest.approx(99.5 + 2 * 0.71)


def test_a_bar_through_stop_and_target_counts_the_stop():
    day = short_day((M(9, 36), 100.3, 101.5, 99.0, 99.1))
    trade = run_day(*day, supply=101.0, demand=None, p=Params())
    assert trade is not None and trade.reason == "stop"
    assert trade.exit == pytest.approx(101.21)


def test_no_sweep_no_trade():
    day = short_day((M(9, 36), 100.3, 100.4, 99.0, 99.1))
    assert run_day(*day, supply=102.0, demand=None, p=Params()) is None


def test_the_order_is_cancelled_when_price_reaches_the_target_unfilled():
    minute, o, h, low, c = short_day((M(9, 36), 100.3, 100.4, 99.0, 99.1))
    h = h.copy()
    h[minute == M(9, 35)] = 100.45          # never trades at 100.5
    low = low.copy()
    low[minute == M(9, 34)] = 99.0            # target 99.08 printed first
    assert run_day(minute, o, h, low, c, supply=101.0, demand=None, p=Params()) is None
