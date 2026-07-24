"""finish_place must return ok=False when broker cancels with no fill (Error 10243)."""
from __future__ import annotations

import asyncio

import execution.broker_send as broker_send
import execution.telemetry as telemetry
from constants import IBKR_ERROR_FRACTIONAL_API, IBKR_FRACTIONAL_ORDER_API_MSG
from execution.models import ExecutionCommand, StageTimings


def _cmd() -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key="frac-1",
        source="flatten",
        symbol="IBKR",
        side="SELL",
        qty=0.0642,
        order_type="MKT",
    )


def test_finish_place_fails_on_cancelled_with_10243(monkeypatch):
    monkeypatch.setattr(broker_send.store, "update_stages", lambda *_a, **_k: None)
    watch = telemetry.OrderWatch(2928)
    watch.note_error(
        IBKR_ERROR_FRACTIONAL_API,
        "Fractional-sized order cannot be placed via API.",
    )
    watch.note_status("Cancelled")

    receipt = asyncio.run(
        broker_send.finish_place(
            "exec-1",
            _cmd(),
            StageTimings(received_ns=1),
            {"ok": True, "order_id": 2928},
            watch,
            "live",
            wait_ack=True,
        )
    )
    assert receipt.ok is False
    assert receipt.reason_code == "QTY_FRACTIONAL_API"
    assert receipt.broker_status == "Cancelled"
    assert "10243" in (receipt.error or "")
    assert receipt.error == IBKR_FRACTIONAL_ORDER_API_MSG


def test_finish_place_fails_on_cancelled_without_error_code(monkeypatch):
    monkeypatch.setattr(broker_send.store, "update_stages", lambda *_a, **_k: None)
    watch = telemetry.OrderWatch(99)
    watch.note_status("Cancelled")

    receipt = asyncio.run(
        broker_send.finish_place(
            "exec-2",
            _cmd(),
            StageTimings(received_ns=1),
            {"ok": True, "order_id": 99},
            watch,
            "live",
            wait_ack=True,
        )
    )
    assert receipt.ok is False
    assert receipt.reason_code == "BROKER_REJECT"
    assert receipt.broker_status == "Cancelled"


def test_finish_place_ok_when_cancelled_but_filled(monkeypatch):
    """A filled then closed path must not be treated as a reject."""
    monkeypatch.setattr(broker_send.store, "update_stages", lambda *_a, **_k: None)
    watch = telemetry.OrderWatch(100)
    watch.note_status("Filled")
    watch.note_filled()
    # Unusual, but has_fill() must win over a later Cancelled label.
    watch.ack_status = "Cancelled"

    receipt = asyncio.run(
        broker_send.finish_place(
            "exec-3",
            _cmd(),
            StageTimings(received_ns=1),
            {"ok": True, "order_id": 100},
            watch,
            "live",
            wait_ack=True,
        )
    )
    # First ack was Filled; we rewrote ack_status for the test — has_fill keeps ok.
    assert receipt.ok is True
