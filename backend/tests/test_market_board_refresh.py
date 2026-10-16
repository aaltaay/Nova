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
from market_board import ibkr_reads, jobs, refresh
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
    assert "quotes" not in [j.key for j in jobs.history_jobs(now)]
    assert not any(j.key.startswith(("prior:", "line:", "closes:")) for j in jobs.ibkr_jobs(now))


def test_tiles_without_a_price_read_their_bars_first(monkeypatch):
    calls: list[str] = []
    _wire_lanes(monkeypatch, calls)
    now = time.time()
    priced = {s["id"]: {"last": 1.0} for s in jobs.QUOTE_SPECS if s["id"] not in ("vix", "tnx")}
    store().put("quotes", "ibkr", priced, now)
    keys = [j.key for j in jobs.history_jobs(now)]
    assert keys[:4] == ["prior:vix", "line:vix", "prior:tnx", "line:tnx"]


def test_without_a_spare_line_the_ibkr_lane_opens_nothing_and_bars_price(monkeypatch):
    monkeypatch.setattr(ibkr_reads, "headroom_ok", lambda: False)
    now = time.time()
    assert jobs.ibkr_jobs(now) == []
    assert {"etf_bars", "movers_bars"} <= {j.key for j in jobs.history_jobs(now)}


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


# -- ETF prices from bars when no line is spare (2026-10-16) -------------------------------------------------------
# At the open the historical service shed every pass after its first symbol; each pass stored only XLK, over the
# rest, and started at XLK again five minutes later -- the 1D column stayed empty for 25 of 26 ETFs.

def _shedding_bars(monkeypatch, per_pass: int, today: str, refused: frozenset[str] = frozenset()):
    from ibkr import historical_service

    asked: list[str] = []
    budget = {"left": per_pass}

    def run(sym, timeout, label):
        if budget["left"] <= 0:
            raise historical_service.HistoricalShed("open chart has priority")
        budget["left"] -= 1
        asked.append(sym)
        if sym in refused:
            raise RuntimeError(f"no security definition for {sym}")
        return [{"date": "2026-10-15", "close": 100.0}, {"date": today, "close": 101.0}]

    monkeypatch.setattr(historical_service, "request_daily_bars", lambda sym, duration, use_rth: sym)
    monkeypatch.setattr(ibkr_reads, "_run", run)
    monkeypatch.setattr(ibkr_reads, "headroom_ok", lambda: False)
    return asked, budget


def _etf_bars_job(now: float):
    return next(j for j in jobs.history_jobs(now) if j.key == "etf_bars")


def test_a_shed_bar_pass_keeps_what_it_read_and_reads_the_rest_next(monkeypatch):
    now = time.time()
    today = jobs.clock.trading_date(now).isoformat()
    asked, budget = _shedding_bars(monkeypatch, 3, today)
    etfs = list(jobs.SECTOR_ETFS + jobs.INDUSTRY_ETFS)
    job = _etf_bars_job(now)
    t, passes = now, 0
    while not jobs._etf_bars_whole(store().get("etf_bars", t, jobs.FOREVER)):
        budget["left"] = 3
        assert refresh._due(job, t), "a pass cut short is read again after the shed retry"
        refresh._run(job, t)
        passes += 1
        assert not refresh._due(job, t + cmb.MARKET_SHED_RETRY_SEC - 1)
        t += cmb.MARKET_SHED_RETRY_SEC + 1
        assert passes <= len(etfs)
    value = store().get("etf_bars", t, jobs.FOREVER)
    assert passes == -(-len(etfs) // 3)
    # Every ETF read; the missing ones first, so none twice until all were read (the last pass refreshes the oldest).
    assert set(asked[:len(etfs)]) == set(etfs)
    assert all(value[s]["price"] == 101.0 and value[s]["prev_close"] == 100.0 for s in etfs)
    # Whole now: the next pass waits for the TTL, and starts at the oldest answer.
    assert not refresh._due(job, t)
    oldest = min(etfs, key=lambda s: value[s]["at"])
    asked.clear()
    budget["left"] = 1
    refresh._run(job, t + cmb.MARKET_BARS_QUOTES_TTL_SEC)
    assert asked == [oldest] and len(store().get("etf_bars", t, jobs.FOREVER)) == len(etfs)


def test_a_refused_etf_is_stated_and_the_others_still_price(monkeypatch):
    now = time.time()
    today = jobs.clock.trading_date(now).isoformat()
    asked, _ = _shedding_bars(monkeypatch, 100, today, refused=frozenset({"XLK"}))
    refresh._run(_etf_bars_job(now), now)
    value = store().get("etf_bars", now, jobs.FOREVER)
    assert value["XLK"]["price"] is None and "XLK" in value["XLK"]["error"]
    assert value["XLE"]["price"] == 101.0
    assert jobs._etf_bars_whole(value)


def test_yesterdays_bar_prices_are_never_carried_into_today(monkeypatch):
    now = time.time()
    today = jobs.clock.trading_date(now).isoformat()
    asked, _ = _shedding_bars(monkeypatch, 1, today)
    store().put("etf_bars", "ibkr", {s: {"price": 50.0, "prev_close": 49.0, "date": "2026-10-15", "at": now - 9e4}
                                     for s in jobs.SECTOR_ETFS + jobs.INDUSTRY_ETFS}, now - 9e4)
    refresh._run(_etf_bars_job(now), now)
    value = store().get("etf_bars", now, jobs.FOREVER)
    assert list(value) == asked and value[asked[0]]["price"] == 101.0


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
