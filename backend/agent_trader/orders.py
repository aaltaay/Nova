"""What Claude sends on Paper (ADR 068 decisions 5, 8). The one door: ``execution.service``, in the Live Trader
bot's shape (ADR 055).

- An **entry** is a long bracket -- a LMT entry with its stop and one or two targets resting with it
  (``practice.bracket``), so a fill is never unprotected -- source ``bot``, ``origin: "claude"``, sent on the
  desk's venue, which must be Paper (``expected_venue``; ``venue_door`` refuses any ``claude`` send elsewhere).
- A **stop move** is a price-only replace of Claude's own stop leg, also on Paper only.
- A **close** is the day cover's protective flatten (source ``flatten``, market) and a **cancel** is source
  ``cancel_working``; both name Paper (``target_venue``), so they reach Claude's shares whatever the desk shows.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from agent_trader.constants_agent_trader import AGENT_KEY_PREFIX, AGENT_ORIGIN, AGENT_SETUP_PREFIX, AGENT_VENUE
from execution.models import ExecutionCommand

logger = logging.getLogger(__name__)


def _key(kind: str) -> str:
    return f"{AGENT_KEY_PREFIX}{kind}:{uuid.uuid4().hex}"


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


async def send_entry(order: dict[str, Any], *, tag: str) -> Any:
    """The long bracket for ``order`` (``rules.shape_refusal`` has passed): entry at ``entry``."""
    entry = round(float(order["entry"]), 4)
    two = order.get("target2") is not None
    return await _execute(ExecutionCommand(
        operation="bracket", idempotency_key=_key("entry"), source="bot", origin=AGENT_ORIGIN,
        symbol=str(order["symbol"]).upper(), side="BUY", qty=float(order["qty"]), order_type="LMT",
        limit_price=entry, entry_price=entry, reference_price=entry,
        stop_price=round(float(order["stop"]), 4), target_price=round(float(order["target"]), 4),
        target2_price=round(float(order["target2"]), 4) if two else None,
        target1_qty=float(order["target1_qty"]) if two else None,
        outside_rth=_outside_rth(), setup=f"{AGENT_SETUP_PREFIX}{tag}", skip_risk=True,
        expected_venue=AGENT_VENUE))


async def move_stop(order_id: int, symbol: str, stop: float) -> Any:
    return await _execute(ExecutionCommand(
        operation="replace", idempotency_key=_key("stop"), source="bot", origin=AGENT_ORIGIN,
        symbol=symbol.upper(), order_id=int(order_id), stop_price=round(float(stop), 4),
        expected_venue=AGENT_VENUE))


async def cancel(order_id: int, symbol: str) -> Any:
    return await _execute(ExecutionCommand(
        operation="cancel", idempotency_key=_key(f"cancel:{order_id}"), source="cancel_working",
        symbol=symbol.upper(), order_id=int(order_id), target_venue=AGENT_VENUE, origin=AGENT_ORIGIN))


async def close(symbol: str, qty: float) -> Any:
    """Sell ``qty`` of Claude's shares at market on Paper (the day cover's close). While the desk is on Paper the
    close also carries ``intent: "flatten"``, which the door holds to the position less closes already working."""
    from sim.mode import venue

    return await _execute(ExecutionCommand(
        operation="place", idempotency_key=_key("close"), source="flatten", symbol=symbol.upper(), side="SELL",
        qty=float(qty), order_type="MKT", outside_rth=True, skip_risk=True, target_venue=AGENT_VENUE,
        origin=AGENT_ORIGIN, setup=f"{AGENT_SETUP_PREFIX}close",
        intent="flatten" if venue() == AGENT_VENUE else None))


async def stand_down(reason: str) -> list[str]:
    """Cancel every working order of Claude's and sell every share of Claude's on Paper; return what failed."""
    from agent_trader import ledger

    problems: list[str] = []
    try:
        for row in ledger.working():
            receipt = await cancel(int(row["order_id"]), str(row["symbol"]))
            if why := receipt_error(receipt):
                problems.append(f"cancel {row['order_id']}: {why}")
        for sym, qty in ledger.positions().items():
            receipt = await close(sym, qty)
            if why := receipt_error(receipt):
                problems.append(f"close {sym}: {why}")
    except ledger.ReadError:
        logger.warning("AGENT stand down (%s): Paper could not be read", reason, exc_info=True)
        problems.append(ledger.UNREAD_TEXT)
    if problems:
        logger.error("AGENT stand down (%s): %s", reason, "; ".join(problems))
    return problems
