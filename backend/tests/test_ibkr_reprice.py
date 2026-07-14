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

    async def broadcast_trade_update(sym, price, size, ts, volume, prev_close):
        broadcasts.append((sym, price, volume, prev_close))

    calls = {"n": 0}

    def run_ibkr(coro):
        calls["n"] += 1
        if calls["n"] == 1:
            coro.close()
            return {}  # simulate an empty/failed snapshot_quotes() response
        return asyncio.run(coro)

    def find_cache_row(sym):
        return {"symbol": sym, "current_price": 4.45, "volume": 12345, "previous_close": 2.96}

    reprice.reprice_detail_symbols(["SHPH"], run_ibkr, broadcast_trade_update, find_cache_row)

    assert broadcasts == [("SHPH", 4.45, 12345, 2.96)]


def test_reprice_detail_symbols_skips_symbol_with_no_price_anywhere():
    def run_ibkr(coro):
        if asyncio.iscoroutine(coro):
            coro.close()
        return {}

    reprice.reprice_detail_symbols(["ZZZZ"], run_ibkr, lambda *a, **k: None, lambda s: None)
    # No assertion needed beyond "doesn't raise" — absence of a cache row and
    # an empty quote means there's nothing to broadcast.


def test_reprice_table_caches_returns_none_when_all_caches_empty():
    assert reprice.reprice_table_caches([], [], [], lambda coro: {}) is None


def test_reprice_table_caches_returns_none_when_quotes_empty():
    def run_ibkr(coro):
        if asyncio.iscoroutine(coro):
            coro.close()
        return {}

    gapper = [{"symbol": "ABC", "price": 1.0, "prev_close": 0.5}]
    assert reprice.reprice_table_caches(gapper, [], [], run_ibkr) is None
