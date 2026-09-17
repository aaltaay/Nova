"""ADR 007 decision 5 — the lock covers reservation, validation, and the send.

D-011: `send_broker` used to run after `async with _lock` exited, and the
position gates only compared against `long_qty`. Two SELLs with different
idempotency keys could both pass OVERSELL against the same long and both
reach `placeOrder` (the second slips in while the first waits for its ack).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import execution.inflight as inflight
import execution.service as exec_svc
import execution.store as store
import execution.telemetry as telemetry
import ibkr.account as account_mod
import ibkr.client as client_mod
import ibkr.orders as orders_mod
import ibkr.safety as safety_mod
import strategy.executor as executor
import strategy.risk as risk_mod
from execution.models import ExecutionCommand
from nova_os import control_mode, staged_tickets


@pytest.fixture(autouse=True)
def isolated_execution(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    import execution.broker_send as broker_send
    import execution.qty_gate as qty_gate

    monkeypatch.setattr(broker_send, "EXECUTION_ACK_WAIT_SEC", 0.05)
    # These cases are about qty arithmetic against a real position — the
    # MASTER TEST QTY GATE would clamp every send to one share.
    monkeypatch.setattr(qty_gate, "IBKR_FORCE_ONE_SHARE", False)
    store.init_db()
    telemetry.reset_for_tests()
    inflight.reset_for_tests()
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    risk_mod.reset_day()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()
    yield
    telemetry.reset_for_tests()
    inflight.reset_for_tests()
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    risk_mod.reset_day()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()


def _arm_paper(monkeypatch, *, positions: list | None = None):
    monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    monkeypatch.setattr(safety_mod, "orders_enabled", lambda: True)
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 1_000_000.0, "pending": False},
    )
    monkeypatch.setattr(account_mod, "get_positions", lambda: positions or [])


def _market(key: str, side: str, qty: float, **kw) -> ExecutionCommand:
    base = dict(
        operation="place",
        idempotency_key=key,
        source="manual",
        symbol="AAPL",
        side=side,
        qty=qty,
        order_type="MKT",
        skip_risk=True,
        skip_concurrency=True,
    )
    base.update(kw)
    return ExecutionCommand(**base)


class TestConcurrentSellRace:
    def test_two_concurrent_sells_reach_the_broker_once(self, monkeypatch):
        """D-011 repro: long 100, two SELL 100 with different keys → one send."""
        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": 100.0}])
        calls: list[dict] = []

        def place(**kw):
            calls.append(kw)
            return {
                "ok": True, "order_id": 500 + len(calls), "error": None,
                "mode": "paper",
            }

        monkeypatch.setattr(orders_mod, "place_order", place)

        async def both():
            return await asyncio.gather(
                exec_svc.execute(_market("sell-a", "SELL", 100)),
                exec_svc.execute(_market("sell-b", "SELL", 100)),
            )

        first, second = asyncio.run(both())
        assert len(calls) == 1, f"double broker send: {calls}"
        blocked = [r for r in (first, second) if not r.ok]
        assert len(blocked) == 1
        assert blocked[0].reason_code == "OVERSELL"

    def test_broker_send_runs_while_the_lock_is_held(self, monkeypatch):
        """ADR 007 decision 5 — the send is inside the lock, the ack wait is not."""
        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": 100.0}])
        locked_during_send: list[bool] = []

        def place(**kw):
            locked_during_send.append(exec_svc._lock.locked())
            return {"ok": True, "order_id": 601, "error": None, "mode": "paper"}

        monkeypatch.setattr(orders_mod, "place_order", place)
        receipt = asyncio.run(exec_svc.execute(_market("lock-1", "SELL", 10)))
        assert receipt.ok is True
        assert locked_during_send == [True]
        assert exec_svc._lock.locked() is False

    def test_rejected_send_frees_the_commitment(self, monkeypatch):
        """A refused broker send must not keep the symbol blocked."""
        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": 100.0}])
        calls: list[dict] = []

        def place(**kw):
            calls.append(kw)
            if len(calls) == 1:
                return {
                    "ok": False, "order_id": None, "error": "broker refused",
                    "mode": "paper",
                }
            return {"ok": True, "order_id": 700, "error": None, "mode": "paper"}

        monkeypatch.setattr(orders_mod, "place_order", place)
        first = asyncio.run(exec_svc.execute(_market("free-a", "SELL", 100)))
        assert first.ok is False
        second = asyncio.run(exec_svc.execute(_market("free-b", "SELL", 100)))
        assert second.ok is True
        assert len(calls) == 2

    def test_broker_cancel_callback_frees_the_commitment(self, monkeypatch):
        """A working order holds the shares; a cancelled one must give them back."""
        from types import SimpleNamespace

        from execution.telemetry_handlers import make_handlers

        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": 100.0}])
        calls: list[dict] = []

        def place(**kw):
            calls.append(kw)
            return {"ok": True, "order_id": 610, "error": None, "mode": "paper"}

        monkeypatch.setattr(orders_mod, "place_order", place)
        first = asyncio.run(exec_svc.execute(_market("hold-a", "SELL", 100)))
        assert first.ok is True
        blocked = asyncio.run(exec_svc.execute(_market("hold-b", "SELL", 100)))
        assert blocked.reason_code == "OVERSELL"

        _err, on_status, _exec, _comm = make_handlers(telemetry._watches.get)
        on_status(
            SimpleNamespace(
                order=SimpleNamespace(orderId=610, permId=0),
                orderStatus=SimpleNamespace(
                    status="Cancelled", filled=0, remaining=100, avgFillPrice=0,
                ),
            )
        )
        after = asyncio.run(exec_svc.execute(_market("hold-c", "SELL", 100)))
        assert after.ok is True
        assert len(calls) == 2

    def test_sequential_sells_still_split_one_position(self, monkeypatch):
        """Two 50-share sells against a 100 long both belong on the wire."""
        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": 100.0}])
        calls: list[dict] = []

        def place(**kw):
            calls.append(kw)
            return {
                "ok": True, "order_id": 800 + len(calls), "error": None,
                "mode": "paper",
            }

        monkeypatch.setattr(orders_mod, "place_order", place)

        async def both():
            return await asyncio.gather(
                exec_svc.execute(_market("half-a", "SELL", 50)),
                exec_svc.execute(_market("half-b", "SELL", 50)),
            )

        first, second = asyncio.run(both())
        assert first.ok is True and second.ok is True
        assert len(calls) == 2


class TestBuyCoverGate:
    def test_buy_beyond_short_qty_is_refused(self, monkeypatch):
        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": -100.0}])
        called: list[dict] = []
        monkeypatch.setattr(
            orders_mod, "place_order",
            lambda **k: called.append(k) or {"ok": True, "order_id": 1},
        )
        receipt = asyncio.run(exec_svc.execute(_market("cover-over", "BUY", 150)))
        assert receipt.ok is False
        assert receipt.reason_code == "OVERCOVER"
        assert called == []

    def test_buy_within_short_qty_is_allowed(self, monkeypatch):
        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": -100.0}])
        called: list[dict] = []
        monkeypatch.setattr(
            orders_mod, "place_order",
            lambda **k: called.append(k) or {
                "ok": True, "order_id": 2, "error": None, "mode": "paper",
            },
        )
        receipt = asyncio.run(exec_svc.execute(_market("cover-ok", "BUY", 100)))
        assert receipt.ok is True
        assert len(called) == 1

    def test_buy_while_flat_is_untouched_by_the_cover_gate(self, monkeypatch):
        _arm_paper(monkeypatch, positions=[])
        called: list[dict] = []
        monkeypatch.setattr(
            orders_mod, "place_order",
            lambda **k: called.append(k) or {
                "ok": True, "order_id": 3, "error": None, "mode": "paper",
            },
        )
        receipt = asyncio.run(exec_svc.execute(_market("flat-buy", "BUY", 500)))
        assert receipt.ok is True
        assert len(called) == 1

    def test_two_concurrent_covers_reach_the_broker_once(self, monkeypatch):
        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": -100.0}])
        calls: list[dict] = []

        def place(**kw):
            calls.append(kw)
            return {
                "ok": True, "order_id": 900 + len(calls), "error": None,
                "mode": "paper",
            }

        monkeypatch.setattr(orders_mod, "place_order", place)

        async def both():
            return await asyncio.gather(
                exec_svc.execute(_market("cover-a", "BUY", 100)),
                exec_svc.execute(_market("cover-b", "BUY", 100)),
            )

        first, second = asyncio.run(both())
        assert len(calls) == 1, f"double cover send: {calls}"
        blocked = [r for r in (first, second) if not r.ok]
        assert len(blocked) == 1
        assert blocked[0].reason_code == "OVERCOVER"
