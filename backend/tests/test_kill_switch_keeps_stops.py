"""Freeze all orders keeps the stops that protect a position (ADR 048 gap 6, the operator's decision).

The kill switch still cancels every entry and every target on every venue, and refuses every new
order until it is reset. A working stop on the side that closes a held position -- a SELL stop under
a long, a BUY stop over a short -- no larger than it, stays resting, and the sweep lists it.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from execution import inflight, store, telemetry
from ibkr import safety as _safety
from kill_switch import sweep
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from sim.fill_model import Reference
from sim.mode import reset_for_tests as reset_venue, set_venue

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
    store.init_db()
    reset_venue()
    reset_for_tests()
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: FakeLive())
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    yield SimpleNamespace(broker=for_venue("paper"))
    reset_for_tests()
    inflight.reset_for_tests()
    telemetry.reset_for_tests()
    reset_venue()


def _row(**kw) -> dict:
    base = {"order_id": 7, "symbol": "RDYN", "side": "BUY", "qty": 416, "remaining_qty": 416,
            "order_type": "STP", "stop_price": 5.89, "status": "Submitted", "parent_id": None}
    base.update(kw)
    return base


def test_a_stop_on_the_closing_side_of_a_held_position_is_protective():
    assert sweep.protective_stop(_row(), {"RDYN": -416.0}) == "protects the 416 RDYN short"
    assert sweep.protective_stop(_row(side="SELL", stop_price=5.0), {"RDYN": 416.0}) == "protects the 416 RDYN long"
    assert sweep.protective_stop(_row(order_type="TRAIL"), {"RDYN": -500.0}) is not None


@pytest.mark.parametrize("row, held", [
    (_row(), {}),                                        # flat: a buy stop would open a long -- an entry
    (_row(side="SELL"), {"RDYN": -416.0}),               # a sell stop over a short adds to it
    (_row(qty=500, remaining_qty=500), {"RDYN": -416.0}),  # larger than the short: it would flip
    (_row(order_type="LMT"), {"RDYN": -416.0}),          # a target, not a stop
    (_row(status="PreSubmitted", parent_id=6), {"RDYN": -416.0}),  # waits on an entry: protects nothing yet
])
def test_entries_targets_and_stops_that_protect_nothing_are_cancelled(row, held):
    assert sweep.protective_stop(row, held) is None


def test_the_paper_sweep_keeps_the_protective_stop_and_cancels_the_rest(paper):
    broker = paper.broker
    assert broker.place("IMCC", "BUY", 10, "MKT")["broker_status"] == "Filled"
    stop = broker.place("IMCC", "SELL", 10, "STP", stop_price=9.50)["order_id"]
    target = broker.place("IMCC", "SELL", 5, "LMT", limit_price=11.00)["order_id"]
    entry = broker.place("IMCC", "BUY", 3, "LMT", limit_price=9.00)["order_id"]
    bracket = broker.place_bracket("IMCC", "BUY", 1, entry_price=9.00, target_price=11.0, stop_price=8.5)

    out = asyncio.run(sweep.sweep_venue("paper"))

    assert [k["order_id"] for k in out["kept"]] == [stop]
    assert out["kept"][0]["why"] == "protects the 10 IMCC long"
    assert {target, entry, bracket["order_id"]} <= set(out["cancelled"])
    assert out["failed"] == [] and out["error"] is None
    working = broker.working_orders()
    assert [row["order_id"] for row in working] == [stop]      # the stop alone still rests


def test_positions_nova_cannot_read_keep_no_stop_and_say_so(paper, monkeypatch):
    broker = paper.broker
    broker.place("IMCC", "BUY", 10, "MKT")
    stop = broker.place("IMCC", "SELL", 10, "STP", stop_price=9.50)["order_id"]
    monkeypatch.setattr(sweep, "_practice_held", lambda venue: (_ for _ in ()).throw(RuntimeError("ledger gone")))
    out = asyncio.run(sweep.sweep_venue("paper"))
    assert out["kept"] == [] and stop in out["cancelled"]
    assert sweep.POSITIONS_UNREAD in (out["note"] or "")


def test_the_trip_lists_the_stops_it_kept(paper, monkeypatch):
    import kill_switch

    monkeypatch.setattr(kill_switch._state, "save", lambda **kw: True)
    monkeypatch.setattr(kill_switch, "_record", lambda *a, **k: None)
    paper.broker.place("IMCC", "BUY", 10, "MKT")
    stop = paper.broker.place("IMCC", "SELL", 10, "STP", stop_price=9.50)["order_id"]
    try:
        answer = asyncio.run(kill_switch.trip())
    finally:
        kill_switch._tripped = False
    assert answer["kept_order_ids"] == [stop]
    paper_sweep = next(v for v in answer["sweep"] if v["venue"] == "paper")
    assert paper_sweep["kept"][0]["order_id"] == stop
