"""Paper resting orders hold the symbol's IBKR tape line (ADR 020).

Modelled on ``capture/feed_hold.py``: while an order rests on the Paper venue
this module counts as one tape viewer for its symbol, so panels opening,
closing or switching away cannot pull the line, and release goes through the
same linger path the panels use (``ws_viewer_closed`` then ``unsubscribe``).

Resting Paper fills read their prints from the local tape archive
(``l2.tape``), which only persists symbols somebody registered. The hold
registers the symbol when nobody else has and withdraws that registration on
release unless a recorder has since taken the symbol over (it stamps a
session id; this hold never does).
"""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)

# symbol -> {"tape": we hold a viewer reference, "watch": we registered it with l2.tape}
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
    """Open (or join) the tape line and hold it; return an error or ``None``.

    Idempotent per symbol. A tape failure holds nothing -- the resting order
    keeps waiting and the matcher says why in the log.
    """
    from ibkr import tape_stream

    sym = symbol.strip().upper()
    if sym in _held:
        _ensure_watch(sym)
        return None
    if not tape_stream.is_subscribed(sym):
        result = await tape_stream.subscribe_async(sym)
        if not result.get("ok"):
            return result.get("error") or f"Could not open the IBKR tape for {sym}"
    tape_stream.ws_viewer_opened(sym)
    _held[sym] = {"tape": True, "watch": False}
    _ensure_watch(sym)
    logger.info("PRACTICE paper: holding the tape line for %s", sym)
    return None


def release(symbol: str) -> None:
    """Drop this module's references; the line closes only if no panel still watches."""
    from ibkr import tape_stream
    from l2 import tape

    sym = symbol.strip().upper()
    hold = _held.pop(sym, None)
    if hold is None:
        return
    if hold.get("tape") and tape_stream.ws_viewer_closed(sym):
        tape_stream.unsubscribe(sym)  # linger, then cancel if still idle
    if hold.get("watch") and tape.is_watched(sym) and tape.session_id(sym) is None:
        tape.unwatch_symbol(sym)
    logger.info("PRACTICE paper: released the tape line for %s", sym)


async def reconcile(wanted: Iterable[str]) -> dict[str, str]:
    """Hold every symbol in ``wanted``, release the rest; ``{symbol: error}`` for lines that would not open."""
    want = {s.strip().upper() for s in wanted if s and s.strip()}
    for sym in list(_held):
        if sym not in want:
            release(sym)
    errors: dict[str, str] = {}
    for sym in sorted(want):
        error = await acquire(sym)
        if error:
            errors[sym] = error
    return errors
