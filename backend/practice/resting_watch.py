"""What a resting Paper or Sim order keeps open for its stock: a Level 1 line, and the tape archive's watch (ADR 071
decision 9; replaces ``practice/tape_hold.py``).

A resting order holds no Level 2 or Time & Sales line: those are the lanes' (``line_lanes``). It fills on its
stock's prints while a lane is on the stock, and on IBKR's Level 1 Last otherwise (``fill_basis: "l1_last"``,
``practice.reference.PaperReference.l1_trade_while_tape_missing``). So the order keeps:

- a Level 1 line (``ibkr.ticks``, owner ``practice``) -- IBKR's Last, the stand-in when no lane is on the stock.
  Each pass asks ``ticks`` whether the line is still this module's: a reconnect clears every Level 1 line
  (``ticks.clear_all_subscriptions``), and the next pass opens it again (PR #1312 review);
- the tape archive's watch (``l2.tape``): resting fills read their prints from the archive, which persists only
  symbols somebody registered. The watch is withdrawn on release unless a recorder has since taken the symbol over
  (it stamps a session id; this module never does).

An order never waits for a line.
"""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)

OWNER = "practice"

# symbol -> {"l1": this module owns a Level 1 reference, "watch": it registered the symbol with l2.tape}
_held: dict[str, dict[str, bool]] = {}


def reset_for_tests() -> None:
    _held.clear()


def held(symbol: str) -> dict[str, bool] | None:
    return _held.get(symbol.strip().upper())


def held_symbols() -> list[str]:
    return list(_held)


def _ensure_watch(sym: str) -> None:
    from l2 import tape

    hold = _held.get(sym)
    if hold is None or tape.is_watched(sym):
        return
    tape.watch_symbol(sym, None)
    hold["watch"] = True


async def acquire(symbol: str) -> str | None:
    """Keep ``symbol``'s Level 1 line and archive watch; an error when the Level 1 line would not open, else None."""
    from ibkr import ticks

    sym = symbol.strip().upper()
    hold = _held.setdefault(sym, {"l1": False, "watch": False})
    _ensure_watch(sym)
    # The line, not this module's memory of it: a reconnect let go of every Level 1 line under the hold.
    if hold["l1"] and OWNER in ticks.owners_for(sym):
        return None
    hold["l1"] = False
    if not await ticks.subscribe(sym, OWNER):
        return f"IBKR did not open {sym}'s Level 1 line"
    hold["l1"] = True
    logger.info("PRACTICE: keeping %s's Level 1 line for its resting orders", sym)
    return None


async def release(symbol: str) -> None:
    """Drop this module's Level 1 reference and archive watch."""
    from ibkr import ticks
    from l2 import tape

    sym = symbol.strip().upper()
    hold = _held.pop(sym, None)
    if hold is None:
        return
    if hold.get("l1"):
        await ticks.unsubscribe(sym, OWNER)
    if hold.get("watch") and tape.is_watched(sym) and tape.session_id(sym) is None:
        tape.unwatch_symbol(sym)
    logger.info("PRACTICE: let go of %s's Level 1 line (no resting order)", sym)


async def reconcile(wanted: Iterable[str]) -> dict[str, str]:
    """Keep every symbol in ``wanted``, release the rest; ``{symbol: error}`` for Level 1 lines that would not open."""
    want = {s.strip().upper() for s in wanted if s and s.strip()}
    for sym in list(_held):
        if sym not in want:
            await release(sym)
    errors: dict[str, str] = {}
    for sym in sorted(want):
        error = await acquire(sym)
        if error:
            errors[sym] = error
    return errors
