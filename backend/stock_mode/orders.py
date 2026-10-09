"""Every order Nova sends for a stock (ADR 037), through the execution door (ADR 007).

Auto-entry sends a BUY limit (source ``bot``); Approve sends the plan as one bracket (source
``manual``: the operator decided the trade, Nova only picked the moment). A short setup's trade (ADR 049,
#778 step 5) is the mirror, through the one short check at the door: Auto-entry's short goes out with its
buy stop (a short never rests without one) and the cover is yours; Approve's is a short bracket. Every send carries an
idempotency key made of the kind, the venue, the setup and the attempt, so a repeat replays its
receipt, and the setup it trades (``setup=<setup_type>``, ADR 042 G); every send and cancel names
the trade's venue (``expected_venue``), so an order id is never sent to another venue.
Reads reuse the first-pullback bot's (``bot.first_pullback.orders``): the venue's own order rows and
long position, and a failed read raises ``ReadError`` -- unknown is never "filled" or "flat".
"""
from __future__ import annotations

import uuid
from typing import Any

from bot.first_pullback.orders import (  # noqa: F401 (re-exported)
    ReadError,
    held_qty,
    last_price,
    order_row,
    order_state,
    short_held_qty,
)
from execution.models import ExecutionCommand
from execution.service import execute


def _outside_rth() -> bool:
    """Extended-hours flag for the venue's clock (Nova trades from the premarket)."""
    from execution.session_gate import regular_hours_now

    return not regular_hours_now()


def _key(trade: dict[str, Any], step: str) -> str:
    """On a Sim replay the key carries the replay's run (ADR 052 amendment, #815): an approved setup the playhead
    plays across again after a rewind is sent again, never answered from the receipt the rewind took back."""
    return f"stock:{trade['kind']}:{trade['venue']}:{run_tag(trade)}{trade['symbol']}:{trade['attempt']}:{step}"


def run_tag(trade: dict[str, Any]) -> str:
    """The replay run's part of a key (``stock_mode.replay.run_tag``); ``""`` for a trade not made on a replay."""
    if not trade.get("replay_key"):
        return ""
    from stock_mode.replay import run_tag as tag

    return tag()


def is_short(trade: dict[str, Any]) -> bool:
    return trade.get("side") == "short"


def held(trade: dict[str, Any]) -> float:
    """The shares the venue holds on the trade's side (long, or short as a positive count)."""
    return short_held_qty(trade["symbol"]) if is_short(trade) else held_qty(trade["symbol"])


async def place_entry(trade: dict[str, Any]) -> Any:
    """Auto-entry: one BUY limit at the setup's entry. It never chases. A short goes out as a short limit with
    its buy stop and no target: the cover is yours, the stop rests until you cover."""
    if is_short(trade):
        entry = round(float(trade["entry"]), 4)
        return await execute(
            ExecutionCommand(
                operation="bracket",
                idempotency_key=_key(trade, "entry"),
                source="bot",
                origin="auto_entry",
                symbol=trade["symbol"],
                side="SELL",
                short_entry=True,
                qty=float(trade["qty"]),
                order_type="LMT",
                limit_price=entry,
                entry_price=entry,
                stop_price=round(float(trade["stop"]), 4),
                reference_price=entry,
                outside_rth=_outside_rth(),
                setup=trade.get("setup_type"),
                skip_risk=True,
                expected_venue=trade.get("venue"),
            ),
            wait_ack=False,
        )
    return await execute(
        ExecutionCommand(
            operation="place",
            idempotency_key=_key(trade, "entry"),
            source="bot",
            origin="auto_entry",
            symbol=trade["symbol"],
            side="BUY",
            qty=float(trade["qty"]),
            order_type="LMT",
            limit_price=round(float(trade["entry"]), 4),
            reference_price=round(float(trade["entry"]), 4),
            outside_rth=_outside_rth(),
            setup=trade.get("setup_type"),
            skip_risk=True,
            expected_venue=trade.get("venue"),
        ),
        wait_ack=False,
    )


async def send_bracket(trade: dict[str, Any]) -> Any:
    """Approve: the plan as one bracket -- a BUY limit at the entry, a SELL limit at the target and a
    SELL stop at the stop, the exits held until the entry fills and then one-cancels-other. A short plan's
    is the mirror: a short limit, a BUY limit at its cover and a BUY stop over it."""
    entry = round(float(trade["entry"]), 4)
    short = is_short(trade)
    return await execute(
        ExecutionCommand(
            operation="bracket",
            idempotency_key=_key(trade, "bracket"),
            source="manual",
            origin="approve",   # the operator approved it; Nova sent it at the trigger
            symbol=trade["symbol"],
            side="SELL" if short else "BUY",
            short_entry=short,
            qty=float(trade["qty"]),
            order_type="LMT",
            limit_price=entry,
            entry_price=entry,
            target_price=round(float(trade["target"]), 4),
            stop_price=round(float(trade["stop"]), 4),
            reference_price=entry,
            outside_rth=_outside_rth(),
            setup=trade.get("setup_type"),
            skip_risk=True,
            expected_venue=trade.get("venue"),
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
            expected_venue=trade.get("venue"),   # the trade's order ids are that venue's own
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
