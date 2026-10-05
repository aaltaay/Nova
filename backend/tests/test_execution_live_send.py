"""The Live send through a real IB loop thread: watched from the place on, and never late (#725)."""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

import execution.store as store
import ibkr.orders as orders_mod
from execution import telemetry
from execution.broker_send import send_broker
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from execution.telemetry_handlers import make_handlers
from ibkr import client as _client
from ibkr import loop_supervisor


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    store.init_db()
    telemetry.reset_for_tests()
    monkeypatch.setattr(_client, "account_mode", lambda: "live")
    loop_supervisor.stop()
    loop_supervisor.start()
    yield
    loop_supervisor.stop()
    telemetry.reset_for_tests()


def _status(order_id: int, status: str) -> SimpleNamespace:
    return SimpleNamespace(
        order=SimpleNamespace(orderId=order_id, permId=0),
        orderStatus=SimpleNamespace(status=status, filled=0.0, remaining=1.0, avgFillPrice=0.0),
    )


def _reserve(key: str) -> str:
    execution_id, _ = store.reserve(
        idempotency_key=key, operation="place", source="manual", symbol="ZTG", received_ns=1,
        payload={"qty": 1, "sent_qty": 1.0, "side": "BUY", "order_type": "LMT"},
    )
    return execution_id


def _refuse(refused: list):
    def reject(execution_id, cmd, timings, detail, reason_code):
        refused.append((reason_code, detail))
        return ExecutionReceipt(
            ok=False, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
            idempotency_key=cmd.idempotency_key, error=detail, reason_code=reason_code, timings=timings,
        )
    return reject


def test_ibkrs_first_status_finds_the_watch_the_send_registered(monkeypatch):
    """A status for an order nobody watches is dropped. Registered on the socket loop after the hop, the
    watch could come after IBKR's first status; registered in the placing callback, it is always first."""
    on_status = make_handlers(telemetry._watches.get)[1]
    seen: list[object] = []

    def fake_place(**_kwargs):
        loop = asyncio.get_running_loop()       # IBKR's answer, processed on the IB loop right after the place

        def ibkr_answers() -> None:
            seen.append(telemetry._watches.get(555))
            on_status(_status(555, "Submitted"))

        loop.call_soon(ibkr_answers)
        return {"ok": True, "order_id": 555, "error": None, "mode": "live", "nova_placed_at": None}

    monkeypatch.setattr(orders_mod, "place_order", fake_place)
    execution_id = _reserve("live-send-1")
    cmd = ExecutionCommand(
        operation="place", idempotency_key="live-send-1", source="manual", symbol="ZTG",
        side="BUY", qty=1, order_type="LMT", limit_price=1.0,
    )
    receipt = asyncio.run(send_broker(
        cmd, execution_id, StageTimings(received_ns=1), wait_ack=True, reject=_refuse([]), venue="live",
    ))
    assert seen and seen[0] is not None          # the watch existed when IBKR's status was processed
    assert receipt.ok is True
    assert receipt.broker_status == "Submitted"
    assert receipt.timings.broker_ack_ns is not None


def test_a_fill_heard_right_after_the_place_frees_the_shares_at_once(monkeypatch):
    """A fill processed before the commitment knew its order id freed nothing, and a send that skips the
    ack wait (the bot, Flatten, KILL) kept the shares "already sent" (QA R31's class). The order id
    joins the commitment in the placing callback, so the fill frees it on the spot."""
    from execution import inflight

    on_status = make_handlers(telemetry._watches.get)[1]
    left: list[float] = []

    def fake_place(**_kwargs):
        loop = asyncio.get_running_loop()

        def ibkr_fills() -> None:
            on_status(_status(777, "Filled"))
            left.append(inflight.committed_qty("ZTG", "BUY", "live"))

        loop.call_soon(ibkr_fills)
        return {"ok": True, "order_id": 777, "error": None, "mode": "live", "nova_placed_at": None}

    monkeypatch.setattr(orders_mod, "place_order", fake_place)
    execution_id = _reserve("live-send-fill")
    inflight.commit(execution_id, symbol="ZTG", side="BUY", qty=1, venue="live")
    cmd = ExecutionCommand(
        operation="place", idempotency_key="live-send-fill", source="bot", symbol="ZTG",
        side="BUY", qty=1, order_type="LMT", limit_price=1.0,
    )
    try:
        receipt = asyncio.run(send_broker(
            cmd, execution_id, StageTimings(received_ns=1), wait_ack=False, reject=_refuse([]), venue="live",
        ))
        time.sleep(0.05)
        assert receipt.ok is True
        assert left == [0.0]
    finally:
        inflight.release_execution(execution_id)


