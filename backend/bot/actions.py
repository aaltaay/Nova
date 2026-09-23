"""Allowlisted NovaActionKind -> execution.service.execute(source=bot).

Every kind passes one symbol gate before anything else is resolved:
``eligibility.assert_symbol_can_fire`` -- allowlist AND a depth line the
backend holds (``409 BOT_NO_DEPTH_LINE`` otherwise, ADR 020 second pass).
"""
from __future__ import annotations

import uuid
from typing import Any

from bot.audit import record as audit
from bot.autonomy import assert_can_fire
from bot.buy_lock import day_lock_active
from bot.errors import BotError
from bot.risk import (
    adjust_bot_qty,
    assert_bp_budget,
    assert_kind,
    assert_no_working_buy,
    drop_working,
    limit_from_book,
    outside_rth,
    remember_working,
    resolve_offset,
    resolve_percent,
    resolve_shares,
)
from bot.eligibility import assert_symbol_can_fire
from bot.entry_rules import assert_entry_allowed, venue_day
from bot.session import require_l2_brain
from constants_bot import BOT_REASON_DAY_LOCK
from execution.models import ExecutionCommand
from execution.service import execute


def _position_qty(symbol: str) -> float:
    from ibkr import account as _account

    try:
        return float(_account.long_qty(symbol) or 0)
    except Exception:
        return 0.0


def _exit_qty(symbol: str, percent: int | None = None) -> tuple[str, float]:
    qty = _position_qty(symbol)
    if qty <= 0:
        raise BotError(f"no long position in {symbol} to exit", 409, "BOT_NO_POSITION")
    if percent is None:
        return "SELL", qty
    return "SELL", max(1.0, round(qty * (percent / 100.0)))


async def _cancel_symbol(symbol: str) -> dict[str, Any]:
    from ibkr import orders as _orders

    cancelled: list[int] = []
    failed: list[dict[str, Any]] = []
    try:
        rows = _orders.open_orders()
    except Exception as exc:
        raise BotError(f"cannot read working orders: {exc}", 503) from exc
    for row in rows:
        if str(row.get("symbol") or "").upper() != symbol:
            continue
        order_id = row.get("order_id")
        if order_id is None:
            continue
        receipt = await execute(
            ExecutionCommand(
                operation="cancel",
                idempotency_key=f"bot:cancel:{order_id}:{uuid.uuid4()}",
                source="bot",
                order_id=int(order_id),
                symbol=symbol,
                skip_risk=True,
            ),
            wait_ack=False,
        )
        if receipt.ok:
            cancelled.append(int(order_id))
            drop_working(int(order_id))
        else:
            failed.append(receipt.legacy_place_dict())
    return {"ok": not failed, "cancelled": cancelled, "failed": failed}


