"""Approaching HOD (strategy 13) — dip-reset re-arm at 0.5% below session high."""
from __future__ import annotations

import time

import hod_momo as hm
import hod_momo_approach as approach
import hod_momo_high as high
from constants import (
    HOD_MOMO_APPROACH_STRATEGY_ID,
    HOD_MOMO_HOD_EPSILON_ABS,
    HOD_MOMO_HOD_EPSILON_PCT,
    HOD_MOMO_REAPPROACH_RESET_PCT,
)
from tests.conftest import reset_hod_engine_state


APPROACH_ID = HOD_MOMO_APPROACH_STRATEGY_ID


def _reset() -> None:
    reset_hod_engine_state()


def _enable_only_approach() -> None:
    state = hm.get_state()
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == APPROACH_ID
    state.master.min_rvol = 0.0
    state.master.surge_pct = 0.0
    state.master.hod_required = True


def _seed_stale_high(sym: str, hod: float, *, age_sec: float = 120.0) -> None:
    """Seed a session high whose raise timestamp is outside the 60s grace."""
    high.apply_session_high(sym, hod, source="bars")
    state = hm.get_state()
    # bars seed does not set raised_ts; force a stale raised_ts so grace is expired.
    state.session_high_raised_ts[sym] = time.time() - age_sec


def _pending_approach(sym: str) -> list:
    state = hm.get_state()
    return [
        alert
        for bucket in state.pending_consolidation.values()
        for _emit, alert in bucket
        if alert.ticker == sym and alert.strategy_id == APPROACH_ID
    ]


def test_approach_fires_on_retouch_after_dip():
    """A1: dip below 0.5%, then re-touch → exactly one Approaching HOD alert."""
    _reset()
    _enable_only_approach()
    sym = "AMIX"
    hod = 5.44
    _seed_stale_high(sym, hod)
    hm.update_ticker_snapshot(
        sym, price=5.30, change_pct=10.0, rvol=5.0, float_shares=500_000,
        gap_pct=5.0, volume=1_000_000, rvol_source="test",
    )
    now = time.time()
    # Pullback arms the latch.
    hm.on_trade_update(sym, 5.30, now - 2.0, volume=1_000_000)
    assert approach.is_armed(sym)
    # Re-touch within epsilon of HOD.
    hm.on_trade_update(sym, 5.435, now, volume=1_100_000)
    pending = _pending_approach(sym)
    assert len(pending) == 1
    assert pending[0].strategy_name == "Approaching HOD"
    assert not approach.is_armed(sym)


def test_approach_no_fire_while_hovering():
    """A2: after one fire, hovering at the high must not re-fire."""
    _reset()
    _enable_only_approach()
    sym = "AMIX"
    hod = 5.44
    _seed_stale_high(sym, hod)
    hm.update_ticker_snapshot(
        sym, price=5.30, change_pct=10.0, rvol=5.0, float_shares=500_000,
        gap_pct=5.0, volume=1_000_000, rvol_source="test",
    )
    now = time.time()
    hm.on_trade_update(sym, 5.30, now - 5.0, volume=1_000_000)
    hm.on_trade_update(sym, 5.44, now - 4.0, volume=1_100_000)
    assert len(_pending_approach(sym)) == 1
    # Hover — no 0.5% dip.
    for i in range(20):
        px = 5.435 + (i % 2) * 0.005
        hm.on_trade_update(sym, px, now - 3.0 + i * 0.05, volume=1_200_000 + i)
    assert len(_pending_approach(sym)) == 1


def test_approach_rearms_only_after_half_percent_dip():
    """A3: 0.37% dip does not re-arm; 0.5%+ dip does."""
    _reset()
    _enable_only_approach()
    sym = "AMIX"
    hod = 5.44
    _seed_stale_high(sym, hod)
    hm.update_ticker_snapshot(
        sym, price=5.30, change_pct=10.0, rvol=5.0, float_shares=500_000,
        gap_pct=5.0, volume=1_000_000, rvol_source="test",
    )
    now = time.time()
    hm.on_trade_update(sym, 5.30, now - 10.0, volume=1_000_000)
    hm.on_trade_update(sym, 5.44, now - 9.0, volume=1_100_000)
    assert len(_pending_approach(sym)) == 1
    assert not approach.is_armed(sym)

    # ~0.37% below 5.44 → 5.42; must NOT re-arm.
    shallow = hod * (1.0 - 0.0037)
    assert shallow > approach.reset_threshold(hod)
    hm.on_trade_update(sym, round(shallow, 4), now - 8.0, volume=1_200_000)
    assert not approach.is_armed(sym)
    hm.on_trade_update(sym, 5.44, now - 7.0, volume=1_300_000)
    assert len(_pending_approach(sym)) == 1

    # Full 0.5% dip → re-arm, then re-touch fires once more.
    deep = approach.reset_threshold(hod) - 0.01
    hm.on_trade_update(sym, deep, now - 6.0, volume=1_400_000)
    assert approach.is_armed(sym)
    hm.on_trade_update(sym, 5.44, now - 5.0, volume=1_500_000)
    assert len(_pending_approach(sym)) == 2


def test_approach_epsilon_boundary():
    """A4: just outside epsilon does not fire; inside does."""
    _reset()
    _enable_only_approach()
    sym = "EDGE"
    hod = 10.0
    _seed_stale_high(sym, hod)
    hm.update_ticker_snapshot(
        sym, price=9.90, change_pct=5.0, rvol=5.0, float_shares=1_000_000,
        gap_pct=3.0, volume=500_000, rvol_source="test",
    )
    now = time.time()
    hm.on_trade_update(sym, 9.90, now - 3.0, volume=500_000)  # arm
    eps = max(HOD_MOMO_HOD_EPSILON_ABS, hod * HOD_MOMO_HOD_EPSILON_PCT)
    # Outside: price + eps < hod
    outside = hod - eps - 0.001
    hm.on_trade_update(sym, outside, now - 2.0, volume=510_000)
    assert _pending_approach(sym) == []
    # Inside
    inside = hod - eps + 0.001
    hm.on_trade_update(sym, inside, now - 1.0, volume=520_000)
    assert len(_pending_approach(sym)) == 1


