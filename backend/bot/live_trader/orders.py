"""What the Live Trader bot sends and reads on Paper (ADR 055 decision 5). The one door: ``execution.service``.

Every send carries ``origin: "live_trader"`` and ``setup: "live_trader:<HOST>"``, so the Orders table's Sent by
and the execution record read the bot apart from the operator. A step is source ``bot`` -- a long a ``place`` BUY
limit, a short ADR 048's bracket (a short limit with ``short_entry`` and its buy stop, no target) -- sent on the
desk's venue, which must be Paper (``expected_venue``). A close is the protective flatten the day cover sends
(source ``flatten``, a market order outside regular hours too), and a cancel is source ``cancel_working``; both
name Paper (``target_venue``), so they reach the bot's Paper shares while the desk shows another venue. Reads come
straight from Paper's ledger (``practice.broker.for_venue("paper")``), whatever the desk shows; a read that fails
raises ``ReadError``: unknown is never "flat" or "filled".
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from bot.live_trader.constants_live_trader import LT_KEY_PREFIX, LT_ORIGIN, LT_SETUP_PREFIX, LT_VENUE
from execution.models import ExecutionCommand

logger = logging.getLogger(__name__)
FILLED = "Filled"
DEAD = frozenset({"Cancelled", "ApiCancelled", "Inactive", "Expired"})


class ReadError(Exception):
    """Paper's ledger could not be read; the caller must not guess."""


def _paper() -> Any:
    from practice.broker import for_venue

    return for_venue(LT_VENUE)


def _execute(cmd: ExecutionCommand) -> Any:
    from execution.service import execute

    return execute(cmd, wait_ack=False)


def _outside_rth() -> bool:
    from execution.session_gate import regular_hours_now

    return not regular_hours_now()


def key(row_id: str, step: str, n: int | str, now: float) -> str:
    """A send's idempotency key, unique to this send: the same trade can be taken again (back on air, after the
    bar was hidden), and a key reused from an earlier send would replay that send's receipt -- a step or a close
    the door never placed."""
    return f"{LT_KEY_PREFIX}{row_id}:{step}{n}:{int(now * 1000)}"


# -- sends -------------------------------------------------------------------------------------------
async def send_step(action: dict[str, Any], n: int | str, now: float) -> Any:
    """The step ``action`` (``decide``'s): a long's BUY limit or a short's bracket, source ``bot``."""
    common = {"idempotency_key": key(action["row_id"], action["step"], n, now), "source": "bot", "origin": LT_ORIGIN,
              "symbol": action["symbol"], "qty": float(action["qty"]), "order_type": "LMT",
              "limit_price": round(float(action["limit"]), 4), "reference_price": round(float(action["limit"]), 4),
              "outside_rth": _outside_rth(), "setup": f"{LT_SETUP_PREFIX}{action['host']}", "skip_risk": True,
              "expected_venue": LT_VENUE}
    if action["side"] == "long":
        return await _execute(ExecutionCommand(operation="place", side="BUY", **common))
    return await _execute(ExecutionCommand(
        operation="bracket", side="SELL", short_entry=True, entry_price=round(float(action["limit"]), 4),
        stop_price=round(float(action["stop"]), 4), target_price=None, **common))


async def cancel(order_id: int, symbol: str, host: str) -> Any:
    return await _execute(ExecutionCommand(
        operation="cancel", idempotency_key=f"{LT_KEY_PREFIX}cancel:{order_id}:{uuid.uuid4()}",
        source="cancel_working", symbol=symbol, order_id=int(order_id), target_venue=LT_VENUE, origin=LT_ORIGIN,
        setup=f"{LT_SETUP_PREFIX}{host}"))


