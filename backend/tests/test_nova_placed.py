"""Persist nova_placed_at on the execution ledger. Fixtures only -- no live IBKR."""
from __future__ import annotations

import asyncio

import pytest

import execution.store as store
from execution.models import ExecutionCommand, StageTimings
from execution.nova_placed import ledger_placed_iso, persist_nova_placed_at
from ibkr.order_times import clear_nova_placed_for_tests, resolve_submitted_at


STAMP = "2026-09-16T18:04:12.123456Z"
LATER = "2026-09-16T19:00:00.000000Z"


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    clear_nova_placed_for_tests()
    yield
    clear_nova_placed_for_tests()


def _reserve() -> str:
    execution_id, is_new = store.reserve(
        idempotency_key="nova-placed-1",
        operation="place",
        source="manual",
        symbol="ZTG",
        received_ns=1,
        payload={"qty": 1, "sent_qty": 1.0, "side": "BUY", "order_type": "LMT"},
    )
    assert is_new is True
    return execution_id


def test_persist_nova_placed_first_wins_and_survives_cleared_ram():
    execution_id = _reserve()
    assert persist_nova_placed_at(execution_id, STAMP) == STAMP
    assert persist_nova_placed_at(execution_id, LATER) == STAMP
    clear_nova_placed_for_tests()
    assert resolve_submitted_at(None, 116071) is None
    row = store.get_by_id(execution_id)
    assert row is not None
    assert row["payload"]["nova_placed_at"] == STAMP
    assert ledger_placed_iso(row) == STAMP


def test_ledger_placed_iso_falls_back_to_created_ts():
    from datetime import datetime, timezone

    execution_id = _reserve()
    row = store.get_by_id(execution_id)
    assert row is not None
    expected = datetime.fromtimestamp(float(row["created_ts"]), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    assert ledger_placed_iso(row) == expected


def test_finish_place_persists_nova_placed_at(monkeypatch):
    import execution.broker_send as broker_send
    from execution import telemetry

    execution_id = _reserve()
    monkeypatch.setattr(broker_send, "audit_place_watch", lambda *_a, **_k: None)
    watch = telemetry.OrderWatch(116071)
    receipt = asyncio.run(
        broker_send.finish_place(
            execution_id,
            ExecutionCommand(
                operation="place",
                idempotency_key="nova-placed-1",
                source="manual",
                symbol="ZTG",
                side="BUY",
                qty=1,
                order_type="LMT",
                limit_price=1.76,
            ),
            StageTimings(received_ns=1),
            {"ok": True, "order_id": 116071, "nova_placed_at": STAMP},
            watch,
            "paper",
            wait_ack=False,
        )
    )
    assert receipt.ok is True
    row = store.get_by_id(execution_id)
    assert row is not None
    assert row["payload"]["nova_placed_at"] == STAMP
    clear_nova_placed_for_tests()
    assert resolve_submitted_at(None, 116071) is None
    assert ledger_placed_iso(row) == STAMP


def test_send_broker_cancel_marks_presubmitted_place(monkeypatch):
    """Cancel watch is fresh=True -- place row must still become Cancelled."""
    import execution.broker_send as broker_send
    from execution.store_facts import record_broker_facts

    place_id, _ = store.reserve(
        idempotency_key="nova-placed-place",
        operation="place",
        source="manual",
        symbol="ZTG",
        received_ns=1,
        payload={"qty": 1, "sent_qty": 1.0, "side": "BUY", "order_type": "LMT"},
    )
    store.update_stages(
        place_id,
        order_id=116071,
        status="acked",
        broker_status="PreSubmitted",
        broker_ack_ns=11,
    )
    persist_nova_placed_at(place_id, STAMP)
    record_broker_facts(place_id, perm_id=888777)
    cancel_id, _ = store.reserve(
        idempotency_key="nova-placed-cancel",
        operation="cancel",
        source="manual",
        symbol="ZTG",
        received_ns=2,
        payload={},
    )

    async def _fake_cancel(order_id, *, watch=None):
        if watch is not None:
            watch.perm_id = 888777
            watch.ack_status = "Cancelled"
            watch.ack_ns = 99
        return {"ok": True, "verified_gone": True, "order_id": order_id}

    monkeypatch.setattr(broker_send, "cancel_order_verified_on_ib", _fake_cancel)
    monkeypatch.setattr(broker_send._client, "account_mode", lambda: "paper")
    monkeypatch.setattr(broker_send.inflight, "release_order", lambda *_a, **_k: None)

    receipt = asyncio.run(
        broker_send.send_broker(
            ExecutionCommand(
                operation="cancel",
                idempotency_key="nova-placed-cancel",
                source="manual",
                symbol="ZTG",
                order_id=116071,
            ),
            cancel_id,
            StageTimings(received_ns=2),
            wait_ack=False,
            reject=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("reject")),
        )
    )
    assert receipt.ok is True
    place = store.get_by_id(place_id)
    cancel = store.get_by_id(cancel_id)
    assert place["broker_status"] == "Cancelled"
    assert place["status"] == "acked"
    assert place["payload"]["nova_placed_at"] == STAMP
    assert cancel["operation"] == "cancel"
    assert cancel["broker_status"] == "Cancelled"
