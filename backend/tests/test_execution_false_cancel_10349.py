"""Error 10349 / Cancelled→PreSubmitted must not false-fail a live place."""
from __future__ import annotations

import asyncio

import execution.broker_send as broker_send
import execution.telemetry as telemetry
from execution.models import ExecutionCommand, StageTimings


def _cmd() -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key="tif-1",
        source="manual",
        symbol="CYCU",
        side="BUY",
        qty=1,
        order_type="MKT",
        outside_rth=True,
    )


def test_finish_place_heals_cancelled_then_presubmitted(monkeypatch):
    monkeypatch.setattr(broker_send.store, "update_stages", lambda *_a, **_k: None)
    import execution.place_reject_guard as guard
    monkeypatch.setattr(guard, "EXECUTION_CANCEL_ACK_GRACE_SEC", 0.0)
    monkeypatch.setattr(guard, "order_still_open", lambda _oid: True)

    watch = telemetry.OrderWatch(95053)
    watch.note_error(10349, "Order TIF was set to DAY based on order preset.")
    watch.note_status("Cancelled")
    watch.note_status("PreSubmitted")

    receipt = asyncio.run(
        broker_send.finish_place(
            "exec-tif",
            _cmd(),
            StageTimings(received_ns=1),
            {"ok": True, "order_id": 95053},
            watch,
            "live",
            wait_ack=True,
        )
    )
    assert receipt.ok is True
    assert receipt.broker_status == "PreSubmitted"


def test_note_status_upgrades_cancelled_to_presubmitted():
    watch = telemetry.OrderWatch(1)
    watch.note_status("Cancelled")
    assert watch.ack_status == "Cancelled"
    watch.note_status("PreSubmitted")
    assert watch.ack_status == "PreSubmitted"
    assert watch.latest_status == "PreSubmitted"


def test_finish_place_still_rejects_true_cancel(monkeypatch):
    monkeypatch.setattr(broker_send.store, "update_stages", lambda *_a, **_k: None)
    import execution.place_reject_guard as guard
    monkeypatch.setattr(guard, "EXECUTION_CANCEL_ACK_GRACE_SEC", 0.0)
    monkeypatch.setattr(guard, "order_still_open", lambda _oid: False)

    watch = telemetry.OrderWatch(42)
    watch.note_status("Cancelled")

    receipt = asyncio.run(
        broker_send.finish_place(
            "exec-real-cancel",
            _cmd(),
            StageTimings(received_ns=1),
            {"ok": True, "order_id": 42},
            watch,
            "live",
            wait_ack=True,
        )
    )
    assert receipt.ok is False
    assert receipt.reason_code == "BROKER_REJECT"
