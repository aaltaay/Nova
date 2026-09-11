"""Startup sweep of ledger rows a previous process left mid-flight (D-011)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import execution.startup_sweep as sweep
import execution.store as store
import ibkr.client as client_mod
import ibkr.orders as orders_mod
from ibkr.errors import IbkrAccountError


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    yield


def _stale_row(
    key: str, *, order_id: int | None, status: str = "sent", symbol: str = "AAPL",
) -> str:
    """A row from an earlier process (boot_id rewritten to a dead run)."""
    execution_id, _ = store.reserve(
        idempotency_key=key,
        operation="place",
        source="manual",
        symbol=symbol,
        received_ns=1,
        payload={"side": "SELL", "qty": 100},
    )
    store.update_stages(execution_id, status=status, order_id=order_id)
    conn = store.get_connection()
    try:
        conn.execute(
            "UPDATE executions SET boot_id = 'previous-boot' WHERE id = ?",
            (execution_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return execution_id


def _arm_connected(monkeypatch, *, working: list[dict], closed: list[dict]):
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(orders_mod, "open_orders", lambda: working)
    monkeypatch.setattr(orders_mod, "closed_orders", lambda *a, **k: closed)


def test_current_boot_rows_are_not_swept(monkeypatch):
    execution_id, _ = store.reserve(
        idempotency_key="live-1",
        operation="place",
        source="manual",
        symbol="AAPL",
        received_ns=1,
    )
    store.update_stages(execution_id, status="sent", order_id=11)
    _arm_connected(monkeypatch, working=[], closed=[])
    summary = sweep.run_startup_sweep()
    assert summary["scanned"] == 0
    assert store.get_by_id(execution_id)["status"] == "sent"


def test_still_working_order_is_left_alone(monkeypatch):
    execution_id = _stale_row("stale-working", order_id=21)
    _arm_connected(
        monkeypatch,
        working=[{"order_id": 21, "symbol": "AAPL", "status": "Submitted"}],
        closed=[],
    )
    summary = sweep.run_startup_sweep()
    assert summary["still_working"] == [execution_id]
    assert store.get_by_id(execution_id)["status"] == "sent"


def test_broker_history_resolves_a_fill(monkeypatch):
    execution_id = _stale_row("stale-filled", order_id=22)
    _arm_connected(
        monkeypatch,
        working=[],
        closed=[{"order_id": 22, "symbol": "AAPL", "status": "Filled"}],
    )
    summary = sweep.run_startup_sweep()
    assert summary["resolved"] == [execution_id]
    row = store.get_by_id(execution_id)
    assert row["status"] == "filled"
    assert row["broker_status"] == "Filled"
    # Cross-boot monotonic stamps stay out of the ledger (ADR 007 decision 7).
    assert row["filled_ns"] is None


def test_broker_history_resolves_a_cancel(monkeypatch):
    execution_id = _stale_row("stale-cancelled", order_id=23)
    _arm_connected(
        monkeypatch,
        working=[],
        closed=[{"order_id": 23, "symbol": "AAPL", "status": "Cancelled"}],
    )
    sweep.run_startup_sweep()
    row = store.get_by_id(execution_id)
    assert row["status"] == "failed"
    assert row["reason_code"] == "SWEEP_UNRESOLVED"


def test_row_that_never_reached_the_broker_is_abandoned(monkeypatch):
    execution_id = _stale_row("stale-reserved", order_id=None, status="reserved")
    _arm_connected(monkeypatch, working=[], closed=[])
    summary = sweep.run_startup_sweep()
    assert summary["abandoned"] == [execution_id]
    row = store.get_by_id(execution_id)
    assert row["status"] == "abandoned"
    assert row["reason_code"] == "SWEEP_NEVER_SENT"


def test_unknown_order_is_abandoned_not_invented(monkeypatch):
    execution_id = _stale_row("stale-ghost", order_id=24)
    _arm_connected(monkeypatch, working=[], closed=[])
    sweep.run_startup_sweep()
    row = store.get_by_id(execution_id)
    assert row["status"] == "abandoned"
    assert row["reason_code"] == "SWEEP_UNRESOLVED"


def test_disconnected_sweep_rewrites_nothing(monkeypatch):
    execution_id = _stale_row("stale-offline", order_id=25)
    monkeypatch.setattr(client_mod, "is_connected", lambda: False)
    summary = sweep.run_startup_sweep()
    assert summary["scanned"] == 1
    assert summary["broker_checked"] is False
    assert store.get_by_id(execution_id)["status"] == "sent"


def test_one_failing_reconciliation_step_does_not_skip_the_rest(monkeypatch):
    import nova_os.recovery as recovery_mod
    import startup_reconciliation
    import strategy.risk as risk_mod

    ran: list[str] = []

    def boom():
        raise RuntimeError("journal unreadable")

    monkeypatch.setattr(risk_mod, "reconstruct_from_journal", boom)
    monkeypatch.setattr(
        sweep, "run_startup_sweep", lambda: ran.append("sweep") or {},
    )
    monkeypatch.setattr(
        recovery_mod, "run_startup_recovery", lambda: ran.append("recovery") or {},
    )
    startup_reconciliation.run_startup_reconciliation()
    assert ran == ["sweep", "recovery"]


def test_broker_read_failure_rewrites_nothing(monkeypatch):
    execution_id = _stale_row("stale-read-fail", order_id=26)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)

    def boom():
        raise IbkrAccountError("open_orders failed")

    monkeypatch.setattr(orders_mod, "open_orders", boom)
    summary = sweep.run_startup_sweep()
    assert summary["broker_checked"] is False
    assert store.get_by_id(execution_id)["status"] == "sent"
