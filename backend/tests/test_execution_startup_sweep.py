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
    sweep.reset_for_testing()
    sweep.completed_orders_state.reset_for_testing()
    yield
    sweep.reset_for_testing()
    sweep.completed_orders_state.reset_for_testing()


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


class _FakeExecution:
    def __init__(self, order_id: int, shares: float, cum_qty: float):
        self.orderId = order_id
        self.shares = shares
        self.cumQty = cum_qty


class _FakeFill:
    def __init__(self, execution: _FakeExecution):
        self.execution = execution


class _FakeIb:
    def __init__(self, fills: list[_FakeFill]):
        self._fills = fills

    def fills(self) -> list[_FakeFill]:
        return list(self._fills)


def _arm_connected(
    monkeypatch,
    *,
    working: list[dict],
    closed: list[dict],
    history_loaded: bool = True,
    fills: list[_FakeFill] | None = None,
):
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "get_ib", lambda: _FakeIb(fills or []))
    monkeypatch.setattr(orders_mod, "open_orders", lambda: working)
    monkeypatch.setattr(orders_mod, "closed_orders", lambda *a, **k: closed)
    monkeypatch.setattr(
        sweep.completed_orders_state, "loaded_for", lambda _ib: history_loaded,
    )


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


def test_unknown_order_left_untouched_while_history_not_loaded(monkeypatch):
    """PROBLEM_LOG 2026-09-19: the Gateway stopped answering reqCompletedOrders
    for hours, so an order that filled while Nova was down is missing from
    closed_orders(). Absence is not evidence then -- never mark it abandoned."""
    execution_id = _stale_row("stale-no-history", order_id=27)
    _arm_connected(monkeypatch, working=[], closed=[], history_loaded=False)
    summary = sweep.run_startup_sweep()
    assert summary["unverified"] == [execution_id]
    assert summary["abandoned"] == []
    row = store.get_by_id(execution_id)
    assert row["status"] == "sent"
    assert row["reason_code"] is None


def test_without_history_known_outcomes_still_resolve(monkeypatch):
    """Only the absence branch waits on history; positive evidence still counts."""
    never_sent = _stale_row("stale-never-sent", order_id=None, status="reserved")
    found = _stale_row("stale-found", order_id=28)
    _arm_connected(
        monkeypatch,
        working=[],
        closed=[{"order_id": 28, "symbol": "AAPL", "status": "Filled"}],
        history_loaded=False,
    )
    summary = sweep.run_startup_sweep()
    assert summary["abandoned"] == [never_sent]
    assert summary["resolved"] == [found]
    assert store.get_by_id(found)["status"] == "filled"


def test_executions_prove_a_fill_while_history_is_stuck(monkeypatch):
    """D-077: reqExecutions still answers when reqCompletedOrders does not, so
    a filled order must resolve from fills instead of sitting unverified."""
    execution_id = _stale_row("stale-filled-by-fills", order_id=30)
    _arm_connected(
        monkeypatch,
        working=[],
        closed=[],
        history_loaded=False,
        fills=[_FakeFill(_FakeExecution(30, 60, 60)), _FakeFill(_FakeExecution(30, 40, 100))],
    )
    summary = sweep.run_startup_sweep()
    assert summary["resolved"] == [execution_id]
    assert summary["resolved_by_executions"] == [execution_id]
    assert summary["unverified"] == []
    row = store.get_by_id(execution_id)
    assert row["status"] == "filled"
    assert row["broker_status"] == "Filled"
    # A non-empty error would make the receipt read as failed.
    assert not row["error"]


def test_partial_execution_is_never_abandoned(monkeypatch):
    """Something happened at the broker -- unknown is not the same as abandoned."""
    execution_id = _stale_row("stale-partial", order_id=31)
    _arm_connected(
        monkeypatch,
        working=[],
        closed=[],
        history_loaded=True,
        fills=[_FakeFill(_FakeExecution(31, 40, 40))],
    )
    summary = sweep.run_startup_sweep()
    assert summary["abandoned"] == []
    assert summary["unverified"] == [execution_id]
    assert store.get_by_id(execution_id)["status"] == "sent"


