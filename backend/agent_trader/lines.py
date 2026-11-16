"""Claude's Level 2 and Time & Sales line: Claude's lane (ADR 068 decision 2; ADR 071 decision 5).

The seat's lane (``line_lanes``, owner ``claude``) is kept for it whether the seat is on or off: no one else uses
it, and the seat never takes, borrows or waits for another's line. ``acquire`` puts the lane on the seat's stock --
the old stock's lines end at once unless another lane is on it -- and ``release`` empties it. A stock your lane or
the bots' is already on costs no line (one pair of lines). The lane asks IBKR again for a line that is down
(``line_lanes.lanes.ensure``); here a missing line is only said.
"""
from __future__ import annotations

import logging

from line_lanes import lanes
from line_lanes.table import CLAUDE

logger = logging.getLogger(__name__)


def reset_for_tests() -> None:
    """Claude's lane lives in ``line_lanes.lanes`` (reset there)."""


def held_symbol() -> str | None:
    """The stock Claude's lane is on, or None."""
    return lanes.table().claude


def holds(symbol: str) -> bool:
    return bool(symbol) and held_symbol() == (symbol or "").strip().upper()


def holds_depth(symbol: str) -> bool:
    """Claude's Level 2 on ``symbol`` is up on this IBKR session."""
    return holds(symbol) and lanes.lines_up(symbol)[lanes.DEPTH]


def holds_tape(symbol: str) -> bool:
    return holds(symbol) and lanes.lines_up(symbol)[lanes.TAPE]


async def acquire(symbol: str) -> str | None:
    """Put Claude's lane on ``symbol``; why its lines are not both up yet, or None."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return "no stock named"
    if held_symbol() != sym:
        await lanes.put(CLAUDE, sym)
    up = lanes.lines_up(sym)
    if up[lanes.DEPTH] and up[lanes.TAPE]:
        return None
    why = lanes.error(sym)
    logger.info("AGENT lines: %s's lines not both up yet (%s)", sym, why or "asked")
    missing = " and ".join(name for name, ok in (("Level 2", up[lanes.DEPTH]), ("Time & Sales", up[lanes.TAPE]))
                           if not ok)
    return f"IBKR has not opened {sym}'s {missing} yet; Nova asks again"


async def release(symbol: str | None = None, *, at_once: bool = True) -> None:
    """Empty Claude's lane (``symbol``: only while the lane is on it). ``at_once`` is kept for its callers: a lane
    always lets go at once."""
    del at_once
    current = held_symbol()
    if current is None or (symbol and symbol.strip().upper() != current):
        return
    await lanes.put(CLAUDE, None)
    logger.info("AGENT lines: released %s", current)
