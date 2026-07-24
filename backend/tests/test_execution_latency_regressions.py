"""Regression coverage for execution latency lifecycle fixes."""
from __future__ import annotations

import asyncio
import sqlite3

import pytest

import execution.broker_send as broker_send
import execution.service as service
import execution.store as store
import execution.telemetry as telemetry
import ibkr.account as account_mod
import ibkr.client as client_mod
import ibkr.orders as orders_mod
import ibkr.safety as safety_mod
from constants import EXECUTION_LEDGER_DB_FILENAME
from execution.latency import latency_summary
from execution.models import ExecutionCommand
from tools import execution_latency_probe


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "cache_dir", lambda: tmp_path)
    telemetry.reset_for_tests()
    store.init_db()
    yield
    telemetry.reset_for_tests()


def _arm_synthetic(monkeypatch) -> None:
    monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    monkeypatch.setattr(safety_mod, "orders_enabled", lambda: True)
    monkeypatch.setattr(safety_mod, "gateway_mode", lambda: "paper")
    monkeypatch.setattr(safety_mod, "live_trading_confirmed", lambda: False)
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000.0, "pending": False},
    )
    monkeypatch.setattr(account_mod, "get_positions", lambda: [])


def _place_command(key: str) -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key=key,
        source="manual",
        symbol="AAPL",
        side="BUY",
        qty=1,
        order_type="LMT",
        limit_price=0.01,
        skip_risk=True,
        skip_concurrency=True,
    )


class _Event:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _FakeIb:
    def __init__(self) -> None:
        self.orderStatusEvent = _Event()
        self.execDetailsEvent = _Event()
        self.errorEvent = _Event()


def test_telemetry_handlers_wire_once_per_reconnected_instance():
    old_ib = _FakeIb()
    new_ib = _FakeIb()

    telemetry.ensure_handlers(old_ib)
    telemetry.ensure_handlers(old_ib)
    telemetry.ensure_handlers(new_ib)
    telemetry.ensure_handlers(new_ib)

    for ib in (old_ib, new_ib):
        assert len(ib.orderStatusEvent.handlers) == 1
        assert len(ib.execDetailsEvent.handlers) == 1
        assert len(ib.errorEvent.handlers) == 1


def test_slow_ack_does_not_hold_send_lock(monkeypatch):
    _arm_synthetic(monkeypatch)
    monkeypatch.setattr(broker_send, "EXECUTION_ACK_WAIT_SEC", 0.2)
    place_called = asyncio.Event()
    cancel_calls: list[int] = []

    def place(**_kwargs):
        place_called.set()
        return {"ok": True, "order_id": 501, "error": None, "mode": "paper"}

    monkeypatch.setattr(orders_mod, "place_order", place)
    monkeypatch.setattr(
        orders_mod,
        "cancel_order",
        lambda order_id: cancel_calls.append(order_id) or {"ok": True},
    )

    async def exercise() -> None:
        slow = asyncio.create_task(service.execute(_place_command("slow-ack")))
        await place_called.wait()
        urgent = await asyncio.wait_for(
            service.execute(
                ExecutionCommand(
                    operation="cancel",
                    idempotency_key="urgent-cancel",
                    source="kill",
                    order_id=501,
                    skip_risk=True,
                    skip_concurrency=True,
                ),
                wait_ack=False,
            ),
            timeout=0.05,
        )
        assert urgent.ok is True
        assert cancel_calls == [501]
        assert slow.done() is False
        await slow

    asyncio.run(exercise())


def test_fill_rollup_has_send_and_ack_deltas():
    execution_id, _ = store.reserve(
        idempotency_key="fill-run:place",
        operation="place",
        source="benchmark",
        symbol="AAPL",
        received_ns=1_000_000,
    )
    store.update_stages(
        execution_id,
        status="filled",
        validation_completed_ns=2_000_000,
        broker_sent_ns=3_000_000,
        broker_ack_ns=5_000_000,
        filled_ns=11_000_000,
    )

    summary = latency_summary(idempotency_prefix="fill-run:")
    send_fill = summary["fill_ms"]["send_to_fill"]
    ack_fill = summary["fill_ms"]["ack_to_fill"]
    assert {
        key: send_fill[key] for key in ("count", "p50", "p95", "p99", "max")
    } == {"count": 1, "p50": 8.0, "p95": 8.0, "p99": 8.0, "max": 8.0}
    assert {
        key: ack_fill[key] for key in ("count", "p50", "p95", "p99", "max")
    } == {"count": 1, "p50": 6.0, "p95": 6.0, "p99": 6.0, "max": 6.0}
    assert send_fill["sufficient"] is False
    assert summary["segments"]["fill_provenance"]["legacy_stage"][
        "callback_from_send_ms"
    ]["count"] == 1


def test_cross_boot_callbacks_and_rollups_ignore_old_rows(monkeypatch):
    execution_id, _ = store.reserve(
        idempotency_key="old-boot",
        operation="place",
        source="manual",
        symbol="AAPL",
        received_ns=1_000,
    )
    store.update_stages(
        execution_id,
        status="sent",
        order_id=700,
        broker_sent_ns=2_000,
    )
    monkeypatch.setattr(store, "_BOOT_ID", "replacement-process")

    assert store.mark_ack_by_order_id(700, 3_000, "Submitted") is False
    assert store.mark_filled_by_order_id(700, 4_000) is False
    assert store.latency_rows() == []
    row = store.get_by_id(execution_id)
    assert row["broker_ack_ns"] is None
    assert row["filled_ns"] is None
    summary = latency_summary()
    assert summary["excluded_reasons"]["cross_boot"] == 1


def test_init_db_migrates_legacy_schema(tmp_path, monkeypatch):
    db_path = tmp_path / EXECUTION_LEDGER_DB_FILENAME
    db_path.unlink()
    legacy_schema = store._SCHEMA.replace("    boot_id TEXT NOT NULL,\n", "")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(legacy_schema)
    monkeypatch.setattr(store, "cache_dir", lambda: tmp_path)

    store.init_db()

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(executions)")}
    assert "boot_id" in columns


def test_synthetic_probe_summary_is_scoped_to_current_run(monkeypatch):
    _arm_synthetic(monkeypatch)
    for module, names in (
        (client_mod, ("is_enabled", "is_connected", "account_mode",
                      "broker_account_kind", "get_ib")),
        (safety_mod, ("orders_enabled", "gateway_mode", "live_trading_confirmed")),
        (account_mod, ("get_account_summary", "get_positions")),
        (orders_mod, ("place_order", "cancel_order")),
    ):
        for name in names:
            monkeypatch.setattr(module, name, getattr(module, name))

    old_id, _ = store.reserve(
        idempotency_key="bench:synth:prior:place",
        operation="place",
        source="benchmark",
        symbol="AAPL",
        received_ns=1,
    )
    store.update_stages(old_id, status="sent", broker_sent_ns=2, broker_ack_ns=3)

    summary = asyncio.run(
        execution_latency_probe._synthetic(2, run_id="current-run")
    )

    assert summary["run_id"] == "current-run"
    assert summary["sample_count"] == 4
    assert summary["ack_count"] == 2
    assert summary["fill_ms"]["send_to_fill"]["count"] == 2
