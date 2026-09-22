"""ADR 020 -- one execution door, three venues: where an allowed order is routed.

``send_broker`` hands Paper and Sim to their own practice broker and Live to
IBKR; validation asks the venue's reference for admission; the orders and
account hooks answer from the venue's ledger; the spend gates need the ADR 018
latch only on a practice venue. Every practice broker here is a fake, so the
tests prove routing, not fills (``test_practice_broker.py`` proves those).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from constants_sim import DESK_PAPER_NO_IBKR_REASON, SIM_NO_IBKR_CODE, SIM_NO_IBKR_REASON
from execution.broker_send import send_broker
from execution.models import ExecutionCommand, ExecutionReceipt, StageTimings
from execution.validate import check_account_and_position, validate_command
from ibkr import account as _account
from ibkr import client as _client
from ibkr import orders as _orders
from ibkr import safety as _safety
from ibkr.safety import DISARMED_REASON
from ibkr.trading_allowed import evaluate_trading_allowed, places_allowed
from sim.mode import reset_for_tests, set_venue, venue


class FakeBroker:
    """Records what the send path asked of it; answers like a filled practice order."""

    def __init__(self, label: str) -> None:
        self.venue = label
        self.account_id = f"NOVA-{label.upper()}"
        self.calls: list[tuple[str, Any]] = []
        self.buying_power = 1_000.0
        self.reference = SimpleNamespace(admission=lambda symbol: (True, "OK", None))

    def place(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("place", kw))
        return {
            "ok": True, "order_id": 7, "error": None, "mode": self.venue,
            "nova_placed_at": "2026-09-21T13:00:00+00:00", "broker_status": "Filled",
        }

    def cancel(self, order_id: int, *, source: str = "manual", bot_id: str | None = None) -> dict[str, Any]:
        self.calls.append(("cancel", (order_id, source)))
        return {"ok": True, "error": None, "verified_gone": True, "mode": self.venue}

    def replace(self, order_id: int, limit_price=None, stop_price=None) -> dict[str, Any]:
        self.calls.append(("replace", (order_id, limit_price, stop_price)))
        return {
            "ok": True, "order_id": order_id, "error": None, "mode": self.venue,
            "nova_placed_at": None, "broker_status": "Submitted",
        }

    def working_orders(self) -> list[dict[str, Any]]:
        return [{"order_id": 1, "symbol": "IMCC", "venue": self.venue, "status": "Submitted"}]

    def closed_orders(self, limit=None) -> list[dict[str, Any]]:
        return [{"order_id": 2, "symbol": "IMCC", "venue": self.venue, "status": "Filled"}]

    def positions(self) -> list[dict[str, Any]]:
        return [{"symbol": "IMCC", "qty": 3.0, "venue": self.venue}]

    def account_summary(self) -> dict[str, Any]:
        return {
            "connected": True, "mode": self.venue, "practice": True, "pending": False,
            "account_id": self.account_id, "BuyingPower": self.buying_power,
        }


@pytest.fixture
def brokers(monkeypatch):
    from execution import store
    from practice import broker as practice_broker

    reset_for_tests()
    fakes = {"paper": FakeBroker("paper"), "sim": FakeBroker("sim")}
    monkeypatch.setattr(practice_broker, "for_venue", lambda label: fakes[label.strip().lower()])
    store.init_db()
    yield fakes
    reset_for_tests()


def _reject(execution_id, cmd, timings, detail, reason) -> ExecutionReceipt:
    return ExecutionReceipt(
        ok=False, execution_id=execution_id, operation=cmd.operation, source=cmd.source,
        idempotency_key=cmd.idempotency_key, error=detail, reason_code=reason, timings=timings,
    )


def _cmd(operation: str = "place", **overrides: Any) -> ExecutionCommand:
    fields: dict[str, Any] = {
        "operation": operation, "idempotency_key": f"venue-{operation}", "source": "manual",
        "symbol": "IMCC", "side": "BUY", "qty": 1, "order_type": "MKT",
    }
    fields.update(overrides)
    return ExecutionCommand(**fields)


def _send(cmd: ExecutionCommand) -> ExecutionReceipt:
    return asyncio.run(send_broker(
        cmd, f"exec-{cmd.idempotency_key}", StageTimings(received_ns=0), wait_ack=False, reject=_reject,
    ))


# ── send_broker routing ──────────────────────────────────────────────────────

@pytest.mark.parametrize("target", ["paper", "sim"])
def test_a_practice_venue_sends_to_its_own_broker(brokers, target: str) -> None:
    set_venue(target)
    _safety.set_armed(True, reason="test")
    receipt = _send(_cmd())
    assert receipt.ok is True, receipt.error
    assert receipt.mode == target and receipt.order_id == 7 and receipt.broker_status == "Filled"
    other = "sim" if target == "paper" else "paper"
    assert brokers[other].calls == [], "the other practice ledger must not see the order"
    (kind, kw), = brokers[target].calls
    assert kind == "place"
    assert (kw["symbol"], kw["side"], kw["qty"], kw["order_type"]) == ("IMCC", "BUY", 1.0, "MKT")
    assert kw["source"] == "manual" and kw["protective"] is False


def test_live_sends_to_ibkr_and_touches_no_practice_ledger(brokers, monkeypatch) -> None:
    set_venue("live")
    _safety.set_armed(True, reason="test")
    sent: list[dict] = []

    def fake_place(**kw):
        sent.append(kw)
        return {"ok": False, "order_id": None, "error": "Gateway dark", "mode": "disconnected"}

    monkeypatch.setattr(_orders, "place_order", fake_place)
    receipt = _send(_cmd())
    assert receipt.ok is False and receipt.reason_code == "BROKER_REJECT"
    assert sent and sent[0]["symbol"] == "IMCC"
    assert brokers["paper"].calls == [] and brokers["sim"].calls == []


def test_cancel_and_replace_on_paper_reach_the_paper_broker(brokers) -> None:
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    cancelled = _send(_cmd("cancel", order_id=5, side=None, qty=None))
    assert cancelled.ok is True and cancelled.broker_status == "Cancelled" and cancelled.mode == "paper"
    replaced = _send(_cmd("replace", order_id=5, side=None, qty=None, limit_price=9.5))
    assert replaced.ok is True and replaced.mode == "paper"
    assert brokers["paper"].calls == [("cancel", (5, "manual")), ("replace", (5, 9.5, None))]
    assert brokers["sim"].calls == []


def test_protective_sources_place_on_paper_without_admission(brokers) -> None:
    set_venue("paper")
    brokers["paper"].reference.admission = lambda symbol: (False, "dark", "PRACTICE_NO_LIVE_PRINT")
    receipt = _send(_cmd(source="flatten", side="SELL"))
    assert receipt.ok is True
    assert brokers["paper"].calls[0][1]["protective"] is True


# ── validation on the practice venues ────────────────────────────────────────

def test_validate_asks_the_paper_reference_for_admission(brokers) -> None:
    set_venue("paper")
    _safety.set_armed(True, reason="test")
    brokers["paper"].reference.admission = lambda symbol: (False, "no live print", "PRACTICE_NO_LIVE_PRINT")
    brokers["sim"].reference.admission = lambda symbol: (_ for _ in ()).throw(AssertionError("sim asked"))
    assert validate_command(_cmd()) == (False, "no live print", "PRACTICE_NO_LIVE_PRINT")
    brokers["paper"].reference.admission = lambda symbol: (True, "OK", None)
    assert validate_command(_cmd()) == (True, "OK", None)


def test_practice_venues_ignore_the_ibkr_env_gates_but_live_keeps_them(brokers, monkeypatch) -> None:
    monkeypatch.setenv("IBKR_ORDERS_ENABLED", "false")
    monkeypatch.setattr(_client, "is_enabled", lambda: False)
    monkeypatch.setattr(_client, "is_connected", lambda: False)
    _safety.set_armed(True, reason="test")
    for target in ("paper", "sim"):
        set_venue(target)
        _safety.set_armed(True, reason="test")
        assert validate_command(_cmd()) == (True, "OK", None), target
        assert validate_command(_cmd("cancel", order_id=1, side=None, qty=None)) == (True, "OK", None)
        assert validate_command(_cmd("replace", order_id=1, side=None, qty=None, limit_price=9.0)) == (True, "OK", None)
    set_venue("live")
    _safety.set_armed(True, reason="test")
    assert validate_command(_cmd())[2] == "ORDERS_GATE"
    assert validate_command(_cmd("cancel", order_id=1, side=None, qty=None))[2] == "CANCEL_GATE"


def test_account_checks_on_paper_read_the_ledger_with_the_gateway_dark(brokers, monkeypatch) -> None:
    set_venue("paper")
    monkeypatch.setattr(_client, "is_connected", lambda: False)
    priced = _cmd(order_type="LMT", limit_price=50.0, qty=10)
    assert check_account_and_position(priced) == (True, "OK", None)
    brokers["paper"].buying_power = 100.0
    assert check_account_and_position(priced)[2] == "BUYING_POWER"


# ── ibkr.orders and the account hooks answer from the venue's ledger ─────────

def test_orders_and_account_read_the_paper_ledger(brokers) -> None:
    set_venue("paper")
    assert _orders.open_orders() == brokers["paper"].working_orders()
    assert _orders.closed_orders() == brokers["paper"].closed_orders()
    assert _account.positions_for_ui() == brokers["paper"].positions()
    assert _account.get_positions() == brokers["paper"].positions()
    assert _account.get_account_summary()["account_id"] == "NOVA-PAPER"
    assert _account.account_summary_for_ui()["mode"] == "paper"
    set_venue("sim")
    assert _orders.open_orders()[0]["venue"] == "sim"
    assert _account.get_account_summary()["account_id"] == "NOVA-SIM"


def test_ibkr_places_are_refused_on_paper_in_papers_own_words(brokers) -> None:
    set_venue("paper")
    placed = _orders.place_order("IMCC", "BUY", 1, "MKT")
    assert placed["ok"] is False and placed["mode"] == "paper"
    assert placed["error"] == DESK_PAPER_NO_IBKR_REASON and placed["reason_code"] == SIM_NO_IBKR_CODE
    bracket = _orders.place_bracket_order("IMCC", "BUY", 1, 25.0, 24.0, 26.0)
    assert bracket["ok"] is False and bracket["mode"] == "paper" and bracket["error"] == DESK_PAPER_NO_IBKR_REASON
    cancelled = _orders.cancel_order(9)
    assert cancelled["ok"] is False and cancelled["mode"] == "paper"
    set_venue("sim")
    assert _orders.place_order("IMCC", "BUY", 1, "MKT")["error"] == SIM_NO_IBKR_REASON


# ── spend gates: a practice venue needs the latch only ───────────────────────

@pytest.fixture
def env_locks_ibkr(monkeypatch):
    monkeypatch.setenv("IBKR_ORDERS_ENABLED", "false")
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "live")
    monkeypatch.setenv("IBKR_LIVE_TRADING_CONFIRMED", "false")
    monkeypatch.setattr(_client, "is_enabled", lambda: False)
    monkeypatch.setattr(_client, "is_ready", lambda: False)
    monkeypatch.setattr(_client, "is_connected", lambda: False)
    monkeypatch.setattr(_client, "account_mode", lambda: "disconnected")
    monkeypatch.setattr(_client, "broker_account_kind", lambda: "unknown")
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.mark.parametrize(("target", "armed_status"), [("paper", "paper_armed"), ("sim", "sim_armed")])
def test_practice_venue_spend_reads_the_latch_alone(env_locks_ibkr, target: str, armed_status: str) -> None:
    set_venue(target)
    assert _safety.spend_permitted("unknown") == (armed_status, "")
    assert _safety.spend_state("unknown") == ("locked_disarmed", DISARMED_REASON)
    snap = _safety.status_snapshot("unknown")
    assert snap["spend_permitted"] is True and snap["spend_permitted_status"] == armed_status
    assert snap["spend_status"] == "locked_disarmed" and snap["armed_for_account_kind"] is None
    assert places_allowed() == (False, DISARMED_REASON)
    dark = evaluate_trading_allowed(client_enabled=False, connected=False, account_mode="disconnected")
    assert dark["trading_allowed"] is False and dark["spend_status"] == "locked_disarmed"

    _safety.set_armed(True, reason="operator")
    assert _safety.spend_state("unknown") == (armed_status, "")
    assert _safety.status_snapshot("unknown")["spend_status"] == armed_status
    assert places_allowed() == (True, "")
    armed = evaluate_trading_allowed(client_enabled=False, connected=False, account_mode="disconnected")
    assert armed["trading_allowed"] is True and armed["spend_status"] == armed_status
    assert armed["trading_allowed_reason"] is None


def test_live_venue_keeps_every_ibkr_env_gate(env_locks_ibkr) -> None:
    set_venue("live")
    _safety.set_armed(True, reason="operator")
    assert _safety.spend_permitted("unknown")[0] == "locked"
    assert _safety.status_snapshot("unknown")["spend_permitted"] is False
    ok, reason = places_allowed()
    assert ok is False and "IBKR" in reason


# ── the legacy IBKR paper Gateway switch never moves the venue ───────────────

@pytest.mark.parametrize(("start", "gateway"), [("paper", "live"), ("live", "paper"), ("sim", "paper")])
def test_gateway_mode_switch_keeps_the_venue(monkeypatch, start: str, gateway: str) -> None:
    from ibkr import gateway_heal as heal

    reset_for_tests()
    set_venue(start)
    monkeypatch.setattr(_client, "_enabled", True)
    monkeypatch.setattr(_client, "_ib", None)
    monkeypatch.setattr(_client, "is_connected", lambda: True)
    monkeypatch.setattr(_client, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(_client, "account_mode", lambda: "paper")
    with (
        patch.object(heal, "persist_gateway_mode", return_value=True),
        patch.object(heal, "apply_runtime_gateway_mode"),
        patch.object(heal, "set_intentional_mode"),
        patch("ibkr.launch_gateway.launch_or_focus_gateway"),
    ):
        result = asyncio.run(_client.request_gateway_mode(gateway))
    assert result["ok"] is True
    assert venue() == start, "POST /api/ibkr/gateway-mode is the legacy Gateway door, not a venue click"
    heal.clear_heal_status_for_tests()
    reset_for_tests()
