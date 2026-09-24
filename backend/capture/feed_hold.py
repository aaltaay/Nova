"""Record owns its IBKR lines: AllLast tape + depth for the recorded symbol (#315).

Record used to borrow whatever a Time & Sales / Level 2 panel happened to have
open. Admission required ``tape_stream.is_subscribed`` -- so Record was refused
with the tape panel hidden, and always on a Sim desk, whose tape socket never
subscribes IBKR. Worse, a recording that did start lost its feed silently when
the last panel closed: the tape line is refcounted by viewers and cancelled
after its linger, and the depth line after its grace window.

Here Record takes its own reference on both lines, counted exactly like a
viewer, for as long as it records. Panels opening, closing or switching to Sim
cannot pull the feed; stop releases through the same linger / grace paths the
panels use, so a panel still watching keeps its line. The depth line is best
effort: without it prints still record (with an explicit status warning), but
quotes, Level 2 and the live print side -- classified against that book -- do
not.
"""
from __future__ import annotations

import logging
import time
from typing import Iterable

from capture.constants_capture import CAPTURE_HOLD_ORPHAN_GRACE_SEC

logger = logging.getLogger(__name__)

# symbol -> which lines this module holds a viewer reference on.
_held: dict[str, dict[str, bool]] = {}
# symbol -> when its hold was taken (a start in flight is not an orphan).
_taken_at: dict[str, float] = {}


def reset_for_tests() -> None:
    _held.clear()
    _taken_at.clear()


def held(symbol: str) -> dict[str, bool] | None:
    return _held.get(symbol.upper())


def held_symbols() -> list[str]:
    return list(_held)


def orphans(recording: Iterable[str], now: float | None = None) -> list[str]:
    """Holds no recording uses -- e.g. the recorder stopped itself on a disk error.

    A hold is taken before ``set_capture_mode`` lists its symbol (on a worker
    thread, behind the writer's drain), so a status poll in that window used to
    release a recording's lines as it started (#525). A young hold is a start in
    flight; one whose start failed is released once it is older than the grace.
    """
    stamp = time.time() if now is None else now
    wanted = {str(s).upper() for s in recording}
    return [sym for sym in _held
            if sym not in wanted and stamp - _taken_at.get(sym, 0.0) >= CAPTURE_HOLD_ORPHAN_GRACE_SEC]


async def acquire(symbol: str) -> str | None:
    """Open (or join) the tape and depth lines and hold them; return an error or None.

    Idempotent per symbol. A tape failure refuses the recording -- there is
    nothing to record without prints -- and holds nothing.
    """
    from ibkr import depth, tape_stream

    sym = symbol.strip().upper()
    if sym in _held:
        return None
    if not tape_stream.is_subscribed(sym):
        result = await tape_stream.subscribe_async(sym)
        if not result.get("ok"):
            return result.get("error") or f"Could not open the IBKR tape for {sym}"
    tape_stream.ws_viewer_opened(sym)
    hold = {"tape": True, "depth": False}
    try:
        # `live`: on a Sim desk a plain subscribe reserves a replay slot, which
        # would record the practice book instead of the market.
        if not depth.is_live(sym):
            result = await depth.subscribe_async(sym, live=True)
            if not result.get("ok"):
                logger.warning("RECORD: depth unavailable for %s (%s); prints only", sym, result.get("error"))
        if depth.is_live(sym):
            depth.ws_viewer_opened(sym)
            hold["depth"] = True
    except Exception:
        logger.exception("RECORD: depth hold failed for %s; prints only", sym)
    _held[sym] = hold
    _taken_at[sym] = time.time()
    logger.info("RECORD: holding IBKR lines for %s (%s)", sym, hold)
    return None


async def renew_tape(symbol: str) -> str | None:
    """Ask IBKR for the recording's tape line again (#525); return an error or None.

    Only the tape: the hold keeps its viewer reference, the depth line is not
    touched (a Gateway drop re-takes both through ``release`` / ``acquire``).
    Without a hold -- it was lost -- this takes one.
    """
    from ibkr import tape_stream

    sym = symbol.strip().upper()
    if sym not in _held:
        return await acquire(sym)
    if tape_stream.is_subscribed(sym):
        return None
    result = await tape_stream.subscribe_async(sym)
    if result.get("ok"):
        logger.warning("RECORD: re-requested the IBKR tape line for %s", sym)
        return None
    return result.get("error") or f"Could not open the IBKR tape for {sym}"


async def release(symbol: str) -> None:
    """Drop this module's references; lines close only if no panel still watches."""
    from ibkr import depth, tape_stream

    sym = symbol.strip().upper()
    hold = _held.pop(sym, None)
    _taken_at.pop(sym, None)
    if hold is None:
        return
    if hold["tape"] and tape_stream.ws_viewer_closed(sym):
        tape_stream.unsubscribe(sym)  # linger, then cancel if still idle
    if hold["depth"] and depth.ws_viewer_closed(sym):
        try:
            if await depth.release_when_idle(sym):
                from l2 import recorder as l2_recorder
                if not l2_recorder.is_recording(sym):
                    depth.unsubscribe(sym)
        except Exception:
            logger.exception("RECORD: depth release failed for %s", sym)
    logger.info("RECORD: released IBKR lines for %s", sym)
