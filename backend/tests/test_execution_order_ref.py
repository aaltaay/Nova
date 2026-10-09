"""Nova's reference on every Live order (orderRef): on the ledger before the send, and how it is matched back.

IBKR does not enforce orderRef uniqueness, so the reference alone never names an order: the match also needs
the symbol, side, quantity and permId, and more than one order passing them is left for the operator.
"""
from __future__ import annotations

import asyncio
import functools
import time
from types import SimpleNamespace

import pytest

import execution.startup_sweep as sweep
import execution.store as store
import ibkr.client as client_mod
import ibkr.orders as orders_mod
from execution import order_ref, telemetry
from execution.broker_send import send_broker
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from ibkr import loop_supervisor, send_hop
from ibkr.order_build import build_ib_order

REF = "nova-0123456789abcdef"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    telemetry.reset_for_tests()
    sweep.reset_for_testing()
    sweep.completed_orders_state.reset_for_testing()
    monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
    yield
    loop_supervisor.stop()
    telemetry.reset_for_tests()
    sweep.reset_for_testing()
    sweep.completed_orders_state.reset_for_testing()


def _refuse(refused: list):
    def reject(execution_id, cmd, timings, detail, reason_code):
        refused.append((reason_code, detail))
        return ExecutionReceipt(
            ok=False, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
            idempotency_key=cmd.idempotency_key, error=detail, reason_code=reason_code, timings=timings,
        )
    return reject


def _reserve(key: str, *, qty: float = 1, side: str = "BUY") -> str:
    execution_id, _ = store.reserve(
        idempotency_key=key, operation="place", source="manual", symbol="ZTG", received_ns=1,
        payload={"qty": qty, "sent_qty": qty, "side": side, "order_type": "LMT", "venue": "live"},
    )
    return execution_id


def _place(key: str) -> ExecutionCommand:
    return ExecutionCommand(
        operation="place", idempotency_key=key, source="manual", symbol="ZTG",
        side="BUY", qty=1, order_type="LMT", limit_price=1.0,
    )


# ── minting and matching ─────────────────────────────────────────────────────

def test_the_reference_comes_from_the_execution_id_and_rides_on_every_built_order():
    ref = order_ref.mint("01234567-89ab-cdef-0123-456789abcdef")
    assert ref == REF and order_ref.is_nova(ref)
    for typ, limit, stop in (("MKT", None, None), ("LMT", 1.0, None), ("STP", None, 0.9),
                             ("STP LMT", 1.0, 0.9), ("TRAIL", None, 0.1)):
        assert build_ib_order("BUY", 1, typ, limit, stop, False, "DAY", order_ref=ref).orderRef == ref


def _broker_row(order_id: int, perm_id: int, *, ref: str = REF, qty: float = 100, side: str = "SELL") -> dict:
    return {"order_id": order_id, "perm_id": perm_id, "symbol": "AAPL", "side": side, "qty": qty,
            "status": "Filled", "order_ref": ref}


def test_a_reference_names_an_order_only_with_its_symbol_side_size_and_perm_id():
    rows = [_broker_row(31, 9001), _broker_row(32, 9002, qty=50), _broker_row(33, 9003, side="BUY"),
            _broker_row(34, 9004, ref="nova-someone-else")]
    one = order_ref.match(rows, order_ref=REF, symbol="aapl", side="sell", qty=100)
    assert one.verdict == "one" and one.row["order_id"] == 31
    assert order_ref.match(rows, order_ref=REF, symbol="AAPL", side="SELL", qty=100, perm_id=9999).verdict == "none"
    # A size Nova does not know matches nothing: it is never assumed.
    assert order_ref.match(rows, order_ref=REF, symbol="AAPL", side="SELL", qty=None).verdict == "none"


