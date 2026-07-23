"""Tests for HOD Momo alert engine gates (Ross-style master + strategy fire)."""
from __future__ import annotations

import time
from collections import defaultdict

import hod_momo as hm
import hod_momo_high as high
import hod_momo_market as market
from hod_momo_state import HodMomoState


def _reset_engine(monkeypatch) -> None:
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
    state.price_buffer = {}
    state.ticker_snaps = {}
    state.gate_counters = defaultdict(int)
    state.total_trades_seen = 0
    state.blocklist = set()
    state.startup_ts = time.monotonic() - 10_000


def test_on_trade_update_fires_when_master_and_strategy_pass(monkeypatch):
    _reset_engine(monkeypatch)

    # Keep only strategy #11 (squeeze +5%/5m) — no float/52wk requirements.
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 11

    state.master.hod_required = True
    state.master.surge_pct = 0.0  # strategies own surge (Warrior parity)
    state.master.surge_window_min = 5
    state.master.min_rvol = 0.0

    sym = "TEST"
    now = time.time()
    # Seed session high so first last does not invent HOD from cold start.
    high.apply_session_high(sym, 10.0, source="bars")
    hm.update_ticker_snapshot(
        sym,
        price=10.6,
        change_pct=12.0,
        rvol=3.5,
        float_shares=5_000_000,
        gap_pct=8.0,
        volume=100_000,
        fifty_two_week_high=20.0,
        rvol_source="test",
    )
    # Rising buffer → surge clears; final print is a new HOD.
    for i, px in enumerate([10.0, 10.1, 10.2, 10.4, 10.6]):
        hm.on_trade_update(sym, px, now - (5 - i) * 30.0, volume=100_000, day_high=10.65)
    hm.on_trade_update(sym, 10.65, now, volume=110_000, day_high=10.65)

    assert state.total_trades_seen >= 6
    pending_alerts = [
        alert
        for bucket in state.pending_consolidation.values()
        for _emit_at, alert in bucket
    ]
    assert pending_alerts, "expected at least one pending consolidated alert"
    assert any(a.ticker == sym and a.strategy_id == 11 for a in pending_alerts)


def test_on_trade_update_blocked_by_strategy_rvol(monkeypatch):
    """Master RVOL retired — Float strategies still hard-block on min_rvol."""
    _reset_engine(monkeypatch)
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid not in (10, 11)
        if cfg.enabled:
            cfg.min_rvol = max(float(cfg.min_rvol or 0.0), 2.0)

    sym = "SLOW"
    now = time.time()
    high.apply_session_high(sym, 5.0, source="bars")
    hm.update_ticker_snapshot(
        sym,
        price=5.0,
        change_pct=15.0,
        rvol=0.5,  # below strategy min_rvol
        float_shares=1_000_000,
        gap_pct=10.0,
        volume=50_000,
        fifty_two_week_high=10.0,
        rvol_source="test",
    )
    for i, px in enumerate([4.5, 4.7, 4.9, 5.0]):
        hm.on_trade_update(sym, px, now - (4 - i) * 20.0, volume=50_000, day_high=5.0)

    assert state.total_trades_seen >= 4
    assert not state.pending_consolidation


def test_squeeze_fires_with_low_pace_rvol(monkeypatch):
    """Warrior Squeeze can fire below 2× pace RVOL (TRT live evidence)."""
    _reset_engine(monkeypatch)
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid in (10, 11)
        if sid in (10, 11):
            cfg.min_rvol = 0.0
            cfg.requires_hod = False  # isolate surge path

    sym = "TRTX"
    now = time.time()
    hm.update_ticker_snapshot(
        sym,
        price=11.0,
        change_pct=5.0,
        rvol=0.32,
        float_shares=6_000_000,
        volume=400_000,
        rvol_source="ibkr_pace",
    )
    # ~10% surge over a few minutes → Squeeze 5% / 10%
    for i, px in enumerate([10.0, 10.2, 10.5, 10.8, 11.0]):
        hm.on_trade_update(sym, px, now - (4 - i) * 30.0, volume=400_000)

    pending_alerts = [
        alert
        for bucket in state.pending_consolidation.values()
        for _emit_at, alert in bucket
    ]
    assert pending_alerts, "Squeeze should queue with pace RVOL 0.32 (master RVOL retired)"
    assert any(a.ticker == sym and a.strategy_id in (10, 11) for a in pending_alerts)


