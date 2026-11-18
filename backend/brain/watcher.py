"""Nova's own watch over the brain, every ``BRAIN_TICK_SEC`` (ADR 072 decisions 1, 7). Registered as ``brain`` in
``app_runtime_tasks``.

- **Flat by.** At the brain's flat-by time (``trader-limits.json``, 15:55 ET) Nova cancels the brain's working
  orders and sells its shares on Paper, whatever its switch says. A stock handed to the operator is the operator's:
  its shares stay and its stop and target keep resting.
- **A program that stopped answering** is said once on the brain's stream. Nothing is sold for it: its stop and
  target keep resting.
- **Fills** are said on the stream as the brain's position changes.
- **The morning wake.** On a trading day Nova turns the brain's switch On once, unless you set it that day
  (``traders.wake``, ADR 072 Amendment 2).

A failed pass is logged and the next one runs; nothing here opens a position.
"""
from __future__ import annotations

import asyncio
import logging

from brain import book, orders, session
from brain.constants_brain import BRAIN_ORIGIN, BRAIN_TICK_SEC

logger = logging.getLogger(__name__)
_FLAT_RETRY_SEC = 60.0
_last_flat_try = 0.0
_seen: dict[str, float] | None = None


def _past_flat_by() -> str | None:
    from market import now_et
    from traders import limits

    clock, flat_by = now_et(), str(limits.of(BRAIN_ORIGIN)["flat_by"])
    return flat_by if clock.weekday() < 5 and clock.strftime("%H:%M") >= flat_by else None


async def _flat_by(now: float) -> None:
    global _last_flat_try
    flat_by = _past_flat_by()
    if flat_by is None or now - _last_flat_try < _FLAT_RETRY_SEC:
        return
    try:
        if not book.positions() and not book.working(with_handed=False):
            return
    except book.ReadError:
        logger.warning("BRAIN flat by: Paper could not be read; trying again", exc_info=True)
        return
    _last_flat_try = now
    problems = await orders.close()
    if problems:
        session.event("flat_by", f"Flat by {flat_by} ET: Nova could not close everything -- {'; '.join(problems)}")
    else:
        session.event("flat_by", f"Flat by {flat_by} ET: Nova cancelled the brain's orders and sold its shares")


def _fills() -> None:
    """Say each change in the brain's position on its stream."""
    global _seen
    try:
        held = {sym: lot["qty"] for sym, lot in book.positions(with_handed=True).items()}
        costs = {sym: lot["avg_cost"] for sym, lot in book.positions(with_handed=True).items()}
    except book.ReadError:
        return
    before, _seen = _seen, held
    if before is None:
        return
    for sym in sorted(set(before) | set(held)):
        was, now_qty = before.get(sym, 0.0), held.get(sym, 0.0)
        if now_qty > was + 1e-9:
            session.event("fill", f"Bought {now_qty - was:g} {sym}; holds {now_qty:g} at {costs[sym]:.4g}", sym)
        elif now_qty < was - 1e-9:
            rest = f"holds {now_qty:g}" if now_qty > 1e-9 else "flat"
            session.event("close", f"Sold {was - now_qty:g} {sym}; {rest}", sym)


def _wake() -> None:
    from traders import wake

    try:
        wake.run_pass()
    except Exception:
        logger.exception("BRAIN watcher: the morning wake failed; trying again next pass")


async def run_pass(now: float | None = None) -> None:
    t = asyncio.get_running_loop().time() if now is None else float(now)
    _wake()
    if session.went_silent():
        session.event("silent", "The brain's program stopped answering. Nothing is sold for it: its stop and target "
                                "keep resting, and flat by still closes it.")
    _fills()
    await _flat_by(t)


async def run() -> None:
    while True:
        try:
            await run_pass()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("BRAIN watcher: a pass failed")
        await asyncio.sleep(BRAIN_TICK_SEC)


def reset_for_tests() -> None:
    global _last_flat_try, _seen
    _last_flat_try, _seen = 0.0, None
