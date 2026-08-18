"""Fake-feed integration tests for the HOD capture chain (capture audit).

Drives the REAL path end-to-end with a scripted IB feed:

    FakeIbkrFeed -> ibkr.ticks.subscribe/_on_ticker_update
        -> ibkr.scanner_l1.on_l1_quote
            -> ibkr_bridge.apply_l1_quote
                -> hod_momo.on_trade_update (real engine)

Asserts admission gating, day-high propagation, coalescing behavior, and
-- as an xfail -- the post-reconnect zombie-subscription gap documented in
docs/audits/2026-07-28-hod-scanner-capture-audit.md.
"""
from __future__ import annotations

import asyncio

import pytest

import hod_momo_active as active
import hod_momo_former as former
import hod_momo_high as high
import ibkr_bridge as bridge
from hod_momo_state import get_state
from ibkr import client as ib_client
from ibkr import scanner_l1, ticks
from runtime_state import get_runtime_state
from tests.conftest import reset_hod_engine_state
from tests.fakes.fake_ibkr_feed import FakeIbkrFeed

SYM = "FAKE"


def _squeeze11_only(state) -> None:
    for sid, cfg in state.configs.items():
        cfg.enabled = sid == 11
    cfg = state.configs[11]
    cfg.surge_pct = 5.0
    cfg.surge_window_min = 5
    cfg.requires_hod = True
    for field in (
        "min_price", "max_price", "min_float", "max_float", "min_volume",
        "min_rvol", "min_gap_pct", "min_change_pct", "proximity_52wk_pct",
    ):
        setattr(cfg, field, 0.0)
    state.master.hod_required = True
    state.master.surge_pct = 0.0
    state.master.min_rvol = 0.0
    state.master.premarket_min_rvol = 0.0
    state.master.afterhours_min_rvol = 0.0


@pytest.fixture()
def pipeline_env(monkeypatch):
    """Fresh engine + fake feed wired into the real L1 chain (full cleanup)."""
    reset_hod_engine_state()
    _squeeze11_only(get_state())
    ticks._subscribe_lock = None

    feed = FakeIbkrFeed()
    holder = {"feed": feed}
    monkeypatch.setattr(ib_client, "get_ib", lambda: holder["feed"])
    monkeypatch.setattr(former, "former_momo_priority_symbols", lambda: [])

    runtime = get_runtime_state()
    saved_gainers, saved_gainers_ts = runtime.gainer_cache, runtime.gainer_cache_ts
    runtime.gainer_cache = [
        {
            "symbol": SYM,
            "price": 10.0,
            "prev_close": 9.5,
            "change_pct": 5.26,
            "gap_percent": 3.0,
            "volume": 50_000,
        }
    ]

    active.clear_session_state()
    import hod_momo as hm

    high.apply_session_high(SYM, 10.0, source="bars")
    hm.update_ticker_snapshot(
        SYM, price=10.0, change_pct=5.26, float_shares=1_000_000, gap_pct=3.0,
    )
    bridge.refresh_hod_active_set()
    assert SYM in active.get_active_symbols()

    scanner_l1.configure(bridge.apply_l1_quote)
    try:
        yield holder
    finally:
        for sym in list(ticks.subscribed_symbols()):
            asyncio.run(ticks.unsubscribe(sym, ticks.OWNER_HOD))
            asyncio.run(ticks.unsubscribe(sym, ticks.OWNER_SCANNER))
        scanner_l1._apply_quote = None
        ticks.remove_quote_listener(scanner_l1.on_l1_quote)
        scanner_l1._pending.clear()
        scanner_l1._active_tab_tables.clear()
        runtime.gainer_cache, runtime.gainer_cache_ts = saved_gainers, saved_gainers_ts
        active.clear_session_state()
        ticks._subscribe_lock = None


def test_admitted_symbol_reaches_engine_and_fires(pipeline_env):
    async def _sub():
        assert await ticks.subscribe(SYM, ticks.OWNER_HOD) is True

    asyncio.run(_sub())
    feed = pipeline_env["feed"]
    feed.emit(SYM, last=10.0, high=10.0, volume=100_000)
    feed.emit(SYM, last=10.3, high=10.3, volume=140_000)
    feed.emit(SYM, last=10.65, high=10.65, volume=220_000)

    state = get_state()
    assert state.total_trades_seen == 3
    assert state.gate_counters.get("strategy_11_fired", 0) > 0
    assert state.pending_consolidation.get(SYM), "fired alert must queue for consolidation"


def test_non_admitted_symbol_never_reaches_engine(pipeline_env):
    async def _sub():
        assert await ticks.subscribe("GHOST", ticks.OWNER_HOD) is True

    asyncio.run(_sub())
    pipeline_env["feed"].emit("GHOST", last=50.0, high=50.0, volume=999_000)

    state = get_state()
    assert state.total_trades_seen == 0
    assert not state.pending_consolidation


def test_day_high_only_update_propagates_to_engine(pipeline_env):
    async def _sub():
        assert await ticks.subscribe(SYM, ticks.OWNER_HOD) is True

    asyncio.run(_sub())
    feed = pipeline_env["feed"]
    feed.emit(SYM, last=10.0, high=10.0, volume=100_000)
    feed.emit(SYM, last=10.0, high=10.4, volume=100_000)

    state = get_state()
    assert state.total_trades_seen == 2
    assert state.day_highs.get(SYM) == 10.4
    assert ticks.get_day_high(SYM) == 10.4


def test_coalescing_drops_display_prints_but_not_hod_evaluations(pipeline_env):
    async def _sub():
        assert await ticks.subscribe(SYM, ticks.OWNER_HOD) is True

    asyncio.run(_sub())
    feed = pipeline_env["feed"]
    feed.emit(SYM, last=10.1, high=10.1, volume=110_000)
    feed.emit(SYM, last=10.2, high=10.2, volume=120_000)
    feed.emit(SYM, last=10.3, high=10.3, volume=130_000)

    # scanner_l1's pending buffer keeps only the last print per symbol...
    assert scanner_l1._pending[SYM]["price"] == 10.3
    # ...but every print reached the engine (no HOD evaluation lost).
    assert get_state().total_trades_seen == 3


def test_reconnect_recreates_streams_on_new_connection(pipeline_env):
    async def _sub():
        assert await ticks.subscribe(SYM, ticks.OWNER_HOD) is True

    asyncio.run(_sub())
    assert pipeline_env["feed"].req_made == [SYM]

    # Gateway drops and reconnects: a brand-new connection object with no
    # server-side streams. client._on_session_ready clears zombie _subs
    # before reconcile re-issues reqMktData (G1 fix).
    pipeline_env["feed"] = FakeIbkrFeed()

    async def _ready_then_reconcile():
        cleared = await ticks.clear_all_subscriptions(reason="test ready bump")
        assert cleared == 1
        await ticks.set_owner_symbols(ticks.OWNER_HOD, [SYM])

    asyncio.run(_ready_then_reconcile())
    assert pipeline_env["feed"].req_made == [SYM]
