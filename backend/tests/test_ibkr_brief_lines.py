"""A quote from a line held for a moment (``ibkr.brief_lines``, ADR 054).

IBKR's snapshot answers only at its snapshot end, ~11 s a batch outside the session (perf record 2026-10-12/13), so
the Market page, the Cryptos page, the Trader's quote head and the detail backstop read a line opened, read and
cancelled instead. These pin its rules: at most 5 lines at once, none opened without spare lines, never a line the
desk holds cancelled, never a stale pooled price, a stock's last trade waited for, and the desk's own generic ticks
on a stock line the desk may join.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from ib_async import Ticker

from constants_ibkr import (
    IBKR_BRIEF_LINE_BATCH,
    IBKR_BRIEF_MIN_FREE_LINES,
    IBKR_L1_GENERIC_TICKS,
    IBKR_QUOTE_QUALITY_CLOSE_FALLBACK,
)
from ibkr import brief_lines, client, qualified_contracts
from metrics import op_metrics
from tests.fakes.brief_line_ib import FakeIB, contracts, stock_qualifier


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    op_metrics.reset_for_tests()
    qualified_contracts.clear_qualified_contracts(reason="test")
    monkeypatch.setattr(brief_lines, "IBKR_BRIEF_LINE_WAIT_SEC", 0.3)
    monkeypatch.setattr(brief_lines, "IBKR_BRIEF_LINE_SETTLE_SEC", 0.05)
    monkeypatch.setattr(brief_lines, "IBKR_BRIEF_LINE_POLL_SEC", 0.01)
    monkeypatch.setattr(brief_lines, "spare_lines", lambda: None)
    yield
    qualified_contracts.clear_qualified_contracts(reason="test")
    op_metrics.reset_for_tests()


def test_a_brief_line_answers_with_its_first_ticks_and_closes():
    ib = FakeIB({1: {"last": 10.0, "close": 9.5}})
    started = time.monotonic()
    got = asyncio.run(brief_lines.read(ib, contracts(1)))
    assert time.monotonic() - started < 0.25        # did not wait out the deadline
    assert (got[1].last, got[1].close) == (10.0, 9.5)
    assert ib.cancelled == [1] and not ib.live
    assert op_metrics.totals()["ibkr.brief_lines"][0] == 1 and op_metrics.is_wall("ibkr.brief_lines")


def test_a_stale_pooled_price_is_never_read_as_this_lines():
    ib = FakeIB()
    stale = ib.pool.setdefault(1, Ticker(contract=contracts(1)[0]))
    stale.last, stale.close = 99.0, 98.0               # the last read of the same contract, line long closed
    got = asyncio.run(brief_lines.read(ib, contracts(1)))
    assert brief_lines._num(got[1].last) is None and brief_lines._num(got[1].close) is None
    assert ib.cancelled == [1]


def test_a_line_the_desk_holds_is_read_and_never_cancelled_and_needs_no_spare_line(monkeypatch):
    monkeypatch.setattr(brief_lines, "spare_lines", lambda: 0)   # every line taken: still readable
    ib = FakeIB()
    desk = ib.hold(contracts(1)[0], last=5.0, close=4.0)
    got = asyncio.run(brief_lines.read(ib, contracts(1)))
    assert got[1] is desk and got[1].last == 5.0
    assert ib.cancelled == [] and 1 in ib.live


def test_a_line_the_desk_subscribes_during_the_read_is_left_open_for_it():
    ib = FakeIB()

    async def go():
        task = asyncio.ensure_future(brief_lines.read(ib, contracts(1)))
        await asyncio.sleep(0.05)
        ib.pool[1].updateEvent += (lambda t: None)    # ibkr.ticks.subscribe attaches its handler to our ticker
        return await task

    asyncio.run(go())
    assert ib.cancelled == [] and 1 in ib.live


def test_at_most_a_batch_of_lines_is_open_at_once():
    ib = FakeIB({i: {"last": 1.0, "close": 1.0} for i in range(1, 13)})
    got = asyncio.run(brief_lines.read(ib, contracts(12)))
    assert len(got) == 12
    assert ib.open_max == IBKR_BRIEF_LINE_BATCH
    assert sorted(ib.cancelled) == list(range(1, 13))


def test_a_read_never_takes_the_lines_it_must_leave_spare():
    assert IBKR_BRIEF_LINE_BATCH < IBKR_BRIEF_MIN_FREE_LINES


def test_no_line_opens_while_too_few_are_spare(monkeypatch):
    monkeypatch.setattr(brief_lines, "spare_lines", lambda: IBKR_BRIEF_MIN_FREE_LINES - 1)
    ib = FakeIB({1: {"last": 1.0, "close": 1.0}})
    with pytest.raises(brief_lines.NoHeadroom):
        asyncio.run(brief_lines.read(ib, contracts(1)))
    assert ib.open_max == 0
    assert "ibkr.brief_lines" not in op_metrics.totals()   # nothing was asked, nothing timed


def test_a_stock_read_waits_for_the_last_trade_not_the_quote():
    """PLUG on the desk, 2026-10-13 14:10 ET: the quote and the prior close came first, the read settled on them and
    returned no last. A stock is priced by a print."""
    ib = FakeIB({1: [(0.01, {"bid": 2.0, "ask": 2.01, "close": 1.9}), (0.15, {"last": 2.005})]})
    got = asyncio.run(brief_lines.read(ib, contracts(1), prints=True))
    assert got[1].last == 2.005


def test_an_indicator_is_priced_by_its_quote():
    ib = FakeIB({1: {"bid": 1200.0, "ask": 800.0, "close": 0.0}})   # NYSE's AD carries its counts as bid / ask
    started = time.monotonic()
    asyncio.run(brief_lines.read(ib, contracts(1)))
    assert time.monotonic() - started < 0.25


def _wire(monkeypatch, ib):
    ib.qualifyContractsAsync = stock_qualifier()
    monkeypatch.setattr(client, "get_ib", lambda: ib)


def test_stock_quotes_have_the_snapshot_shape_and_the_desks_generic_ticks(monkeypatch):
    ib = FakeIB({1: {"last": 30.0, "close": 29.0, "volume": 1200.0}, 2: {"close": 50.0}})
    _wire(monkeypatch, ib)
    got = asyncio.run(brief_lines.stock_quotes(["mstr", "coin", "hood"]))
    assert got["MSTR"]["price"] == 30.0 and got["MSTR"]["quote_quality"] is None
    assert got["MSTR"]["prev_close"] == 29.0 and got["MSTR"]["volume"] == 1200
    # No print by the deadline: the prior close stands in, flagged, never a trade (#541).
    assert got["COIN"] == {**got["COIN"], "price": 50.0, "quote_quality": IBKR_QUOTE_QUALITY_CLOSE_FALLBACK}
    assert "HOOD" not in got                            # neither a print nor a close
    # A desk subscribe joining this line mid-read gets the line it would have opened (RTVolume for its volume).
    assert set(ib.generic.values()) == {IBKR_L1_GENERIC_TICKS}


def test_stock_quotes_reuse_qualified_contracts(monkeypatch):
    ib = FakeIB({1: {"last": 1.0, "close": 1.0}})
    asked: list[str] = []

    async def qualify(*stocks):
        asked.extend(s.symbol for s in stocks)
        return await stock_qualifier()(*stocks)

    ib.qualifyContractsAsync = qualify
    monkeypatch.setattr(client, "get_ib", lambda: ib)
    asyncio.run(brief_lines.stock_quotes(["IBIT"]))
    asyncio.run(brief_lines.stock_quotes(["IBIT"]))
    assert asked == ["IBIT"]


def test_stock_quotes_without_ibkr_are_empty(monkeypatch):
    monkeypatch.setattr(client, "get_ib", lambda: None)
    assert asyncio.run(brief_lines.stock_quotes(["IBIT"])) == {}


def test_every_reader_together_holds_at_most_a_batch_of_lines():
    """The cold slot ran one snapshot batch at a time; brief reads run side by side (the Market page, the Cryptos
    page, the quote head, the detail backstop), so their sum is capped, not each one's."""
    ib = FakeIB({i: {"last": 1.0, "close": 1.0} for i in range(1, 11)}, delay=0.05)
    cs = contracts(10)

    async def go():
        return await asyncio.gather(brief_lines.read(ib, cs[:4]), brief_lines.read(ib, cs[4:8]),
                                    brief_lines.read(ib, cs[8:]))

    got = asyncio.run(go())
    assert sum(len(g) for g in got) == 10
    assert ib.open_max <= IBKR_BRIEF_LINE_BATCH          # side by side, uncapped, they held all 10 at once
    assert brief_lines._lines_open == 0 and sorted(ib.cancelled) == list(range(1, 11))


def test_a_line_left_for_the_desk_frees_its_place():
    ib = FakeIB()

    async def go():
        task = asyncio.ensure_future(brief_lines.read(ib, contracts(1)))
        await asyncio.sleep(0.05)
        ib.pool[1].updateEvent += (lambda t: None)
        await task

    asyncio.run(go())
    assert brief_lines._lines_open == 0 and 1 in ib.live
