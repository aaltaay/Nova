"""Execution service enforces verification latch without blocking exits."""
from __future__ import annotations

import asyncio

import pytest

from execution import service, store, verification_gate
from execution.models import ExecutionCommand
from ibkr import account, client, orders, safety


@pytest.fixture(autouse=True)
def reset_verification_latch():
    verification_gate.reset_for_tests()
    yield
    verification_gate.reset_for_tests()


def _place(key: str, side: str, *, source: str = "manual") -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key=key,
        source=source,  # type: ignore[arg-type]
        symbol="AAPL",
        side=side,
        qty=1,
        order_type="MKT",
        skip_risk=True,
        skip_concurrency=True,
    )


def _arm(monkeypatch, tmp_path, positions: list[dict]) -> list[str]:
    monkeypatch.setattr(store, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(client, "is_enabled", lambda: True)
    monkeypatch.setattr(client, "is_connected", lambda: True)
    monkeypatch.setattr(client, "account_mode", lambda: "paper")
    monkeypatch.setattr(client, "broker_account_kind", lambda: "paper")
    monkeypatch.setattr(client, "get_ib", lambda: None)
    monkeypatch.setattr(safety, "orders_enabled", lambda: True)
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setattr(
        account,
        "get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000.0, "pending": False},
    )
    monkeypatch.setattr(account, "get_positions", lambda: positions)
    calls: list[str] = []
    monkeypatch.setattr(
        orders,
        "place_order",
        lambda **kwargs: calls.append(kwargs["side"]) or {
            "ok": True,
            "order_id": len(calls),
            "mode": "paper",
        },
    )
    store.init_db()
    service.reset_for_tests()
    verification_gate.latch("AAPL")
    return calls


def test_service_blocks_repeated_long_entry(monkeypatch, tmp_path) -> None:
    calls = _arm(monkeypatch, tmp_path, [])

    receipt = asyncio.run(service.execute(_place("blocked-buy", "BUY"), wait_ack=False))

    assert receipt.ok is False
    assert receipt.reason_code == "IBKR_VERIFICATION_REQUIRED"
    assert calls == []


def test_service_allows_long_exit(monkeypatch, tmp_path) -> None:
    calls = _arm(monkeypatch, tmp_path, [{"symbol": "AAPL", "qty": 1}])

    receipt = asyncio.run(service.execute(_place("long-exit", "SELL"), wait_ack=False))

    assert receipt.ok is True
    assert calls == ["SELL"]


def test_service_allows_short_cover(monkeypatch, tmp_path) -> None:
    calls = _arm(monkeypatch, tmp_path, [{"symbol": "AAPL", "qty": -1}])

    receipt = asyncio.run(service.execute(_place("short-cover", "BUY"), wait_ack=False))

    assert receipt.ok is True
    assert calls == ["BUY"]