def test_approach_unseeded_never_fires():
    """A5: unseeded high never fires."""
    _reset()
    _enable_only_approach()
    sym = "COLD"
    state = hm.get_state()
    # No apply_session_high — unseeded.
    assert sym not in state.session_high_seeded
    hm.update_ticker_snapshot(
        sym, price=5.0, change_pct=5.0, rvol=5.0, float_shares=1_000_000,
        gap_pct=3.0, volume=100_000, rvol_source="test",
    )
    now = time.time()
    hm.on_trade_update(sym, 4.90, now - 1.0, volume=100_000)
    hm.on_trade_update(sym, 5.0, now, volume=110_000)
    assert _pending_approach(sym) == []


def test_approach_does_not_fire_on_fresh_new_hod():
    """A6: a genuine new HOD belongs to strategy 10/11, not approach."""
    _reset()
    _enable_only_approach()
    sym = "BRK"
    high.apply_session_high(sym, 10.0, source="bars")
    hm.update_ticker_snapshot(
        sym, price=10.0, change_pct=5.0, rvol=5.0, float_shares=1_000_000,
        gap_pct=3.0, volume=100_000, rvol_source="test",
    )
    now = time.time()
    # Dip to arm, then break to a NEW high (raises session high + fresh grace).
    hm.on_trade_update(sym, 9.90, now - 2.0, volume=100_000)
    assert approach.is_armed(sym)
    hm.on_trade_update(sym, 10.05, now, volume=120_000)  # new HOD
    # Approach must not fire on the breakout tick.
    assert _pending_approach(sym) == []


def test_approach_consolidation_batches_two_retouches():
    """A7: two distinct approach re-touches within consolidation window → count 2."""
    _reset()
    _enable_only_approach()
    sym = "BATCH"
    hod = 5.0
    _seed_stale_high(sym, hod)
    hm.update_ticker_snapshot(
        sym, price=4.90, change_pct=5.0, rvol=5.0, float_shares=1_000_000,
        gap_pct=3.0, volume=100_000, rvol_source="test",
    )
    now = time.time()
    hm.on_trade_update(sym, 4.90, now - 8.0, volume=100_000)
    hm.on_trade_update(sym, 5.0, now - 7.0, volume=110_000)
    hm.on_trade_update(sym, 4.90, now - 6.0, volume=120_000)  # re-arm
    hm.on_trade_update(sym, 5.0, now - 5.0, volume=130_000)
    pending = _pending_approach(sym)
    assert len(pending) == 2
    # Collapse same-strategy burst the same way flush_consolidated_loop does.
    by_strategy: dict[int, list] = {}
    for alert in pending:
        by_strategy.setdefault(int(alert.strategy_id), []).append(alert)
    group = by_strategy[APPROACH_ID]
    primary = group[-1]
    primary.consolidation_count = len(group)
    assert primary.consolidation_count == 2


def test_approach_percent_scales_across_price_levels():
    """A8: 0.5% reset scales on $0.50 and $6.00 names."""
    assert abs(approach.reset_threshold(0.50) - 0.50 * (1 - HOD_MOMO_REAPPROACH_RESET_PCT)) < 1e-9
    assert abs(approach.reset_threshold(6.00) - 6.00 * (1 - HOD_MOMO_REAPPROACH_RESET_PCT)) < 1e-9
    # $0.50 stock: arm at/below 0.4975
    _reset()
    assert not approach.is_armed("PENNY")
    approach.update_latch("PENNY", 0.4975, 0.50, high_seeded=True)
    assert approach.is_armed("PENNY")
    _reset()
    approach.update_latch("SIX", 5.97, 6.00, high_seeded=True)
    assert approach.is_armed("SIX")
    # Just above threshold on $6 — not armed.
    _reset()
    approach.update_latch("SIX", 5.98, 6.00, high_seeded=True)
    assert not approach.is_armed("SIX")


def test_approach_latch_in_memory_only_resets_on_replace_state():
    """A9: latch is in-memory; replace_state clears it (restart semantics)."""
    _reset()
    approach.update_latch("AMIX", 5.40, 5.44, high_seeded=True)
    assert approach.is_armed("AMIX")
    hm.replace_state()
    # Fresh state owner — latch gone (not persisted).
    assert not approach.is_armed("AMIX")


def test_approach_block_reason_pure():
    """Pure-unit coverage for approach_block_reason edges."""
    assert approach.approach_block_reason(
        5.44, 5.44, high_seeded=False, armed=True, new_hod_age_sec=120.0,
    ) == "approach:high_unseeded"
    assert approach.approach_block_reason(
        5.44, 5.44, high_seeded=True, armed=True, new_hod_age_sec=10.0,
    ) == "approach:fresh_new_hod"
    assert approach.approach_block_reason(
        5.30, 5.44, high_seeded=True, armed=True, new_hod_age_sec=120.0,
    ).startswith("approach:below_hod")
    assert approach.approach_block_reason(
        5.44, 5.44, high_seeded=True, armed=False, new_hod_age_sec=120.0,
    ) == "approach:not_armed"
    assert approach.approach_block_reason(
        5.44, 5.44, high_seeded=True, armed=True, new_hod_age_sec=120.0,
    ) is None
