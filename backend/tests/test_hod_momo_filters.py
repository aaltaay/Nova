"""Tests for HOD Momo pure filter/gate evaluation (no module-level state)."""
from __future__ import annotations

from collections import deque

from hod_momo_filters import (
    evaluate_strategy,
    fails_hod_gate,
    is_master_rvol_soft_block,
    passes_master_gate,
    passes_range,
    price_surge,
    strategy_ignores_master_rvol,
)
from hod_momo_models import MasterGateConfig, StrategyConfig, TickerSnap


def test_passes_range_disabled_when_both_zero():
    assert passes_range(None, 0.0, 0.0) == (True, "")


def test_passes_range_below_min():
    ok, reason = passes_range(1.0, 2.0, 0.0)
    assert not ok
    assert "below_min" in reason


def test_passes_range_above_max():
    ok, reason = passes_range(5.0, 0.0, 2.0)
    assert not ok
    assert "above_max" in reason


def test_price_surge_low_to_current():
    buf = deque([(0.0, 10.0), (60.0, 9.0), (120.0, 11.0)])
    surge = price_surge(buf, window_min=5, method="low_to_current")
    assert surge == (11.0 - 9.0) / 9.0 * 100.0


def test_price_surge_insufficient_data_returns_none():
    assert price_surge(deque([(0.0, 10.0)]), window_min=5, method="low_to_current") is None
    assert price_surge(None, window_min=5, method="low_to_current") is None


def test_evaluate_strategy_requests_fundamentals_when_float_unknown():
    cfg = StrategyConfig(strategy_id=1, name="test", color="#fff", min_float=1_000_000.0)
    snap = TickerSnap(price=1.0, float_shares=None)
    calls: list[bool] = []
    passed, reason = evaluate_strategy(cfg, snap, None, lambda: calls.append(True))
    assert not passed
    assert reason == "float:unknown"
    assert calls == [True]


def test_evaluate_strategy_passes_when_all_filters_clear():
    cfg = StrategyConfig(strategy_id=1, name="test", color="#fff")
    snap = TickerSnap(price=5.0, rvol=3.0, change_pct=10.0, gap_pct=5.0)
    passed, reason = evaluate_strategy(cfg, snap, None, lambda: None)
    assert passed
    assert reason == ""


def test_fails_hod_gate_blocks_below_session_high():
    cfg = StrategyConfig(strategy_id=1, name="test", color="#fff", requires_hod=True)
    reason = fails_hod_gate(
        price=9.0, session_high=10.0, cfg=cfg, master_hod_required=True,
        new_hod_age_sec=0.0,
    )
    assert reason is not None and "hod(" in reason


def test_fails_hod_gate_blocks_retest_without_new_hod():
    cfg = StrategyConfig(strategy_id=11, name="Squeeze", color="#fff", requires_hod=True)
    reason = fails_hod_gate(
        price=1.34, session_high=1.34, cfg=cfg, master_hod_required=True,
        high_seeded=True, new_hod_age_sec=None,
    )
    assert reason == "hod:not_new"


def test_fails_hod_gate_blocks_stale_new_hod():
    cfg = StrategyConfig(strategy_id=11, name="Squeeze", color="#fff", requires_hod=True)
    reason = fails_hod_gate(
        price=1.35, session_high=1.35, cfg=cfg, master_hod_required=True,
        high_seeded=True, new_hod_age_sec=120.0, new_hod_grace_sec=60.0,
    )
    assert reason is not None and "hod:stale_new" in reason


def test_fails_hod_gate_allows_fresh_new_hod():
    cfg = StrategyConfig(strategy_id=11, name="Squeeze", color="#fff", requires_hod=True)
    reason = fails_hod_gate(
        price=1.35, session_high=1.35, cfg=cfg, master_hod_required=True,
        high_seeded=True, new_hod_age_sec=5.0, new_hod_grace_sec=60.0,
    )
    assert reason is None


def test_fails_hod_gate_allows_when_requires_hod_false():
    cfg = StrategyConfig(strategy_id=12, name="Running Up", color="#fff", requires_hod=False)
    reason = fails_hod_gate(price=9.0, session_high=10.0, cfg=cfg, master_hod_required=True)
    assert reason is None


def test_passes_master_gate_ignores_rvol_master_retired():
    """Master RVOL retired — unknown/low RVOL no longer blocks at master."""
    master = MasterGateConfig(min_rvol=2.0)
    snap = TickerSnap(price=1.0, rvol=None)
    ok, reason = passes_master_gate(
        snap, master, eff_min_rvol=2.0, in_rvol_warmup_grace=False, surge_buffer=None,
    )
    assert ok
    assert reason == ""


def test_passes_master_gate_blocks_missing_price():
    master = MasterGateConfig()
    snap = TickerSnap(price=None)
    ok, reason = passes_master_gate(
        snap, master, eff_min_rvol=0.0, in_rvol_warmup_grace=False, surge_buffer=None,
    )
    assert not ok
    assert reason == "master_data:no_price"


def test_master_rvol_soft_bypass_retired():
    assert strategy_ignores_master_rvol(
        StrategyConfig(strategy_id=11, name="Squeeze", color="#fff", min_rvol=0.0, surge_pct=5.0, surge_window_min=5)
    ) is False
    assert is_master_rvol_soft_block(False, "master_rvol(0.32<2.0)") is False
