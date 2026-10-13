"""The Market page's refreshers and quote reads (ADR 053 amendment 2026-10-13).

On 2026-10-13 the page sat half empty for 14 minutes: one pass of the tiles' snapshots took 23-66 s, and the bar
reads below it on the same thread never ran. These pin the two fixes -- bars on their own thread, quotes from a line
held for a moment -- and that both are timed in the perf record.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ib_async import Contract, Ticker

import constants_market_board as cmb
from market_board import brief_lines, ibkr_reads, refresh
from market_board.state import store
from metrics import op_metrics


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    from ibkr import ib_scheduler, ticks

    refresh.reset_for_tests()
    op_metrics.reset_for_tests()
    # asyncio locks bind to the loop that first waits on them; each test runs its own loop.
    monkeypatch.setattr(ticks, "_subscribe_lock", None)
    monkeypatch.setattr(ib_scheduler, "_lock", None)
    monkeypatch.setattr(brief_lines, "MARKET_STREAM_WAIT_SEC", 0.3)
    monkeypatch.setattr(brief_lines, "MARKET_STREAM_SETTLE_SEC", 0.05)
    monkeypatch.setattr(brief_lines, "MARKET_STREAM_POLL_SEC", 0.01)
    yield
    refresh.reset_for_tests()
    op_metrics.reset_for_tests()


# -- the lanes ---------------------------------------------------------------------------------------------------

def _wire_lanes(monkeypatch, calls: list[str]) -> None:
    monkeypatch.setattr(ibkr_reads, "ready", lambda: True)
    monkeypatch.setattr(ibkr_reads, "headroom_ok", lambda: True)
    monkeypatch.setattr(refresh, "breadth_due", lambda now: False)

    def fake(name, value):
        def run(*args, **kwargs):
            calls.append(name if not args or not isinstance(args[0], dict) else f"{name}:{args[0]['id']}")
            return value
        return run

    monkeypatch.setattr(ibkr_reads, "reference_quotes", fake("quotes", {}))
    monkeypatch.setattr(ibkr_reads, "stock_quotes", fake("stocks", {}))
    monkeypatch.setattr(ibkr_reads, "prior_close", fake("prior", {"date": "2099-01-01", "close": 1.0}))
    monkeypatch.setattr(ibkr_reads, "line_bars", fake("line", []))
    monkeypatch.setattr(ibkr_reads, "rth_closes", fake("closes", []))


def test_bars_run_on_their_own_lane_while_quotes_are_due(monkeypatch):
    calls: list[str] = []
    _wire_lanes(monkeypatch, calls)
    now = time.time()
    store().want(now - 1.0)

    # The quote read is due on the ibkr lane and stays due; the history lane still reads bars.
    assert refresh.run_once("history", now)
    assert calls[-1].startswith("prior:")
    assert refresh.run_once("ibkr", now)
    assert calls[-1] == "quotes"
    assert "quotes" not in [j.key for j in refresh.history_jobs(now)]
    assert not any(j.key.startswith(("prior:", "line:", "closes:")) for j in refresh.ibkr_jobs(now))


def test_tiles_without_a_price_read_their_bars_first(monkeypatch):
    calls: list[str] = []
    _wire_lanes(monkeypatch, calls)
    now = time.time()
    priced = {s["id"]: {"last": 1.0} for s in refresh.QUOTE_SPECS if s["id"] not in ("vix", "tnx")}
    store().put("quotes", "ibkr", priced, now)
    keys = [j.key for j in refresh.history_jobs(now)]
    assert keys[:4] == ["prior:vix", "line:vix", "prior:tnx", "line:tnx"]


def test_without_a_spare_line_the_ibkr_lane_opens_nothing_and_bars_price(monkeypatch):
    monkeypatch.setattr(ibkr_reads, "headroom_ok", lambda: False)
    now = time.time()
    assert refresh.ibkr_jobs(now) == []
    assert {"etf_bars", "movers_bars"} <= {j.key for j in refresh.history_jobs(now)}


def test_every_read_is_timed_and_the_first_answer_after_the_page_opened(monkeypatch):
    calls: list[str] = []
    _wire_lanes(monkeypatch, calls)
    now = time.time()
    store().want(now - 2.0)
    assert refresh.run_once("ibkr", now)
    totals = op_metrics.totals()
    assert totals["market_board.quotes"][0] == 1
    assert totals["market_board.first.quotes"][0] == 1
    assert op_metrics.is_wall("market_board.quotes")
    # A second answer in the same visit is not a first answer.
    refresh.run_once("ibkr", now + cmb.MARKET_QUOTES_TTL_SEC + 1)
    assert op_metrics.totals()["market_board.first.quotes"][0] == 1


# -- brief lines ---------------------------------------------------------------------------------------------------

class FakeIB:
    """reqMktData / cancelMktData with ib_async's pooled tickers and its one-subscription-per-contract rule."""

    def __init__(self, ticks: dict[int, dict] | None = None, delay: float = 0.02):
        self.ticks = ticks or {}
        self.delay = delay
        self.pool: dict[int, Ticker] = {}
        self.live: dict[int, SimpleNamespace] = {}
        self.cancelled: list[int] = []
        self.open_now = 0
        self.open_max = 0
        self.wrapper = SimpleNamespace(subscriptions=SimpleNamespace(find_market_data=self._find))

    def _find(self, con_id, kind):
        return self.live.get(con_id)

    def reqMktData(self, contract, *_args):
        held = self.live.get(contract.conId)
        if held is not None:
            return held.ticker
        ticker = self.pool.setdefault(contract.conId, Ticker(contract=contract))
        self.live[contract.conId] = SimpleNamespace(ticker=ticker)
        self.open_now += 1
        self.open_max = max(self.open_max, self.open_now)
        fields = self.ticks.get(contract.conId)
        if fields:
            asyncio.get_running_loop().call_later(self.delay, lambda: [setattr(ticker, k, v) for k, v in fields.items()])
        return ticker

    def cancelMktData(self, contract):
        self.live.pop(contract.conId)
        self.cancelled.append(contract.conId)
        self.open_now -= 1


