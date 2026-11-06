"""A protective stop outside regular hours is a stop-limit on every venue (ADR 007, operator decision 2026-11-05)."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from constants_nova_os import NOVA_OS_NYSE_EARLY_CLOSES
from constants_practice import PRACTICE_NO_LIVE_PRINT_CODE
from execution import stop_shape, telemetry
from execution.models import ExecutionCommand
from ibkr import client as client_mod
from ibkr import orders as orders_mod
from practice import broker as practice_broker
from practice.broker import for_venue, reset_for_tests
from practice.clock import ET
from sim.fill_model import Reference, on_print

NOW = datetime(2026, 9, 21, 8, 0, tzinfo=ET).timestamp()


class FakeLive:
    def __init__(self) -> None:
        self.now = NOW

    def reference(self, symbol: str) -> Reference:
        return Reference(10.0, 9.98, 10.02, live=True)

    def admission(self, symbol: str):
        return (True, "OK", None) if symbol == "IMCC" else (False, "dark", PRACTICE_NO_LIVE_PRINT_CODE)

    def prints_between(self, symbol: str, after_ts: float, through_ts: float):
        return []

    def now_ts(self) -> float:
        return self.now


@pytest.fixture
def paper(monkeypatch):
    reset_for_tests()
    telemetry.reset_for_tests()
    fake = FakeLive()
    monkeypatch.setattr(practice_broker, "LiveReference", lambda: fake)
    yield SimpleNamespace(broker=for_venue("paper"), ref=fake)
    reset_for_tests()
    telemetry.reset_for_tests()


def _bracket(paper) -> dict:
    out = paper.broker.place_bracket("IMCC", "BUY", 10, 10.05, 11.0, 9.5, stop_limit=stop_shape.limit_for("SELL", 9.5))
    assert out["ok"]
    return out


def _row(paper, order_id: int) -> dict:
    return paper.broker.ledger.order_row(int(order_id))


def test_the_limit_sits_two_percent_past_the_stop_on_each_side():
    assert stop_shape.limit_for("SELL", 10.0) == 9.8
    assert stop_shape.limit_for("BUY", 10.0) == 10.2
    assert stop_shape.limit_for("SELL", 0.5) == 0.49


def test_only_a_stop_sent_outside_regular_hours_is_a_stop_limit():
    base = dict(idempotency_key="k", source="manual", stop_price=10.0)
    assert stop_shape.exit_limit(ExecutionCommand(operation="bracket", outside_rth=True, **base), NOW) == 9.8
    assert stop_shape.exit_limit(ExecutionCommand(operation="bracket", outside_rth=True, short_entry=True,
                                                  **base), NOW) == 10.2
    assert stop_shape.exit_limit(ExecutionCommand(operation="exit_oco", outside_rth=True, side="BUY", **base),
                                 NOW) == 10.2
    assert stop_shape.exit_limit(ExecutionCommand(operation="bracket", outside_rth=False, **base), NOW) is None


_EARLY_CLOSE = datetime.fromisoformat(sorted(NOVA_OS_NYSE_EARLY_CLOSES)[0]).replace(tzinfo=ET)


@pytest.mark.parametrize("when, limit", [
    (datetime(2026, 9, 21, 9, 29, tzinfo=ET), 9.8),
    (datetime(2026, 9, 21, 9, 30, tzinfo=ET), None),
    (datetime(2026, 9, 21, 10, 0, tzinfo=ET), None),      # Extended Hours saved, a 10:00 bracket: a plain stop
    (datetime(2026, 9, 21, 15, 59, tzinfo=ET), None),
    (datetime(2026, 9, 21, 16, 0, tzinfo=ET), 9.8),
    (datetime(2026, 9, 19, 12, 0, tzinfo=ET), 9.8),       # a Saturday
    (_EARLY_CLOSE.replace(hour=12, minute=30), None),
    (_EARLY_CLOSE.replace(hour=13, minute=30), 9.8),      # past an early close, though 16:00 has not come
])
def test_extended_hours_is_a_permission_and_the_venues_clock_is_the_session(when, limit):
    cmd = ExecutionCommand(operation="bracket", idempotency_key="k", source="manual", stop_price=10.0, outside_rth=True)
    assert stop_shape.exit_limit(cmd, when.timestamp()) == limit


def test_a_print_inside_the_limit_fills_and_a_gap_past_it_does_not():
    assert on_print("SELL", "STP LMT", 9.45, limit=9.31, stop=9.5).price == 9.45
    assert on_print("SELL", "STP LMT", 9.20, limit=9.31, stop=9.5) is None
    assert on_print("SELL", "STP LMT", 9.60, limit=9.31, stop=9.5) is None


def test_a_gap_past_the_limit_rests_as_a_limit_and_fills_on_the_way_back(paper):
    stop_id = _bracket(paper)["stop_order_id"]
    assert _row(paper, stop_id)["order_type"] == "STP LMT"
    paper.ref.now = NOW + 10
    paper.broker.try_fill_working("IMCC", [(NOW + 5, 9.20)])          # through the stop and the limit
    row = _row(paper, stop_id)
    assert row["order_type"] == "LMT" and row["status"] != "Filled"
    assert paper.broker.ledger.held_qty("IMCC") == 10                 # a gap leaves it unfilled: the stated price
    paper.broker.try_fill_working("IMCC", [(NOW + 20, 9.70)])         # above the stop: a triggered order still sells
    assert _row(paper, stop_id)["status"] == "Filled"
    assert paper.broker.ledger.held_qty("IMCC") == 0


def test_moving_the_stop_moves_its_limit(paper):
    stop_id = _bracket(paper)["stop_order_id"]
    assert paper.broker.replace(int(stop_id), stop_price=9.75)["ok"]
    row = _row(paper, stop_id)
    assert (row["stop_price"], row["limit_price"]) == (9.75, stop_shape.limit_for("SELL", 9.75))


def test_live_sends_the_loss_as_a_stop_limit_outside_hours(monkeypatch):
    from ib_async import IB

    placed: list = []
    ids = iter(range(100, 110))
    gateway = SimpleNamespace(client=SimpleNamespace(getReqId=lambda: next(ids)),
                              placeOrder=lambda _c, order: placed.append(order))
    gateway.bracketOrder = lambda *a, **k: IB.bracketOrder(gateway, *a, **k)
    monkeypatch.setattr(orders_mod, "_safety_check", lambda: (True, ""))
    monkeypatch.setattr(orders_mod, "_ib_sync", lambda fn, label, timeout=15.0: fn())
    monkeypatch.setattr(client_mod, "get_ib", lambda: gateway)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
    monkeypatch.setattr("sim.mode.is_practice_venue", lambda: False)
    out = orders_mod.place_bracket_order(symbol="ZTG", side="BUY", qty=1, entry_price=2.0, stop_price=1.9,
                                         target_price=2.2, outside_rth=True, stop_limit=1.86)
    assert out["ok"] is True
    stop = placed[-1]
    assert (stop.orderType, stop.auxPrice, stop.lmtPrice, stop.outsideRth) == ("STP LMT", 1.9, 1.86, True)
    assert stop.transmit is True
