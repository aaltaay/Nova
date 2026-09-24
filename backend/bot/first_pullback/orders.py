"""What the first-pullback bot sends and reads (ADR 030).

Every order enters ``execution.service.execute`` with source ``bot`` -- the one
door (ADR 007) -- under an idempotency key made of the venue, the setup id and
the step, so a repeated send replays its receipt instead of placing twice. The
one exception is the last-resort close, which is the protective flatten
(``bot.flatten``): a practice position can always get flat, padlock or not.

Reads come from ``ibkr.orders`` / ``ibkr.account`` / ``bot.quotes``, which
answer from the practice ledger and the live feed on Paper and Sim. A failed
read raises ``ReadError``: unknown is never "flat", "filled" or "cancelled".
"""
from __future__ import annotations

import uuid
from typing import Any

from constants_bot import BOT_DEFAULT_BID_EXIT_OFFSET_USD, BOT_SETUP_FIRST_PULLBACK
from execution.models import ExecutionCommand
from execution.service import execute

FILLED = "Filled"
DEAD = frozenset({"Cancelled", "ApiCancelled", "Inactive", "Expired"})


class ReadError(Exception):
    """An order, position or quote read failed; the caller must not guess."""


def _key(trade: dict[str, Any], step: str) -> str:
    return f"bot:fp:{trade['venue']}:{trade['setup_id']}:{step}"


def _outside_rth() -> bool:
    """Extended-hours flag for the venue's clock: the window opens at 07:00, before the open."""
    from execution.session_gate import regular_hours_now

    return not regular_hours_now()


# -- reads ---------------------------------------------------------------------
def order_row(order_id: int | None) -> dict[str, Any] | None:
    """The venue's row for ``order_id`` (working or closed); None when the ledger has no such order."""
    if order_id is None:
        return None
    from ibkr import orders as _orders

    target = int(order_id)
    try:
        for row in _orders.open_orders():
            if int(row.get("order_id") or 0) == target:
                return row
        for row in _orders.closed_orders():
            if int(row.get("order_id") or 0) == target:
                return row
    except Exception as exc:
        raise ReadError(f"orders unreadable: {exc}") from exc
    return None


def order_state(row: dict[str, Any] | None) -> str:
    """``filled`` | ``dead`` | ``working`` | ``gone`` (no such order on this venue's ledger)."""
    if row is None:
        return "gone"
    status = str(row.get("status") or "")
    if status == FILLED:
        return "filled"
    if status in DEAD:
        return "dead"
    return "working"


def held_qty(symbol: str) -> float:
    from ibkr import account as _account

    try:
        return float(_account.long_qty(symbol) or 0.0)
    except Exception as exc:
        raise ReadError(f"position unreadable: {exc}") from exc


def last_price(symbol: str) -> float | None:
    """IBKR's Last (a print that set a price), from the shared feed; None when unknown."""
    from bot.quotes import last_quote

    row = last_quote(symbol) or {}
    if row.get("quote_quality") == "close_fallback":
        return None                     # the prior close is not a trade (#541)
    try:
        price = float(row.get("price"))
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def best_bid(symbol: str) -> float | None:
    from bot.quotes import top_of_book

    bid, _ask = top_of_book(symbol)
    return float(bid) if bid is not None and bid > 0 else None


# -- sends ---------------------------------------------------------------------
async def _place(trade: dict[str, Any], step: str, *, side: str, qty: float, order_type: str,
                 limit_price: float | None = None, stop_price: float | None = None) -> Any:
    return await execute(
        ExecutionCommand(
            operation="place",
            idempotency_key=_key(trade, step),
            source="bot",
            symbol=trade["symbol"],
            side=side,
            qty=float(qty),
            order_type=order_type,
            limit_price=None if limit_price is None else round(float(limit_price), 4),
            stop_price=None if stop_price is None else round(float(stop_price), 4),
            reference_price=limit_price if limit_price is not None else stop_price,
            outside_rth=_outside_rth(),
            setup=BOT_SETUP_FIRST_PULLBACK,
            skip_risk=True,
        ),
        wait_ack=False,
    )


async def place_entry(trade: dict[str, Any]) -> Any:
    """BUY limit at the entry the scanner scored at the trigger; it never chases."""
    return await _place(trade, "entry", side="BUY", qty=trade["qty"], order_type="LMT",
                        limit_price=trade["entry_planned"])


async def place_target(trade: dict[str, Any]) -> Any:
    """SELL limit resting at target 1."""
    return await _place(trade, "target", side="SELL", qty=trade["qty"], order_type="LMT",
                        limit_price=trade["target1"])


async def close_at_bid(trade: dict[str, Any], attempt: int) -> tuple[Any | None, float | None]:
    """SELL limit a few cents under the bid (marketable); ``(None, None)`` when no bid is known."""
    bid = best_bid(trade["symbol"])
    if bid is None:
        return None, None
    limit = max(0.01, round(bid - BOT_DEFAULT_BID_EXIT_OFFSET_USD, 4))
    receipt = await _place(trade, f"close:{attempt}", side="SELL", qty=trade["qty"], order_type="LMT",
                           limit_price=limit)
    return receipt, limit


async def cancel(trade: dict[str, Any], order_id: int) -> Any:
    return await execute(
        ExecutionCommand(
            operation="cancel",
            idempotency_key=f"{_key(trade, 'cancel')}:{order_id}:{uuid.uuid4()}",
            source="bot",
            order_id=int(order_id),
            symbol=trade["symbol"],
            skip_risk=True,
        ),
        wait_ack=False,
    )


async def protective_close(trade: dict[str, Any], qty: float) -> dict[str, Any]:
    """The last resort: the protective flatten, which a disarmed desk still sends (ADR 018)."""
    from bot.flatten import place_close

    return await place_close(trade["symbol"], qty, "SELL")


def receipt_error(receipt: Any) -> str:
    if receipt is None:
        return "no receipt"
    return str(getattr(receipt, "error", None) or getattr(receipt, "reason_code", None) or "refused")
