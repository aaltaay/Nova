"""Session-high truth — never invent HOD from first last print."""
from __future__ import annotations

import time
from collections import defaultdict

import hod_momo as hm
import hod_momo_high as high
from hod_momo_filters import fails_hod_gate
from hod_momo_models import StrategyConfig
from hod_momo_state import HodMomoState


def _reset() -> None:
    hm.replace_state(HodMomoState())
    hm.load_state()
    state = hm.get_state()
    state.today_alerts = []
    state.pending_consolidation = {}
    state.cooldown = {}
    state.session_highs = {}
    state.session_high_seeded = set()
    state.day_highs = {}
    state.session_high_source = {}
    state.session_high_raised_ts = {}
    state.price_buffer = {}
    state.ticker_snaps = {}
    state.gate_counters = defaultdict(int)
    state.startup_ts = time.monotonic() - 10_000


def test_bars_session_high_takes_max_h():
    assert high.bars_session_high([
        {"h": 10.0, "l": 9.0, "c": 9.5},
        {"h": 12.5, "l": 10.0, "c": 11.0},
        {"h": 11.0, "l": 10.5, "c": 10.8},
    ]) == 12.5


def test_fails_hod_gate_blocks_unseeded():
    cfg = StrategyConfig(strategy_id=11, name="Squeeze", color="#fff", requires_hod=True)
    reason = fails_hod_gate(
        price=10.0,
        session_high=0.0,
        cfg=cfg,
        master_hod_required=True,
        high_seeded=False,
    )
    assert reason == "hod:high_unseeded"


def test_cold_start_last_does_not_invent_hod(monkeypatch):
    """First L1 last must not become session high without tick6/bars seed."""
    _reset()
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 11
        if sid == 11:
            cfg.requires_hod = True
            cfg.min_rvol = 0.0
            cfg.surge_pct = 0.0
    state.master.hod_required = True
    state.master.surge_pct = 0.0
    state.master.min_rvol = 0.0

    sym = "COLD"
    hm.update_ticker_snapshot(
        sym, price=5.2, change_pct=10.0, rvol=5.0,
        float_shares=1_000_000, volume=100_000, rvol_source="test",
    )
    hm.on_trade_update(sym, 5.2, time.time(), volume=100_000)

    assert sym not in state.session_high_seeded
    assert state.session_highs.get(sym) in (None, 0.0) or not high.is_high_seeded(sym)
    assert not state.pending_consolidation


def test_seeded_high_retest_does_not_fire():
    """VCIG-class: bars/tick6 floor at HOD + print at same price is not a new HOD."""
    _reset()
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 11
        if sid == 11:
            cfg.requires_hod = True
            cfg.min_rvol = 0.0
            cfg.surge_pct = 0.0
    state.master.hod_required = True
    state.master.surge_pct = 0.0

    sym = "RETEST"
    high.apply_session_high(sym, 1.34, source="bars")
    hm.update_ticker_snapshot(
        sym, price=1.34, change_pct=46.0, rvol=5.0,
        float_shares=1_000_000, volume=100_000, rvol_source="test",
    )
    hm.on_trade_update(sym, 1.34, time.time(), volume=100_000, day_high=1.34)

    assert not state.pending_consolidation
    assert high.last_new_hod_age_sec(sym) is None


def test_observed_raise_above_seed_allows_hod_fire(monkeypatch):
    _reset()
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 11
        if sid == 11:
            cfg.requires_hod = True
            cfg.min_rvol = 0.0
            cfg.surge_pct = 0.0
    state.master.hod_required = True
    state.master.surge_pct = 0.0

    sym = "HOT"
    high.apply_session_high(sym, 10.0, source="bars")
    hm.update_ticker_snapshot(
        sym, price=10.05, change_pct=12.0, rvol=5.0,
        float_shares=1_000_000, volume=100_000, rvol_source="test",
    )
    hm.on_trade_update(sym, 10.05, time.time(), volume=100_000, day_high=10.0)

    pending = [
        a for bucket in state.pending_consolidation.values() for _, a in bucket
    ]
    assert any(a.strategy_id == 11 for a in pending)
    assert high.last_new_hod_age_sec(sym) is not None


def test_last_below_seeded_high_blocks():
    _reset()
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 11
        if sid == 11:
            cfg.requires_hod = True
            cfg.min_rvol = 0.0
            cfg.surge_pct = 0.0
    state.master.hod_required = True
    state.master.surge_pct = 0.0

    sym = "PULL"
    high.apply_session_high(sym, 12.0, source="tick6")
    hm.update_ticker_snapshot(
        sym, price=9.0, change_pct=5.0, rvol=5.0,
        float_shares=1_000_000, volume=100_000, rvol_source="test",
    )
    hm.on_trade_update(sym, 9.0, time.time(), volume=100_000, day_high=12.0)

    assert not state.pending_consolidation
    assert state.session_highs[sym] == 12.0
