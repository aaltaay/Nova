"""Paper matcher: fills resting Paper orders on live tape prints, once a second.

The Sim feed matches practice orders against replay prints
(``sim.feed.match_practice_fills``); this loop does the same for the Paper
venue against the live tape. Each pass rolls the practice day if the clock
crossed the boundary, holds the tape line of every symbol with a resting
order (``practice.tape_hold``) and releases the others, then hands the prints
since the last pass to ``PracticeBroker.try_fill_working``. Registered from
``app_runtime_tasks`` as ``practice.matcher``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from constants_practice import PRACTICE_MATCHER_INTERVAL_SEC, PRACTICE_VENUE_PAPER
from practice import tape_hold

logger = logging.getLogger(__name__)

# symbol -> venue time of the last pass that looked for its prints. Prints are
# only ever matched after it, so a pass never re-reads what it already saw.
_cursor: dict[str, float] = {}


def reset_for_tests() -> None:
    _cursor.clear()


def _earliest_rest(broker: Any, symbol: str) -> float | None:
    placed = [
        float(row.get("placed_ts") or 0)
        for row in broker.working_orders()
        if row.get("symbol") == symbol
    ]
    return min(placed) if placed else None


async def pass_once(broker: Any = None, *, now: float | None = None) -> list[dict[str, Any]]:
    """One matcher pass; returns the rows filled. ``broker`` defaults to the Paper venue."""
    if broker is None:
        from practice.broker import for_venue

        broker = for_venue(PRACTICE_VENUE_PAPER)
    broker.rollover()
    wanted = broker.working_symbols()
    errors = await tape_hold.reconcile(wanted)
    for sym, error in errors.items():
        logger.warning("PRACTICE paper: tape line for %s unavailable, resting orders wait (%s)", sym, error)
    for sym in list(_cursor):
        if sym not in wanted:
            _cursor.pop(sym, None)
    now_ts = float(now) if now is not None else float(broker.reference.now_ts())
    filled: list[dict[str, Any]] = []
    for sym in wanted:
        after = _cursor.get(sym)
        if after is None:
            after = _earliest_rest(broker, sym)
        _cursor[sym] = now_ts
        if after is None or now_ts <= after:
            continue
        prints = await asyncio.to_thread(broker.reference.prints_between, sym, after, now_ts)
        if prints:
            filled.extend(broker.try_fill_working(sym, prints))
    return filled


async def run() -> None:
    """Background loop on the HTTP loop (the tape hold's line lives there)."""
    while True:
        try:
            await asyncio.sleep(PRACTICE_MATCHER_INTERVAL_SEC)
            await pass_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("PRACTICE paper: matcher pass failed")
