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
        lastSize=None,
        rtVolume=None,
    ):
        self.last = last
        self.close = close
        self.volume = volume
        self.high = high
        self.lastTimestamp = lastTimestamp
        self.rtTime = rtTime
        self.time = time
        self.lastSize = lastSize
        self.rtVolume = rtVolume


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


def test_on_ticker_update_observes_halt_when_last_is_missing():
    """ticker.halted can arrive with no last -- still record halt (#173)."""
    from ibkr import halt_status

    _reset()
    halt_status.reset()
    ticks._subs["RETO"] = {
        "owners": {ticks.OWNER_DETAIL}, "last_price": None, "last_update_ts": None,
    }
    ticks._broadcast = None
    ticks._quote_listeners.clear()

    ticker = _FakeTicker(last=None)
    ticker.halted = 2.0
    ticks._on_ticker_update(ticker, "RETO")

    snap = halt_status.snapshot("RETO")
    assert snap is not None
    assert snap["kind"] == "luld"
    halt_status.reset()


def test_seed_existing_ticker_observes_halt_without_update_event():
    """reqMktData attach after an already-halted name -- tick 49 may not repeat."""
    from ibkr import halt_status

    _reset()
    halt_status.reset()
    ticker = _FakeTicker(last=None)
    ticker.halted = 2.0
    ticks._subs["DAIC"] = {
        "owners": {ticks.OWNER_DETAIL},
        "last_price": None,
        "last_update_ts": None,
        "ticker": ticker,
    }
    ticks._broadcast = None
    ticks._quote_listeners.clear()
    ticks._seed_existing_ticker("DAIC")
    snap = halt_status.snapshot("DAIC")
    assert snap is not None
    assert snap["kind"] == "luld"
    halt_status.reset()


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


def test_on_ticker_update_forwards_last_size_and_prefers_rt_volume():
    _reset()
    ticks._subs["ABC"] = {
        "owners": {ticks.OWNER_SCANNER},
        "last_price": None,
        "last_update_ts": None,
    }
    ticks._broadcast = None
    ticks._quote_listeners.clear()
    captured: dict = {}

    def listener(
        symbol, price, volume, prev_close, ts_unix, *,
        quote_quality=None, open_price=None, last_size=None,
    ):
        captured["volume"] = volume
        captured["last_size"] = last_size
        captured["price"] = price

    ticks._quote_listeners.append(listener)
    ticks._on_ticker_update(
        _FakeTicker(last=2.5, volume=9_999, lastSize=40, rtVolume=1_250),
        "ABC",
    )
    assert captured["price"] == 2.5
    assert captured["last_size"] == 40
    assert captured["volume"] == 1250  # RTVolume total, not the slower tick-8 day total


def test_on_ticker_update_notifies_when_rt_volume_rises_on_a_flat_last():
    _reset()
    ticks._subs["ABC"] = {
        "owners": {ticks.OWNER_SCANNER},
        "last_price": 5.0,
        "last_update_ts": None,
        "last_cum_volume": 1_000.0,
    }
    ticks._broadcast = None
    ticks._quote_listeners.clear()
    seen: list[float] = []

    def listener(symbol, price, volume, prev_close, ts_unix, **_kw):
        seen.append(volume)

    ticks._quote_listeners.append(listener)
    ticks._on_ticker_update(
        _FakeTicker(last=5.0, lastSize=80, rtVolume=1_250),
        "ABC",
    )
    assert seen == [1250]
    assert ticks.is_fresh("ABC", 8.0) is True


def test_l1_size_fields_ignore_ticker_vwap():
    from ibkr.ticks_handler import l1_size_fields

    class _VwapTicker:
        lastSize = 10
        rtVolume = 500
        volume = 9_000
        vwap = 12.34

    size, cum = l1_size_fields(_VwapTicker())
    assert size == 10
    assert cum == 500


