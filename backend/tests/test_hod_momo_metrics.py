"""Tests for Warrior 5-min relative volume metrics."""
from __future__ import annotations

from hod_momo_metrics import (
    clear_volume_buffers,
    compute_symbol_rvol_5min,
    rvol_5min,
    tod_5min_session_fraction,
    typical_5min_volume,
    update_cum_volume,
    volume_in_window,
)


def setup_function() -> None:
    clear_volume_buffers()


def test_typical_5min_volume_flat():
    # 720 min session → 144 bars; avg 1.44M → typical 10k per 5m
    assert typical_5min_volume(1_440_000, session_minutes=720, use_tod=False) == 10_000.0


def test_rvol_5min_ratio_flat():
    assert rvol_5min(50_000, 1_440_000, session_minutes=720, use_tod=False) == 5.0


def test_tod_open_heavier_than_midday():
    open_frac = tod_5min_session_fraction(et_minute=9 * 60 + 35)
    lunch_frac = tod_5min_session_fraction(et_minute=12 * 60 + 30)
    assert open_frac > lunch_frac


def test_tod_typical_open_gt_flat_midday():
    avg = 1_440_000.0
    open_typ = typical_5min_volume(avg, use_tod=True, et_minute=9 * 60 + 35)
    lunch_typ = typical_5min_volume(avg, use_tod=True, et_minute=12 * 60 + 30)
    assert open_typ is not None and lunch_typ is not None
    assert open_typ > lunch_typ


def test_volume_in_window_from_cum_delta():
    sym = "TSSI"
    t0 = 1_000_000.0
    update_cum_volume(sym, 100_000, t0)
    update_cum_volume(sym, 120_000, t0 + 60)
    update_cum_volume(sym, 150_000, t0 + 300)
    assert volume_in_window(sym, window_sec=300, ts=t0 + 300) == 50_000
    # Flat path for deterministic ratio (TOD depends on wall clock ET)
    assert rvol_5min(50_000, 1_440_000, session_minutes=720, use_tod=False) == 5.0
    assert compute_symbol_rvol_5min(sym, 1_440_000, ts=t0 + 300) is not None
