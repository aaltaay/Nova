"""QA R42 / R45 (2026-09-22): the ticket's Flatten never closes the same shares twice.

R42 (P0, a regression from #454): the second of two flattens was accepted while
the first rested, and the Sim account ended short 2 GRML -- the route checked
the position only, and source ``flatten`` skips the manual OVERSELL check. The
check now lives in the execution door, inside the execution lock, and
subtracts the closes already working; the practice broker also cancels a SELL
that would fill past what is held.

R45: the breaker's first poll of a new practice day read yesterday's day P&L,
because nothing had rolled the ledger yet. The account summary rolls first.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import execution.flatten_intent as flatten_intent
import execution.inflight as inflight
from constants_practice import PRACTICE_NO_SHORTS_CODE
from execution.models import ExecutionCommand
from ibkr.errors import IbkrAccountError
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue

NOW = 1_700_000_000.0
DAY = 86_400.0


def _flatten(side: str = "SELL", qty: float = 2.0, **kw) -> ExecutionCommand:
    base = dict(
        operation="place", idempotency_key="flatten", source="flatten", symbol="GRML",
        side=side, qty=qty, order_type="MKT", intent="flatten",
    )
    base.update(kw)
    return ExecutionCommand(**base)


def _working(order_id: int, side: str = "SELL", qty: float = 2.0, symbol: str = "GRML",
             filled: float = 0.0) -> dict:
    return {
        "order_id": order_id, "symbol": symbol, "side": side, "qty": qty,
        "filled_qty": filled, "remaining_qty": qty - filled, "status": "Submitted",
    }


@pytest.fixture
def venue(monkeypatch):
    state: dict = {"positions": [], "orders": []}
    monkeypatch.setattr("ibkr.account.get_positions", lambda: state["positions"])
    monkeypatch.setattr("ibkr.orders.open_orders", lambda: state["orders"])
    inflight.reset_for_tests()
    yield state
    inflight.reset_for_tests()


# ---------------------------------------------------------------- R42: the door
def test_a_second_flatten_while_the_first_rests_is_refused(venue) -> None:
    venue["positions"] = [{"symbol": "GRML", "qty": 2}]
    assert flatten_intent.refusal(_flatten()) is None
    venue["orders"] = [_working(11)]
    refusal = flatten_intent.refusal(_flatten())
    assert refusal is not None
    assert "already being closed" in refusal and "#11" in refusal and "KILL" in refusal


def test_a_resting_partial_exit_leaves_only_the_rest_to_flatten(venue) -> None:
    venue["positions"] = [{"symbol": "GRML", "qty": 5}]
    venue["orders"] = [_working(12, qty=2)]
    too_big = flatten_intent.refusal(_flatten(qty=5))
    assert too_big is not None and "3 GRML shares not already being closed" in too_big
    assert flatten_intent.refusal(_flatten(qty=3)) is None


def test_a_partly_filled_close_counts_only_what_is_still_open(venue) -> None:
    venue["positions"] = [{"symbol": "GRML", "qty": 3}]  # 4 held, 1 of the 2 working already sold
    venue["orders"] = [_working(13, qty=2, filled=1)]
    assert flatten_intent.refusal(_flatten(qty=2)) is None
    assert flatten_intent.refusal(_flatten(qty=3)) is not None


def test_a_short_is_covered_once(venue) -> None:
    venue["positions"] = [{"symbol": "GRML", "qty": -3}]
    venue["orders"] = [_working(14, side="BUY", qty=3)]
    refusal = flatten_intent.refusal(_flatten(side="BUY", qty=3))
    assert refusal is not None and "already being closed" in refusal


def test_opening_orders_and_other_symbols_do_not_count(venue) -> None:
    venue["positions"] = [{"symbol": "GRML", "qty": 2}]
    venue["orders"] = [_working(15, side="BUY", qty=5), _working(16, symbol="IMCC")]
    assert flatten_intent.refusal(_flatten()) is None


def test_only_commitments_the_venue_does_not_list_yet_count(venue) -> None:
    venue["positions"] = [{"symbol": "GRML", "qty": 2}]
    inflight.commit("stale", symbol="GRML", side="SELL", qty=2)
    inflight.attach_order("stale", 99)  # the venue no longer lists #99: stale, not working
    assert flatten_intent.refusal(_flatten()) is None
    inflight.commit("sending", symbol="GRML", side="SELL", qty=2)  # no order id yet
    assert flatten_intent.refusal(_flatten()) is not None


def test_unreadable_working_orders_refuse_rather_than_guess(venue, monkeypatch) -> None:
    venue["positions"] = [{"symbol": "GRML", "qty": 2}]

    def unreadable():
        raise IbkrAccountError("open_orders failed")

    monkeypatch.setattr("ibkr.orders.open_orders", unreadable)
    refusal = flatten_intent.refusal(_flatten())
    assert refusal is not None and "cannot confirm the close" in refusal


def test_the_door_answers_flatten_not_a_close(venue, monkeypatch) -> None:
    from execution import validate

    monkeypatch.setattr("sim.mode.is_practice_venue", lambda: True)
    venue["positions"] = [{"symbol": "GRML", "qty": 2}]
    venue["orders"] = [_working(17)]
    ok, detail, code = validate.check_account_and_position(_flatten())
    assert (ok, code) == (False, "FLATTEN_NOT_A_CLOSE") and "#17" in detail


def test_a_flatten_on_a_flat_practice_position_says_it_is_not_a_close(venue, monkeypatch) -> None:
    """2026-09-23 test run: Flatten pressed while flat on Paper read "no short entries"."""
    from execution import practice_checks, validate

    fake = SimpleNamespace(
        reference=SimpleNamespace(admission=lambda symbol: (True, "OK", None)),
        ledger=SimpleNamespace(held_qty=lambda symbol: 0.0),
    )
    monkeypatch.setattr(practice_checks, "venue_broker", lambda: fake)
    monkeypatch.setattr("sim.mode.is_practice_venue", lambda: True)
    venue["positions"] = []

    assert practice_checks.practice_refusal(_flatten()) is None
    ok, _detail, code = validate.check_account_and_position(_flatten())
    assert (ok, code) == (False, "FLATTEN_NOT_A_CLOSE")
    # A manual SELL from flat is still an opening short.
    manual = _flatten(source="manual", intent=None)
    assert practice_checks.practice_refusal(manual)[1] == PRACTICE_NO_SHORTS_CODE


def test_the_route_sends_the_intent_to_the_door() -> None:
    from routes import trading_execution as route

    req = route.OrderRequest(symbol="GRML", side="SELL", qty=2, order_type="MKT", intent="flatten")
    cmd = route._manual_order_command(req, "k", None, 0)
    assert (cmd.source, cmd.intent) == ("flatten", "flatten")
    plain = route._manual_order_command(
        route.OrderRequest(symbol="GRML", side="SELL", qty=2, order_type="MKT"), "k2", None, 0,
    )
    assert (plain.source, plain.intent) == ("manual", None)


# ---------------------------------------------------------------- practice floor at the fill
class FakeLive:
    def __init__(self) -> None:
        self.now = NOW

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True)

    def admission(self, symbol: str):
        return True, "OK", None

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return self.now


@pytest.fixture
def paper(monkeypatch):
    reset_venue()
    reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake)
    reset_for_tests()
    reset_venue()


def test_two_resting_closes_of_the_same_shares_never_leave_the_account_short(paper) -> None:
    broker = paper.broker
    assert broker.place("IMCC", "BUY", 10, "MKT")["broker_status"] == "Filled"
    first = broker.place("IMCC", "SELL", 10, "LMT", limit_price=10.5)
    second = broker.place("IMCC", "SELL", 10, "LMT", limit_price=10.5)
    assert first["broker_status"] == second["broker_status"] == "Submitted"
    filled = broker.try_fill_working("IMCC", [(NOW + 1, 10.6)])
    assert [row["order_id"] for row in filled] == [first["order_id"]]
    assert broker.positions() == []
    cancelled = broker.closed_orders()[0]
    assert cancelled["order_id"] == second["order_id"]
    assert (cancelled["status"], cancelled["reason_code"]) == ("Cancelled", PRACTICE_NO_SHORTS_CODE)
    assert broker.working_orders() == []


# ---------------------------------------------------------------- R45: the new day
def test_the_account_summary_rolls_to_the_new_practice_day_first(paper) -> None:
    broker = paper.broker
    broker.place("IMCC", "BUY", 10, "MKT")
    broker.place("IMCC", "SELL", 10, "MKT")
    yesterday = broker.account_summary()
    assert yesterday["DayPnL"] < 0 and yesterday["RealizedPnL"] < 0
    paper.ref.now = NOW + DAY  # past the next 04:00 ET boundary, nothing else has rolled
    today = broker.account_summary()
    assert today["DayPnL"] == 0.0 and today["RealizedPnL"] == 0.0