def test_former_momo_empty_list_never_fires(monkeypatch):
    """Warrior Former Momo only tags known runners — empty list != all symbols."""
    _reset_engine(monkeypatch)
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 1
        if sid == 1:
            cfg.former_momo_list = []
            cfg.min_rvol = 2.0

    state.master.hod_required = True
    state.master.surge_pct = 0.0
    state.master.min_rvol = 2.0

    sym = "CNEY"
    now = time.time()
    hm.update_ticker_snapshot(
        sym, price=0.65, change_pct=25.0, rvol=27.0,
        float_shares=5_000_000, gap_pct=29.0, volume=34_000_000,
        fifty_two_week_high=2.0, rvol_source="test",
    )
    for i, px in enumerate([0.60, 0.62, 0.64, 0.65]):
        hm.on_trade_update(sym, px, now - (4 - i) * 20.0, volume=34_000_000)

    assert not state.pending_consolidation


def test_former_momo_fires_when_on_list(monkeypatch):
    _reset_engine(monkeypatch)
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 1
        if sid == 1:
            cfg.former_momo_list = ["CNEY"]
            cfg.min_rvol = 2.0

    state.master.hod_required = True
    state.master.surge_pct = 0.0
    state.master.min_rvol = 2.0

    sym = "CNEY"
    now = time.time()
    # Floor below final print so the last tick is a true new HOD (not a retest).
    high.apply_session_high(sym, 0.64, source="bars")
    hm.update_ticker_snapshot(
        sym, price=0.65, change_pct=25.0, rvol=27.0,
        float_shares=5_000_000, gap_pct=29.0, volume=34_000_000,
        fifty_two_week_high=2.0, rvol_source="test",
    )
    for i, px in enumerate([0.60, 0.62, 0.64, 0.65]):
        hm.on_trade_update(sym, px, now - (4 - i) * 20.0, volume=34_000_000, day_high=0.64)

    pending = [
        a for bucket in state.pending_consolidation.values() for _, a in bucket
    ]
    assert any(a.strategy_id == 1 and a.ticker == sym for a in pending)


def test_running_up_fires_without_hod(monkeypatch):
    """Warrior Running Up alerts on momentum without requiring a new HOD."""
    _reset_engine(monkeypatch)
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 12
        if sid == 12:
            cfg.requires_hod = False
            cfg.surge_pct = 5.0
            cfg.surge_window_min = 5
            cfg.min_rvol = 2.0

    state.master.hod_required = True
    state.master.surge_pct = 0.0
    state.master.min_rvol = 2.0

    sym = "VEEE"
    now = time.time()
    # Establish a prior HOD well above current path
    state.session_highs[sym] = 50.0
    hm.update_ticker_snapshot(
        sym, price=43.0, change_pct=40.0, rvol=8.0,
        float_shares=5_000_000, gap_pct=-10.0, volume=20_000_000,
        fifty_two_week_high=60.0, rvol_source="test", avg_volume=2_000_000,
    )
    # Squeeze up but stay below prior HOD
    for i, px in enumerate([40.0, 41.0, 42.0, 43.0]):
        hm.on_trade_update(sym, px, now - (4 - i) * 30.0, volume=20_000_000 + i * 10_000)

    pending = [
        a for bucket in state.pending_consolidation.values() for _, a in bucket
    ]
    assert any(a.strategy_id == 12 and a.ticker == sym for a in pending)
    # Classic HOD strategies must still be blocked below HOD
    assert all(a.strategy_id == 12 for a in pending)


def test_medium_float_fires_without_master_surge(monkeypatch):
    """Warrior Medium Float Med Rel Vol needs HOD+float+RVOL, not a global 3% surge."""
    _reset_engine(monkeypatch)
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 9

    state.master.hod_required = True
    state.master.surge_pct = 0.0
    state.master.min_rvol = 2.0

    sym = "FRE"
    now = time.time()
    high.apply_session_high(sym, 22.60, source="bars")
    hm.update_ticker_snapshot(
        sym, price=22.65, change_pct=8.0, rvol=3.2,
        float_shares=25_000_000, gap_pct=2.0, volume=5_000_000,
        fifty_two_week_high=40.0, rvol_source="test",
    )
    for i, px in enumerate([22.50, 22.55, 22.60, 22.65]):
        hm.on_trade_update(sym, px, now - (4 - i) * 60.0, volume=5_000_000, day_high=22.60)

    pending = [
        a for bucket in state.pending_consolidation.values() for _, a in bucket
    ]
    assert any(a.strategy_id == 9 and a.ticker == sym for a in pending)


