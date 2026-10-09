"""IBKR saying an order is already closed is a cancel, never a reject (check 4 of the 2026-10-09 audit).

Error 10148 answers a cancel of an order that had filled or been cancelled; Error 201 naming the OCA
group is a one-cancels-all sibling closed because another member filled. Neither is IBKR refusing the
order, and a 10148 that says ``state: Filled`` means the cancel came too late -- the order filled.
"""
from __future__ import annotations

import asyncio

import pytest

import execution.broker_send as broker_send
import execution.store as store
import ibkr.client as client_mod
import ibkr.orders as orders_mod
from execution import telemetry
from execution.models import ExecutionCommand, StageTimings
from execution.order_outcome import closed_state, is_closure_notice, latest_hard_error, reduce_order_events

OCA = "Order rejected - reason:OCA group is already filled."
ALREADY_FILLED = "OrderId 55 that needs to be cancelled cannot be cancelled, state: Filled."
ALREADY_CANCELLED = "OrderId 56 that needs to be cancelled cannot be cancelled, state: Cancelled."


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    telemetry.reset_for_tests()
    monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
    yield
    telemetry.reset_for_tests()


def test_10148_and_an_oca_201_are_closure_notices_and_never_latch_as_the_hard_error():
    assert is_closure_notice(10148, ALREADY_FILLED) and is_closure_notice(201, OCA)
    assert not is_closure_notice(201, "Order rejected - reason: no opening trades")
    assert latest_hard_error([(10148, ALREADY_CANCELLED), (201, OCA)]) == (None, None)
    assert latest_hard_error([(201, "Order rejected - reason: margin")])[0] == 201
    assert closed_state([(10148, ALREADY_FILLED)]) == "Filled"
    assert closed_state([(10148, ALREADY_CANCELLED)]) == "Cancelled"


def test_an_order_its_oca_group_closed_reads_cancelled_not_rejected():
    events = [{"kind": "status", "status": "Cancelled"}, {"kind": "error", "code": 201, "message": OCA}]
    outcome = reduce_order_events(events)
    assert outcome.verdict == "cancelled" and outcome.open_reject_modal is False
    refused = [{"kind": "status", "status": "Cancelled"}, {"kind": "error", "code": 201, "message": "margin"}]
    assert reduce_order_events(refused).verdict == "rejected"


def _place_row(key: str, order_id: int) -> str:
    execution_id, _ = store.reserve(
        idempotency_key=key, operation="place", source="manual", symbol="ZTG", received_ns=1,
        payload={"qty": 1, "sent_qty": 1, "side": "BUY", "venue": "live"},
    )
    store.update_stages(execution_id, status="acked", order_id=order_id, mode="live", broker_status="Submitted")
    return execution_id


def test_a_place_its_oca_group_closed_ends_cancelled_not_failed(monkeypatch):
    monkeypatch.setattr(orders_mod, "open_orders", lambda **_k: [])
    execution_id = _place_row("oca-place", 61)
    watch = telemetry.watch_order(61, execution_id, side="BUY")
    watch.note_status("Cancelled")
    watch.note_error(201, OCA)
    cmd = ExecutionCommand(operation="place", idempotency_key="oca-place", source="manual", symbol="ZTG",
                           side="BUY", qty=1, order_type="LMT", limit_price=1.0)
    receipt = asyncio.run(broker_send.finish_place(
        execution_id, cmd, StageTimings(received_ns=1), {"ok": True, "order_id": 61}, watch, "live",
    ))
    assert receipt.ok is True and receipt.reason_code is None
    assert store.get_by_id(execution_id)["status"] == "cancelled"


def test_a_cancel_that_came_too_late_never_marks_the_filled_order_cancelled(monkeypatch):
    """The order filled as the cancel went out: it left the working orders because it filled, and the
    place row was marked Cancelled because the order was "gone"."""
    place_id = _place_row("too-late-place", 55)

    async def verified(order_id, *, watch=None):
        watch.note_error(10148, ALREADY_FILLED)
        return {"ok": True, "error": None, "verified_gone": True, "order_id": order_id}

    monkeypatch.setattr(broker_send, "cancel_order_verified_on_ib", verified)
    cancel_id, _ = store.reserve(idempotency_key="too-late-cancel", operation="cancel", source="manual",
                                 symbol="ZTG", received_ns=1, payload={"venue": "live"})
    cmd = ExecutionCommand(operation="cancel", idempotency_key="too-late-cancel", source="manual", order_id=55)
    receipt = asyncio.run(broker_send.send_broker(
        cmd, cancel_id, StageTimings(received_ns=1), wait_ack=False, reject=None, venue="live",
    ))
    assert receipt.ok is True and receipt.reason_code == "CANCEL_TOO_LATE" and receipt.broker_status == "Filled"
    assert store.get_by_id(place_id)["broker_status"] == "Submitted"
    assert store.get_by_id(cancel_id)["reason_code"] == "CANCEL_TOO_LATE"


def test_a_cancel_of_an_order_already_cancelled_still_reads_cancelled(monkeypatch):
    place_id = _place_row("already-cancelled", 56)

    async def verified(order_id, *, watch=None):
        watch.note_error(10148, ALREADY_CANCELLED)
        return {"ok": True, "error": None, "verified_gone": True, "order_id": order_id}

    monkeypatch.setattr(broker_send, "cancel_order_verified_on_ib", verified)
    cancel_id, _ = store.reserve(idempotency_key="already-cancelled-cancel", operation="cancel",
                                 source="manual", symbol="ZTG", received_ns=1, payload={"venue": "live"})
    cmd = ExecutionCommand(operation="cancel", idempotency_key="already-cancelled-cancel", source="manual",
                           order_id=56)
    receipt = asyncio.run(broker_send.send_broker(
        cmd, cancel_id, StageTimings(received_ns=1), wait_ack=False, reject=None, venue="live",
    ))
    assert receipt.ok is True and receipt.reason_code is None
    assert store.get_by_id(place_id)["broker_status"] == "Cancelled"
