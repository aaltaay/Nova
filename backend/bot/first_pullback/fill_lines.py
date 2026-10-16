"""Nova's own bot's ``partial`` lines: a working entry, resting exit or close that filled more shares
(operator ask 2026-10-16; architecture/schema/bot.md, "Fills on the bot audit stream"). The marks are
``bot.fill_progress``'s; this module only says them for the bot's trade.
"""
from __future__ import annotations

from typing import Any, Callable

from bot import fill_progress
from bot.audit import record as audit
from bot.first_pullback import orders
from constants_bot import BOT_AUDIT_ACTION_TRADE, BOT_AUDIT_OUTCOME_PARTIAL


def progress(trade: dict[str, Any], row: dict[str, Any] | None, state: str, leg: str, order_id: Any,
             summary: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """``leg``: ``entry`` | ``target1`` | ``target2`` | ``stop`` | ``close``. An order that ended is forgotten."""
    if state != "working":
        fill_progress.forget(order_id)
        return
    phase = "entry" if leg == "entry" else "exit"
    fill = fill_progress.partial(row, phase=phase, leg=leg, order_id=order_id)
    if fill is None:
        return
    short = orders.is_short(trade)
    verb = ("shorted" if short else "bought") if phase == "entry" else ("covered" if short else "sold")
    audit(action=BOT_AUDIT_ACTION_TRADE, outcome=BOT_AUDIT_OUTCOME_PARTIAL, order_id=int(order_id),
          inputs=summary(trade), reason=f"{fill_progress.words(fill, trade['symbol'], verb)} ({leg})", fill=fill)