def test_every_bracket_leg_is_watched_before_any_status(monkeypatch):
    on_status = make_handlers(telemetry._watches.get)[1]
    watched: list[bool] = []

    def fake_bracket(**_kwargs):
        loop = asyncio.get_running_loop()

        def ibkr_answers() -> None:
            watched.extend(telemetry._watches.get(oid) is not None for oid in (601, 602, 603))
            on_status(_status(601, "Submitted"))

        loop.call_soon(ibkr_answers)
        return {"ok": True, "parent_order_id": 601, "target_order_id": 602, "stop_order_id": 603,
                "error": None, "mode": "live", "nova_placed_at": None}

    monkeypatch.setattr(orders_mod, "place_bracket_order", fake_bracket)
    execution_id = _reserve("live-send-2")
    cmd = ExecutionCommand(
        operation="bracket", idempotency_key="live-send-2", source="manual", symbol="ZTG",
        side="BUY", qty=1, entry_price=1.0, stop_price=0.9, target_price=1.2, order_type="LMT",
    )
    receipt = asyncio.run(send_broker(
        cmd, execution_id, StageTimings(received_ns=1), wait_ack=True, reject=_refuse([]), venue="live",
    ))
    assert watched == [True, True, True]
    assert receipt.ok is True and receipt.broker_status == "Submitted"


def test_a_desk_order_the_ib_loop_takes_after_its_deadline_is_refused_and_never_placed(monkeypatch):
    """ADR 045's 750 ms from the click to the broker, enforced where the order leaves: the IB loop."""
    placed: list[bool] = []
    monkeypatch.setattr(orders_mod, "place_order", lambda **_k: placed.append(True) or {"ok": True, "order_id": 9})
    loop = loop_supervisor.get_loop()
    free = threading.Event()
    loop.call_soon_threadsafe(lambda: free.wait(0.5))      # IBKR's thread busy for half a second
    act_ms = time.time() * 1000.0 - 600.0                   # the click: 600 ms ago, so 150 ms are left
    cmd = ExecutionCommand(
        operation="place", idempotency_key="live-send-3", source="manual", symbol="ZTG",
        side="BUY", qty=1, order_type="LMT", limit_price=1.0,
        client_timing={"action_wall_ms": act_ms}, view={"schema_version": 1, "action_wall_ms": act_ms},
    )
    refused: list = []
    receipt = asyncio.run(send_broker(
        cmd, _reserve("live-send-3"), StageTimings(received_ns=1), wait_ack=True,
        reject=_refuse(refused), venue="live",
    ))
    time.sleep(0.6)                                         # the IB loop is free again: still nothing sent
    assert placed == []
    assert receipt.ok is False and refused[0][0] == "ORDER_LATE"
    assert "after your click" in refused[0][1]


class _Event:
    def __init__(self) -> None:
        self.threads: list[str] = []

    def __iadd__(self, _handler):
        self.threads.append(threading.current_thread().name)
        return self


class _FakeIb:
    def __init__(self) -> None:
        self.orderStatusEvent = _Event()
        self.execDetailsEvent = _Event()
        self.errorEvent = _Event()
        self.commissionReportEvent = _Event()


def test_order_events_are_wired_on_the_ib_loop_without_holding_the_socket_loop():
    """The first order after a connect wired IBKR's order events with a blocking hop (READY now wires them)."""
    ib = _FakeIb()
    assert asyncio.run(telemetry.wire_for_send(ib)) is None
    assert ib.orderStatusEvent.threads == ["nova-ib-loop"]
    assert asyncio.run(telemetry.wire_for_send(ib)) is None          # once per IB session
    assert ib.orderStatusEvent.threads == ["nova-ib-loop"]


def test_an_order_whose_events_ibkrs_thread_cannot_wire_is_refused_with_the_reason(monkeypatch):
    import constants_ibkr

    monkeypatch.setattr(constants_ibkr, "IBKR_ORDER_EVENTS_WIRE_TIMEOUT_SEC", 0.1)
    free = threading.Event()
    loop_supervisor.get_loop().call_soon_threadsafe(lambda: free.wait(0.5))
    why = asyncio.run(telemetry.wire_for_send(_FakeIb()))
    assert why is not None and "It was not sent" in why