def test_two_orders_under_one_reference_are_the_operators_call_never_a_pick():
    rows = [_broker_row(31, 9001), _broker_row(41, 9101)]
    found = order_ref.match(rows, order_ref=REF, symbol="AAPL", side="SELL", qty=100)
    assert found.verdict == "ambiguous" and sorted(found.order_ids()) == [31, 41]
    # The working and closed lists can both carry one order: counted once.
    assert order_ref.match([_broker_row(31, 9001), dict(_broker_row(31, 9001), status="Submitted")],
                           order_ref=REF, symbol="AAPL", side="SELL", qty=100).verdict == "one"


# ── the send ─────────────────────────────────────────────────────────────────

def test_the_reference_is_on_the_ledger_before_the_order_leaves(monkeypatch):
    loop_supervisor.start()
    seen: list = []

    def fake_place(**kwargs):
        seen.append((kwargs["order_ref"], store.get_by_id(execution_id)["order_ref"]))
        return {"ok": True, "order_id": 501, "error": None, "mode": "live", "nova_placed_at": None}

    monkeypatch.setattr(orders_mod, "place_order", fake_place)
    execution_id = _reserve("ref-1")
    receipt = asyncio.run(send_broker(_place("ref-1"), execution_id, StageTimings(received_ns=1),
                                      wait_ack=False, reject=_refuse([]), venue="live"))
    assert receipt.ok is True
    assert seen == [(order_ref.mint(execution_id), order_ref.mint(execution_id))]


def test_a_replace_sends_the_working_orders_own_reference_or_ibkr_would_erase_it(monkeypatch):
    loop_supervisor.start()
    sent: list = []
    monkeypatch.setattr(orders_mod, "open_orders", lambda **_k: [{
        "order_id": 77, "symbol": "ZTG", "side": "BUY", "qty": 1.0, "order_type": "LMT", "limit_price": 1.0,
        "stop_price": None, "outside_rth": False, "tif": "DAY", "order_ref": REF,
    }])
    monkeypatch.setattr(orders_mod, "place_order",
                        lambda **k: sent.append(k["order_ref"]) or {"ok": True, "order_id": 77, "mode": "live"})
    execution_id = _reserve("ref-replace")
    cmd = ExecutionCommand(operation="replace", idempotency_key="ref-replace", source="manual",
                           order_id=77, limit_price=1.05)
    asyncio.run(send_broker(cmd, execution_id, StageTimings(received_ns=1), wait_ack=False,
                            reject=_refuse([]), venue="live"))
    assert sent == [REF]
    assert store.get_by_id(execution_id)["order_ref"] == REF


def test_an_unknown_send_stays_open_with_its_reference_and_settles_when_the_send_ends(monkeypatch):
    """SEND_UNKNOWN used to close the row ``failed``: nothing could find the order later. The row now stays
    ``sent`` with its reference, and the send's own end writes the order id it got."""
    loop_supervisor.start()
    monkeypatch.setattr(send_hop, "IBKR_SEND_RUNNING_GRACE_SEC", 0.1)
    monkeypatch.setattr(send_hop, "send", functools.partial(send_hop.send, timeout=0.05))

    def slow_place(**_kwargs):
        time.sleep(0.4)                       # IBKR's thread is inside the send past the grace
        return {"ok": True, "order_id": 888, "error": None, "mode": "live", "nova_placed_at": None}

    monkeypatch.setattr(orders_mod, "place_order", slow_place)
    execution_id = _reserve("ref-unknown")

    async def run():
        receipt = await send_broker(_place("ref-unknown"), execution_id, StageTimings(received_ns=1),
                                    wait_ack=False, reject=_refuse([]), venue="live")
        row = store.get_by_id(execution_id)
        await asyncio.sleep(0.8)              # the socket loop lives on; the send ends meanwhile
        return receipt, row

    receipt, row_then = asyncio.run(run())
    assert receipt.ok is False and receipt.reason_code == "SEND_UNKNOWN"
    assert row_then["status"] == "sent" and row_then["reason_code"] == "SEND_UNKNOWN"
    assert row_then["order_ref"] == order_ref.mint(execution_id)
    row = store.get_by_id(execution_id)
    assert row["order_id"] == 888 and row["reason_code"] == order_ref.FINISHED_LATE and row["error"] is None