async def close(pos: dict[str, Any], qty: float, *, tries: int, now: float) -> Any:
    """Sell (or cover) ``qty`` of the bot's shares at market on Paper: the day cover's own close.

    While the desk is on Paper the close also carries ``intent: "flatten"``, so the door holds it, under its
    lock, to the position less the closes already working there (``execution.flatten_intent``)."""
    from sim.mode import venue

    side = "SELL" if pos["side"] == "long" else "BUY"
    return await _execute(ExecutionCommand(
        operation="place", idempotency_key=key(pos["row_id"], "close", tries, now), source="flatten",
        symbol=pos["symbol"], side=side, qty=float(qty), order_type="MKT", outside_rth=True, skip_risk=True,
        target_venue=LT_VENUE, origin=LT_ORIGIN, setup=f"{LT_SETUP_PREFIX}{pos['host']}",
        intent="flatten" if venue() == LT_VENUE else None))


def receipt_error(receipt: Any) -> str:
    if receipt is None:
        return "no receipt"
    return str(getattr(receipt, "error", None) or getattr(receipt, "reason_code", None) or "refused")


def receipt_ids(receipt: Any) -> tuple[int | None, int | None]:
    """``(order, stop)``: the step's order id (a bracket's entry) and a short bracket's buy stop."""
    def num(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    order = num(getattr(receipt, "parent_order_id", None)) or num(getattr(receipt, "order_id", None))
    return order, num(getattr(receipt, "stop_order_id", None))


# -- reads -------------------------------------------------------------------------------------------
def order_row(order_id: int | None) -> dict[str, Any] | None:
    """Paper's row for ``order_id``, working or closed; None when Paper has no such order."""
    if order_id is None:
        return None
    try:
        return _paper().ledger.order_row(int(order_id))
    except Exception as exc:
        raise ReadError(f"Paper's orders could not be read: {exc}") from exc


def fees_of(order_id: int | None) -> float | None:
    """What Paper charged for ``order_id``'s fill (commission, SEC and FINRA); None when Paper does not show it."""
    try:
        row = order_row(order_id)
    except ReadError:
        return None
    if order_state(row) != "filled":
        return None
    total = ((row or {}).get("fees") or {}).get("total")
    return float(total) if isinstance(total, (int, float)) else None


def order_state(row: dict[str, Any] | None) -> str:
    """``filled`` | ``dead`` | ``working`` | ``gone``."""
    if row is None:
        return "gone"
    status = str(row.get("status") or "")
    if status == FILLED:
        return "filled"
    return "dead" if status in DEAD else "working"


def closed_by_others(symbol: str, side: str, since_ts: float, *,
                     not_ids: set[int] | frozenset[int] = frozenset()) -> list[dict[str, Any]]:
    """Paper's filled orders that closed ``side`` of ``symbol`` at or after ``since_ts``, the newest first, none of
    them the Live Trader bot's nor in ``not_ids``: what the operator, the loss limit's Auto sell, KILL or Nova's day
    cover sold or covered. Raises ``ReadError`` when Paper cannot be read."""
    want = "SELL" if side == "long" else "BUY"
    try:
        rows = _paper().ledger.closed_orders()
    except Exception as exc:
        raise ReadError(f"Paper's orders could not be read: {exc}") from exc
    out = []
    for r in rows:
        if order_state(r) != "filled" or str(r.get("symbol") or "").upper() != symbol.upper():
            continue
        if str(r.get("side") or "").upper() != want or r.get("order_origin") == LT_ORIGIN:
            continue
        if r.get("effect") not in (None, "closes") or r.get("position_side") not in (None, side):
            continue                       # a buy that opened a long is not the cover of a short
        if int(r["order_id"]) in not_ids or float(r.get("fill_ts") or 0.0) < since_ts:
            continue
        out.append(r)
    return out


def held(symbol: str, side: str) -> float | None:
    """The shares Paper holds in ``symbol`` on ``side`` (a positive count); None when Paper cannot be read."""
    try:
        rows = _paper().positions()
    except Exception:
        logger.warning("Live Trader bot: Paper's positions could not be read", exc_info=True)
        return None
    qty = sum(float(r.get("qty") or 0.0) for r in rows if str(r.get("symbol") or "").upper() == symbol.upper())
    if side == "long":
        return max(qty, 0.0)
    return max(-qty, 0.0)
