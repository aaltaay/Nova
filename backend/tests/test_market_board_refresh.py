"""The Market page's refreshers and quote reads (ADR 053 amendment 2026-10-13).

On 2026-10-13 the page sat half empty for 14 minutes: one pass of the tiles' snapshots took 23-66 s, and the bar
reads below it on the same thread never ran. These pin the two fixes -- bars on their own thread, quotes from a line
held for a moment -- and that both are timed in the perf record. The line held for a moment itself is
``ibkr.brief_lines`` (ADR 054), pinned in ``test_ibkr_brief_lines.py``.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import constants_market_board as cmb
from ibkr import brief_lines
from market_board import ibkr_reads, refresh
from market_board.state import store
from metrics import op_metrics
from tests.fakes.brief_line_ib import FakeIB, stock_qualifier


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    refresh.reset_for_tests()
    op_metrics.reset_for_tests()
    monkeypatch.setattr(brief_lines, "IBKR_BRIEF_LINE_WAIT_SEC", 0.3)
    monkeypatch.setattr(brief_lines, "IBKR_BRIEF_LINE_SETTLE_SEC", 0.05)
    monkeypatch.setattr(brief_lines, "IBKR_BRIEF_LINE_POLL_SEC", 0.01)
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


# -- the ETFs' quotes ----------------------------------------------------------------------------------------------

def test_stock_quotes_read_prints_and_say_no_trade(monkeypatch):
    from ibkr import client, qualified_contracts

    qualified_contracts.clear_qualified_contracts(reason="test")
    ib = FakeIB({1: {"last": 30.0, "close": 29.0}, 2: {"close": 50.0}})
    ib.qualifyContractsAsync = stock_qualifier()
    monkeypatch.setattr(client, "get_ib", lambda: ib)
    monkeypatch.setattr(brief_lines, "spare_lines", lambda: None)
    monkeypatch.setattr(ibkr_reads, "_run", lambda coro, timeout, label: asyncio.run(coro))
    try:
        got = ibkr_reads.stock_quotes(["xlk", "xlu", "xle"])
    finally:
        qualified_contracts.clear_qualified_contracts(reason="test")
    assert got["XLK"] == {"price": 30.0, "prev_close": 29.0, "no_trade": False}
    assert got["XLU"] == {"price": None, "prev_close": 50.0, "no_trade": True}
    assert "XLE" not in got                          # neither a print nor a close


def test_every_quote_read_waits_for_spare_lines(monkeypatch):
    """The page's guard is the shared one (``ibkr.brief_lines``, ADR 054): no read opens a line without spare ones."""
    monkeypatch.setattr(brief_lines, "spare_lines", lambda: 0)
    monkeypatch.setattr(ibkr_reads, "_run", lambda coro, timeout, label: pytest.fail(f"{label} asked IBKR"))
    for read in (lambda: ibkr_reads.movers(), lambda: ibkr_reads.stock_quotes(["XLK"]),
                 lambda: ibkr_reads.reference_quotes([], "2026-10-13")):
        with pytest.raises(ibkr_reads.NoHeadroom):
            read()
    assert ibkr_reads.headroom_ok() is False