async def fire(
    body: dict[str, Any],
    *,
    brain_session_id: str | None,
) -> dict[str, Any]:
    row = assert_can_fire()
    require_l2_brain(brain_session_id, claim=True)
    kind = assert_kind(str(body.get("kind") or body.get("action") or ""), row)
    symbol = assert_symbol_can_fire(str(body.get("symbol") or ""), row)
    if day_lock_active() and kind.startswith("buy_"):
        raise BotError("-$200 day lock -- buys locked until next ET midnight", 409, BOT_REASON_DAY_LOCK)
    assert_entry_allowed(kind)  # ADR 027: the material's window and one trade a day

    assert_no_working_buy(kind, row)
    eh = outside_rth(row)
    ttl = int((row.get("caps") or {}).get("working_ttl_sec") or 3)

    if kind == "cancel_symbol":
        result = await _cancel_symbol(symbol)
        audit(action=kind, outcome="ok" if result.get("ok") else "failed", inputs={"symbol": symbol}, brain_session_id=brain_session_id)
        return result

    if kind == "exit_pos":
        side, qty = _exit_qty(symbol)
        cmd = ExecutionCommand(
            operation="place",
            idempotency_key=str(body.get("idempotency_key") or f"bot:{kind}:{symbol}:{uuid.uuid4()}"),
            source="bot",
            symbol=symbol,
            side=side,
            qty=qty,
            order_type="MKT",
            outside_rth=eh,
            skip_risk=True,
        )
        receipt = await execute(cmd, wait_ack=False)
        if receipt.ok:
            adjust_bot_qty(symbol, -qty)
        audit(action=kind, outcome="ok" if receipt.ok else "failed", order_id=receipt.order_id, reason=receipt.reason_code, inputs={"symbol": symbol, "qty": qty}, brain_session_id=brain_session_id)
        return receipt.legacy_place_dict()

    if kind == "exit_pos_pct":
        percent = resolve_percent(body)
        side, qty = _exit_qty(symbol, percent)
        cmd = ExecutionCommand(
            operation="place",
            idempotency_key=str(body.get("idempotency_key") or f"bot:{kind}:{symbol}:{uuid.uuid4()}"),
            source="bot",
            symbol=symbol,
            side=side,
            qty=qty,
            order_type="MKT",
            outside_rth=eh,
            skip_risk=True,
        )
        receipt = await execute(cmd, wait_ack=False)
        if receipt.ok:
            adjust_bot_qty(symbol, -qty)
        audit(action=kind, outcome="ok" if receipt.ok else "failed", order_id=receipt.order_id, reason=receipt.reason_code, inputs={"symbol": symbol, "qty": qty, "percent": percent}, brain_session_id=brain_session_id)
        return receipt.legacy_place_dict()

    if kind == "buy_market":
        qty = float(resolve_shares(kind, body, row))
        assert_bp_budget(kind, symbol, qty, None, row)
        cmd = ExecutionCommand(
            operation="place",
            idempotency_key=str(body.get("idempotency_key") or f"bot:{kind}:{symbol}:{uuid.uuid4()}"),
            source="bot",
            symbol=symbol,
            side="BUY",
            qty=qty,
            order_type="MKT",
            outside_rth=eh,
            skip_risk=True,
        )
        receipt = await execute(cmd, wait_ack=False)
        if receipt.ok:
            adjust_bot_qty(symbol, qty)
        audit(action=kind, outcome="ok" if receipt.ok else "failed", order_id=receipt.order_id, reason=receipt.reason_code, inputs={"symbol": symbol, "qty": qty, "venue_day": venue_day()}, brain_session_id=brain_session_id)
        return receipt.legacy_place_dict()

    offset = resolve_offset(kind, body)
    if kind in ("sell_pos_pct_ask", "sell_pos_pct_bid_offset"):
        percent = resolve_percent(body)
        side, qty = _exit_qty(symbol, percent)
        limit = limit_from_book(kind, symbol, offset)
        cmd = ExecutionCommand(
            operation="place",
            idempotency_key=str(body.get("idempotency_key") or f"bot:{kind}:{symbol}:{uuid.uuid4()}"),
            source="bot",
            symbol=symbol,
            side=side,
            qty=qty,
            order_type="LMT",
            limit_price=round(limit, 4),
            reference_price=limit,
            outside_rth=eh,
            skip_risk=True,
        )
        receipt = await execute(cmd, wait_ack=False)
        if receipt.ok and receipt.order_id is not None:
            remember_working(order_id=int(receipt.order_id), symbol=symbol, side=side, qty=qty, price=limit, kind=kind, ttl_sec=ttl)
        audit(action=kind, outcome="ok" if receipt.ok else "failed", order_id=receipt.order_id, reason=receipt.reason_code, inputs={"symbol": symbol, "qty": qty, "limit": limit}, brain_session_id=brain_session_id)
        return receipt.legacy_place_dict()

    qty = float(resolve_shares(kind, body, row))
    limit = limit_from_book(kind, symbol, offset)
    side = "BUY" if kind.startswith("buy_") else "SELL"
    if side == "BUY":
        assert_bp_budget(kind, symbol, qty, limit, row)
    elif side == "SELL":
        long_qty = _position_qty(symbol)
        if long_qty + 1e-9 < qty:
            raise BotError("sell qty exceeds long position", 409, "BOT_NO_POSITION")
    cmd = ExecutionCommand(
        operation="place",
        idempotency_key=str(body.get("idempotency_key") or f"bot:{kind}:{symbol}:{uuid.uuid4()}"),
        source="bot",
        symbol=symbol,
        side=side,
        qty=qty,
        order_type="LMT",
        limit_price=round(limit, 4),
        reference_price=limit,
        outside_rth=eh,
        skip_risk=True,
    )
    receipt = await execute(cmd, wait_ack=False)
    if receipt.ok and receipt.order_id is not None:
        remember_working(order_id=int(receipt.order_id), symbol=symbol, side=side, qty=qty, price=limit, kind=kind, ttl_sec=ttl)
    inputs = {"symbol": symbol, "qty": qty, "limit": limit}
    if side == "BUY":
        inputs["venue_day"] = venue_day()
    audit(action=kind, outcome="ok" if receipt.ok else "failed", order_id=receipt.order_id, reason=receipt.reason_code, inputs=inputs, brain_session_id=brain_session_id)
    return receipt.legacy_place_dict()
