"""The bots' lane: one setup a bot may buy, at a time (ADR 071 decision 6; operator, 2026-11-13).

Every tick (``runner``) reads the candidates (``bots_pick.wanted``: the setups a bot may buy now, best first) and
puts the lane (``choose``, pure):

- on the stock it is on while that still wants it -- a candidate, or a stock Nova holds a trade on -- unless a
  candidate of a better tier wants the lane and the stock is not in a trade;
- else on the best candidate;
- else nowhere: an empty lane stays empty.

A read that failed leaves the lane where it is and says why (``status()['error']``), never a guess. The lane is
never lent and takes no one else's line; a setup with no lane reads ``blind`` on its row, as before.

ADR 072: the bots are retired, so ``wanted`` names no candidate (``status()['blocked']`` says why) and the lane
stays empty until it becomes the brain's.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from line_lanes import bots_pick, lanes
from line_lanes.bots_pick import Candidate, Wanted, rank
from line_lanes.constants_lanes import WHY_TRADE
from line_lanes.table import BOTS

logger = logging.getLogger(__name__)

_on: Candidate | None = None       # the candidate the lane was last put on (None: empty, or a held trade's stock)
_wanted: Wanted = Wanted()
_last_tick: float | None = None


def reset_for_tests() -> None:
    global _on, _wanted, _last_tick
    _on, _wanted, _last_tick = None, Wanted(), None


def choose(current: str | None, wanted: Wanted, nova_trade: Callable[[str], bool]) -> tuple[str | None, Candidate | None]:
    """Pure: the stock the bots' lane goes on, and the candidate it is on for (None for a held trade's stock)."""
    best = wanted.candidates[0] if wanted.candidates else None
    if wanted.error is not None:
        return current, wanted.get(current) if current else None
    if current:
        mine = wanted.get(current)
        # A trade Nova holds keeps the lane even while a newer setup on the stock is only armed (PR #1312 review).
        held = nova_trade(current)
        if mine is not None or held:
            in_trade = held or (mine is not None and mine.why == WHY_TRADE)
            better = best is not None and best.symbol != current and (
                mine is None or rank(best.why) < rank(mine.why))
            if in_trade or not better:
                return current, mine
    if best is None:
        return None, None
    return best.symbol, best


async def tick(now: float | None = None) -> None:
    """Choose again and put the lane there."""
    global _on, _wanted, _last_tick
    ts = time.time() if now is None else float(now)
    _wanted = bots_pick.wanted(ts)
    current = lanes.table().bots
    symbol, candidate = choose(current, _wanted, bots_pick.nova_trade)
    _on = candidate
    _last_tick = ts
    if symbol != current:
        await lanes.put(BOTS, symbol)


def status() -> dict[str, Any]:
    """``{setup, why, waiting: [{symbol, setup, why}], error}`` for ``GET /api/ibkr/lanes``."""
    current = lanes.table().bots
    on = _on if (_on is not None and _on.symbol == current) else None
    return {
        "setup": on.setup_type if on else None,
        "why": on.why if on else None,
        "waiting": [{"symbol": c.symbol, "setup": c.setup_type, "why": c.why}
                    for c in _wanted.candidates if c.symbol != current],
        "error": _wanted.error,
        "blocked": _wanted.blocked,
    }
