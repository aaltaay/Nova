"""What Nova's exit sends (``stock_mode.exit_trade``), through the execution door (ADR 007).

Moved out of ``exit_trade`` when the exit gained its targets (#681). Every send is source ``manual``, origin
``nova_exit`` (you handed Nova the exit; Nova placed and manages it), and names the trade's venue:

- ``place_stop``: one stop for every share -- a SELL stop under a long, a BUY stop over a short (a cover);
- ``place_pair``: the exit-only pair (``operation: "exit_oco"``) -- that stop and a limit per half beside
  it, committed once: the stop's fill cancels the targets, a target's shrinks the stop to the shares left;
- ``replace_stop``: the stop's new price (the trail), which keeps the pair whole.
"""
from __future__ import annotations

import uuid
from typing import Any

from execution.models import ExecutionCommand
from execution.service import execute
from stock_mode import orders


def key(trade: dict[str, Any], step: str) -> str:
    return f"stock:exit:{trade['venue']}:{orders.run_tag(trade)}{trade['symbol']}:{trade['attempt']}:{step}"


def short(trade: dict[str, Any]) -> bool:
    return trade.get("side") == "short"


async def place_stop(trade: dict[str, Any], stop: float) -> Any:
    """One stop for every share of the trade: a SELL stop under a long, a BUY stop over a short (a cover)."""
    return await execute(
        ExecutionCommand(
            operation="place",
            idempotency_key=key(trade, "stop"),
            source="manual",
            origin="nova_exit",    # you handed Nova the exit; Nova placed and manages it
            symbol=trade["symbol"],
            side="BUY" if short(trade) else "SELL",
            qty=float(trade["qty"]),
            order_type="STP",
            stop_price=round(float(stop), 4),
            reference_price=round(float(stop), 4),
            outside_rth=orders._outside_rth(),   # the stock-mode orders' own clock
            skip_risk=True,
            expected_venue=trade.get("venue"),
        ),
        wait_ack=False,
    )


async def place_pair(trade: dict[str, Any], stop: float) -> Any:
    """The stop and its targets as one exit-only pair (#681): target 1 sells ``target1_qty``, target 2 the rest."""
    second = trade.get("target2_qty") or 0
    return await execute(
        ExecutionCommand(
            operation="exit_oco",
            idempotency_key=key(trade, "pair"),
            source="manual",
            origin="nova_exit",
            symbol=trade["symbol"],
            side="BUY" if short(trade) else "SELL",
            qty=float(trade["qty"]),
            order_type="STP",
            stop_price=round(float(stop), 4),
            target_price=round(float(trade["target"]), 4),
            target2_price=round(float(trade["target2"]), 4) if second else None,
            target1_qty=float(trade["target1_qty"]) if second else None,
            reference_price=round(float(stop), 4),
            outside_rth=orders._outside_rth(),
            skip_risk=True,
            expected_venue=trade.get("venue"),
        ),
        wait_ack=False,
    )


async def replace_stop(trade: dict[str, Any], stop: float) -> Any:
    return await execute(
        ExecutionCommand(
            operation="replace",
            idempotency_key=f"{key(trade, 'raise')}:{uuid.uuid4()}",
            source="manual",
            origin="nova_exit",
            order_id=int(trade["stop_order_id"]),
            symbol=trade["symbol"],
            stop_price=round(float(stop), 4),
            skip_risk=True,
            expected_venue=trade.get("venue"),
        ),
        wait_ack=False,
    )


def order_id(receipt: Any, field: str = "order_id") -> int | None:
    try:
        oid = getattr(receipt, field, None)
        return int(oid) if oid is not None else None
    except (TypeError, ValueError):
        return None
