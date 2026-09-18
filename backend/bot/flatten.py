"""Whole-account MKT flatten through the existing execution door.

Desk HTTP: POST /api/ibkr/flatten-account (Emergency KILL + tests).
Breakers call flatten_account_with_retry directly -- same function.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from constants_bot import BOT_FLATTEN_RETRIES

logger = logging.getLogger(__name__)


async def _place_close(symbol: str, qty: float, side: str) -> dict[str, Any]:
    from execution.models import ExecutionCommand
    from execution.service import execute

    receipt = await execute(
        ExecutionCommand(
            operation="place",
            idempotency_key=f"bot:flatten:{side.lower()}:{symbol}:{uuid.uuid4()}",
            source="flatten",
            symbol=symbol,
            side=side,
            qty=abs(float(qty)),
            order_type="MKT",
            skip_risk=True,
            skip_concurrency=True,
        ),
        wait_ack=False,
    )
    return receipt.legacy_place_dict()


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
                skip_concurrency=True,
            ),
            wait_ack=False,
        )
        results.append(receipt.legacy_place_dict())
    return results


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
    from ibkr import client as _client
    from ibkr.errors import IbkrAccountError

    if not _client.is_connected():
        return {"ok": False, "error": "IBKR not connected -- cannot flatten", "results": []}
    try:
        positions = _account.get_positions()
    except IbkrAccountError as exc:
        return {"ok": False, "error": str(exc), "results": []}

    results: list[dict[str, Any]] = []
    for symbol, qty, side in _position_closes(positions):
        close = await _place_close(symbol, qty, side)
        results.append({"symbol": symbol, "qty": qty, "side": side, "close": close})
    cancels = await _cancel_working()
    ok = all((r.get("close") or {}).get("ok") for r in results) if results else True
    if cancels and not results:
        ok = all(c.get("ok") for c in cancels)
    return {"ok": ok, "results": results, "cancels": cancels}


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
