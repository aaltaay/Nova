"""Auto sell: at a line, close what was opened today -- and nothing held before (ADR 056, ADR 061).

For each stock the count holds open from today, on that account whatever the desk shows
(``target_venue``): cancel its working orders (source ``cancel_working``), then close it through
the execution door as a protective flatten (source ``flatten``). On Live, and on a practice account
the desk is showing, it carries ``intent: "flatten"``, so the door holds the close to the position
less the closes already working (``execution.flatten_intent``, which reads IBKR's own book for Live
and the desk's ledger otherwise); a practice account the desk is not showing is closed for the
shares its own ledger holds, as the Live Trader bot's closes are (ADR 055). Paper and Sim close at
market at any hour; Live closes at market in regular hours and with a marketable limit outside them
(``execution.flatten_exit``). A stock held before today is never in the list. Each close is tried up
to ``LOSS_LIMIT_SELL_RETRIES`` times and answers ``{symbol, side, qty, ok, order_id, error}``.

Which line sold (ADR 061): the Account line closes every share opened today, after cancelling every
working order on those stocks, with origin ``loss_limit``. The You or Bots line closes only that
side's shares (the count's ``opened_today(line)``) and cancels only that side's working orders there
(``loss_limit.accounts.by_of``; on Live every order is yours), with origin ``loss_limit_you`` /
``loss_limit_bots`` -- so the count gives the sold shares back to that side, and the Orders table
says which line sold.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from constants_loss_limit import (
    LOSS_LIMIT_LINE_ACCOUNT,
    LOSS_LIMIT_LINE_YOU,
    LOSS_LIMIT_ORIGIN,
    LOSS_LIMIT_SELL_RETRIES,
    LOSS_LIMIT_SIDE_ORIGINS,
)

logger = logging.getLogger(__name__)


def origin_of(line: str) -> str:
    """The origin on ``line``'s cancels and closes."""
    return LOSS_LIMIT_ORIGIN if line == LOSS_LIMIT_LINE_ACCOUNT else LOSS_LIMIT_SIDE_ORIGINS[line]


def _working(account: str, symbols: set[str], line: str = LOSS_LIMIT_LINE_ACCOUNT) -> list[dict[str, Any]]:
    if account == "live":
        from ibkr import live_book

        rows = live_book.open_rows()
        mine = None if line == LOSS_LIMIT_LINE_ACCOUNT else (lambda row: line == LOSS_LIMIT_LINE_YOU)
    else:
        from loss_limit.accounts import by_of
        from practice.broker import for_venue

        rows = for_venue(account).working_orders()
        mine = None if line == LOSS_LIMIT_LINE_ACCOUNT else (lambda row: by_of(row) == line)
    return [r for r in rows if str(r.get("symbol") or "").upper() in symbols and r.get("order_id") is not None
            and (mine is None or mine(r))]


async def _cancel(account: str, row: dict[str, Any], line: str) -> None:
    from execution.models import ExecutionCommand
    from execution.service import execute

    receipt = await execute(ExecutionCommand(
        operation="cancel", idempotency_key=f"loss_limit:cancel:{account}:{row['order_id']}:{uuid.uuid4()}",
        source="cancel_working", symbol=str(row["symbol"]).upper(), order_id=int(row["order_id"]),
        target_venue=account, origin=origin_of(line), skip_risk=True), wait_ack=True)  # type: ignore[arg-type]
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


async def _close(account: str, stock: dict[str, Any], line: str) -> dict[str, Any]:
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
            target_venue=account, origin=origin_of(line), **fields), wait_ack=False)  # type: ignore[arg-type]
        if getattr(receipt, "ok", False):
            out.update(ok=True, order_id=getattr(receipt, "order_id", None), error=None)
            return out
        out["error"] = str(getattr(receipt, "error", None) or getattr(receipt, "reason_code", None) or "refused")
        logger.warning("LOSS LIMIT: close %d of %s %s on %s refused: %s", attempt, side, symbol, account,
                       out["error"])
    return out


async def sell_opened_today(account: str, stocks: list[dict[str, Any]],
                            on_close: Callable[[dict[str, Any]], None] | None = None, *,
                            line: str = LOSS_LIMIT_LINE_ACCOUNT) -> list[dict[str, Any]]:
    """Close every stock in ``stocks`` (the count's ``opened_today(line)``) on ``account`` for ``line``.

    ``on_close`` hears each close's answer as soon as it has one, so the caller can save it before
    the next close is sent: a restart mid-sale never loses a close that already went out."""
    if not stocks:
        return []
    symbols = {s["symbol"].upper() for s in stocks}
    try:
        for row in _working(account, symbols, line):
            await _cancel(account, row, line)
    except Exception:
        # The closes still go: the door holds each to what is not already being closed.
        logger.exception("LOSS LIMIT: working orders on %s could not be read or cancelled", account)
    out: list[dict[str, Any]] = []
    for stock in stocks:
        result = await _close(account, stock, line)
        out.append(result)
        if on_close is not None:
            on_close(result)
    return out