def test_history_load_reruns_the_sweep_for_unverified_rows(monkeypatch):
    """D-077 acceptance: unverified rows resolve on the first completed-orders
    answer, without waiting for the next API restart."""
    execution_id = _stale_row("stale-resweep", order_id=32)
    history = {"loaded": False}
    closed: list[dict] = []
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "get_ib", lambda: _FakeIb([]))
    monkeypatch.setattr(orders_mod, "open_orders", lambda: [])
    monkeypatch.setattr(orders_mod, "closed_orders", lambda *a, **k: closed)
    monkeypatch.setattr(
        sweep.completed_orders_state, "loaded_for", lambda _ib: history["loaded"],
    )

    assert sweep.run_startup_sweep()["unverified"] == [execution_id]
    assert store.get_by_id(execution_id)["status"] == "sent"

    # The Gateway finally answers: completed orders load and Closed Orders now
    # carries the fill that happened while Nova was down.
    history["loaded"] = True
    closed.append({"order_id": 32, "symbol": "AAPL", "status": "Filled"})
    sweep.completed_orders_state.mark_loaded(_FakeIb([]))

    row = store.get_by_id(execution_id)
    assert row["status"] == "filled"
    assert row["broker_status"] == "Filled"


def test_history_resweep_listener_fires_once(monkeypatch):
    _stale_row("stale-resweep-once", order_id=33)
    _arm_connected(monkeypatch, working=[], closed=[], history_loaded=False)
    sweep.run_startup_sweep()

    runs: list[int] = []
    monkeypatch.setattr(sweep, "run_startup_sweep", lambda: runs.append(1))
    sweep.completed_orders_state.mark_loaded(_FakeIb([]))
    sweep.completed_orders_state.mark_loaded(_FakeIb([]))
    assert len(runs) == 1


def test_resweep_stays_armed_when_the_socket_dropped(monkeypatch):
    """A re-run that cannot read the broker must not disarm the hook."""
    execution_id = _stale_row("stale-resweep-offline", order_id=35)
    _arm_connected(monkeypatch, working=[], closed=[], history_loaded=False)
    assert sweep.run_startup_sweep()["unverified"] == [execution_id]

    monkeypatch.setattr(client_mod, "is_connected", lambda: False)
    sweep.completed_orders_state.mark_loaded(_FakeIb([]))
    assert store.get_by_id(execution_id)["status"] == "sent"

    _arm_connected(
        monkeypatch,
        working=[],
        closed=[{"order_id": 35, "symbol": "AAPL", "status": "Filled"}],
    )
    sweep.completed_orders_state.mark_loaded(_FakeIb([]))
    assert store.get_by_id(execution_id)["status"] == "filled"


def test_no_resweep_is_armed_when_nothing_is_unverified(monkeypatch):
    _stale_row("stale-clean", order_id=34)
    _arm_connected(
        monkeypatch,
        working=[],
        closed=[{"order_id": 34, "symbol": "AAPL", "status": "Filled"}],
        history_loaded=False,
    )
    sweep.run_startup_sweep()

    runs: list[int] = []
    monkeypatch.setattr(sweep, "run_startup_sweep", lambda: runs.append(1))
    sweep.completed_orders_state.mark_loaded(_FakeIb([]))
    assert runs == []


def test_disconnected_sweep_rewrites_nothing(monkeypatch):
    execution_id = _stale_row("stale-offline", order_id=25)
    monkeypatch.setattr(client_mod, "is_connected", lambda: False)
    summary = sweep.run_startup_sweep()
    assert summary["scanned"] == 1
    assert summary["broker_checked"] is False
    assert store.get_by_id(execution_id)["status"] == "sent"


def test_one_failing_reconciliation_step_does_not_skip_the_rest(monkeypatch):
    import startup_reconciliation
    import strategy.risk as risk_mod

    ran: list[str] = []

    def boom():
        raise RuntimeError("journal unreadable")

    monkeypatch.setattr(risk_mod, "reconstruct_from_journal", boom)
    monkeypatch.setattr(
        sweep, "run_startup_sweep", lambda: ran.append("sweep") or {},
    )
    startup_reconciliation.run_startup_reconciliation()
    assert ran == ["sweep"]


def test_broker_read_failure_rewrites_nothing(monkeypatch):
    execution_id = _stale_row("stale-read-fail", order_id=26)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)

    def boom():
        raise IbkrAccountError("open_orders failed")

    monkeypatch.setattr(orders_mod, "open_orders", boom)
    summary = sweep.run_startup_sweep()
    assert summary["broker_checked"] is False
    assert store.get_by_id(execution_id)["status"] == "sent"
