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
    def __init__(self, last=None, close=None, volume=None):
        self.last = last
        self.close = close
        self.volume = volume


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
