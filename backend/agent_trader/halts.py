"""Claude's seat and trading halts (ADR 068 decision 16, 2026-10-27: AIOK halted at 15.74 seconds after a resting
buy at 15.76, and the buy rested through the halt).

The halt is the scanner's own (``ibkr.halt_status.halted_now``: IBKR's tick 49 where Nova holds a Level 1 line,
else the Nasdaq Trade Halt feed; None when neither knows -- a halt is never inferred). While a stock is halted:
- a new entry is refused (``rules.entry_refusal``, ``AGENT_HALTED``);
- Claude's unfilled buys and armed breaks on it are cancelled at once, each said on the desk (``run``);
- held shares keep their stop and targets resting, and the guard does not judge it (``guard_pass``), so it never
  market-sells into the reopening auction.
No state of its own; every read asks the halt source.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def halted(symbol: str) -> bool | None:
    """True / False / None (not known), as the scanner's ``halted``. A read that fails is unknown (logged)."""
    from ibkr import halt_status

    sym = (symbol or "").strip().upper()
    try:
        return halt_status.halted_now([sym]).get(sym)
    except Exception:
        logger.warning("AGENT halts: %s's halt state could not be read", sym, exc_info=True)
        return None


async def run(t: float) -> None:
    """Cancel Claude's unfilled buys and breaks on a stock that halted (the watcher, every pass)."""
    from agent_trader import ledger, orders, seat

    try:
        buys = [r for r in ledger.working() if str(r.get("side") or "").upper() == "BUY"
                and r.get("leg_role") in (None, "parent")]
    except ledger.ReadError:
        logger.warning("AGENT halts: Paper could not be read; checked next pass", exc_info=True)
        return
    rows = seat.breaks()
    for sym in sorted({str(r["symbol"]).upper() for r in buys} | {str(b["symbol"]).upper() for b in rows}):
        if halted(sym) is not True:
            continue
        for r in [r for r in buys if str(r["symbol"]).upper() == sym]:
            why = orders.receipt_error(await orders.cancel(int(r["order_id"]), sym))
            seat.event("refused", f"{sym} is halted: Nova cancelled Claude's buy at {float(r.get('limit_price') or 0):g}"
                       if not why else f"{sym} is halted, but Claude's buy could not be cancelled: {why}", t)
        for b in [b for b in rows if str(b["symbol"]).upper() == sym]:
            seat.drop_break(b["id"], f"{sym} is halted: Nova took back Claude's break at {float(b['trigger']):g}", t)
