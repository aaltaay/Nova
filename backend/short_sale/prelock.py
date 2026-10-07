"""What the execution door reads before its lock for a short, and for a practice buy (ADR 048).

Nothing under the execution lock may wait on IBKR (ADR 048 gap 4): it would hold every other order,
Flatten included, and ADR 045's 750 ms send deadline. So before the lock the door gathers a short
entry's facts (``short_sale.facts``), and asks IBKR's what-if margin:

- a bot's short (no desk view: ADR 045 binds only the desk's own orders) may wait up to
  ``SHORT_WHATIF_BOT_WAIT_SEC`` for IBKR's answer;
- the ticket's short never waits: the what-if is asked in the background, and this order is judged
  by the answer Nova kept for the stock today, else the published rules;
- a practice buy (longs use margin too) asks in the background for the next order.

A Live short while ``IBKR_SHORT_ENABLED`` is off gathers nothing: the door refuses it at once.
"""
from __future__ import annotations

import asyncio

from constants_shorts import SHORT_WHATIF_BOT_WAIT_SEC
from execution.models import ExecutionCommand
from short_sale import whatif
from short_sale.facts import Facts, gather, is_replay


def _venue() -> str:
    from execution.venue_door import current

    return current()


def _price(cmd: ExecutionCommand) -> float | None:
    from short_sale.door import entry_price

    return entry_price(cmd)


async def facts_for(cmd: ExecutionCommand) -> Facts | None:
    """A short entry's facts; None for anything else (a practice buy only warms IBKR's figure)."""
    if cmd.operation not in ("place", "bracket"):
        return None
    from ibkr import client as _client
    from short_sale.door import order_qty

    venue = _venue()
    symbol = cmd.normalized_symbol() or ""
    qty = order_qty(cmd)
    price = _price(cmd) if cmd.short_entry else (cmd.limit_price or cmd.entry_price)
    ready = _client.is_ready() and not is_replay(venue) and bool(symbol) and qty > 0 and bool(price)
    if not cmd.short_entry:
        if ready and venue in ("paper", "sim") and (cmd.side or "BUY").upper() == "BUY":
            whatif.request(symbol, "BUY", qty, float(price))
        return None
    from ibkr import safety as _safety

    if venue == "live" and not _safety.short_enabled():
        return None
    if ready and not whatif.fresh(symbol, "SELL"):
        if cmd.client_timing is None:
            await whatif.ask(symbol, "SELL", qty, float(price), timeout=SHORT_WHATIF_BOT_WAIT_SEC)
        else:
            whatif.request(symbol, "SELL", qty, float(price))
    return await asyncio.to_thread(gather, symbol, venue)
