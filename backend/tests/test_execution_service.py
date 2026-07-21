"""Centralized execution path (ADR 007) — safety, idempotency, telemetry."""
from __future__ import annotations

import ast
import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
from paths import cache_dir as _real_cache_dir  # noqa: F401 — patched via paths


@pytest.fixture(autouse=True)
def isolated_execution(tmp_path, monkeypatch):
    monkeypatch.setattr("paths.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("execution.store.cache_dir", lambda: tmp_path)
    import execution.broker_send as broker_send

    monkeypatch.setattr(broker_send, "EXECUTION_ACK_WAIT_SEC", 0.05)
    store.init_db()
    telemetry.reset_for_tests()
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    risk_mod.reset_day()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()
    yield
    telemetry.reset_for_tests()
    control_mode.reset_for_tests()
    staged_tickets.reset_for_tests()
    risk_mod.reset_day()
    executor._kill_switch_tripped = False
    executor._open_positions.clear()


def _arm_paper(monkeypatch, *, buying_power: float = 100_000.0, positions: list | None = None):
    monkeypatch.setattr(client_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(client_mod, "is_connected", lambda: True)
    monkeypatch.setattr(client_mod, "account_mode", lambda: "paper")
    monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(client_mod, "get_ib", lambda: None)
    monkeypatch.setattr(safety_mod, "orders_enabled", lambda: True)
    # ibkr.safety.assert_orders_allowed reads the *real* IBKR_GATEWAY_MODE env
    # var independently of the account_mode/broker_account_kind mocks above —
    # pin it to paper so these tests don't depend on the developer's real
    # .env. monkeypatch.setenv (not a gateway_mode function patch) so a test
    # that needs "live" can still override it afterward (see TestPaperLiveParity).
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setattr(
        account_mod,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": buying_power, "pending": False},
    )
    monkeypatch.setattr(account_mod, "get_positions", lambda: positions or [])


def _limit_buy(key: str = "k1", **kw) -> ExecutionCommand:
    base = dict(
        operation="place",
        idempotency_key=key,
        source="manual",
        symbol="AAPL",
        side="BUY",
        qty=1,
        order_type="LMT",
        limit_price=1.0,
        skip_risk=True,
        skip_concurrency=True,
    )
    base.update(kw)
    return ExecutionCommand(**base)


class TestIdempotencyAndDuplicates:
    def test_duplicate_key_replays_without_second_send(self, monkeypatch):
        _arm_paper(monkeypatch)
        calls = []

        def place(**kw):
            calls.append(kw)
            return {"ok": True, "order_id": 99, "error": None, "mode": "paper"}

        monkeypatch.setattr(orders_mod, "place_order", place)
        r1 = asyncio.run(exec_svc.execute(_limit_buy("dup-1"), wait_ack=False))
        r2 = asyncio.run(exec_svc.execute(_limit_buy("dup-1"), wait_ack=False))
        assert r1.ok and r1.order_id == 99
        assert r2.duplicate is True
        assert r2.execution_id == r1.execution_id
        assert len(calls) == 1

    def test_concurrent_identical_keys_single_broker_send(self, monkeypatch):
        _arm_paper(monkeypatch)
        calls = []

        def place(**kw):
            calls.append(1)
            time.sleep(0.02)
            return {"ok": True, "order_id": 7, "error": None, "mode": "paper"}

        monkeypatch.setattr(orders_mod, "place_order", place)

        async def both():
            c = _limit_buy("race-key")
            return await asyncio.gather(
                exec_svc.execute(c, wait_ack=False),
                exec_svc.execute(_limit_buy("race-key"), wait_ack=False),
            )

        a, b = asyncio.run(both())
        assert len(calls) == 1
        assert sum(1 for r in (a, b) if r.duplicate) == 1
        assert a.execution_id == b.execution_id


class TestAccountAndRiskGates:
    def test_live_unconfirmed_zero_broker_calls(self, monkeypatch):
        _arm_paper(monkeypatch)
        monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
        monkeypatch.setattr(client_mod, "account_mode", lambda: "live")
        monkeypatch.setattr(client_mod, "broker_account_kind", lambda: "live")
        monkeypatch.setattr(safety_mod, "live_trading_confirmed", lambda: False)
        called = []
        monkeypatch.setattr(
            orders_mod, "place_order", lambda **k: called.append(1) or {"ok": True}
        )
        r = asyncio.run(exec_svc.execute(_limit_buy("live-no"), wait_ack=False))
        assert r.ok is False
        assert r.reason_code == "ORDERS_GATE"
        assert called == []

    def test_buying_power_blocks_priced_buy(self, monkeypatch):
        _arm_paper(monkeypatch, buying_power=10.0)
        called = []
        monkeypatch.setattr(
            orders_mod, "place_order", lambda **k: called.append(1) or {"ok": True}
        )
        r = asyncio.run(
            exec_svc.execute(
                _limit_buy("bp", qty=100, limit_price=50.0), wait_ack=False
            )
        )
        assert r.ok is False
        assert r.reason_code == "BUYING_POWER"
        assert called == []

    def test_buying_power_unknown_when_account_summary_raises(self, monkeypatch):
        """accountValues() failure must refuse LMT BUY (not silently allow)."""
        from ibkr.errors import IbkrAccountError

        _arm_paper(monkeypatch, buying_power=1_000_000.0)

        def boom():
            raise IbkrAccountError("accountValues boom")

        monkeypatch.setattr(account_mod, "get_account_summary", boom)
        called = []
        monkeypatch.setattr(
            orders_mod, "place_order", lambda **k: called.append(1) or {"ok": True}
        )
        r = asyncio.run(
            exec_svc.execute(
                _limit_buy("bp-unknown", qty=1, limit_price=50.0), wait_ack=False
            )
        )
        assert r.ok is False
        assert r.reason_code == "BUYING_POWER_UNKNOWN"
        assert called == []

    def test_sell_without_position_blocked(self, monkeypatch):
        _arm_paper(monkeypatch, positions=[])
        called = []
        monkeypatch.setattr(
            orders_mod, "place_order", lambda **k: called.append(1) or {"ok": True}
        )
        r = asyncio.run(
            exec_svc.execute(
                ExecutionCommand(
                    operation="place",
                    idempotency_key="short-1",
                    source="manual",
                    symbol="AAPL",
                    side="SELL",
                    qty=1,
                    order_type="MKT",
                    skip_risk=True,
                    skip_concurrency=True,
                ),
                wait_ack=False,
            )
        )
        assert r.ok is False
        assert r.reason_code == "NO_POSITION"
        assert called == []

    def test_flatten_sell_allowed_with_position(self, monkeypatch):
        _arm_paper(monkeypatch, positions=[{"symbol": "AAPL", "qty": 5.0}])
        calls = []
        monkeypatch.setattr(
            orders_mod,
            "place_order",
            lambda **k: calls.append(k) or {"ok": True, "order_id": 3, "mode": "paper"},
        )
        r = asyncio.run(
            exec_svc.execute(
                ExecutionCommand(
                    operation="place",
                    idempotency_key="flat-1",
                    source="flatten",
                    symbol="AAPL",
                    side="SELL",
                    qty=5,
                    order_type="MKT",
                    skip_risk=True,
                    skip_concurrency=True,
                ),
                wait_ack=False,
            )
        )
        assert r.ok is True
        assert len(calls) == 1

    def test_max_concurrent_rejects_second_bracket(self, monkeypatch):
        from constants import NOVA_OS_MAX_CONCURRENT_POSITIONS

        _arm_paper(monkeypatch)
        monkeypatch.setattr(risk_mod, "can_trade", lambda: (True, "OK"))
        monkeypatch.setattr(risk_mod, "validate_trade_plan", lambda e, s, t: (True, []))
        monkeypatch.setattr(control_mode, "auto_paper_gate_status", lambda: (True, "OK"))
        for i in range(NOVA_OS_MAX_CONCURRENT_POSITIONS):
            executor._open_positions[f"S{i}"] = executor.OpenPosition(
                symbol=f"S{i}", setup="gap_and_go", qty=1,
                entry_price=5, stop_price=4.9, target_price=5.2,
                parent_order_id=i, target_order_id=i + 100, stop_order_id=i + 200,
                opened_ts=time.time(),
            )
        called = []
        monkeypatch.setattr(
            orders_mod, "place_bracket_order", lambda *a, **k: called.append(1)
        )
        r = asyncio.run(
            exec_svc.execute(
                ExecutionCommand(
                    operation="bracket",
                    idempotency_key="mc-1",
                    source="approve",
                    symbol="NEWSYM",
                    entry_price=5.0,
                    stop_price=4.9,
                    target_price=5.2,
                    shares=1,
                ),
                wait_ack=False,
            )
        )
        assert r.ok is False
        assert r.reason_code == "MAX_CONCURRENT"
        assert called == []


class TestPersistBeforeSend:
    def test_ledger_row_exists_before_broker_call(self, monkeypatch):
        _arm_paper(monkeypatch)
        seen = []

        def place(**kw):
            rows = store.list_recent(limit=5)
            seen.append(len(rows) >= 1 and rows[0]["status"] in ("reserved", "validated", "sent"))
            return {"ok": True, "order_id": 11, "error": None, "mode": "paper"}

        monkeypatch.setattr(orders_mod, "place_order", place)
        asyncio.run(exec_svc.execute(_limit_buy("persist-1"), wait_ack=False))
        assert seen == [True]


class TestTelemetryCallbacks:
    def test_pending_submit_is_not_ack(self):
        w = telemetry.watch_order(55)
        w.note_status("PendingSubmit")
        assert w.ack_ns is None
        w.note_status("Submitted")
        assert w.ack_ns is not None
        assert w.ack_status == "Submitted"

    def test_duplicate_status_does_not_reset_ack(self):
        w = telemetry.watch_order(56)
        w.note_status("Submitted")
        first = w.ack_ns
        w.note_status("Submitted")
        assert w.ack_ns == first

    def test_exec_details_marks_ack_and_fill(self, monkeypatch):
        _arm_paper(monkeypatch)
        store.reserve(
            idempotency_key="fill-corr",
            operation="place",
            source="manual",
            symbol="AAPL",
            received_ns=time.perf_counter_ns(),
        )
        row = store.get_by_idempotency("fill-corr")
        store.update_stages(row["id"], order_id=77, status="sent", broker_sent_ns=1)
        w = telemetry.watch_order(77)
        trade = SimpleNamespace(
            order=SimpleNamespace(orderId=77),
            orderStatus=SimpleNamespace(status="Filled", remaining=0),
        )
        fill = SimpleNamespace(execution=SimpleNamespace(avgPrice=10.0, shares=1.0))
        telemetry._on_exec_details(trade, fill)
        assert w.ack_ns is not None
        assert w.filled_ns is not None
        updated = store.get_by_id(row["id"])
        assert updated["filled_ns"] is not None
        assert updated["broker_ack_ns"] is not None


class TestReplaceConstraints:
    def test_replace_requires_open_order(self, monkeypatch):
        _arm_paper(monkeypatch)
        monkeypatch.setattr(orders_mod, "open_orders", lambda: [])
        called = []
        monkeypatch.setattr(
            orders_mod, "place_order", lambda **k: called.append(1) or {"ok": True}
        )
        r = asyncio.run(
            exec_svc.execute(
                ExecutionCommand(
                    operation="replace",
                    idempotency_key="rep-miss",
                    source="manual",
                    order_id=123,
                    limit_price=9.5,
                    skip_risk=True,
                    skip_concurrency=True,
                ),
                wait_ack=False,
            )
        )
        assert r.ok is False
        assert r.reason_code == "REPLACE_NOT_OPEN"
        assert called == []

    def test_replace_price_only(self, monkeypatch):
        _arm_paper(monkeypatch)
        monkeypatch.setattr(
            orders_mod,
            "open_orders",
            lambda: [{
                "order_id": 5,
                "symbol": "AAPL",
                "side": "BUY",
                "qty": 2.0,
                "order_type": "LMT",
                "limit_price": 10.0,
                "stop_price": None,
                "outside_rth": False,
            }],
        )
        calls = []

        def place(**kw):
            calls.append(kw)
            return {"ok": True, "order_id": 5, "error": None, "mode": "paper"}

        monkeypatch.setattr(orders_mod, "place_order", place)
        r = asyncio.run(
            exec_svc.execute(
                ExecutionCommand(
                    operation="replace",
                    idempotency_key="rep-ok",
                    source="manual",
                    order_id=5,
                    limit_price=9.5,
                    skip_risk=True,
                    skip_concurrency=True,
                ),
                wait_ack=False,
            )
        )
        assert r.ok is True
        assert calls[0]["order_id"] == 5
        assert calls[0]["limit_price"] == 9.5
        assert calls[0]["qty"] == 2.0
        assert calls[0]["side"] == "BUY"


class TestPaperLiveParity:
    @pytest.mark.parametrize("mode", ["paper", "live"])
    def test_same_execute_path(self, monkeypatch, mode):
        _arm_paper(monkeypatch)
        monkeypatch.setenv("IBKR_GATEWAY_MODE", mode)
        monkeypatch.setattr(client_mod, "account_mode", lambda: mode)
        monkeypatch.setattr(client_mod, "broker_account_kind", lambda: mode)
        if mode == "live":
            monkeypatch.setattr(safety_mod, "live_trading_confirmed", lambda: True)
        calls = []
        monkeypatch.setattr(
            orders_mod,
            "place_order",
            lambda **k: calls.append(mode) or {"ok": True, "order_id": 1, "mode": mode},
        )
        r = asyncio.run(exec_svc.execute(_limit_buy(f"parity-{mode}"), wait_ack=False))
        assert r.ok is True
        assert r.mode == mode
        assert calls == [mode]


class TestNoBypassAst:
    def test_no_production_placeorder_outside_adapter(self):
        root = Path(__file__).resolve().parents[1]
        offenders: list[str] = []
        allow = {
            root / "ibkr" / "orders.py",
            root / "execution" / "service.py",
            root / "execution" / "broker_send.py",
            root / "execution" / "telemetry.py",
        }
        for path in root.rglob("*.py"):
            if "tests" in path.parts or path.name.startswith("test_"):
                continue
            if "graphify-out" in path.parts or ".venv" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "placeOrder" not in text and "cancelOrder" not in text:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = None
                if isinstance(func, ast.Attribute):
                    name = func.attr
                elif isinstance(func, ast.Name):
                    name = func.id
                if name in ("placeOrder", "cancelOrder") and path.resolve() not in {
                    p.resolve() for p in allow
                }:
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}:{name}")
        assert offenders == [], f"broker SDK bypass: {offenders}"


class TestLatencySummary:
    def test_summary_shape(self, monkeypatch):
        _arm_paper(monkeypatch)

        def place(**kw):
            oid = 40
            # Status is noted via the watch execution.service re-creates below
            # (run_one), not here.
            return {"ok": True, "order_id": oid, "error": None, "mode": "paper"}

        monkeypatch.setattr(orders_mod, "place_order", place)

        async def run_one(i: int):
            r = await exec_svc.execute(_limit_buy(f"lat-{i}"), wait_ack=False)
            if r.order_id:
                telemetry.watch_order(int(r.order_id)).note_status("Submitted")
            return r

        async def many():
            return await asyncio.gather(*[run_one(i) for i in range(5)])

        asyncio.run(many())
        summary = exec_svc.latency_summary(limit=50)
        assert summary["sample_count"] >= 5
        assert "broker_ack_ms" in summary
        assert summary["sla_p95_ms"] == 250.0
