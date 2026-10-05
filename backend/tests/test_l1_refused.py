"""A Level 1 line IBKR refused at its cap is not open, is said, and is asked for again (2026-10-05).

After the close IBKR answered 176 ``reqMktData`` with Error 101 ("Max number of tickers has been
reached") while Nova held 51-56 lines of its own: the login's other IBKR platforms count against the
same cap. ib_async 2.1.0 keeps a refused request registered and hands it back to the next request for
the contract, so 17 of the 50 After Hours rows never got a price and Nova counted the dead lines
as open. The fake IB here behaves like ib_async: one registry, a registered line handed back
unasked, and an error answered on the request's own id.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from constants import (
    IBKR_ERROR_MAX_TICKERS,
    IBKR_L1_CAP_RELAX_SEC,
    IBKR_L1_CAP_RELAX_STEP,
    IBKR_L1_REFUSED_RESET_SEC,
    IBKR_L1_REFUSED_RETRY_SEC,
    IBKR_L1_STREAM_BUDGET,
    IBKR_L1_STREAM_RESERVE,
)
from ibkr import client, l1_refused, ticks
from ibkr.scanner_l1_plan import budget_for_streams, plan_stream_symbols, subscription_error
from tests.fakes.fake_ibkr_feed import FakeTicker

MKT_DATA = "mktData"
REFUSED = "Max number of tickers has been reached"


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def emit(self, *args):
        for handler in list(self.handlers):
            handler(*args)


class _IB:
    """ib_async 2.1.0's shape: one registry; a refused request stays registered."""

    def __init__(self):
        self.subs: dict[tuple[int, str], SimpleNamespace] = {}
        self.wrapper = SimpleNamespace(subscriptions=SimpleNamespace(
            find_market_data=lambda con_id, kind: self.subs.get((con_id, kind))))
        self.errorEvent = _Event()
        self.log: list[tuple[str, str]] = []
        self.next_req = 100
        self.con_ids: dict[str, int] = {}

    async def qualifyContractsAsync(self, contract):
        contract.conId = self.con_ids.setdefault(contract.symbol, 1000 + len(self.con_ids))
        return [contract]

    def reqMktData(self, contract, generic_ticks="", snapshot=False, regulatory=False):
        key = (contract.conId, MKT_DATA)
        sub = self.subs.get(key)
        if sub is None:  # a registered line is handed back and nothing is sent
            sub = SimpleNamespace(reqId=self.next_req, ticker=FakeTicker(contract.symbol), contract=contract)
            sub.close = lambda send_cancel=True, sub=sub: self._close(sub, send_cancel)
            self.next_req += 1
            self.subs[key] = sub
            self.log.append(("reqMktData", contract.symbol))
        return sub.ticker

    def _close(self, sub, send_cancel):
        self.subs.pop((sub.contract.conId, MKT_DATA), None)
        if send_cancel:
            self.log.append(("cancelMktData", sub.contract.symbol))

    def cancelMktData(self, contract):
        sub = self.subs.get((contract.conId, MKT_DATA))
        if sub is not None:
            sub.close()
        return True

    def req_id(self, symbol: str) -> int:
        return self.subs[(self.con_ids[symbol], MKT_DATA)].reqId

    def refuse(self, symbol: str, code: int = IBKR_ERROR_MAX_TICKERS) -> None:
        sub = self.subs[(self.con_ids[symbol], MKT_DATA)]
        self.errorEvent.emit(sub.reqId, code, REFUSED, sub.contract)


@pytest.fixture
def ib(monkeypatch):
    fake = _IB()
    clock = SimpleNamespace(now=1_000_000.0)
    ticks._subs.clear()
    ticks._subscribe_lock = None
    l1_refused.reset_for_tests()
    monkeypatch.setattr(client, "get_ib", lambda: fake)
    monkeypatch.setattr(client, "current_generation", lambda: 7)
    monkeypatch.setattr(l1_refused, "time", SimpleNamespace(time=lambda: clock.now))
    fake.clock = clock
    yield fake
    ticks._subs.clear()
    ticks._subscribe_lock = None
    l1_refused.reset_for_tests()


def _run(coro):
    ticks._subscribe_lock = None  # each asyncio.run is a new loop
    return asyncio.run(coro)


def _open(*symbols: str, owner: str = ticks.OWNER_SCANNER) -> None:
    for sym in symbols:
        assert _run(ticks.subscribe(sym, owner)) is True


