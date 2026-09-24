"""Whole-account flatten through the existing execution door.

Desk HTTP: POST /api/ibkr/flatten-account (Emergency KILL + tests).
Breakers call flatten_account_with_retry directly -- same function.
Cancel leftover working first, then place closes -- never cancel after place.
Weekday RTH closes are MKT. After hours / weekend uses an EH LMT so IBKR
cannot hold the exit until the next regular session.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from constants_bot import BOT_FLATTEN_RETRIES

logger = logging.getLogger(__name__)


async def _place_close(symbol: str, qty: float, side: str) -> dict[str, Any]:
    from execution.flatten_exit import (
        plan_flatten_exit,
        plan_practice_flatten_exit,
        resolve_flatten_marks,
        ticket_to_command_fields,
    )
    from execution.models import ExecutionCommand
    from execution.service import execute
    from sim.mode import is_practice_venue

    if is_practice_venue():
        # The practice broker closes a held position at the last mark at any
        # hour, feed or no feed (ADR 018 / 019) -- no EH sweep, no mark needed.
        ticket = plan_practice_flatten_exit()
    else:
        bid, ask, last = resolve_flatten_marks(symbol)
        ticket = plan_flatten_exit(side, bid=bid, ask=ask, last=last)
    if not ticket.ok:
        return {"ok": False, "error": ticket.error, "reason_code": "FLATTEN_EH_NO_MARK"}

    receipt = await execute(
        ExecutionCommand(
            operation="place",
            idempotency_key=f"bot:flatten:{side.lower()}:{symbol}:{uuid.uuid4()}",
            source="flatten",
            symbol=symbol,
            side=side,
            qty=abs(float(qty)),
            skip_risk=True,
            **ticket_to_command_fields(ticket),
        ),
        wait_ack=False,
    )
    out = receipt.legacy_place_dict()
    # What the broker was actually sent, so the caller can prove a whole close.
    out["sent_qty"] = _sent_qty(receipt)
    return out


def _sent_qty(receipt: Any) -> float | None:
    """The size execute() sent for this receipt, from its record (QA R33).

    A receipt's own payload does not carry ``sent_qty``; the execution record
    does (``execution.record_payload``). Unknown stays None -- never a guess.
    """
    payload = getattr(receipt, "payload", None) or {}
    sent = payload.get("sent_qty")
    execution_id = getattr(receipt, "execution_id", None)
    if sent is None and execution_id:
        try:
            from execution import store

            row = store.get_by_id(str(execution_id)) or {}
            sent = (row.get("payload") or {}).get("sent_qty")
        except Exception:
            logger.exception("bot flatten: execution record unreadable for %s", execution_id)
            return None
    try:
        return float(sent) if sent is not None else None
    except (TypeError, ValueError):
        return None


async def _cancel_working() -> list[dict[str, Any]]:
    from execution.models import ExecutionCommand
    from execution.service import execute
    from ibkr import orders as _orders

    results: list[dict[str, Any]] = []
    try:
        open_rows = _orders.open_orders()
    except Exception as exc:
        logger.exception("bot flatten: open_orders failed")
        return [{"ok": False, "error": str(exc)}]
    for row in open_rows:
        order_id = row.get("order_id")
        if order_id is None:
            continue
        receipt = await execute(
            ExecutionCommand(
                operation="cancel",
                idempotency_key=f"bot:flatten:cancel:{order_id}:{uuid.uuid4()}",
                source="cancel_working",
                order_id=int(order_id),
                skip_risk=True,
            ),
            wait_ack=False,
        )
        results.append(receipt.legacy_place_dict())
    return results


def _short_close(close: dict[str, Any], qty: float) -> str | None:
    """Why a close did not cover the position, or None when it did (QA R6)."""
    if not close.get("ok"):
        return None  # already a failure; its own error says why
    sent = close.get("sent_qty")
    try:
        sent_f = float(sent) if sent is not None else None
    except (TypeError, ValueError):
        sent_f = None
    if sent_f is not None and sent_f + 1e-9 < abs(qty):
        return f"flatten sent {sent_f:g} of {abs(qty):g} shares"
    return None


def _position_closes(positions: list[dict[str, Any]]) -> list[tuple[str, float, str]]:
    closes: list[tuple[str, float, str]] = []
    for row in positions:
        symbol = str(row.get("symbol") or "").strip().upper()
        try:
            qty = float(row.get("qty") or 0)
        except (TypeError, ValueError):
            continue
        if not symbol or abs(qty) < 1e-9:
            continue
        side = "SELL" if qty > 0 else "BUY"
        closes.append((symbol, abs(qty), side))
    return closes


async def flatten_account_once() -> dict[str, Any]:
    from ibkr import account as _account
    from ibkr.errors import IbkrAccountError

    from sim.mode import desk_connected, is_practice_venue

    # A practice account is a local ledger whose broker closes a held position
    # at the last mark with the Gateway dark (ADR 018 / 019) -- the same
    # exemption execution.validate.check_account_and_position gives it.
    if not is_practice_venue() and not desk_connected():
        return {"ok": False, "error": "IBKR not connected -- cannot flatten", "results": []}
    try:
        positions = _account.get_positions()
    except IbkrAccountError as exc:
        return {"ok": False, "error": str(exc), "results": []}

    # Cancel leftover working first. Never cancel after place -- openTrades
    # can include the unfilled liquidation MKTs (wait_ack=False) and kill them.
    cancels = await _cancel_working()
    results: list[dict[str, Any]] = []
    for symbol, qty, side in _position_closes(positions):
        close = await _place_close(symbol, qty, side)
        short = _short_close(close, qty)
        if short:
            close = {**close, "ok": False, "error": short, "reason_code": "FLATTEN_PARTIAL"}
            logger.error("bot flatten: %s %s -- %s", side, symbol, short)
        results.append({"symbol": symbol, "qty": qty, "side": side, "close": close})
    ok = all((r.get("close") or {}).get("ok") for r in results) if results else True
    if cancels and not results:
        ok = all(c.get("ok") for c in cancels)
    left = _practice_left_open(positions) if ok and results and is_practice_venue() else []
    if left:
        # The practice broker fills a protective close at placement, so any share
        # still held means the close did not cover it -- never report success.
        ok = False
        logger.error("bot flatten: positions still open after close: %s", left)
    out: dict[str, Any] = {"ok": ok, "results": results, "cancels": cancels}
    if left is None:
        # The re-read failed: the closes were sent, but flat is unproven.
        out["ok"] = False
        out["error"] = "flatten sent, but positions could not be re-read to confirm it"
    elif left:
        out["error"] = "positions still open after flatten: " + ", ".join(left)
        out["left_open"] = left
    return out


def _practice_left_open(before: list[dict[str, Any]]) -> list[str] | None:
    """``["GRML 1"]`` for symbols the flatten closed that still hold shares;
    None when the positions cannot be re-read (unproven, never "flat")."""
    from ibkr import account as _account
    from ibkr.errors import IbkrAccountError

    closed = {symbol for symbol, _qty, _side in _position_closes(before)}
    try:
        after = _account.get_positions()
    except IbkrAccountError as exc:
        logger.warning("bot flatten: could not re-read positions after close: %s", exc)
        return None
    return [f"{symbol} {qty:g}" for symbol, qty, _side in _position_closes(after) if symbol in closed]


async def flatten_account_with_retry() -> dict[str, Any]:
    last: dict[str, Any] = {"ok": False, "error": "flatten not attempted", "results": []}
    attempts = 1 + int(BOT_FLATTEN_RETRIES)
    for attempt in range(attempts):
        last = await flatten_account_once()
        last["attempt"] = attempt + 1
        if last.get("ok"):
            return last
    return last


def alert_flatten_failed(detail: dict[str, Any]) -> None:
    try:
        from alerts.dispatch import dispatch_alert
        from constants import ALERTS_EVENT_TYPE_SYSTEM

        dispatch_alert({
            "type": ALERTS_EVENT_TYPE_SYSTEM,
            "ok": False,
            "text": (
                "Bot loss breaker flatten failed after retry. "
                f"Close positions manually. detail={detail.get('error') or detail}"
            ),
        })
    except Exception:
        logger.exception("bot flatten: alert dispatch failed")


# One symbol's protective close, for the first-pullback bot's last resort (ADR 030).
place_close = _place_close
