"""L2 fire path -- mocked execution door only."""
from __future__ import annotations

import pytest

from bot.actions import fire
from bot.autonomy import apply_patch
from bot.errors import BotError
from bot.persist import load_session
from constants_bot import (
    BOT_REASON_FREE_FORM_QTY,
    BOT_REASON_L0_DARK,
    BOT_REASON_L1_NO_FIRE,
    BOT_REASON_NOT_ACTIVE,
    BOT_REASON_PACK_STUB,
)
from tests.bot_helpers import ready_l2
from execution.models import ExecutionReceipt


def _ok(order_id: int = 42, **kw) -> ExecutionReceipt:
    return ExecutionReceipt(
        ok=True,
        execution_id="exec-1",
        operation="place",
        source="bot",
        idempotency_key="k",
        order_id=order_id,
        **kw,
    )


@pytest.fixture
def l2_brain():
    ready_l2(brain="brain-1", heartbeat=True)


@pytest.mark.asyncio
async def test_l0_cannot_fire():
    with pytest.raises(BotError) as exc:
        await fire({"kind": "buy_market", "symbol": "ABCD"}, brain_session_id="x")
    assert exc.value.reason == BOT_REASON_L0_DARK


@pytest.mark.asyncio
async def test_l1_cannot_fire():
    apply_patch({"level": 1}, desk=True)
    with pytest.raises(BotError) as exc:
        await fire({"kind": "buy_market", "symbol": "ABCD"}, brain_session_id="x")
    assert exc.value.reason == BOT_REASON_L1_NO_FIRE


@pytest.mark.asyncio
async def test_l2_pack_allowlist_not_active_rejects(monkeypatch):
    """L2 + live pack + allowlist is not enough -- Activate is a separate axis."""
    from bot.arming import disarm_session

    ready_l2(brain="brain-1", heartbeat=True)
    disarm_session()
    called = {"n": 0}

    async def fake_execute(cmd, wait_ack=False):
        called["n"] += 1
        return _ok(1)

    monkeypatch.setattr("bot.actions.execute", fake_execute)
    with pytest.raises(BotError) as exc:
        await fire({"kind": "buy_market", "symbol": "ABCD"}, brain_session_id="brain-1")
    assert exc.value.reason == BOT_REASON_NOT_ACTIVE
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_buy_market_uses_preset_shares_and_source_bot(monkeypatch, l2_brain):
    seen = {}

    async def fake_execute(cmd, wait_ack=False):
        seen["cmd"] = cmd
        return _ok(51)

    monkeypatch.setattr("bot.actions.execute", fake_execute)
    monkeypatch.setattr("bot.risk.last_quote", lambda _s: {"price": 2.0})
    monkeypatch.setattr("bot.risk.top_of_book", lambda _s: (1.9, 2.1))
    result = await fire({"kind": "buy_market", "symbol": "abcd"}, brain_session_id="brain-1")
    assert result["ok"] is True
    assert result["order_id"] == 51
    cmd = seen["cmd"]
    assert cmd.source == "bot"
    assert cmd.side == "BUY"
    assert cmd.qty == 1.0
    assert cmd.order_type == "MKT"
    assert cmd.outside_rth is False
    assert cmd.skip_risk is True
    assert load_session()["bot_qty"]["ABCD"] == 1.0


@pytest.mark.asyncio
async def test_free_form_qty_on_fire(l2_brain):
    with pytest.raises(BotError) as exc:
        await fire({"kind": "buy_market", "symbol": "ABCD", "qty": 4}, brain_session_id="brain-1")
    assert exc.value.reason == BOT_REASON_FREE_FORM_QTY


@pytest.mark.asyncio
async def test_limit_buy_remembers_working_not_bot_qty(monkeypatch, l2_brain):
    async def fake_execute(cmd, wait_ack=False):
        return _ok(77)

    monkeypatch.setattr("bot.actions.execute", fake_execute)
    monkeypatch.setattr("bot.risk.top_of_book", lambda _s: (1.0, 2.0))
    monkeypatch.setattr("bot.risk.last_quote", lambda _s: {"price": 2.0})
    await fire({"kind": "buy_limit_ask_offset", "symbol": "ABCD"}, brain_session_id="brain-1")
    row = load_session()
    assert row["bot_qty"] == {}
    assert len(row["working"]) == 1
    assert row["working"][0]["order_id"] == 77
    assert row["working"][0]["side"] == "BUY"
    assert row["working"][0]["price"] == pytest.approx(2.05)


@pytest.mark.asyncio
async def test_cancel_symbol_uses_execute(monkeypatch, l2_brain):
    monkeypatch.setattr(
        "ibkr.orders.open_orders",
        lambda: [{"symbol": "ABCD", "order_id": 9}, {"symbol": "ZZZ", "order_id": 8}],
    )
    cancelled = []

    async def fake_execute(cmd, wait_ack=False):
        cancelled.append(cmd.order_id)
        return _ok(cmd.order_id or 0)

    monkeypatch.setattr("bot.actions.execute", fake_execute)
    result = await fire({"kind": "cancel_symbol", "symbol": "ABCD"}, brain_session_id="brain-1")
    assert result["ok"] is True
    assert cancelled == [9]


@pytest.mark.asyncio
async def test_exit_pos_needs_long(monkeypatch, l2_brain):
    monkeypatch.setattr("bot.actions._position_qty", lambda _s: 0)
    with pytest.raises(BotError) as exc:
        await fire({"kind": "exit_pos", "symbol": "ABCD"}, brain_session_id="brain-1")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_eh_follows_session(monkeypatch, l2_brain):
    apply_patch({"caps": {"extended_hours": True}}, desk=True)
    seen = {}

    async def fake_execute(cmd, wait_ack=False):
        seen["eh"] = cmd.outside_rth
        return _ok(1)

    monkeypatch.setattr("bot.actions.execute", fake_execute)
    monkeypatch.setattr("bot.risk.last_quote", lambda _s: {"price": 1.0})
    await fire({"kind": "buy_market", "symbol": "ABCD"}, brain_session_id="brain-1")
    assert seen["eh"] is True


@pytest.mark.asyncio
async def test_stub_pack_cannot_fire(l2_brain):
    apply_patch({"active_pack": "volume"}, desk=True)
    with pytest.raises(BotError) as exc:
        await fire({"kind": "buy_market", "symbol": "ABCD"}, brain_session_id="brain-1")
    assert exc.value.reason == BOT_REASON_PACK_STUB
