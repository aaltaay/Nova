"""Live matcher: fills resting practice orders on live tape prints, once a second.

The Sim feed matches practice orders against replay prints
(``sim.feed.match_practice_fills``); this loop does the same against the live
tape for every venue that fills on it right now -- Paper always, and Sim
while its clock is at the live edge (ADR 020 live-edge amendment, where the
Sim broker's reference is Paper's ``LiveReference``). Each pass rolls the
practice day if the clock crossed the boundary, holds the tape line of every
symbol with a resting order across those venues (``practice.tape_hold``) and
releases the others, then hands the prints since the last pass to
``PracticeBroker.try_fill_working`` and finally expires every DAY order whose
session has closed (``PracticeBroker.expire_due``) -- after the match, so a
print at the close itself still fills and a print past it never does.
Registered from ``app_runtime_tasks`` as ``practice.matcher``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from constants_practice import PRACTICE_MATCHER_INTERVAL_SEC, PRACTICE_VENUE_PAPER, PRACTICE_VENUE_SIM
from practice import tape_hold

logger = logging.getLogger(__name__)

# venue -> symbol -> venue time of the last pass that looked for its prints.
# Prints are only ever matched after it, so a pass never re-reads what it
# already saw. Per venue: Paper and Sim rest their own orders.
_cursors: dict[str, dict[str, float]] = {}


def reset_for_tests() -> None:
    _cursors.clear()


def _earliest_rest(broker: Any, symbol: str) -> float | None:
    placed = [
        float(row.get("placed_ts") or 0)
        for row in broker.working_orders()
        if row.get("symbol") == symbol
    ]
    return min(placed) if placed else None


def _sim_at_live_edge() -> bool:
    """Sim fills on the live tape only while its clock is at the live edge, on the Sim venue."""
    try:
        from sim import session_clock
        from sim.mode import is_sim_mode

        return is_sim_mode() and session_clock.live_edge()
    except Exception:
        logger.debug("PRACTICE matcher: Sim edge unknown, treating as off", exc_info=True)
        return False


def live_brokers() -> list[Any]:
    """The brokers whose resting orders fill on the live tape this pass."""
    from practice.broker import for_venue

    brokers = [for_venue(PRACTICE_VENUE_PAPER)]
    if _sim_at_live_edge():
        brokers.append(for_venue(PRACTICE_VENUE_SIM))
    return brokers


async def _hold_lines(wanted: list[str]) -> None:
    errors = await tape_hold.reconcile(wanted)
    for sym, error in errors.items():
        logger.warning("PRACTICE: tape line for %s unavailable, resting orders wait (%s)", sym, error)


async def _match(broker: Any, *, now: float | None) -> list[dict[str, Any]]:
    """Match one broker's resting orders against the live prints since its last pass."""
    broker.rollover()
    wanted = broker.working_symbols()
    cursor = _cursors.setdefault(str(broker.venue), {})
    for sym in list(cursor):
        if sym not in wanted:
            cursor.pop(sym, None)
    now_ts = float(now) if now is not None else float(broker.reference.now_ts())
    filled: list[dict[str, Any]] = []
    for sym in wanted:
        after = cursor.get(sym)
        if after is None:
            after = _earliest_rest(broker, sym)
        cursor[sym] = now_ts
        if after is None or now_ts <= after:
            continue
        prints = await asyncio.to_thread(broker.reference.prints_between, sym, after, now_ts)
        if prints:
            filled.extend(broker.try_fill_working(sym, prints))
    for row in broker.expire_due(now_ts):
        logger.info("PRACTICE %s: DAY order %s expired at the session close", broker.venue, row.get("order_id"))
    return filled


async def pass_once(broker: Any = None, *, now: float | None = None) -> list[dict[str, Any]]:
    """One matcher pass for one broker; returns the rows filled. Defaults to the Paper venue."""
    if broker is None:
        from practice.broker import for_venue

        broker = for_venue(PRACTICE_VENUE_PAPER)
    await _hold_lines(broker.working_symbols())
    return await _match(broker, now=now)


async def pass_venues(*, now: float | None = None) -> list[dict[str, Any]]:
    """One pass over every venue filling on the live tape, holding the union of their symbols.

    The hold is reconciled once for all of them: reconciling per broker would
    release Paper's lines while holding Sim's, and vice versa.
    """
    brokers = live_brokers()
    await _hold_lines(sorted({sym for broker in brokers for sym in broker.working_symbols()}))
    filled: list[dict[str, Any]] = []
    for broker in brokers:
        filled.extend(await _match(broker, now=now))
    return filled


async def run() -> None:
    """Background loop on the HTTP loop (the tape hold's line lives there)."""
    while True:
        try:
            await asyncio.sleep(PRACTICE_MATCHER_INTERVAL_SEC)
            await pass_venues()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("PRACTICE: matcher pass failed")
