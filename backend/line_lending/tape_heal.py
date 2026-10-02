"""A Time & Sales socket never sits on a dead line: IBKR's refusal is answered, not shown forever (#698).

2026-10-02 07:54 ET: IBKR refused AMOD's AllLast line with 10190, its tick-by-tick cap, while three
recordings and a resume that never gave its line back held the lines. The socket stayed open on a
dead line and said so, and nothing asked again until the operator switched tabs at 07:55:50.

While a Time & Sales socket watches a symbol whose AllLast line is down (IBKR refused or ended it),
one task per symbol brings it back:

- after a cap refusal (``LINE_LENDING_TAPE_CAP_CODES``) it makes room first, once per refusal:
  every line no viewer watches is cancelled now, not after its 16 s remount linger; failing that,
  for the tab in front (or a panel outside a Trader tab), auto-record gives back its lowest-ranked
  line (``auto_record.make_room_for``). A recording the operator started is never touched;
- it waits out IBKR's 15 s same-instrument rule, plus ``LINE_LENDING_TAPE_HEAL_BACKOFF_SEC`` after
  refusals in a row, then asks again -- at once when a hidden tab comes to the front; while IBKR is
  not ready it waits without counting a try. It never stops while a socket watches;
- it tells the socket what it is doing: an ``error`` frame with the reason, what it freed or who
  holds the lines, and ``retry_at``; ``subscribed`` once the new line stood
  ``LINE_LENDING_TAPE_HEAL_CONFIRM_SEC`` without IBKR ending it.

A recording's own line is the keepalive's (``capture.tape_watch``); a loan's is ``loan_tape``'s.
A replay desk opens no line, so nothing is asked there.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from line_lending import sockets
from line_lending.constants_line_lending import (
    LINE_LENDING_TAPE_CAP_CODES,
    LINE_LENDING_TAPE_HEAL_BACKOFF_SEC,
    LINE_LENDING_TAPE_HEAL_CONFIRM_SEC,
    LINE_LENDING_TAPE_HEAL_POLL_SEC,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

_tasks: dict[str, asyncio.Task] = {}


def reset_for_tests() -> None:
    for task in list(_tasks.values()):
        if not task.done():
            task.cancel()
    _tasks.clear()


def healing(symbol: str) -> bool:
    task = _tasks.get(symbol.upper())
    return task is not None and not task.done()


def watched(symbol: str) -> bool:
    return sockets.count(symbol, sockets.TAPE) > 0


def line_down(symbol: str) -> None:
    """A socket found its line down (IBKR's error, or a heartbeat): bring it back unless already."""
    sym = symbol.upper()
    if healing(sym) or not watched(sym) or not _down(sym):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # maintainer: allow-swallow no loop means no socket to heal for
        return
    _tasks[sym] = loop.create_task(_heal(sym))


def _down(sym: str) -> bool:
    from ibkr import tape_stream
    from sim.mode import is_replay_desk

    return not is_replay_desk() and not tape_stream.is_subscribed(sym)


def _in_front(sym: str) -> bool:
    """The operator is looking at this Time & Sales: the focus sensor's word, else the socket's own."""
    from line_lending import focus

    front = focus.read().is_front(sym)
    return front if front is not None else sockets.opened_in_front(sym, sockets.TAPE)


def _cap_refusal(sym: str) -> float | None:
    """When IBKR last refused this symbol's line for its tick-by-tick cap, else None."""
    from ibkr import tape_line

    ended = tape_line.ended(sym) or {}
    return ended.get("at") if ended.get("code") in LINE_LENDING_TAPE_CAP_CODES else None


def _holders(sym: str) -> str:
    """Who holds the other AllLast lines, in words."""
    from capture import feed_hold
    from ibkr import tape_stream
    from leaderboard import auto_record

    auto = set(auto_record.held_symbols())
    words = []
    for other in sorted(s for s in tape_stream._tickers if s != sym):
        if other in auto:
            words.append(f"{other} (auto-record)")
        elif feed_hold.held(other):
            words.append(f"{other} (your recording)")
        elif sockets.count(other, sockets.TAPE):
            words.append(f"{other} (a Trader tab)")
        else:
            words.append(other)
    return ", ".join(words) or "nothing Nova holds"


async def _make_room(sym: str) -> str | None:
    """Free one line for ``sym`` after a cap refusal; what was freed, in words, or None."""
    from ibkr import tape_line

    idle = tape_line.release_idle(keep=sym, why=f"{sym}'s Time & Sales needs IBKR's room")
    if idle:
        return f"cancelled the idle line of {', '.join(idle)}"
    if not _in_front(sym):
        return None
    try:
        from leaderboard import auto_record

        victim = await auto_record.make_room_for(sym, tape_refused=True)
    except Exception:
        logger.exception("IBKR tape: auto-record could not give a line back for %s", sym)
        return None
    return f"auto-record gave back {victim}'s recording line" if victim else None


def _say(sym: str, message: str, retry_at: float) -> None:
    from ibkr import tape_stream

    tape_stream._push_queue(sym, {"type": "error", "symbol": sym, "message": message,
                                  "retry_at": retry_at, "healing": True})


def _words(sym: str, *, capped: bool, freed: str | None, error: str | None, retry_at: float) -> str:
    when = datetime.fromtimestamp(retry_at, ET).strftime("%H:%M:%S")
    if capped:
        head = "IBKR refused this Time & Sales: every tick-by-tick line is in use (IB error 10190)"
        tail = f"; {freed}" if freed else f"; held by {_holders(sym)} -- stop a recording or close a tab to free one"
        return f"{head}{tail}. Asking again at {when} ET."
    return f"{error or 'IBKR ended this Time & Sales line'}. Asking again at {when} ET."


async def _wait(sym: str, seconds: float, *, guard_until: float) -> bool:
    """Sleep while a socket watches; early once a hidden tab comes to the front past the guard.
    False when no socket watches any more."""
    end = time.time() + seconds
    was_front = _in_front(sym)
    while time.time() < end:
        await asyncio.sleep(min(LINE_LENDING_TAPE_HEAL_POLL_SEC, max(0.0, end - time.time())))
        if not watched(sym):
            return False
        if not was_front and time.time() >= guard_until and _in_front(sym):
            return True
    return watched(sym)


async def _heal(sym: str) -> None:
    from ibkr import client, tape_line, tape_stream

    tries, room_for, error = 0, None, None
    try:
        while watched(sym) and _down(sym):
            refused_at = _cap_refusal(sym)
            freed = None
            if refused_at is not None and refused_at != room_for:
                room_for = refused_at
                freed = await _make_room(sym)
            guard = tape_stream.guard_remaining(sym)
            backoff = LINE_LENDING_TAPE_HEAL_BACKOFF_SEC[min(tries, len(LINE_LENDING_TAPE_HEAL_BACKOFF_SEC) - 1)]
            wait = guard + backoff
            retry_at = time.time() + wait
            ended = tape_line.ended(sym) or {}
            _say(sym, _words(sym, capped=refused_at is not None, freed=freed,
                             error=error or ended.get("message"), retry_at=retry_at), retry_at)
            if not await _wait(sym, wait, guard_until=time.time() + guard):
                return
            if not _down(sym):
                break                           # another socket or a hold brought it back
            if not client.is_ready():
                await asyncio.sleep(LINE_LENDING_TAPE_HEAL_POLL_SEC)
                continue                        # IBKR is down: not a try
            tries += 1
            result = await tape_stream.subscribe_async(sym)
            if not result.get("ok"):
                error = result.get("error")
                continue
            error = None
            if not await _wait(sym, LINE_LENDING_TAPE_HEAL_CONFIRM_SEC, guard_until=float("inf")):
                return
        if watched(sym) and not _down(sym):
            tape_stream._push_queue(sym, {"type": "subscribed", "symbol": sym})
            if tries:
                logger.warning("IBKR tape: %s's Time & Sales line is back (asked %d time%s)",
                               sym, tries, "" if tries == 1 else "s")
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("IBKR tape: bringing %s's Time & Sales line back failed", sym)
    finally:
        if _tasks.get(sym) is asyncio.current_task():
            _tasks.pop(sym, None)