def test_error_101_marks_the_line_refused_and_it_no_longer_counts_as_open(ib):
    _open("WHLR", "OLOX", "INBS")
    ib.refuse("INBS")

    status = ticks.ticker_budget_status()
    assert (status["reqMktData_lines"], status["reqMktData_refused"], status["reqMktData_cap"]) == (2, 1, 2)
    assert status["reqMktData_remaining"] == 0  # the learned cap, not 100, says what is left
    view = ticks.refused_view()
    assert [row["symbol"] for row in view["refused"]] == ["INBS"]
    assert view["refused"][0]["retry_at"] == ib.clock.now + IBKR_L1_REFUSED_RETRY_SEC[0]
    # The line keeps its owners and handler, so a Trader tab or the scanner gets it back in place.
    assert ticks.owners_for("INBS") == {ticks.OWNER_SCANNER}
    text = l1_refused.error_text(view)
    assert "IBKR refused 1 Level 1 line(s)" in text and "Error 101: INBS" in text and "Nova holds 2" in text


def test_only_error_101_on_the_lines_own_request_id_counts(ib):
    _open("INBS")
    ib.refuse("INBS", code=300)  # Can't find EId: the answer to a cancel, not a refusal
    ib.errorEvent.emit(9999, IBKR_ERROR_MAX_TICKERS, REFUSED, None)  # a request that is not a line
    assert ticks.refused_view()["refused"] == []
    ib.refuse("INBS")
    ib.refuse("INBS")  # the same refusal heard twice is one
    assert ticks.refused_view()["refused"][0]["refusals"] == 1


def test_a_refusal_of_an_ended_session_names_nothing(ib, monkeypatch):
    _open("INBS")
    monkeypatch.setattr(client, "current_generation", lambda: 8)
    ib.refuse("INBS")
    assert ticks.refused_view()["refused"] == []


def test_a_refused_line_is_asked_for_again_once_its_wait_is_over_and_there_is_room(ib):
    _open("WHLR", "OLOX")
    _open("INBS")
    ib.refuse("INBS")
    old_id = ib.req_id("INBS")
    assert _run(ticks.retry_refused()) == []  # still waiting

    ib.clock.now += IBKR_L1_REFUSED_RETRY_SEC[0]
    assert _run(ticks.retry_refused()) == []  # waited, but Nova holds the 2 lines the cap allows

    _run(ticks.unsubscribe("WHLR", ticks.OWNER_SCANNER))
    ib.log.clear()
    assert _run(ticks.retry_refused()) == ["INBS"]
    # IBKR never opened the refused request: it is let go without a cancel, then asked again.
    assert ib.log == [("reqMktData", "INBS")]
    assert ticks.refused_view()["refused"] == []
    assert ticks.owners_for("INBS") == {ticks.OWNER_SCANNER}
    assert len(ticks.get_ticker("INBS").updateEvent._handlers) == 1
    # A late answer to the old request names nothing; a refusal of the new one counts, waiting longer.
    ib.errorEvent.emit(old_id, IBKR_ERROR_MAX_TICKERS, REFUSED, None)
    assert ticks.refused_view()["refused"] == []
    ib.refuse("INBS")
    row = ticks.refused_view()["refused"][0]
    assert (row["refusals"], row["retry_at"]) == (2, ib.clock.now + IBKR_L1_REFUSED_RETRY_SEC[1])


def test_refusals_in_a_row_wait_longer_and_a_quiet_spell_starts_over(ib):
    _open("INBS")
    waits = []
    for _ in range(len(IBKR_L1_REFUSED_RETRY_SEC) + 1):
        ib.refuse("INBS")
        row = ticks.refused_view()["refused"][0]
        waits.append(row["retry_at"] - ib.clock.now)
        ib.clock.now = row["retry_at"]
        l1_refused._cap.clear()  # room for the retry
        assert _run(ticks.retry_refused()) == ["INBS"]
    assert waits == [*IBKR_L1_REFUSED_RETRY_SEC, IBKR_L1_REFUSED_RETRY_SEC[-1]]
    ib.clock.now += IBKR_L1_REFUSED_RESET_SEC + 1
    ib.refuse("INBS")
    assert ticks.refused_view()["refused"][0]["refusals"] == 1


