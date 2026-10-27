"""The guard's pass over Claude's open trades (ADR 068 decision 13), run by the watcher every pass.

Judges each position with ``guard`` on the live book and the last prints (the live ring first, ``wake``) and sells
at once when a condition holds; raises a pop exit's stop to entry once its first half sold or at the first stall.
Every outcome is a seat event the desk shows.
"""
from __future__ import annotations

import logging
from typing import Any

from agent_trader.constants_agent_trader import AGENT_GUARD_STALL_SEC

logger = logging.getLogger(__name__)


async def run(t: float) -> None:
    """Judge Claude's open trades every pass; sell at once when one condition holds (``guard``)."""
    from agent_trader import guard, journal, ledger, seat, watcher
    from ibkr import depth, ticks

    try:
        fills = ledger.fills_today()
        held = ledger.positions(fills)
    except ledger.ReadError:
        logger.warning("AGENT guard: Paper could not be read; judged next pass", exc_info=True)
        return
    guard.forget_except({s for s, q in held.items() if q > 0})
    plans = seat.exits()
    for sym, qty in held.items():
        if qty <= 0:
            continue
        book = depth.current_book(sym)
        row = guard.mark(sym, fills, book, t)
        if row is None:
            continue
        if (plans.get(sym) or {}).get("mode") == "pop" and not row["breakeven"]:
            guard.note_price(row, (ticks.last_quotes([sym]).get(sym) or {}).get("price"), t)
            await _stop_to_entry(sym, row, fills, t)
        if not guard.due(sym, t):
            continue
        prints = await watcher._recent_prints(sym, t)       # none when they cannot be read: the book is judged alone
        why = guard.judge(row, book=book, prints=prints, now=t, l1_bid=ticks.bid_ask(sym)[0])
        if why is None:
            continue
        guard.note_fired(sym, t)
        journal.note_exit(sym, "guard", why)
        done = await watcher._act({"action": "sell_all"}, sym, qty)
        seat.event("reflex_fired", f"Nova's guard on {sym}: {why} -- {done}", t)


async def _stop_to_entry(sym: str, row: dict[str, Any], fills: list[dict[str, Any]], t: float) -> None:
    """The pop exit: once its first half sold, or at the first stall, Claude's stop rises to its entry (never
    lowered)."""
    from agent_trader import guard, ledger, orders, seat

    if guard.first_half_sold(fills, sym, row.get("opened")):
        cause = f"the first half of {sym} sold at the pop"
    elif guard.stalled(row, t):
        cause = f"{sym} stalled (no new high for {AGENT_GUARD_STALL_SEC:g} s after {row['high']:g})"
    else:
        return
    entry = round(float(row["entry"]), 2 if float(row["entry"]) >= 1.0 else 4)
    try:
        stops = [r for r in ledger.working() if str(r["symbol"]).upper() == sym and r.get("leg_role") == "stop"]
    except ledger.ReadError:
        return
    for r in stops:
        if r.get("stop_price") is not None and float(r["stop_price"]) >= entry - 1e-9:
            continue
        why = orders.receipt_error(await orders.move_stop(int(r["order_id"]), sym, entry))
        seat.event("stop", f"{cause}: stop moved up to entry {entry:g}" if not why
                   else f"{cause}, but the stop could not move to entry: {why}", t)
        if why:
            return
    row["breakeven"] = True
