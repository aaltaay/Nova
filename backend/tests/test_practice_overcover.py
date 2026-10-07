"""Paper and Sim never fill a cover past flat (ADR 048 gap 8, the mirror of QA R42).

A row records what it does to the position when it is placed (``order_rules.side_fields``). A cover
-- a BUY placed against a short -- that would buy past flat when its print arrives, because another
cover filled first, is cancelled ``PRACTICE_OVERCOVER`` at the fill, never filled: a short is never
turned into a long. Practice accounts cannot open a short until ADR 048 step 2; these tests put a
short on the ledger directly.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from constants_practice import PRACTICE_OVERCOVER_CODE
from practice import broker as practice_broker
from practice import order_rules
from practice.broker import for_venue, reset_for_tests
from practice.fees import Fees
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue

NOW = 1_700_000_000.0


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
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: FakeLive())
    yield SimpleNamespace(broker=for_venue("paper"))
    reset_for_tests()
    reset_venue()


def _go_short(broker, qty: float = 100) -> None:
    """Put a short on the ledger directly: the broker refuses to open one until step 2."""
    ledger = broker.ledger
    oid = ledger.alloc_id()
    row = broker._row(oid, "IMCC", "SELL", qty, "MKT", None, None, NOW, "manual", None, "DAY", short_entry=True)
    ledger.place(row, ts=NOW, source="manual")
    ledger.fill(oid, ts=NOW, price=10.0, basis="quote", fees=Fees(0.0, 0.0, 0.0, 0.0))
    assert ledger.held_qty("IMCC") == -qty


def test_rows_say_what_they_do_to_the_position():
    assert order_rules.side_fields("BUY", 0.0) == {"short_entry": False, "position_side": "long", "effect": "opens"}
    assert order_rules.side_fields("BUY", -100.0) == {"short_entry": False, "position_side": "short",
                                                       "effect": "closes"}
    assert order_rules.side_fields("SELL", 100.0) == {"short_entry": False, "position_side": "long",
                                                       "effect": "closes"}
    assert order_rules.side_fields("SELL", 0.0, short_entry=True) == {"short_entry": True,
                                                                       "position_side": "short", "effect": "opens"}
    assert order_rules.exit_side_fields({"position_side": "short"}) == {
        "short_entry": False, "position_side": "short", "effect": "closes"}


def test_a_placed_row_carries_its_side(paper):
    raw = paper.broker.place("IMCC", "BUY", 5, "LMT", limit_price=9.0)
    row = paper.broker.ledger.order_row(raw["order_id"])
    assert (row["short_entry"], row["position_side"], row["effect"]) == (False, "long", "opens")
    bracket = paper.broker.place_bracket("IMCC", "BUY", 1, entry_price=9.0, target_price=11.0, stop_price=8.5)
    target = paper.broker.ledger.order_row(bracket["target_order_id"])
    assert (target["position_side"], target["effect"]) == ("long", "closes")


def test_a_second_cover_is_cancelled_at_the_fill_never_flipping_the_short(paper):
    broker = paper.broker
    _go_short(broker, 100)
    first = broker.place("IMCC", "BUY", 100, "LMT", limit_price=9.50)
    second = broker.place("IMCC", "BUY", 100, "LMT", limit_price=9.50)
    assert first["broker_status"] == second["broker_status"] == "Submitted"
    covers = broker.ledger.order_row(second["order_id"])
    assert (covers["position_side"], covers["effect"]) == ("short", "closes")

    broker.try_fill_working("IMCC", [(NOW + 1, 9.40)])

    assert broker.ledger.held_qty("IMCC") == 0
    assert broker.ledger.order_row(first["order_id"])["status"] == "Filled"
    gone = broker.ledger.order_row(second["order_id"])
    assert gone["status"] == "Cancelled" and gone["reason_code"] == PRACTICE_OVERCOVER_CODE
    assert "never turns a short into a long" in gone["error"]


def test_a_cover_larger_than_the_short_is_refused_at_its_fill(paper):
    broker = paper.broker
    _go_short(broker, 100)
    row = {"symbol": "IMCC", "side": "BUY", "qty": 150.0, "effect": "closes"}
    refused = order_rules.fill_refusal(broker.ledger, row, 9.4)
    assert refused is not None and refused[1] == PRACTICE_OVERCOVER_CODE
    assert "100 short" in refused[0]
    assert order_rules.fill_refusal(broker.ledger, {**row, "qty": 100.0}, 9.4) is None