def test_same_ticker_shares_consolidation_emit_deadline(monkeypatch):
    """Warrior batches same-ticker fires into one window (not per-alert deadlines)."""
    _reset_engine(monkeypatch)
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 11

    state.master.hod_required = True
    state.master.surge_pct = 0.0
    state.master.min_rvol = 2.0
    state.master.cooldown_sec = 0.0
    state.master.consolidation_sec = 10.0

    sym = "TRT"
    now = time.time()
    high.apply_session_high(sym, 11.0, source="bars")
    hm.update_ticker_snapshot(
        sym, price=12.0, change_pct=20.0, rvol=5.0,
        float_shares=5_000_000, gap_pct=2.0, volume=1_000_000,
        fifty_two_week_high=20.0, rvol_source="test", avg_volume=100_000,
    )
    for i, px in enumerate([11.0, 11.3, 11.6, 12.0]):
        # day_high tracks the print (true new HOD path) — not a future high.
        hm.on_trade_update(sym, px, now - (4 - i) * 20.0, volume=1_000_000, day_high=px)
    assert sym in state.pending_consolidation
    first_deadline = state.pending_consolidation[sym][0][0]

    # Second burst within the open window — must share the same emit_after.
    hm.on_trade_update(sym, 12.2, now + 1.0, volume=1_100_000, day_high=12.2)
    bucket = state.pending_consolidation[sym]
    assert len(bucket) >= 2
    assert all(et == first_deadline for et, _ in bucket)


def test_effective_min_rvol_uses_afterhours_setting(monkeypatch):
    state = hm.get_state()
    state.master.min_rvol = 5.0
    state.master.premarket_min_rvol = 2.0
    state.master.afterhours_min_rvol = 1.5
    monkeypatch.setattr(market, "in_afterhours_et", lambda: True)
    monkeypatch.setattr(market, "in_premarket_et", lambda: False)
    assert hm._effective_min_rvol() == 1.5
    monkeypatch.setattr(market, "in_afterhours_et", lambda: False)
    monkeypatch.setattr(market, "in_premarket_et", lambda: True)
    assert hm._effective_min_rvol() == 2.0
    monkeypatch.setattr(market, "in_premarket_et", lambda: False)
    assert hm._effective_min_rvol() == 5.0


def test_reset_config_resets_strategy_12_running_up(monkeypatch):
    """Regression: reset_config() used a hardcoded range(1, 12), excluding strategy
    12 (Running Up) from HOD_MOMO_STRATEGY_ID_MAX=12's inclusive range, so it could
    never be reset individually via the config API."""
    _reset_engine(monkeypatch)
    state = hm.get_state()
    state.configs[12].enabled = False
    state.configs[12].min_rvol = 99.0
    state.configs[12].surge_pct = 0.0

    result = hm.reset_config(12)

    assert result is not None, "reset_config(12) must not be rejected as out-of-range"
    default = hm._build_default_config(12)
    assert result == hm._config_to_dict(default)
    assert state.configs[12].enabled == default.enabled
    assert state.configs[12].min_rvol == default.min_rvol
    assert state.configs[12].surge_pct == default.surge_pct


def test_reset_config_still_rejects_out_of_range_ids(monkeypatch):
    _reset_engine(monkeypatch)
    assert hm.reset_config(0) is None
    assert hm.reset_config(13) is None


