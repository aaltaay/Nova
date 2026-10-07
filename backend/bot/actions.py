"""Allowlisted NovaActionKind -> execution.service.execute(source=bot).

ADR 042 J: every kind -- buys, exits and cancels alike -- is refused on Live and on a
replay desk (``409 BOT_LIVE_NOT_BUILT``): a bot never touches Live. On Paper and Sim at
the live edge every kind passes one symbol gate before anything else is resolved:
``eligibility.assert_symbol_can_fire`` -- this venue's bot list AND a depth line the
backend holds (``409 BOT_NO_DEPTH_LINE`` otherwise, ADR 020 second pass).

Shorts (ADR 049, #778 step 5): ``short_limit_bid_offset`` shorts the sleeve's max shares one cent over the
bid with its buy stop (``BOT_DEFAULT_SHORT_STOP_OFFSET_USD`` over the limit) in one bracket, through the one
short check at the door; never while the venue holds the stock long. The covers buy back what the venue holds
short and never past it: ``cover_limit_ask_offset`` and ``cover_market`` up to the max shares, ``cover_pos``
the whole short as a protective close (like Flatten).
"""
from __future__ import annotations

import uuid
from typing import Any

from bot.audit import record as audit
from bot.autonomy import assert_can_fire
from bot.buy_lock import day_lock_active
from bot.errors import BotError
from bot.kinds import is_entry_kind
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
from constants_bot import (
    BOT_DEFAULT_ASK_OFFSET_USD,
    BOT_DEFAULT_SHORT_STOP_OFFSET_USD,
    BOT_REASON_DAY_LOCK,
)
from execution.models import ExecutionCommand
from execution.service import execute


def _position_qty(symbol: str) -> float:
    from ibkr import account as _account

    try:
        return float(_account.long_qty(symbol) or 0)
    except Exception as exc:
        # Unknown is never "flat": an exit on an unreadable position is refused with the reason.
        raise BotError(f"the {symbol} position could not be read ({exc})", 503, "BOT_POSITION_UNREADABLE") from exc


