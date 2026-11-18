"""An AI trader's raise of its own stop on Paper, whatever the desk shows (ADR 072 Amendment 3).

While the desk is on Live or Sim, Claude and the brain open nothing and their open Paper trade keeps its exits. A
raise of the trader's own resting stop only ever takes risk off, so it may name Paper like their closes and cancels
do (``execution.venue_door``): a ``replace`` with source ``cancel_working``, the new stop price alone.

``is_one`` reads the command's shape; ``refusal`` checks it against Paper's own book and says why it may not go.
Nothing here sends anything. Shapes: ``architecture/schema/execution.md`` "A trader's stop raise".
"""
from __future__ import annotations

import logging
from typing import Any

from constants_owners import AI_TRADERS, OWNER_NAMES
from constants_practice import PRACTICE_VENUE_PAPER

logger = logging.getLogger(__name__)


def is_one(cmd: Any) -> bool:
    """``cmd`` is shaped as a stop raise: Claude's or the brain's protective replace of a stop price, nothing else."""
    return (cmd.origin in AI_TRADERS and cmd.operation == "replace" and cmd.source == "cancel_working"
            and cmd.order_id is not None and cmd.stop_price is not None
            and cmd.limit_price is None and cmd.resize_qty is None)


def refusal(cmd: Any, target: str) -> str | None:
    """Why this stop raise may not go to ``target``, or None: the trader's own resting stop on Paper, on a stock
    not handed to the operator, moved up. Paper's book unread is a refusal, never a pass."""
    name = OWNER_NAMES.get(str(cmd.origin), str(cmd.origin))
    if target != PRACTICE_VENUE_PAPER:
        return f"{name} raises a stop on Paper only, not on {target}; nothing was sent"
    try:
        from practice.broker import for_venue
        from traders import handed

        broker = for_venue(target)
        row = broker.ledger.working_row(int(cmd.order_id))
        handed_now = handed.active(broker.venue, broker.ledger, broker.reference.now_ts())
    except Exception:
        logger.exception("STOP RAISE: Paper's book could not be read for order %s", cmd.order_id)
        return "Paper's orders could not be read, so the stop was not moved; nothing was sent"
    if row is None:
        return f"order {cmd.order_id} is not working on Paper; nothing was sent"
    symbol = str(row.get("symbol") or "").upper()
    own_stop = (row.get("order_origin") == cmd.origin and row.get("leg_role") == "stop"
                and str(row.get("side") or "").upper() == "SELL" and row.get("stop_price") is not None)
    if not own_stop:
        return f"order {cmd.order_id} is not {name}'s own resting stop; nothing was sent"
    if symbol in handed_now:
        return f"{symbol} is handed to you: its stop is yours to move, not {name}'s; nothing was sent"
    resting = float(row["stop_price"])
    if float(cmd.stop_price) <= resting:
        return f"a stop only moves up: {float(cmd.stop_price):g} is not above {resting:g}; nothing was sent"
    return None
