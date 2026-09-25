"""Every order Nova sends for a stock (ADR 037), through the execution door (ADR 007).

Auto-entry sends a BUY limit (source ``bot``); Approve sends the plan as one bracket (source
``manual``: the operator decided the trade, Nova only picked the moment). Every send carries an
idempotency key made of the kind, the venue, the setup and the attempt, so a repeat replays its receipt.
Reads reuse the first-pullback bot's (``bot.first_pullback.orders``): the venue's own order rows and
long position, and a failed read raises ``ReadError`` -- unknown is never "filled" or "flat".
"""
from __future__ import annotations

import uuid
from typing import Any

from bot.first_pullback.orders import ReadError, held_qty, order_row, order_state  # noqa: F401 (re-exported)
from execution.models import ExecutionCommand
from execution.service import execute


def _outside_rth() -> bool:
    """Extended-hours flag for the venue's clock (Nova trades from the premarket)."""
    from execution.session_gate import regular_hours_now

    return not regular_hours_now()


def _key(trade: dict[str, Any], step: str) -> str:
    return f"stock:{trade['kind']}:{trade['venue']}:{trade['symbol']}:{trade['attempt']}:{step}"


async def place_entry(trade: dict[str, Any]) -> Any:
    """Auto-entry: one BUY limit at the setup's entry. It never chases."""
    return await execute(
        ExecutionCommand(
            operation="place",
            idempotency_key=_key(trade, "entry"),
            source="bot",
            symbol=trade["symbol"],
            side="BUY",
            qty=float(trade["qty"]),
            order_type="LMT",
            limit_price=round(float(trade["entry"]), 4),
            reference_price=round(float(trade["entry"]), 4),
            outside_rth=_outside_rth(),
            skip_risk=True,
        ),
        wait_ack=False,
    )


async def send_bracket(trade: dict[str, Any]) -> Any:
    """Approve: the plan as one bracket -- a BUY limit at the entry, a SELL limit at the target and a
    SELL stop at the stop, the exits held until the entry fills and then one-cancels-other."""
    entry = round(float(trade["entry"]), 4)
    return await execute(
        ExecutionCommand(
            operation="bracket",
            idempotency_key=_key(trade, "bracket"),
            source="manual",
            symbol=trade["symbol"],
            side="BUY",
            qty=float(trade["qty"]),
            order_type="LMT",
            limit_price=entry,
            entry_price=entry,
            target_price=round(float(trade["target"]), 4),
            stop_price=round(float(trade["stop"]), 4),
            reference_price=entry,
            outside_rth=_outside_rth(),
            skip_risk=True,
        ),
        wait_ack=False,
    )


async def cancel(trade: dict[str, Any], order_id: int, *, source: str = "bot") -> Any:
    return await execute(
        ExecutionCommand(
            operation="cancel",
            idempotency_key=f"{_key(trade, 'cancel')}:{order_id}:{uuid.uuid4()}",
            source=source,
            order_id=int(order_id),
            symbol=trade["symbol"],
            skip_risk=True,
        ),
        wait_ack=False,
    )


def receipt_error(receipt: Any) -> str:
    if receipt is None:
        return "no receipt"
    return str(getattr(receipt, "error", None) or getattr(receipt, "reason_code", None) or "refused")


def leg_ids(receipt: Any) -> tuple[int | None, int | None, int | None]:
    """``(entry, target, stop)`` order ids from a bracket receipt (None where the broker gave none)."""
    def num(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    parent = num(getattr(receipt, "parent_order_id", None)) or num(getattr(receipt, "order_id", None))
    return parent, num(getattr(receipt, "target_order_id", None)), num(getattr(receipt, "stop_order_id", None))