def _contracts(n: int, sec_type: str = "FUT") -> list[Contract]:
    return [Contract(conId=i + 1, symbol=f"S{i + 1}", secType=sec_type) for i in range(n)]


def test_a_brief_line_answers_with_its_first_ticks_and_closes():
    ib = FakeIB({1: {"last": 10.0, "close": 9.5}})
    started = time.monotonic()
    got = asyncio.run(brief_lines.read(ib, _contracts(1)))
    assert time.monotonic() - started < 0.25        # did not wait out the deadline
    assert (got[1].last, got[1].close) == (10.0, 9.5)
    assert ib.cancelled == [1] and not ib.live


def test_a_stale_pooled_price_is_never_read_as_this_lines():
    ib = FakeIB()
    stale = ib.pool.setdefault(1, Ticker(contract=_contracts(1)[0]))
    stale.last, stale.close = 99.0, 98.0               # the last read of the same contract, line long closed
    got = asyncio.run(brief_lines.read(ib, _contracts(1)))
    assert brief_lines._num(got[1].last) is None and brief_lines._num(got[1].close) is None
    assert ib.cancelled == [1]


def test_a_line_the_desk_holds_is_read_and_never_cancelled():
    ib = FakeIB()
    desk = Ticker(contract=_contracts(1)[0])
    desk.last, desk.close = 5.0, 4.0
    ib.live[1] = SimpleNamespace(ticker=desk)
    got = asyncio.run(brief_lines.read(ib, _contracts(1)))
    assert got[1] is desk and got[1].last == 5.0
    assert ib.cancelled == [] and 1 in ib.live


