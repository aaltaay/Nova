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


# ---------------------------------------------------------------- PR #782 review: the kept stops never pass the position
def _stop(order_id: int, side: str, qty: float, stop: float | None, **kw) -> dict:
    return _row(order_id=order_id, side=side, qty=qty, remaining_qty=qty, stop_price=stop, **kw)


def test_two_stops_that_each_cover_the_long_keep_only_the_nearest():
    rows = [_stop(11, "SELL", 100, 9.00), _stop(12, "SELL", 100, 9.50)]
    kept, dropped = sweep.kept_stops(rows, {"RDYN": 100.0})
    assert kept == {1: "protects the 100 RDYN long"}           # 9.50 fires first: it limits the loss most
    assert len(dropped) == 1 and dropped[0].startswith("order 11 (RDYN stop, 100)")


def test_a_ladder_of_stops_is_kept_until_the_next_would_pass_the_position():
    rows = [_stop(21, "SELL", 300, 8.50), _stop(22, "SELL", 200, 9.00), _stop(23, "SELL", 100, 9.50)]
    kept, dropped = sweep.kept_stops(rows, {"RDYN": 300.0})
    assert kept == {2: "protects 100 of the 300 RDYN long", 1: "protects 200 of the 300 RDYN long"}
    assert [d.split(" (")[0] for d in dropped] == ["order 21"]


def test_a_shorts_buy_stops_keep_the_lowest_first_and_a_stop_nova_cannot_cancel_counts_first():
    rows = [_stop(31, "BUY", 416, 6.40), _stop(32, "BUY", 416, 5.89)]
    kept, _ = sweep.kept_stops(rows, {"RDYN": -416.0})
    assert list(kept) == [1]                                   # 5.89 sits nearer a short's market
    outside = [_stop(0, "BUY", 416, 6.40), _stop(32, "BUY", 416, 5.89)]
    kept, dropped = sweep.kept_stops(outside, {"RDYN": -416.0})
    assert list(kept) == [0] and dropped[0].startswith("order 32")   # TWS's stop rests whatever Nova does
    assert "keeping it too would take the closing orders past the 416 RDYN short" in dropped[0]
    # A closing order Nova cannot cancel takes its room even when it is no stop, or too big to keep.
    over = [_stop(0, "BUY", 500, 6.40), _stop(32, "BUY", 416, 5.89)]
    kept, dropped = sweep.kept_stops(over, {"RDYN": -416.0})
    assert kept == {} and dropped[0].startswith("order 32")   # the sweep names TWS's 500 as a problem
    target = [_row(order_id=0, order_type="LMT", stop_price=None, limit_price=5.20), _stop(32, "BUY", 416, 5.89)]
    kept, dropped = sweep.kept_stops(target, {"RDYN": -416.0})
    assert kept == {} and dropped[0].startswith("order 32")


def test_a_live_bracket_stop_whose_entry_still_works_goes_with_its_entry():
    entry = {"order_id": 40, "symbol": "RDYN", "side": "SELL", "qty": 100, "remaining_qty": 100,
             "filled_qty": 0.0, "order_type": "LMT", "status": "Submitted", "parent_id": None}
    waiting = _stop(42, "BUY", 100, 5.89, status="PreSubmitted", parent_id=40)
    # The account already holds RDYN short from earlier: the waiting stop still protects none of it.
    kept, _ = sweep.kept_stops([entry, waiting], {"RDYN": -100.0})
    assert kept == {}
    # Its entry filled (no longer working): IBKR holds the stop PreSubmitted, and it protects the short.
    kept, _ = sweep.kept_stops([waiting], {"RDYN": -100.0})
    assert kept == {0: "protects the 100 RDYN short"}
    # An entry that filled some may already have its exits working: judged as a stop.
    part = {**entry, "filled_qty": 40.0, "remaining_qty": 60}
    assert sweep.kept_stops([part, waiting], {"RDYN": -100.0})[0] == {1: "protects the 100 RDYN short"}


def test_the_paper_sweep_cancels_a_second_full_size_stop_and_says_why(paper):
    broker = paper.broker
    broker.place("IMCC", "BUY", 10, "MKT")
    near = broker.place("IMCC", "SELL", 10, "STP", stop_price=9.50)
    far = broker.place("IMCC", "SELL", 10, "STP", stop_price=9.00)
    assert near.get("order_id") and far.get("order_id"), (near, far)

    out = asyncio.run(sweep.sweep_venue("paper"))

    assert [k["order_id"] for k in out["kept"]] == [near["order_id"]]
    assert far["order_id"] in out["cancelled"]
    assert "stops beyond the position were cancelled" in (out["note"] or "")
    assert [row["order_id"] for row in broker.working_orders()] == [near["order_id"]]


def test_live_order_rows_carry_their_brackets_entry():
    from ibkr.order_rows import trade_to_order_row

    def trade(parent_id):
        return SimpleNamespace(
            order=SimpleNamespace(orderId=42, permId=9, parentId=parent_id, action="BUY", totalQuantity=100,
                                  orderType="STP", lmtPrice=0.0, auxPrice=5.89, outsideRth=False, tif="DAY"),
            contract=SimpleNamespace(symbol="RDYN"),
            orderStatus=SimpleNamespace(status="PreSubmitted", filled=0, remaining=100, avgFillPrice=0.0),
            fills=[], log=[],
        )

    assert trade_to_order_row(trade(40))["parent_id"] == 40
    assert trade_to_order_row(trade(0))["parent_id"] is None