def test_ticker_budget_status_counts_unique_lines_and_owners():
    """D-039: Error 101 budget is a visible number before Gateway trips."""
    from constants import IBKR_L1_STREAM_BUDGET

    _reset()
    ticks._subs["AAA"] = {"owners": {ticks.OWNER_SCANNER, ticks.OWNER_HOD}}
    ticks._subs["BBB"] = {"owners": {ticks.OWNER_DETAIL}}
    snap = ticks.ticker_budget_status()
    assert snap["reqMktData_lines"] == 2
    assert snap["reqMktData_by_owner"][ticks.OWNER_SCANNER] == 1
    assert snap["reqMktData_by_owner"][ticks.OWNER_HOD] == 1
    assert snap["reqMktData_by_owner"][ticks.OWNER_DETAIL] == 1
    assert snap["reqMktData_limit"] == IBKR_L1_STREAM_BUDGET
    assert snap["reqMktData_remaining"] == IBKR_L1_STREAM_BUDGET - 2
    assert snap["max_tickers_hit"] is False
    _reset()


def test_last_quotes_exposes_shared_day_volume():
    _reset()
    ticks._subs["ABCD"] = {
        "owners": {ticks.OWNER_DETAIL},
        "last_price": 1.25,
        "last_update_ts": 12.0,
        "last_cum_volume": 44000,
    }
    row = ticks.last_quotes(["ABCD"])["ABCD"]
    assert row["price"] == 1.25
    assert row["volume"] == 44000
    assert "prev_close" not in row  # no ticker on the line: unknown, never 0
    _reset()


def test_last_quotes_carries_the_lines_prior_close_once_ibkr_sent_it():
    from types import SimpleNamespace

    _reset()
    ticks._subs["ABCD"] = {
        "owners": {ticks.OWNER_DETAIL}, "last_price": 1.25, "last_update_ts": 12.0,
        "ticker": SimpleNamespace(close=float("nan")),
    }
    assert "prev_close" not in ticks.last_quotes(["ABCD"])["ABCD"]  # tick 9 not sent yet
    ticks._subs["ABCD"]["ticker"] = SimpleNamespace(close=1.07)
    assert ticks.last_quotes(["ABCD"])["ABCD"]["prev_close"] == 1.07
    _reset()


def _last_tick(price, tick_type=4):
    from types import SimpleNamespace

    return SimpleNamespace(tickType=tick_type, price=price, size=100)


def test_last_is_ibkrs_tick_4_not_an_alllast_or_rtvolume_print():
    """ib_async writes ``ticker.last`` from every AllLast print and from RTVolume
    (unreported trades included) on the one Ticker it keeps per contract. A PLTR
    ``4 W`` print at 190.38 became the desk's last and a candle wick (2026-09-23)."""
    _reset()
    ticks._subs["PLTR"] = {
        "owners": {ticks.OWNER_DETAIL}, "last_price": None, "last_update_ts": None,
    }
    ticks._broadcast = None
    ticks._quote_listeners.clear()
    seen: list[float] = []
    ticks._quote_listeners.append(lambda sym, price, *_a, **_kw: seen.append(price))

    first = _FakeTicker(last=192.75)
    first.ticks = [_last_tick(192.75)]
    ticks._on_ticker_update(first, "PLTR")

    # The average-price print lands in ticker.last with no IBKR Last behind it.
    wick = _FakeTicker(last=190.38)
    wick.ticks = [_last_tick(190.38, tick_type=48)]
    ticks._on_ticker_update(wick, "PLTR")

    moved = _FakeTicker(last=190.37)
    moved.ticks = [_last_tick(192.80)]
    ticks._on_ticker_update(moved, "PLTR")

    assert seen == [192.75, 192.80]
    assert ticks.last_quotes(["PLTR"])["PLTR"]["price"] == 192.80


def test_last_falls_back_to_ticker_last_until_the_line_delivers_tick_4():
    _reset()
    ticks._subs["ABC"] = {
        "owners": {ticks.OWNER_SCANNER}, "last_price": None, "last_update_ts": None,
    }
    ticks._broadcast = None
    ticks._quote_listeners.clear()
    seen: list[float] = []
    ticks._quote_listeners.append(lambda sym, price, *_a, **_kw: seen.append(price))

    ticks._on_ticker_update(_FakeTicker(last=3.10), "ABC")  # a seed: no ticks yet
    delayed = _FakeTicker(last=3.20)
    delayed.ticks = [_last_tick(3.15, tick_type=68)]
    ticks._on_ticker_update(delayed, "ABC")
    assert seen == [3.10, 3.15]
