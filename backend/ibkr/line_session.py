"""A tape or depth line belongs to the IBKR session that opened it (#562).

A reconnect builds a new session -- a new ``IB()``, or the same one after
ib_async's disconnect wiped its subscription registry -- and every
tick-by-tick and Level 2 request of the old one dies with it; IBKR does not
bring them back. Nova's line maps (``tape_stream._tickers``, the depth state)
used to outlive the session, so ``is_subscribed`` said yes, a viewer or a
Record re-acquire joined the dead entry, and nothing asked IBKR again.

Every line is stamped with the session generation it was requested on
(``ibkr.client.current_generation``, bumped at every READY). A line from
another generation is stale: it no longer counts as subscribed or live
(checked lazily, so no reader depends on the hook below), and ``settle`` lets
it go and asks again for the ones a viewer or a hold still watches -- their
queues stay registered, so the new line feeds them. ``on_session_ready`` runs
``settle`` on the HTTP loop at every READY; a subscribe that meets a stale
line runs it too.

How a stale line is let go depends on what happened to its session
(``fate``):

* ``gone`` -- the socket dropped: the IB in hand does not hold the line. It is
  forgotten; nothing is cancelled (the old IB is gone and the new one never
  heard of it), and IB's 15 s tape rule does not start.
* ``kept`` -- the same socket, IBKR restored connectivity with its data kept
  (1102): the line lives and is restamped.
* ``lost`` -- the same socket, restored with data lost (1101): IBKR forgot the
  line but ib_async still holds it and would hand it back instead of asking,
  so it is cancelled on this (current) session first.

Level 1 lines follow the same ``fate`` at READY (``ibkr/ticks_session.py``,
#565); their owners ask again themselves, so nothing here renews them.

Asking again is bounded (IBKR_LINE_RENEW_BACKOFF_SEC). When it keeps failing
the viewers are told -- a released tape / evicted depth message closes their
sockets, which ask again themselves -- and a recording's keepalive takes it
from there (its producer reads ``disconnected``).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from constants import IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT, IBKR_LINE_RENEW_BACKOFF_SEC

logger = logging.getLogger(__name__)

GONE = "gone"
KEPT = "kept"
LOST = "lost"

TAPE = "tape"
DEPTH = "depth"

# (kind, symbol) -> the task asking IBKR again for that line.
_renewing: dict[tuple[str, str], asyncio.Task] = {}


def reset_for_tests() -> None:
    for task in list(_renewing.values()):
        if not task.done():
            task.cancel()
    _renewing.clear()


def generation() -> int:
    from ibkr import client

    return client.current_generation()


def is_stale(stamp: int | None) -> bool:
    """A line stamped on another session than the current one. Unstamped: not an IBKR line."""
    return stamp is not None and stamp != generation()


def fate(ib: Any, contract: Any, kind: str, ticker: Any) -> str:
    """What became of a stale line: ``gone``, ``kept`` or ``lost`` (module docstring)."""
    registry = getattr(getattr(ib, "wrapper", None), "subscriptions", None)
    find = getattr(registry, "find_market_data", None)
    con_id = getattr(contract, "conId", None)
    if find is None or not con_id or ticker is None:
        return GONE
    try:
        sub = find(con_id, kind)
    except Exception:
        logger.warning("IBKR: could not read ib_async's %s line for conId %s; taking it as gone",
                       kind, con_id, exc_info=True)
        return GONE
    if sub is None or getattr(sub, "ticker", None) is not ticker:
        return GONE  # this IB never requested it (a new session), or holds another request
    from ibkr import session_errors

    kept = session_errors.last_connectivity_code() == IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT
    return KEPT if kept else LOST


def on_session_ready(gen: int) -> None:
    """Every READY (IB loop): let the HTTP loop, where the viewers' queues live, settle. Never blocks."""
    from ibkr import loop_supervisor

    logger.info("IBKR: session generation %s -- settling the tape and depth lines of the last one", gen)
    loop_supervisor.publish_to_http(settle)


def settle() -> None:
    """Let go of every line of an ended session; ask again for those still watched. Idempotent."""
    from ibkr import depth, tape_line

    for kind, drop in ((TAPE, tape_line.drop_stale), (DEPTH, depth.drop_stale)):
        try:
            watched = drop()
        except Exception:
            logger.exception("IBKR %s: could not let go of the lines of the last IBKR session", kind)
            continue
        for symbol in watched:
            _spawn(kind, symbol)


def renewing(kind: str, symbol: str) -> bool:
    task = _renewing.get((kind, symbol.upper()))
    return task is not None and not task.done()


def _spawn(kind: str, symbol: str) -> None:
    if renewing(kind, symbol):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("IBKR %s: no loop to ask again for %s on; its viewers ask when they reconnect", kind, symbol)
        return
    _renewing[(kind, symbol.upper())] = loop.create_task(_renew(kind, symbol), name=f"ibkr.renew.{kind}.{symbol}")


@dataclass(frozen=True)
class _Lane:
    watched: Callable[[str], bool]                 # a viewer or a hold still wants the line
    live: Callable[[str], bool]                    # a line of this session is up (someone asked first)
    wait: Callable[[str], float]                   # IB's own rule before another request
    ask: Callable[[str], Awaitable[dict]]          # subscribe; {"ok", "error"}
    gave_up: Callable[[str, str], None]            # tell the viewers


def _lane(kind: str) -> _Lane:
    if kind == TAPE:
        from ibkr import tape_stream

        def tape_gave_up(symbol: str, message: str) -> None:
            tape_stream._push_queue(symbol, {"type": "error", "symbol": symbol, "message": message, "released": True})

        return _Lane(lambda s: tape_stream.viewer_count(s) > 0, tape_stream.is_subscribed,
                     tape_stream.guard_remaining, tape_stream.subscribe_async, tape_gave_up)
    from ibkr import depth
    from ibkr.depth import state as depth_state

    def depth_gave_up(symbol: str, message: str) -> None:
        depth_state.push_error(symbol, message, evicted=True)

    return _Lane(depth.is_watched, depth.is_live, lambda _s: 0.0,
                 lambda s: depth.subscribe_async(s, live=True), depth_gave_up)


async def _renew(kind: str, symbol: str) -> None:
    """Ask IBKR again for one line on the new session, bounded; tell its viewers when it will not come."""
    lane = _lane(kind)
    error = "no attempt was made"
    try:
        for attempt, delay in enumerate(IBKR_LINE_RENEW_BACKOFF_SEC, start=1):
            await asyncio.sleep(max(float(delay), lane.wait(symbol)))
            if not lane.watched(symbol) or lane.live(symbol):
                return  # nobody watches any more, or a viewer / the keepalive asked first
            result = await lane.ask(symbol)
            if result.get("ok"):
                logger.warning("IBKR %s: asked again for %s's line on the new IBKR session", kind, symbol)
                return
            error = result.get("error") or "IBKR gave no reason"
            logger.warning("IBKR %s: asking again for %s on the new IBKR session failed (%d/%d): %s",
                           kind, symbol, attempt, len(IBKR_LINE_RENEW_BACKOFF_SEC), error)
        message = f"The IBKR session this {kind} line was on ended; asking again failed: {error}"
        logger.error("IBKR %s: giving up on %s's line -- %s", kind, symbol, message)
        lane.gave_up(symbol, message)
    finally:
        if _renewing.get((kind, symbol.upper())) is asyncio.current_task():
            _renewing.pop((kind, symbol.upper()), None)