def test_a_trader_tab_waits_least_for_a_line_again(ib):
    _open("HODX", owner=ticks.OWNER_HOD)
    _open("ROWX", owner=ticks.OWNER_SCANNER)
    _open("TABX", owner=ticks.OWNER_DETAIL)
    for sym in ("HODX", "ROWX", "TABX"):
        ib.refuse(sym)
    l1_refused._cap["lines"] = 2.0  # room for two
    ib.clock.now += IBKR_L1_REFUSED_RETRY_SEC[0]
    assert l1_refused.due(ticks._subs) == ["TABX", "ROWX"]


def test_letting_go_of_a_refused_line_sends_no_cancel(ib):
    _open("INBS")
    ib.refuse("INBS")
    ib.log.clear()
    _run(ticks.unsubscribe("INBS", ticks.OWNER_SCANNER))
    assert ib.log == [] and ib.subs == {} and ticks.subscribed_symbols() == []
    _open("OLOX")
    ib.log.clear()
    _run(ticks.unsubscribe("OLOX", ticks.OWNER_SCANNER))
    assert ib.log == [("cancelMktData", "OLOX")]  # an open line is still cancelled


def test_a_tick_upgrade_of_a_refused_line_is_a_new_request(ib):
    _open("OLOX")
    ib.refuse("OLOX")
    ib.log.clear()
    assert _run(ticks.subscribe("OLOX", ticks.OWNER_LISTING, generic_ticks="236")) is True
    assert ib.log == [("reqMktData", "OLOX")]  # no cancel for the request IBKR never opened
    assert ticks.refused_view()["refused"] == []
    assert ticks.owners_for("OLOX") == {ticks.OWNER_SCANNER, ticks.OWNER_LISTING}


def test_the_learned_cap_rises_back_and_clears_at_the_budget():
    l1_refused.reset_for_tests()
    l1_refused._cap.update(lines=50.0, at=0.0)
    assert l1_refused.ceiling(0.0) == 50
    assert l1_refused.ceiling(IBKR_L1_CAP_RELAX_SEC) == 50 + IBKR_L1_CAP_RELAX_STEP
    steps = -(-(IBKR_L1_STREAM_BUDGET - 50) // IBKR_L1_CAP_RELAX_STEP)
    assert l1_refused.ceiling(steps * IBKR_L1_CAP_RELAX_SEC) is None
    assert l1_refused._cap == {}


def test_a_burst_of_refusals_learns_the_fewest_lines_held(ib):
    _open("A", "B", "C", "D")
    ib.refuse("D")  # A, B, C open: the cap is 3
    ib.refuse("C")  # then 2 open: within the burst the cap is the fewest held
    assert ticks.refused_view()["cap"] == 2


def test_the_planner_plans_within_the_learned_cap_less_the_lines_it_does_not_plan():
    assert budget_for_streams() == IBKR_L1_STREAM_BUDGET - IBKR_L1_STREAM_RESERVE
    assert budget_for_streams(53, 3) == 53 - 3 - IBKR_L1_STREAM_RESERVE
    rows = [f"R{i}" for i in range(50)]
    plan = plan_stream_symbols(rows, ["H1", "H2"], budget=budget_for_streams(53, 3))
    # The displayed rows first, as always; HOD Momo's other names fit into what is left.
    assert (len(plan["tab"]), plan["hod"], len(plan["rejected"])) == (45, [], 7)


def test_plan_budget_takes_out_only_the_open_lines_no_planned_owner_holds():
    l1_refused.reset_for_tests()
    l1_refused._cap.update(lines=20.0, at=0.0)
    subs = {
        "TAB": {"owners": {"detail"}},
        "ROW": {"owners": {"scanner", "detail"}},
        "DEAD": {"owners": {"detail"}, "refused": {"at": 0.0}},
    }
    assert l1_refused.plan_budget(subs, {"scanner", "hod"}, now=0.0) == 20 - 1 - IBKR_L1_STREAM_RESERVE
    l1_refused.reset_for_tests()


def test_the_subscription_error_joins_every_reason():
    assert subscription_error([], [], [], None) is None
    assert subscription_error(["X"], ["Y", "Z"], ["afterhours"], "IBKR refused 1 Level 1 line(s)") == (
        "IBKR L1 subscribe failed for 1 symbol(s); capacity: 2 symbol(s) not streamed; "
        "IBKR refused 1 Level 1 line(s); no live L1 for displayed table(s): afterhours"
    )
