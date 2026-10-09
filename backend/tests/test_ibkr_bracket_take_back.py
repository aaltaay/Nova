"""A Live bracket reaches IBKR whole, or what went is taken back (check 4 of the 2026-10-09 audit).

``ib.bracketOrder`` sends the entry and target untransmitted and the stop transmits all three. A
later leg that fails, or that IBKR refuses as it transmits, must not leave the entry held at the
Gateway or working without its stop.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import execution.live_send as live_send
import execution.store as store
import ibkr.client as client_mod
import ibkr.order_bracket as order_bracket
import ibkr.orders as orders_mod
from execution import persist_queue, telemetry
from execution.bracket_guard import REASON, BracketGuard
from execution.broker_send import send_broker
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from execution.order_watch import OrderWatch
from execution.telemetry_handlers import make_handlers
from ibkr import loop_supervisor

REF = "nova-0123456789abcdef"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    telemetry.reset_for_tests()
    monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
    yield
    loop_supervisor.stop()
    telemetry.reset_for_tests()


def _reserve(key: str) -> str:
    execution_id, _ = store.reserve(
        idempotency_key=key, operation="bracket", source="manual", symbol="ZTG", received_ns=1,
        payload={"qty": 1, "sent_qty": 1, "venue": "live"},
    )
    return execution_id


class _Gateway:
    """An ``IB()`` whose ``placeOrder`` breaks on one leg."""

    def __init__(self, *, break_on: int | None) -> None:
        from ib_async import IB

        self.next_id = 100
        self.break_on = break_on
        self.placed: list = []
        self.cancelled: list[int] = []
        self.client = SimpleNamespace(getReqId=self._next)
        self.bracketOrder = lambda *a, **k: IB.bracketOrder(self, *a, **k)

    def _next(self) -> int:
        self.next_id += 1
        return self.next_id

    def placeOrder(self, _contract, order):
        if len(self.placed) == self.break_on:
            raise ConnectionError("socket closed mid-bracket")
        self.placed.append(order)

    def cancelOrder(self, order):
        self.cancelled.append(int(order.orderId))


def _arm(monkeypatch, gateway: _Gateway) -> None:
    monkeypatch.setattr(orders_mod, "_safety_check", lambda: (True, ""))
    monkeypatch.setattr(orders_mod, "_ib_sync", lambda fn, label, timeout=15.0: fn())
    monkeypatch.setattr(client_mod, "get_ib", lambda: gateway)


def _bracket() -> dict:
    return orders_mod.place_bracket_order(
        symbol="ZTG", side="BUY", qty=1, entry_price=2.0, stop_price=1.9, target_price=2.2, order_ref=REF,
    )


def test_every_leg_carries_the_reference_with_its_role(monkeypatch):
    gateway = _Gateway(break_on=None)
    _arm(monkeypatch, gateway)
    out = _bracket()
    assert out["ok"] is True
    assert [o.orderRef for o in gateway.placed] == [REF, f"{REF}-tp", f"{REF}-sl"]
    assert [o.transmit for o in gateway.placed] == [False, False, True]


def test_a_stop_that_never_went_out_takes_back_the_legs_held_at_the_gateway(monkeypatch):
    gateway = _Gateway(break_on=2)                 # the entry and target went; the transmitting stop did not
    _arm(monkeypatch, gateway)
    out = _bracket()
    entry, target = (o.orderId for o in gateway.placed)
    assert out["ok"] is False
    assert gateway.cancelled == [target, entry]    # exits first, then the entry
    assert out["taken_back"] == [target, entry] and out["not_taken_back"] == []
    assert "Nova cancelled them" in out["error"]


def test_a_first_leg_that_fails_leaves_nothing_to_take_back(monkeypatch):
    gateway = _Gateway(break_on=0)
    _arm(monkeypatch, gateway)
    out = _bracket()
    assert out["ok"] is False and gateway.cancelled == [] and "socket closed" in out["error"]


def _legs(execution_id: str) -> dict:
    return {role: OrderWatch(oid, execution_id, leg_role=role) for role, oid in
            (("parent", 601), ("target", 602), ("stop", 603))}


def test_a_leg_ibkr_refuses_before_it_worked_takes_the_rest_back(monkeypatch):
    execution_id = _reserve("guard-1")
    taken: list = []
    monkeypatch.setattr(order_bracket, "take_back", lambda ids: taken.append(list(ids)) or (list(ids), []))
    legs = _legs(execution_id)
    guard = BracketGuard(execution_id, legs)
    legs["stop"].note_error(201, "Order rejected - reason: the stop price is invalid")
    legs["stop"].note_status("Cancelled")
    assert guard.refused == "stop" and taken == [[601, 602]]
    row = store.get_by_id(execution_id)
    assert row["status"] == "failed" and row["reason_code"] == REASON
    assert "IBKR refused the bracket's stop (Error 201" in row["error"] and "cancelled the rest" in row["error"]


def test_a_leg_that_worked_then_closed_is_not_a_refusal(monkeypatch):
    execution_id = _reserve("guard-2")
    monkeypatch.setattr(order_bracket, "take_back", lambda ids: pytest.fail("nothing to take back"))
    legs = _legs(execution_id)
    guard = BracketGuard(execution_id, legs)
    legs["stop"].note_status("PreSubmitted")
    legs["stop"].note_status("Cancelled")           # the target filled: the stop's OCA sibling closed it
    assert guard.refused is None


def test_a_stop_refused_after_the_entry_filled_says_the_position_has_no_stop(monkeypatch):
    execution_id = _reserve("guard-3")
    monkeypatch.setattr(order_bracket, "take_back", lambda ids: pytest.fail("a filled entry is never cancelled"))
    legs = _legs(execution_id)
    BracketGuard(execution_id, legs)
    legs["parent"].note_status("Filled", filled=1.0)
    legs["stop"].note_error(201, "Order rejected - reason: stop price above the market")
    legs["stop"].note_status("Inactive")
    assert "NO STOP" in store.get_by_id(execution_id)["error"]


def test_a_leg_cancelled_before_it_worked_with_no_error_is_a_cancel_not_a_refusal(monkeypatch):
    execution_id = _reserve("guard-4")
    monkeypatch.setattr(order_bracket, "take_back", lambda ids: pytest.fail("an operator's cancel is not refused"))
    legs = _legs(execution_id)
    guard = BracketGuard(execution_id, legs)
    legs["target"].note_status("Cancelled")         # the operator cancelled the bracket before IBKR answered
    assert guard.refused is None


def test_the_live_bracket_receipt_names_the_refusal_without_waiting_out_the_ack(monkeypatch):
    loop_supervisor.start()
    monkeypatch.setattr(live_send, "EXECUTION_ACK_WAIT_SEC", 3.0)
    taken: list = []
    monkeypatch.setattr(order_bracket, "take_back", lambda ids: taken.append(list(ids)) or (list(ids), []))
    on_err, on_status = make_handlers(telemetry._watches.get)[:2]

    def status(order_id: int, text: str):
        return SimpleNamespace(order=SimpleNamespace(orderId=order_id, permId=0),
                               orderStatus=SimpleNamespace(status=text, filled=0.0, remaining=1.0, avgFillPrice=0.0))

    def fake_bracket(**kwargs):
        assert kwargs["order_ref"]
        loop = asyncio.get_running_loop()

        def ibkr_refuses() -> None:                 # ib_async: the Cancelled status first, then the error
            on_status(status(703, "Cancelled"))
            on_err(703, 201, "Order rejected - reason: stop price below the market")

        loop.call_soon(ibkr_refuses)
        return {"ok": True, "parent_order_id": 701, "target_order_id": 702, "stop_order_id": 703,
                "error": None, "mode": "live", "nova_placed_at": None}

    monkeypatch.setattr(orders_mod, "place_bracket_order", fake_bracket)
    execution_id = _reserve("live-bracket-refused")
    cmd = ExecutionCommand(operation="bracket", idempotency_key="live-bracket-refused", source="manual",
                           symbol="ZTG", side="BUY", qty=1, entry_price=2.0, stop_price=1.9, target_price=2.2,
                           order_type="LMT")

    def reject(execution_id, cmd, timings, detail, reason_code):
        return ExecutionReceipt(ok=False, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
                                idempotency_key=cmd.idempotency_key, error=detail, reason_code=reason_code)

    async def run():
        began = asyncio.get_running_loop().time()
        receipt = await send_broker(cmd, execution_id, StageTimings(received_ns=1), wait_ack=True,
                                    reject=reject, venue="live")
        return receipt, asyncio.get_running_loop().time() - began

    receipt, took = asyncio.run(run())
    assert receipt.ok is False and receipt.reason_code == "BRACKET_LEG_REFUSED"
    assert "stop price below the market" in receipt.error
    assert took < 2.0 and taken == [[701, 702]]
    assert persist_queue.flush()                    # the guard writes from IBKR's thread, through the queue
    assert store.get_by_id(execution_id)["status"] == "failed"