def test_would_fire_now_queues_symbol_being_debugged_not_stale_active_symbol(monkeypatch):
    """Regression: _would_fire_now() (backs GET /api/hod-momo/debug/symbol/{sym})
    never set _active_symbol_name, so mark_needs_fundamentals() picked up whatever
    on_trade_update last left there instead of the symbol actually being debugged."""
    _reset_engine(monkeypatch)
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 9  # Medium Float strategy requires min_float
    state.master.min_rvol = 0.0
    state.master.premarket_min_rvol = 0.0
    state.master.afterhours_min_rvol = 0.0
    state.master.surge_pct = 0.0

    # Simulate a stale "active symbol" left over from a previous live trade —
    # this is exactly the state on_trade_update leaves between calls.
    from collections import deque as _deque
    state.active_symbol_name = "STALE"
    state.fundamentals_queue = _deque()
    state.fundamentals_queued = set()

    debug_sym = "DEBUGME"
    high.apply_session_high(debug_sym, 24.90, source="bars")
    # Fresh new-HOD window so requires_hod strategies reach the float gate.
    high.apply_session_high(
        debug_sym, 25.0, source="observed", open_alert_window=True,
    )
    hm.update_ticker_snapshot(debug_sym, price=25.0)  # float_shares left None → "float:unknown"

    hm._would_fire_now(debug_sym)

    assert list(state.fundamentals_queue) == [debug_sym]
    assert "STALE" not in state.fundamentals_queue


def test_on_trade_update_recomputes_ibkr_pace_rvol(monkeypatch):
    """IBKR cum volume should refresh pace RVOL (not leave stale yfinance ~1.3x)."""
    _reset_engine(monkeypatch)
    state = hm.get_state()
    for _sid, cfg in state.configs.items():
        cfg.enabled = False
    state.master.min_rvol = 2.0
    state.master.surge_pct = 0.0
    monkeypatch.setattr(market, "in_afterhours_et", lambda: True)
    monkeypatch.setattr(market, "in_premarket_et", lambda: False)

    import market as m
    monkeypatch.setattr(m, "volume_day_elapsed_fraction", lambda now=None: 1.0)

    sym = "XCUR"
    hm.update_ticker_snapshot(
        sym, price=2.38, rvol=1.34, volume=27_000,
        rvol_source="yfinance_pace", avg_volume=100_000.0, change_pct=44.0,
    )
    hm.on_trade_update(sym, 2.55, time.time(), volume=4_170_000)
    snap = state.ticker_snaps[sym]
    assert snap.rvol == 41.7
    assert snap.rvol_source == "ibkr_pace"


def _fire_squeeze_setup(monkeypatch) -> tuple[object, str, float]:
    """Shared master+strategy setup that would fire strategy #11 on a new HOD."""
    _reset_engine(monkeypatch)
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 11
    state.master.hod_required = True
    state.master.surge_pct = 0.0
    state.master.surge_window_min = 5
    state.master.min_rvol = 0.0

    sym = "INTG"
    now = time.time()
    high.apply_session_high(sym, 10.0, source="bars")
    hm.update_ticker_snapshot(
        sym,
        price=10.6,
        change_pct=12.0,
        rvol=3.5,
        float_shares=5_000_000,
        gap_pct=8.0,
        volume=100_000,
        fifty_two_week_high=20.0,
        rvol_source="test",
    )
    for i, px in enumerate([10.0, 10.1, 10.2, 10.4, 10.6]):
        hm.on_trade_update(sym, px, now - (5 - i) * 30.0, volume=100_000, day_high=10.65)
    return state, sym, now


def test_integrity_fail_suppress_blocks_on_hod_scope_fail(monkeypatch):
    """REQ-HOD-004: a genuine hod-scope integrity fail still suppresses fires."""
    state, sym, now = _fire_squeeze_setup(monkeypatch)
    monkeypatch.setattr("integrity_live.hod_integrity_is_failing", lambda: True)

    hm.on_trade_update(sym, 10.65, now, volume=110_000, day_high=10.65)

    assert not state.pending_consolidation.get(sym)
    assert state.gate_counters["integrity_fail_suppress"] >= 1


def test_integrity_fail_suppress_ignores_scanner_only_fail(monkeypatch):
    """REQ-HOD-004: an unrelated scanner-tab failure must NOT suppress HOD fires
    once suppression is scoped to hod_integrity_is_failing() only."""
    state, sym, now = _fire_squeeze_setup(monkeypatch)
    # Simulate: scanner scope failing, hod scope healthy — scoped check returns False.
    monkeypatch.setattr("integrity_live.hod_integrity_is_failing", lambda: False)

    hm.on_trade_update(sym, 10.65, now, volume=110_000, day_high=10.65)

    pending_alerts = [
        alert
        for bucket in state.pending_consolidation.values()
        for _emit_at, alert in bucket
    ]
    assert any(a.ticker == sym and a.strategy_id == 11 for a in pending_alerts)
    assert state.gate_counters["integrity_fail_suppress"] == 0