def test_a_line_the_desk_subscribes_during_the_read_is_left_open_for_it():
    ib = FakeIB()

    async def go():
        task = asyncio.ensure_future(brief_lines.read(ib, _contracts(1)))
        await asyncio.sleep(0.05)
        ib.pool[1].updateEvent += (lambda t: None)    # ibkr.ticks.subscribe attaches its handler to our ticker
        return await task

    asyncio.run(go())
    assert ib.cancelled == [] and 1 in ib.live


def test_at_most_a_batch_of_lines_is_open_at_once():
    ib = FakeIB({i: {"last": 1.0, "close": 1.0} for i in range(1, 13)})
    got = asyncio.run(brief_lines.read(ib, _contracts(12)))
    assert len(got) == 12
    assert ib.open_max == cmb.MARKET_STREAM_BATCH
    assert sorted(ib.cancelled) == list(range(1, 13))


def test_the_page_never_takes_the_lines_it_must_leave_spare():
    assert cmb.MARKET_STREAM_BATCH < cmb.MARKET_MIN_FREE_LINES


def test_stock_quotes_read_prints_and_say_no_trade(monkeypatch):
    from ibkr import client, qualified_contracts

    qualified_contracts.clear_qualified_contracts(reason="test")
    ib = FakeIB({1: {"last": 30.0, "close": 29.0}, 2: {"close": 50.0}})

    async def qualify(*stocks):
        return [Contract(conId=i + 1, symbol=s.symbol, secType="STK") for i, s in enumerate(stocks)]

    ib.qualifyContractsAsync = qualify
    monkeypatch.setattr(client, "get_ib", lambda: ib)
    monkeypatch.setattr(ibkr_reads, "spare_lines", lambda: None)
    monkeypatch.setattr(ibkr_reads, "_run", lambda coro, timeout, label: asyncio.run(coro))
    try:
        got = ibkr_reads.stock_quotes(["xlk", "xlu", "xle"])
    finally:
        qualified_contracts.clear_qualified_contracts(reason="test")
    assert got["XLK"] == {"price": 30.0, "prev_close": 29.0, "no_trade": False}
    assert got["XLU"] == {"price": None, "prev_close": 50.0, "no_trade": True}
    assert "XLE" not in got                          # neither a print nor a close


def test_a_desk_subscribe_waits_for_a_stock_batch_and_never_lands_on_its_line():
    """Review on PR #912: a ticks.subscribe landing on a brief line would get none of its generic ticks (236)."""
    from ibkr import ticks

    ib = FakeIB()
    seen: dict[str, object] = {}

    async def desk_subscribe():
        await asyncio.sleep(0.02)                       # the brief stock line is open by now
        async with ticks.get_subscribe_lock():          # what ticks.subscribe holds across its reqMktData
            seen["line_open_when_desk_got_in"] = 1 in ib.live

    async def go():
        desk = asyncio.ensure_future(desk_subscribe())
        await brief_lines.read(ib, _contracts(1, "STK"))
        await desk

    asyncio.run(go())
    assert seen["line_open_when_desk_got_in"] is False   # the brief line was already cancelled
    assert ib.cancelled == [1]


def test_a_read_holds_the_cold_slot_so_snapshots_and_brief_lines_never_overlap():
    """Review on PR #912: snapshots' lines are not in the Level 1 count, so the two must not run together."""
    from ibkr import ib_scheduler

    ib = FakeIB()
    seen: dict[str, bool] = {}

    async def go():
        task = asyncio.ensure_future(brief_lines.read(ib, _contracts(2)))
        await asyncio.sleep(0.02)
        seen["slot_held"] = ib_scheduler._get_lock().locked()
        await task

    asyncio.run(go())
    assert seen["slot_held"] is True


def test_a_read_dropped_for_interactive_work_is_asked_again_not_failed(monkeypatch):
    from ibkr.ib_scheduler import ColdDropped

    def dropped():
        raise ColdDropped("interactive chart has priority")

    now = time.time()
    refresh._run(refresh.Job("quotes", "ibkr", 10.0, dropped), now)
    assert store().error("quotes") is None
    assert not store().due("quotes", now + 1.0, 10.0)
