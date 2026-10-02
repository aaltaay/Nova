"""Moving a lender's lines to a borrower, and back (ADR 043 decision 6).

The writes the loans make, over ``ibkr.depth``, ``ibkr.tape_stream`` and ``ibkr.tape_line``:

- **releasing** the lender's depth line and its AllLast line once their sockets closed --
  the AllLast line cancelled at once (``tape_line.drop_line``), never after the 16 s
  linger a closed socket leaves it in, because IBKR counts tick-by-tick lines like depth
  lines and the borrower's request must find the room;
- **holding** the borrower's depth line and AllLast line (the line the setup scanner's
  tape feed reads its prints from) with a viewer reference each, counted exactly like a
  Trader tab or a Record hold (``capture.feed_hold``), so no idle eviction takes them;
- **giving them back** at the loan's end: the borrower's references dropped and, when
  nothing else watches them, both lines cancelled at once, so the lender's tab finds
  the room for its own;
- **the borrower's tape**: whether prints arrive on it (``ibkr.tape_recording``), and
  why it is down when IBKR refused or ended it (``ibkr.tape_line.ended``: 10190, the
  tick-by-tick cap, and the rest).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from line_lending.constants_line_lending import (
    LINE_LENDING_RELEASE_POLL_SEC,
    TAPE_RECEIVING,
    TAPE_REFUSED,
    TAPE_WAITING,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Taken:
    """One line asked for: whether the hold took (a viewer reference is held), and why not."""
    held: bool
    error: str | None = None


@dataclass(frozen=True)
class TapeRead:
    """The borrower's AllLast line now (``tape_state``)."""
    state: str                    # receiving | waiting | refused
    error: str | None = None
    last_print: float | None = None
    ibkr_ended: bool = False      # IBKR refused or ended it in its own words (10190, ...)


async def wait_released(symbol: str, timeout: float, *, tape: bool) -> bool:
    """Wait for the lender's sockets to close (they read the lent frame); False on the timeout."""
    from ibkr import depth, tape_stream

    deadline = time.monotonic() + timeout
    while depth.viewer_count(symbol) > 0 or (tape and tape_stream.viewer_count(symbol) > 0):
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(LINE_LENDING_RELEASE_POLL_SEC)
    return True


async def free_depth(symbol: str) -> None:
    """Let the lender's depth line go now (its sockets closed), unless something still wants it."""
    from ibkr import depth
    from l2 import continuous, recorder

    if depth.viewer_count(symbol) > 0 or recorder.is_recording(symbol):
        return
    try:
        await continuous.stop(symbol)
    except Exception:
        logger.exception("line lending: could not stop the L2 snapshots of %s", symbol)
    if depth.viewer_count(symbol) <= 0 and depth.is_subscribed(symbol):
        depth.unsubscribe(symbol)


def free_tape(symbol: str, why: str) -> bool:
    """Cancel the lender's AllLast line now (its sockets closed); False when something still watches it."""
    from ibkr import tape_line, tape_stream

    if tape_stream.viewer_count(symbol) > 0:
        return False
    tape_line.drop_line(symbol, why)
    return True


async def take_depth(symbol: str) -> Taken:
    """Open (or join) the borrower's depth line and hold it."""
    from ibkr import depth

    res = await depth.subscribe_async(symbol, live=True)
    if not res.get("ok") or not depth.is_live(symbol):
        return Taken(False, res.get("error") or f"no Level 2 line opened for {symbol}")
    depth.ws_viewer_opened(symbol)
    return Taken(True)


async def open_tape(symbol: str) -> str | None:
    """Ask IBKR for the borrower's AllLast line when none is up; None when it is up now, else why not."""
    from ibkr import tape_stream

    try:
        if not tape_stream.is_subscribed(symbol):
            got = await tape_stream.subscribe_async(symbol)
            if not got.get("ok"):
                return got.get("error") or f"IBKR refused the tape line for {symbol}"
    except Exception as exc:
        logger.exception("line lending: the tape line for %s failed", symbol)
        return f"{type(exc).__name__}: {exc}"
    return None if tape_stream.is_subscribed(symbol) else f"no tape line for {symbol}"


async def take_tape(symbol: str) -> Taken:
    """Open (or join) the borrower's AllLast line and hold it."""
    from ibkr import tape_stream

    error = await open_tape(symbol)
    if error is not None:
        logger.warning("line lending: %s has no tape line (%s) -- the tape gate reads no prints", symbol, error)
        return Taken(False, error)
    tape_stream.ws_viewer_opened(symbol)
    return Taken(True)


def tape_state(symbol: str, *, held: bool, error: str | None) -> TapeRead:
    """The borrower's AllLast line: ``receiving`` once a print arrived on it, ``waiting`` while it
    is up with none yet, ``refused`` when Nova holds none or IBKR refused or ended it -- the error
    says why. Unreadable is refused, never receiving."""
    from ibkr import tape_line, tape_recording, tape_stream

    try:
        up = held and tape_stream.is_subscribed(symbol)
        producer = tape_recording.producer_status(symbol)
        ended = tape_line.ended(symbol)
    except Exception as exc:
        logger.warning("line lending: %s's tape line could not be read", symbol, exc_info=True)
        return TapeRead(TAPE_REFUSED, f"the tape line could not be read ({type(exc).__name__})")
    last = producer.get("last_print_ts")
    if up:
        return TapeRead(TAPE_RECEIVING if last is not None else TAPE_WAITING, None, last)
    if ended:
        said = f"IBKR ended the tape line (error {ended.get('code')}: {ended.get('message')})"
        return TapeRead(TAPE_REFUSED, said, last, ibkr_ended=True)
    return TapeRead(TAPE_REFUSED, error or (f"no tape line for {symbol}" if not held else "the tape line is gone"),
                    last)


def give_back(symbol: str, *, depth_held: bool, tape_held: bool) -> None:
    """Drop the loan's references; each line is cancelled at once when nothing else watches it."""
    from ibkr import depth, tape_line, tape_stream
    from l2 import recorder

    if tape_held and tape_stream.ws_viewer_closed(symbol):
        tape_line.drop_line(symbol, "the loan of its line ended")
    if depth_held and depth.ws_viewer_closed(symbol) and not recorder.is_recording(symbol):
        depth.unsubscribe(symbol)
