"""Auto sell: at the limit, close what the account opened today -- and nothing it held before (ADR 056).

For each stock the count holds open from today, on that account whatever the desk shows
(``target_venue``): cancel its working orders (source ``cancel_working``), then close it through
the execution door as a protective flatten (source ``flatten``, origin ``loss_limit``). On Live, and
on a practice account the desk is showing, it carries ``intent: "flatten"``, so the door holds the
close to the position less the closes already working (``execution.flatten_intent``, which reads
IBKR's own book for Live and the desk's ledger otherwise); a practice account the desk is not showing
is closed for the shares its own ledger holds, as the Live Trader bot's closes are (ADR 055). Paper and Sim close at market at any hour; Live closes at market in
regular hours and with a marketable limit outside them (``execution.flatten_exit``). A stock held
before today is never in the list. Each close is tried up to ``LOSS_LIMIT_SELL_RETRIES`` times and
answers ``{symbol, side, qty, ok, order_id, error}``.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from constants_loss_limit import LOSS_LIMIT_ORIGIN, LOSS_LIMIT_SELL_RETRIES

logger = logging.getLogger(__name__)


def _working(account: str, symbols: set[str]) -> list[dict[str, Any]]:
    if account == "live":
        from ibkr import live_book

        rows = live_book.open_rows()
    else:
        from practice.broker import for_venue

        rows = for_venue(account).working_orders()
    return [r for r in rows if str(r.get("symbol") or "").upper() in symbols and r.get("order_id") is not None]


async def _cancel(account: str, row: dict[str, Any]) -> None:
    from execution.models import ExecutionCommand
    from execution.service import execute

    receipt = await execute(ExecutionCommand(
        operation="cancel", idempotency_key=f"loss_limit:cancel:{account}:{row['order_id']}:{uuid.uuid4()}",
        source="cancel_working", symbol=str(row["symbol"]).upper(), order_id=int(row["order_id"]),
        target_venue=account, origin=LOSS_LIMIT_ORIGIN, skip_risk=True), wait_ack=True)
    if not getattr(receipt, "ok", False):
        logger.warning("LOSS LIMIT: cancel of %s order %s on %s was refused: %s", row["symbol"],
                       row["order_id"], account, getattr(receipt, "error", None))


def _ticket(account: str, symbol: str, side: str) -> dict[str, Any] | None:
    from execution.flatten_exit import (
        plan_flatten_exit,
        plan_practice_flatten_exit,
        resolve_flatten_marks,
        ticket_to_command_fields,
    )

    if account == "live":
        bid, ask, last = resolve_flatten_marks(symbol)
        ticket = plan_flatten_exit(side, bid=bid, ask=ask, last=last)
    else:
        ticket = plan_practice_flatten_exit()
    return ticket_to_command_fields(ticket) if ticket.ok else None


def _intent(account: str) -> str | None:
    """``flatten`` where the door can check the close against the account's own positions."""
    if account == "live":
        return "flatten"
    from sim.mode import venue

    return "flatten" if venue() == account else None


async def _close(account: str, stock: dict[str, Any]) -> dict[str, Any]:
    from execution.models import ExecutionCommand
    from execution.service import execute

    symbol, shares = stock["symbol"], float(stock["shares"])
    side = "SELL" if shares > 0 else "BUY"
    out: dict[str, Any] = {"symbol": symbol, "side": side, "qty": abs(shares), "ok": False,
                           "order_id": None, "error": None}
    fields = _ticket(account, symbol, side)
    if fields is None:
        out["error"] = "no price to close it outside regular hours"
        return out
    for attempt in range(1, LOSS_LIMIT_SELL_RETRIES + 1):
        receipt = await execute(ExecutionCommand(
            operation="place", idempotency_key=f"loss_limit:close:{account}:{symbol}:{attempt}:{uuid.uuid4()}",
            source="flatten", symbol=symbol, side=side, qty=abs(shares), skip_risk=True, intent=_intent(account),
            target_venue=account, origin=LOSS_LIMIT_ORIGIN, **fields), wait_ack=False)
        if getattr(receipt, "ok", False):
            out.update(ok=True, order_id=getattr(receipt, "order_id", None), error=None)
            return out
        out["error"] = str(getattr(receipt, "error", None) or getattr(receipt, "reason_code", None) or "refused")
        logger.warning("LOSS LIMIT: close %d of %s %s on %s refused: %s", attempt, side, symbol, account,
                       out["error"])
    return out


async def sell_opened_today(account: str, stocks: list[dict[str, Any]],
                            on_close: Callable[[dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
    """Close every stock in ``stocks`` (the count's ``opened_today``) on ``account``.

    ``on_close`` hears each close's answer as soon as it has one, so the caller can save it before
    the next close is sent: a restart mid-sale never loses a close that already went out."""
    if not stocks:
        return []
    symbols = {s["symbol"].upper() for s in stocks}
    try:
        for row in _working(account, symbols):
            await _cancel(account, row)
    except Exception:
        # The closes still go: the door holds each to what is not already being closed.
        logger.exception("LOSS LIMIT: working orders on %s could not be read or cancelled", account)
    out: list[dict[str, Any]] = []
    for stock in stocks:
        result = await _close(account, stock)
        out.append(result)
        if on_close is not None:
            on_close(result)
    return out