def _short_qty(symbol: str) -> float:
    """The shares the venue holds short (a positive count); unknown is never flat."""
    from ibkr import account as _account

    try:
        return float(_account.short_qty(symbol) or 0)
    except Exception as exc:
        raise BotError(f"the {symbol} position could not be read ({exc})", 503, "BOT_POSITION_UNREADABLE") from exc


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
                origin="bot_api",  # the localhost bot API
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
    row = assert_can_fire()      # Live / a replay desk refuse first (BOT_LIVE_NOT_BUILT)
    require_l2_brain(brain_session_id, claim=True)
    kind = assert_kind(str(body.get("kind") or body.get("action") or ""), row)
    symbol = assert_symbol_can_fire(str(body.get("symbol") or ""), row)
    if day_lock_active() and is_entry_kind(kind):
        from bot.gates import current_venue, day_lock, lock_text

        raise BotError(lock_text(day_lock(row, current_venue())), 409, BOT_REASON_DAY_LOCK)
    assert_entry_allowed(kind)  # the Strategy setups' windows, extended hours, the shared daily cap

    assert_no_working_buy(kind, row)
    eh = outside_rth(row)
    from bot.sleeve import of as sleeve_of

    ttl = int(sleeve_of(row)["working_ttl_sec"])

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
            origin="bot_api",  # the localhost bot API
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
            origin="bot_api",  # the localhost bot API
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
            origin="bot_api",  # the localhost bot API
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

    if kind in ("short_limit_bid_offset", "cover_limit_ask_offset", "cover_market", "cover_pos"):
        return await _fire_short_side(kind, symbol, body, row, eh=eh, ttl=ttl, brain_session_id=brain_session_id)

    offset = resolve_offset(kind, body)
    if kind in ("sell_pos_pct_ask", "sell_pos_pct_bid_offset"):
        percent = resolve_percent(body)
        side, qty = _exit_qty(symbol, percent)
        limit = limit_from_book(kind, symbol, offset)
        cmd = ExecutionCommand(
            operation="place",
            idempotency_key=str(body.get("idempotency_key") or f"bot:{kind}:{symbol}:{uuid.uuid4()}"),
            source="bot",
            origin="bot_api",  # the localhost bot API
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
        origin="bot_api",  # the localhost bot API
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


async def _fire_short_side(kind: str, symbol: str, body: dict[str, Any], row: dict[str, Any], *, eh: bool,
                           ttl: int, brain_session_id: str | None) -> dict[str, Any]:
    """A short with its buy stop, or a cover of what the venue holds short (see the module)."""
    from bot.first_pullback.orders import best_ask, best_bid
    from bot.flatten import place_close

    key = str(body.get("idempotency_key") or f"bot:{kind}:{symbol}:{uuid.uuid4()}")
    if kind == "short_limit_bid_offset":
        if body.get("qty") is not None or body.get("stop_price") is not None:
            raise BotError("free-form qty and stop are refused -- the short's size and buy stop come from the "
                           "session presets", 400, "BOT_FREE_FORM_QTY")
        held = _position_qty(symbol)
        if held > 0:
            raise BotError(f"you hold {symbol} long: Nova never shorts a stock you hold long", 409,
                           "BOT_SKIP_HELD_OTHER_SIDE")
        bid = best_bid(symbol)
        if bid is None:
            raise BotError("needs a live bid for the focused symbol", 409, "BOT_NEEDS_DEPTH")
        qty = float(resolve_shares(kind, body, row))
        limit = round(bid + 0.01, 4)
        stop = round(limit + BOT_DEFAULT_SHORT_STOP_OFFSET_USD, 4)
        assert_bp_budget(kind, symbol, qty, limit, row)
        cmd = ExecutionCommand(operation="bracket", idempotency_key=key, source="bot", origin="bot_api",
                               symbol=symbol, side="SELL", short_entry=True, qty=qty, order_type="LMT",
                               limit_price=limit, entry_price=limit, stop_price=stop, reference_price=limit,
                               outside_rth=eh, skip_risk=True)
        receipt = await execute(cmd, wait_ack=False)
        if receipt.ok and receipt.order_id is not None:
            remember_working(order_id=int(receipt.order_id), symbol=symbol, side="SELL", qty=qty, price=limit,
                             kind=kind, ttl_sec=ttl, short_entry=True)
        audit(action=kind, outcome="ok" if receipt.ok else "failed", order_id=receipt.order_id,
              reason=receipt.reason_code, brain_session_id=brain_session_id,
              inputs={"symbol": symbol, "qty": qty, "limit": limit, "stop": stop, "side": "short",
                      "venue_day": venue_day()})
        return receipt.legacy_place_dict()
    short = _short_qty(symbol)
    if short <= 0:
        raise BotError(f"no short position in {symbol} to cover", 409, "BOT_NO_POSITION")
    if kind == "cover_pos":
        out = await place_close(symbol, short, "BUY", origin="bot_api")
        if out.get("ok"):
            adjust_bot_qty(symbol, short)
        audit(action=kind, outcome="ok" if out.get("ok") else "failed", order_id=out.get("order_id"),
              reason=out.get("reason_code"), inputs={"symbol": symbol, "qty": short}, brain_session_id=brain_session_id)
        return out
    qty = min(float(resolve_shares(kind, body, row)), short)       # a cover never buys past flat
    if kind == "cover_market":
        cmd = ExecutionCommand(operation="place", idempotency_key=key, source="bot", origin="bot_api", symbol=symbol,
                               side="BUY", qty=qty, order_type="MKT", outside_rth=eh, skip_risk=True)
        limit = None
    else:
        ask = best_ask(symbol)
        if ask is None:
            raise BotError("needs a live ask for the focused symbol", 409, "BOT_NEEDS_DEPTH")
        limit = round(ask + BOT_DEFAULT_ASK_OFFSET_USD, 4)
        cmd = ExecutionCommand(operation="place", idempotency_key=key, source="bot", origin="bot_api", symbol=symbol,
                               side="BUY", qty=qty, order_type="LMT", limit_price=limit, reference_price=limit,
                               outside_rth=eh, skip_risk=True)
    receipt = await execute(cmd, wait_ack=False)
    if receipt.ok and receipt.order_id is not None:
        if limit is None:
            adjust_bot_qty(symbol, qty)
        else:
            remember_working(order_id=int(receipt.order_id), symbol=symbol, side="BUY", qty=qty, price=limit,
                             kind=kind, ttl_sec=ttl, cover=True)
    audit(action=kind, outcome="ok" if receipt.ok else "failed", order_id=receipt.order_id,
          reason=receipt.reason_code, inputs={"symbol": symbol, "qty": qty, "limit": limit, "side": "cover"},
          brain_session_id=brain_session_id)
    return receipt.legacy_place_dict()
