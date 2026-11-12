"""The operator's lane: on the last stock they opened, with no timer (ADR 071 decisions 2, 3).

A Level 2 or Time & Sales socket that says it is in front (``front=1``: the Trader tab in front, the phone's
Trade screen) names the lane's stock. The lane then holds one viewer reference on each of that stock's two
lines, taken and given back like a Session Record's (``capture.feed_hold``): the socket closing, the tab
hiding or the phone's page going to the background leaves both lines up, because the lane still watches them.

The lane moves only when a socket in front opens another stock, and then at once: its references on the old
stock are dropped and, when nothing else watches that stock, both its lines are cancelled before the new
stock's are asked for. The lane opens no line itself; the socket that named the stock does.

Not persisted: a restart closes every socket, and the first one in front names the lane again.
"""
from __future__ import annotations

import logging

from line_lanes.table import YOU, Lanes, put

logger = logging.getLogger(__name__)

DEPTH = "depth"
TAPE = "tape"
MOVED_WHY = "your lane moved to another stock"

_lanes = Lanes()
# Which of the lane's stock's lines the lane holds a viewer reference on.
_held: dict[str, bool] = {DEPTH: False, TAPE: False}


def reset_for_tests() -> None:
    global _lanes
    _lanes = Lanes()
    _held.update({DEPTH: False, TAPE: False})


def stock() -> str | None:
    """The stock the operator's lane is on, or None before they opened one."""
    return _lanes.on(YOU)


def holds(symbol: str, kind: str) -> bool:
    return stock() == (symbol or "").strip().upper() and bool(_held.get(kind))


async def moving_to(symbol: str) -> None:
    """A socket in front is opening ``symbol``: the lane leaves any other stock now, before the new lines are asked for."""
    global _lanes
    sym = (symbol or "").strip().upper()
    old = stock()
    if not sym or old == sym:
        return
    if old is not None:
        await _let_go(old)
    _lanes, _ = put(_lanes, YOU, sym)
    logger.info("LANES: your lane is on %s%s", sym, f" (was {old})" if old else "")


def hold(symbol: str, kind: str) -> None:
    """The lane's stock has its ``kind`` line up: the lane watches it from now on (once per line)."""
    sym = (symbol or "").strip().upper()
    if stock() != sym or _held.get(kind) or not _up(sym, kind):
        return
    _viewers(kind).ws_viewer_opened(sym)
    _held[kind] = True


async def _let_go(symbol: str) -> None:
    """Drop the lane's references on ``symbol``; a line nothing else watches is cancelled at once."""
    from ibkr import depth, tape_line, tape_stream

    had_tape, had_depth = _held[TAPE], _held[DEPTH]
    _held.update({DEPTH: False, TAPE: False})
    if had_tape and tape_stream.ws_viewer_closed(symbol):
        if not tape_line.release_now(symbol, MOVED_WHY):
            tape_stream.unsubscribe(symbol)
    if had_depth and depth.ws_viewer_closed(symbol):
        await _end_depth(symbol)


async def _end_depth(symbol: str) -> None:
    from ibkr import depth
    from l2 import continuous, recorder

    if depth.viewer_count(symbol) > 0 or recorder.is_recording(symbol):
        return
    try:
        await continuous.stop(symbol)
    except Exception:
        logger.exception("LANES: could not stop the Level 2 snapshots of %s", symbol)
    if depth.viewer_count(symbol) <= 0 and depth.is_subscribed(symbol):
        depth.unsubscribe(symbol)


def _viewers(kind: str):
    from ibkr import depth, tape_stream

    return depth if kind == DEPTH else tape_stream


def _up(symbol: str, kind: str) -> bool:
    from ibkr import depth, tape_stream

    return depth.is_live(symbol) if kind == DEPTH else tape_stream.is_subscribed(symbol)
