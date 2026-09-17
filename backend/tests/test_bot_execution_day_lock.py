"""-$200 day lock refuses bot and manual BUY through the order SSOT."""
from __future__ import annotations

import asyncio

import execution.store as store
import execution.telemetry as telemetry
import execution.service as exec_svc
import ibkr.orders as orders_mod
from bot.persist import load_session, save_session
from execution.models import ExecutionCommand


def _buy(source: str, key: str) -> ExecutionCommand:
    return ExecutionCommand(
        operation="place",
        idempotency_key=key,
        source=source,  # type: ignore[arg-type]
        symbol="AAPL",
        side="BUY",
        qty=1,
        order_type="MKT",
        skip_risk=True,
        skip_concurrency=True,
    )


def test_day_lock_blocks_manual_and_bot_buy(monkeypatch):
    store.init_db()
    telemetry.reset_for_tests()
    row = load_session()
    row["hard_lock_until_date"] = "2099-01-01"
    save_session(row)
    called = []
    monkeypatch.setattr(orders_mod, "place_order", lambda **k: called.append(1) or {"ok": True})
    monkeypatch.setattr("ibkr.client.is_enabled", lambda: True)
    monkeypatch.setattr("ibkr.client.is_connected", lambda: True)
    monkeypatch.setattr("ibkr.client.account_mode", lambda: "paper")
    monkeypatch.setattr("ibkr.client.broker_account_kind", lambda: "paper")
    monkeypatch.setattr("ibkr.safety.orders_enabled", lambda: True)
    monkeypatch.setenv("IBKR_GATEWAY_MODE", "paper")
    monkeypatch.setattr(
        "ibkr.account.get_account_summary",
        lambda: {"connected": True, "BuyingPower": 100_000, "pending": False},
    )
    monkeypatch.setattr("ibkr.account.get_positions", lambda: [])

    manual = asyncio.run(exec_svc.execute(_buy("manual", "lock-manual"), wait_ack=False))
    assert manual.ok is False
    assert manual.reason_code == "BOT_DAY_LOCK"
    bot = asyncio.run(exec_svc.execute(_buy("bot", "lock-bot"), wait_ack=False))
    assert bot.ok is False
    assert bot.reason_code == "BOT_DAY_LOCK"
    flatten = asyncio.run(
        exec_svc.execute(
            ExecutionCommand(
                operation="place",
                idempotency_key="lock-flat",
                source="flatten",
                symbol="AAPL",
                side="BUY",
                qty=1,
                order_type="MKT",
                skip_risk=True,
                skip_concurrency=True,
            ),
            wait_ack=False,
        )
    )
    assert flatten.reason_code != "BOT_DAY_LOCK"
    assert called == [1]
