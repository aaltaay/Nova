"""Working-order TTL auto-cancel uses the execution door."""
from __future__ import annotations

import time

import pytest

from bot.persist import load_session, save_session
from bot.risk import remember_working
from bot.ttl import cancel_due
from execution.models import ExecutionReceipt


@pytest.mark.asyncio
async def test_cancel_due_drops_working(monkeypatch):
    remember_working(
        order_id=88,
        symbol="ABCD",
        side="BUY",
        qty=1,
        price=2.0,
        kind="buy_limit_ask_offset",
        ttl_sec=1,
    )
    row = load_session()
    row["working"][0]["expire_ts"] = time.time() - 1
    save_session(row)
    seen = []

    async def fake_execute(cmd, wait_ack=False):
        seen.append(cmd)
        return ExecutionReceipt(
            ok=True,
            execution_id="e",
            operation="cancel",
            source="bot",
            idempotency_key=cmd.idempotency_key,
            order_id=cmd.order_id,
        )

    monkeypatch.setattr("execution.service.execute", fake_execute)
    results = await cancel_due()
    assert results[0]["ok"] is True
    assert seen[0].source == "bot"
    assert seen[0].operation == "cancel"
    assert load_session()["working"] == []