# ── the sweep ────────────────────────────────────────────────────────────────

def _stale(key: str, *, order_id: int | None = None, ref: str | None = REF, current: bool = False) -> str:
    execution_id, _ = store.reserve(
        idempotency_key=key, operation="place", source="manual", symbol="AAPL", received_ns=1,
        payload={"side": "SELL", "qty": 100, "sent_qty": 100, "venue": "live"},
    )
    store.update_stages(execution_id, status="sent", order_id=order_id, mode="live", order_ref=ref,
                        reason_code=None if order_id else "SEND_UNKNOWN")
    if not current:
        conn = store.get_connection()
        try:
            conn.execute("UPDATE executions SET boot_id = 'previous-boot' WHERE id = ?", (execution_id,))
            conn.commit()
        finally:
            conn.close()
    return execution_id


def _broker(monkeypatch, *, working=(), closed=(), fills=(), history_loaded=True):
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "get_ib", lambda: SimpleNamespace(fills=lambda: list(fills)))
    monkeypatch.setattr(orders_mod, "open_orders", lambda **_k: list(working))
    monkeypatch.setattr(orders_mod, "closed_orders", lambda *a, **k: list(closed))
    monkeypatch.setattr(sweep.completed_orders_state, "loaded_for", lambda _ib: history_loaded)


def test_the_sweep_finds_an_unknown_sends_order_by_its_reference(monkeypatch):
    execution_id = _stale("sweep-ref-1")
    _broker(monkeypatch, closed=[_broker_row(31, 9001)])
    summary = sweep.run_startup_sweep()
    row = store.get_by_id(execution_id)
    assert summary["resolved"] == [execution_id]
    assert row["order_id"] == 31 and row["perm_id"] == 9001 and row["status"] == "filled"
    assert row["reason_code"] == order_ref.RESOLVED_BY_REF and row["error"] is None


def test_an_execution_carrying_the_reference_proves_the_order_before_history_loads(monkeypatch):
    execution_id = _stale("sweep-ref-exec")
    fill = SimpleNamespace(
        contract=SimpleNamespace(symbol="AAPL"),
        execution=SimpleNamespace(orderRef=REF, side="SLD", permId=9001, orderId=31, shares=100.0, cumQty=100.0),
    )
    _broker(monkeypatch, fills=[fill], history_loaded=False)
    sweep.run_startup_sweep()
    row = store.get_by_id(execution_id)
    assert row["order_id"] == 31 and row["status"] == "filled"


def test_two_orders_under_the_reference_leave_the_row_for_the_operator(monkeypatch):
    execution_id = _stale("sweep-ref-2")
    _broker(monkeypatch, closed=[_broker_row(31, 9001), _broker_row(41, 9101)])
    summary = sweep.run_startup_sweep()
    row = store.get_by_id(execution_id)
    assert summary["unverified"] == [execution_id] and row["status"] == "sent"
    assert row["reason_code"] == order_ref.AMBIGUOUS and "31" in row["error"] and "41" in row["error"]


def test_no_order_under_the_reference_is_never_sent_only_once_history_answers(monkeypatch):
    waiting = _stale("sweep-ref-3")
    _broker(monkeypatch, history_loaded=False)
    assert sweep.run_startup_sweep()["unverified"] == [waiting]
    sweep.reset_for_testing()
    _broker(monkeypatch, history_loaded=True)
    assert sweep.run_startup_sweep()["abandoned"] == [waiting]
    assert "no order under its reference" in store.get_by_id(waiting)["error"]


