"""Regression tests for ibkr/reprice.py.

See PROBLEM_LOG 2026-07-14, "Detail panel updates every ~30s instead of
every tick": the ticker-detail panel's price refresh must never be blocked
by (or depend on) the much larger, much slower gapper/gainer/loser table
batch refresh. These two concerns are intentionally separate functions/
tasks — this test locks that separation in so a future edit can't
accidentally re-merge them.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ibkr import reprice  # noqa: E402


def test_reprice_detail_symbols_noop_when_no_symbols():
    """No open detail WS -> no IBKR call at all (cheap no-op every tick)."""
    calls = []

    def run_ibkr(_coro):
        calls.append(_coro)
        return {}

    reprice.reprice_detail_symbols([], run_ibkr, lambda *a, **k: None, lambda s: None)

    assert calls == []


def test_reprice_detail_symbols_falls_back_to_cache_row_when_quote_empty():
    """If snapshot_quotes() comes back empty (pacing/timeout), still broadcast
    using the last known cache price instead of silently dropping the tick —
    this is the exact failure mode that made the panel look frozen."""
    broadcasts = []

    def schedule_broadcast(sym, price, size, ts, volume, prev_close):
        broadcasts.append((sym, price, volume, prev_close))

    def run_ibkr(coro):
        if asyncio.iscoroutine(coro):
            coro.close()
        return {}  # simulate an empty/failed snapshot_quotes() response

    def find_cache_row(sym):
        return {"symbol": sym, "current_price": 4.45, "volume": 12345, "previous_close": 2.96}

    reprice.reprice_detail_symbols(["SHPH"], run_ibkr, schedule_broadcast, find_cache_row)

    assert broadcasts == [("SHPH", 4.45, 12345, 2.96)]


def test_reprice_detail_symbols_skips_symbol_with_no_price_anywhere():
    def run_ibkr(coro):
        if asyncio.iscoroutine(coro):
            coro.close()
        return {}

    reprice.reprice_detail_symbols(["ZZZZ"], run_ibkr, lambda *a: None, lambda s: None)


def test_reprice_detail_symbols_skips_snapshot_when_stream_is_fresh():
    """A symbol already served by ibkr/ticks.py's reqMktData stream must not
    also fire a reqTickersAsync snapshot — that was pure IBKR-request-queue
    contention with table_reprice_loop now that streaming ticks own the
    broadcast for that symbol."""
    calls = []
    broadcasts = []

    def run_ibkr(coro):
        calls.append(coro)
        if asyncio.iscoroutine(coro):
            coro.close()
        return {}

    def schedule_broadcast(*args):
        broadcasts.append(args)

    reprice.reprice_detail_symbols(
        ["FRESH"], run_ibkr, schedule_broadcast, lambda s: None,
        is_stream_fresh=lambda s: True,
    )

    assert calls == []
    assert broadcasts == []


def test_reprice_detail_symbols_backstops_only_non_fresh_symbols():
    """Mixed batch: the fresh-streaming symbol is excluded from the snapshot
    request entirely; the stale/unsubscribed one still gets the full
    snapshot-backstop treatment."""
    snapshotted = []

    def run_ibkr(coro):
        if asyncio.iscoroutine(coro):
            coro.close()
        return {"STALE": {"price": 1.23, "prev_close": 1.0, "volume": 500, "open": 1.1}}

    def schedule_broadcast(sym, price, size, ts, volume, prev_close):
        snapshotted.append(sym)

    def is_fresh(sym):
        return sym == "FRESH"

    reprice.reprice_detail_symbols(
        ["FRESH", "STALE"], run_ibkr, schedule_broadcast, lambda s: None,
        is_stream_fresh=is_fresh,
    )

    assert snapshotted == ["STALE"]


def test_reprice_detail_symbols_defaults_to_full_backstop_without_freshness_fn():
    """Backward compatible: omitting is_stream_fresh keeps prior behavior of
    snapshotting every open detail symbol every tick."""
    broadcasts = []

    def run_ibkr(coro):
        if asyncio.iscoroutine(coro):
            coro.close()
        return {"ABC": {"price": 2.0, "prev_close": 1.0, "volume": 10, "open": 1.5}}

    def schedule_broadcast(sym, *rest):
        broadcasts.append(sym)

    reprice.reprice_detail_symbols(["ABC"], run_ibkr, schedule_broadcast, lambda s: None)

    assert broadcasts == ["ABC"]


def test_reprice_table_caches_returns_none_when_all_caches_empty():
    assert reprice.reprice_table_caches([], [], [], lambda coro: {}) is None


def test_reprice_table_caches_returns_none_when_quotes_empty():
    def run_ibkr(coro):
        if asyncio.iscoroutine(coro):
            coro.close()
        return {}

    gapper = [{"symbol": "ABC", "price": 1.0, "prev_close": 0.5}]
    assert reprice.reprice_table_caches(gapper, [], [], run_ibkr) is None


def test_reprice_table_caches_returns_patch_rows():
    def run_ibkr(coro):
        if asyncio.iscoroutine(coro):
            coro.close()
        return {"ABC": {"price": 2.0, "prev_close": 1.0, "volume": 100, "open": 1.5}}

    gapper = [{
        "symbol": "ABC", "price": 1.0, "prev_close": 1.0,
        "change_pct": 0.0, "change_abs": 0.0, "volume": 10, "gap_percent": 0.0,
    }]
    out = reprice.reprice_table_caches(gapper, [], [], run_ibkr)
    assert out is not None
    gappers, gainers, losers, ts, rows = out
    assert gappers[0]["price"] == 2.0
    assert rows[0]["symbol"] == "ABC"
    assert rows[0]["price"] == 2.0
    assert isinstance(ts, float)


def test_table_reprice_loop_emits_stale_when_busy():
    """Skip-if-busy must tell the UI prices are not refreshing — never hide it."""
    from constants import IBKR_TABLE_REPRICE_INTERVAL_SEC

    pushes = []

    async def push(payload):
        pushes.append(payload)

    reprice._table_reprice_busy = True

    async def run_one():
        task = asyncio.create_task(reprice.table_reprice_loop(
            lambda: "ibkr",
            lambda: ["AAPL"],
            lambda quotes: None,
            push,
        ))
        await asyncio.sleep(IBKR_TABLE_REPRICE_INTERVAL_SEC + 0.25)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run_one())
    reprice._table_reprice_busy = False
    assert any(p.get("type") == "price_heartbeat" and p.get("stale") for p in pushes)


def test_table_reprice_loop_pushes_one_chunk_per_tick(monkeypatch):
    """Progressive chunks: each 1Hz tick snapshots one batch and pushes immediately."""
    from constants import IBKR_TABLE_REPRICE_CHUNK_SIZE, IBKR_TABLE_REPRICE_INTERVAL_SEC

    symbols = [f"S{i:02d}" for i in range(IBKR_TABLE_REPRICE_CHUNK_SIZE * 2 + 3)]
    snapped: list[list[str]] = []
    pushes: list[dict] = []

    async def fake_snapshot(syms, *, timeout_sec=4.0):
        snapped.append(list(syms))
        return {s: {"price": 1.0, "prev_close": 1.0, "volume": 1, "open": 1.0} for s in syms}

    def apply_quotes(quotes):
        return {"type": "price_patch", "ts": 1.0, "rows": list(quotes.keys())}

    async def push(payload):
        pushes.append(payload)

    monkeypatch.setattr(reprice, "snapshot_table_quotes", fake_snapshot)
    reprice._table_reprice_busy = False
    reprice._table_chunk_rotate = 0

    async def run_two_ticks():
        task = asyncio.create_task(reprice.table_reprice_loop(
            lambda: "ibkr",
            lambda: symbols,
            apply_quotes,
            push,
        ))
        await asyncio.sleep(IBKR_TABLE_REPRICE_INTERVAL_SEC * 2 + 0.4)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run_two_ticks())
    assert len(snapped) >= 2
    assert len(snapped[0]) == IBKR_TABLE_REPRICE_CHUNK_SIZE
    assert snapped[0] != snapped[1]
    assert all(p.get("type") == "price_patch" for p in pushes[:2])
