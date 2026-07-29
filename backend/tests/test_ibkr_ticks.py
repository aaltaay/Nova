"""Tests for ibkr/ticks.py freshness tracking.

See CHANGELOG "Open ticker: skip redundant snapshot backstop while
reqMktData is streaming" — ``is_fresh`` is what lets ``ibkr/reprice.py``'s
detail backstop skip a reqTickersAsync snapshot for a symbol whose streaming
subscription is already delivering, cutting IBKR-request-queue contention
with table_reprice_loop.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ibkr import ticks  # noqa: E402


def _reset():
    ticks._subs.clear()


def test_is_fresh_false_when_symbol_not_subscribed():
    _reset()
    assert ticks.is_fresh("NOPE", 8.0) is False


def test_is_fresh_false_before_first_tick():
    """Subscribed but no updateEvent has fired yet -> not fresh (the
    snapshot backstop must still cover the symbol until streaming proves
    itself live)."""
    _reset()
    ticks._subs["FRESH"] = {
        "owners": {ticks.OWNER_DETAIL}, "last_price": None, "last_update_ts": None,
    }
    assert ticks.is_fresh("FRESH", 8.0) is False


def test_is_fresh_true_within_window_false_after():
    _reset()
    ticks._subs["FRESH"] = {
        "owners": {ticks.OWNER_DETAIL}, "last_price": 1.0, "last_update_ts": time.time(),
    }
    assert ticks.is_fresh("FRESH", 8.0) is True

    ticks._subs["FRESH"]["last_update_ts"] = time.time() - 100
    assert ticks.is_fresh("FRESH", 8.0) is False


def test_is_fresh_is_case_insensitive():
    _reset()
    ticks._subs["ABC"] = {
        "owners": {ticks.OWNER_DETAIL}, "last_price": 1.0, "last_update_ts": time.time(),
    }
    assert ticks.is_fresh("abc", 8.0) is True


class _FakeTicker:
    def __init__(
        self,
        last=None,
        close=None,
        volume=None,
        high=None,
        lastTimestamp=None,
        rtTime=None,
        time=None,
    ):
        self.last = last
        self.close = close
        self.volume = volume
        self.high = high
        self.lastTimestamp = lastTimestamp
        self.rtTime = rtTime
        self.time = time


def test_set_owner_symbols_caps_adds_per_reconcile(monkeypatch):
    """Explore rotation must not qualify dozens of symbols under one lock."""
    _reset()
    calls: list[str] = []

    async def fake_subscribe(symbol, owner="detail"):
        calls.append(symbol)
        ticks._subs[symbol] = {
            "owners": {owner}, "last_price": 1.0, "last_update_ts": time.time(),
            "ticker": None, "contract": None, "handler": None,
        }
        return True

    async def fake_unsubscribe(symbol, owner="detail"):
        sub = ticks._subs.get(symbol)
        if sub:
            (sub.get("owners") or set()).discard(owner)
            if not sub.get("owners"):
                ticks._subs.pop(symbol, None)

    monkeypatch.setattr(ticks, "subscribe", fake_subscribe)
    monkeypatch.setattr(ticks, "unsubscribe", fake_unsubscribe)
    monkeypatch.setattr(ticks, "IBKR_L1_MAX_SUBSCRIBE_PER_RECONCILE", 3)

    import asyncio
    result = asyncio.run(ticks.set_owner_symbols("hod", [f"S{i:02d}" for i in range(10)]))
    assert result["deferred"] == 7
    assert len(calls) == 3
    assert result["subscribed"] == 3


def test_on_ticker_update_marks_fresh_even_when_price_unchanged():
    """A thinly-traded symbol whose price hasn't moved must still count as
    'streaming fine' — only a dead/missing subscription should fall back to
    the snapshot backstop, not merely an unchanged price."""
    _reset()
    ticks._subs["ABC"] = {
        "owners": {ticks.OWNER_DETAIL}, "last_price": 5.0, "last_update_ts": None,
    }
    ticks._broadcast = None  # no broadcast wired; only checking freshness bookkeeping
    ticks._quote_listeners.clear()

    ticks._on_ticker_update(_FakeTicker(last=5.0), "ABC")

    assert ticks.is_fresh("ABC", 8.0) is True


def test_on_ticker_update_flags_close_fallback_and_prefers_exchange_time():
    _reset()
    ticks._subs["ABC"] = {
        "owners": {ticks.OWNER_SCANNER},
        "last_price": None,
        "last_update_ts": None,
    }
    ticks._broadcast = None
    ticks._quote_listeners.clear()
    captured: dict = {}

    def listener(symbol, price, volume, prev_close, ts_unix, *, quote_quality=None):
        captured["price"] = price
        captured["ts"] = ts_unix
        captured["quote_quality"] = quote_quality

    ticks._quote_listeners.append(listener)
    ticks._on_ticker_update(
        _FakeTicker(last=None, close=9.5, lastTimestamp=1_700_000_123),
        "ABC",
    )
    assert captured["price"] == 9.5
    assert captured["quote_quality"] == "close_fallback"
    assert captured["ts"] == 1_700_000_123.0


def test_on_ticker_update_still_notifies_legacy_five_arg_listener():
    _reset()
    ticks._subs["ABC"] = {
        "owners": {ticks.OWNER_SCANNER},
        "last_price": None,
        "last_update_ts": None,
    }
    ticks._broadcast = None
    ticks._quote_listeners.clear()
    seen: list[tuple] = []

    def legacy(symbol, price, volume, prev_close, ts_unix):
        seen.append((symbol, price, volume, prev_close, ts_unix))

    ticks._quote_listeners.append(legacy)
    ticks._on_ticker_update(_FakeTicker(last=2.0, close=1.9), "ABC")
    assert len(seen) == 1
    assert seen[0][0] == "ABC"
    assert seen[0][1] == 2.0