def test_an_order_id_ibkr_gave_another_order_is_never_this_rows_outcome(monkeypatch):
    """Lean IB #242: a Gateway restart rolled nextValidId back and ids were issued again."""
    execution_id = _stale("sweep-ref-reused", order_id=40)
    _broker(monkeypatch, closed=[dict(_broker_row(40, 7777, ref="nova-ffffffffffffffff"), status="Cancelled")])
    summary = sweep.run_startup_sweep()
    row = store.get_by_id(execution_id)
    assert summary["unverified"] == [execution_id]
    assert row["status"] == "sent" and row["broker_status"] is None


def test_a_reconnect_sweeps_this_process_rows_on_evidence_only(monkeypatch):
    filled = _stale("current-filled", order_id=50, current=True)
    silent = _stale("current-silent", order_id=51, current=True)
    reserved, _ = store.reserve(idempotency_key="current-reserved", operation="place", source="manual",
                                symbol="AAPL", received_ns=1, payload={"venue": "live"})
    practice, _ = store.reserve(idempotency_key="current-paper", operation="place", source="manual",
                                symbol="AAPL", received_ns=1, payload={"venue": "paper"})
    store.update_stages(practice, status="sent", order_id=1, mode="paper")
    _broker(monkeypatch, closed=[dict(_broker_row(50, 9050), status="Filled")])
    assert sweep.run_startup_sweep()["scanned"] == 0          # the startup sweep leaves this process alone
    summary = sweep.run_startup_sweep(include_current_boot=True)
    assert summary["resolved"] == [filled]
    assert silent in summary["unverified"] and summary["abandoned"] == []
    assert store.get_by_id(silent)["status"] == "sent"
    assert store.get_by_id(reserved)["status"] == "reserved"
    assert store.get_by_id(practice)["status"] == "sent"


def test_a_reconnect_finds_this_process_unknown_send_by_its_reference(monkeypatch):
    unknown = _stale("current-unknown", ref="nova-1111111111111111", current=True)
    on_its_way, _ = store.reserve(idempotency_key="current-on-its-way", operation="place", source="manual",
                                  symbol="AAPL", received_ns=1, payload={"side": "SELL", "qty": 100, "venue": "live"})
    store.update_stages(on_its_way, status="sent", mode="live", order_ref="nova-2222222222222222")
    _broker(monkeypatch, working=[dict(_broker_row(61, 9061, ref="nova-1111111111111111"), status="Submitted"),
                                  dict(_broker_row(62, 9062, ref="nova-2222222222222222"), status="Submitted")])
    summary = sweep.run_startup_sweep(include_current_boot=True)
    assert summary["still_working"] == [unknown]
    assert store.get_by_id(unknown)["order_id"] == 61
    assert store.get_by_id(on_its_way)["order_id"] is None      # its own send path writes it


def _execution(perm_id: int, shares: float, *, order_id: int = 31) -> SimpleNamespace:
    return SimpleNamespace(
        contract=SimpleNamespace(symbol="AAPL"),
        execution=SimpleNamespace(orderRef=REF, side="SLD", permId=perm_id, orderId=order_id, shares=shares,
                                  cumQty=shares),
    )


def test_an_execution_match_needs_the_rows_perm_id_and_size_too(monkeypatch):
    """PR #811 review: executions matched on reference, symbol and side alone."""
    other_perm = _stale("exec-perm")
    store.update_stages(other_perm, order_ref=REF)
    conn = store.get_connection()
    try:
        conn.execute("UPDATE executions SET perm_id = 9001 WHERE id = ?", (other_perm,))
        conn.commit()
    finally:
        conn.close()
    _broker(monkeypatch, fills=[_execution(7777, 100)], history_loaded=False)
    sweep.run_startup_sweep()
    assert store.get_by_id(other_perm)["order_id"] is None          # another permId: not this row's order
    sweep.reset_for_testing()
    too_big = _stale("exec-size")
    _broker(monkeypatch, fills=[_execution(9100, 60), _execution(9100, 60)], history_loaded=False)
    sweep.run_startup_sweep()
    assert store.get_by_id(too_big)["order_id"] is None             # 120 filled: more than the 100 it sent
