"""What the brain sends on Paper (ADR 072 decision 10). The one door: ``execution.service``, in Claude's shape.

- An **entry** is a long bracket: a LMT entry with its stop and target resting with it (``practice.bracket``), so a
  fill is never unprotected. Source ``bot``, origin ``brain``, on the desk's venue, which must be Paper
  (``expected_venue``; ``venue_door`` refuses any ``brain`` send elsewhere).
- A **stop move** is a price-only replace of the brain's own stop leg.
- A **close** is a protective flatten (source ``flatten``, market) and a **cancel** is source ``cancel_working``;
  both name Paper (``target_venue``), so they reach the brain's shares whatever the desk shows.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from brain.constants_brain import BRAIN_KEY_PREFIX, BRAIN_ORIGIN, BRAIN_SETUP_PREFIX, BRAIN_VENUE
from execution.models import ExecutionCommand

logger = logging.getLogger(__name__)


def _key(kind: str) -> str:
    return f"{BRAIN_KEY_PREFIX}{kind}:{uuid.uuid4().hex}"


async def _execute(cmd: ExecutionCommand) -> Any:
    from execution.service import execute

    return await execute(cmd, wait_ack=False)


def _outside_rth() -> bool:
    from execution.session_gate import regular_hours_now

    return not regular_hours_now()


def receipt_error(receipt: Any) -> str | None:
    """Why the door refused, or None when it took the order."""
    if receipt is None:
        return "no receipt"
    if getattr(receipt, "ok", True) is False or getattr(receipt, "error", None):
        return str(getattr(receipt, "error", None) or getattr(receipt, "reason_code", None) or "refused")
    return None


async def send_entry(order: dict[str, Any]) -> Any:
    """The long bracket for ``order`` (``rules.shape_refusal`` has passed)."""
    limit = round(float(order["limit"]), 4)
    return await _execute(ExecutionCommand(
        operation="bracket", idempotency_key=_key("entry"), source="bot", origin=BRAIN_ORIGIN,
        symbol=str(order["symbol"]).upper(), side="BUY", qty=float(order["qty"]), order_type="LMT",
        limit_price=limit, entry_price=limit, reference_price=limit,
        stop_price=round(float(order["stop"]), 4), target_price=round(float(order["target"]), 4),
        outside_rth=_outside_rth(), setup=f"{BRAIN_SETUP_PREFIX}entry", skip_risk=True,
        expected_venue=BRAIN_VENUE))


async def move_stop(order_id: int, symbol: str, stop: float) -> Any:
    return await _execute(ExecutionCommand(
        operation="replace", idempotency_key=_key("stop"), source="bot", origin=BRAIN_ORIGIN,
        symbol=symbol.upper(), order_id=int(order_id), stop_price=round(float(stop), 4),
        expected_venue=BRAIN_VENUE))


async def cancel(order_id: int, symbol: str) -> Any:
    return await _execute(ExecutionCommand(
        operation="cancel", idempotency_key=_key(f"cancel:{order_id}"), source="cancel_working",
        symbol=symbol.upper(), order_id=int(order_id), target_venue=BRAIN_VENUE, origin=BRAIN_ORIGIN))


async def sell(symbol: str, qty: float) -> Any:
    """Sell ``qty`` of the brain's shares at market on Paper. While the desk is on Paper the close also carries
    ``intent: "flatten"``, which the door holds to the position less closes already working."""
    from sim.mode import venue

    return await _execute(ExecutionCommand(
        operation="place", idempotency_key=_key("close"), source="flatten", symbol=symbol.upper(), side="SELL",
        qty=float(qty), order_type="MKT", outside_rth=True, skip_risk=True, target_venue=BRAIN_VENUE,
        origin=BRAIN_ORIGIN, setup=f"{BRAIN_SETUP_PREFIX}close",
        intent="flatten" if venue() == BRAIN_VENUE else None))


async def close(symbol: str | None = None) -> list[str]:
    """Cancel the brain's working orders (on ``symbol``, or everywhere) and sell its own shares there at market;
    return what failed, in words. Shares handed to the operator are left alone: they are the operator's to close."""
    from brain import book

    sym = (symbol or "").upper() or None
    problems: list[str] = []
    try:
        for row in book.working():
            if sym and str(row.get("symbol") or "").upper() != sym:
                continue
            receipt = await cancel(int(row["order_id"]), str(row["symbol"]))
            if why := receipt_error(receipt):
                problems.append(f"cancel {row['order_id']}: {why}")
        for held, lot in book.positions().items():
            if sym and held != sym:
                continue
            if lot["qty"] > 0:
                receipt = await sell(held, lot["qty"])
                if why := receipt_error(receipt):
                    problems.append(f"close {held}: {why}")
    except book.ReadError as exc:
        logger.warning("BRAIN close: Paper could not be read", exc_info=True)
        problems.append(str(exc))
    if problems:
        logger.error("BRAIN close (%s): %s", sym or "everything", "; ".join(problems))
    return problems
