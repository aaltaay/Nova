"""Moving one Level 2 line from a hidden Trader tab to a borrower, and back (ADR 043 decision 6).

The primitives the loans use, over ``ibkr.depth`` and ``ibkr.tape_stream``:

- a line's **holder**: a replay slot, a loan, auto-record, a Record hold, else a Trader tab;
- the **free** depth lines: ``IBKR_MAX_DEPTH_SYMBOLS`` less the lines a viewer holds. Depth
  only -- a loan records nothing, so the Session Record slots auto-record also counts
  (``auto_record.free_lines``) do not matter here;
- whether a line **may be lent**, and why not: only a live line whose every viewer is a
  Trader tab's socket (``line_lending.sockets``), on a tab the focus sensor knows and does
  not show, and that has not been in front in the last ``LINE_LENDING_FRONT_COOLDOWN_SEC``;
- **releasing** the lender's line once its sockets closed, and **holding** the borrower's
  depth line -- and, best effort, its tape line, which the tape gate reads beside it --
  with a viewer reference, counted exactly like a Trader tab or a Record hold
  (``capture.feed_hold``), so no idle eviction takes it; and dropping those references
  when the loan ends.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from constants_ibkr import IBKR_MAX_DEPTH_SYMBOLS
from line_lending import sockets
from line_lending.constants_line_lending import (
    HELD_BY_AUTO_RECORD,
    HELD_BY_LOAN,
    HELD_BY_RECORD,
    HELD_BY_REPLAY,
    HELD_BY_TAB,
    LINE_LENDING_FRONT_COOLDOWN_SEC,
    LINE_LENDING_RELEASE_POLL_SEC,
)
from line_lending.focus import FocusRead

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Held:
    """What a borrower holds after ``hold_borrower``: its depth line, its tape line, and why not."""
    depth: bool
    tape: bool
    error: str | None = None
    tape_error: str | None = None


def auto_record_symbols() -> set[str]:
    from leaderboard import auto_record

    return set(auto_record.held_symbols())


def record_holds(symbol: str) -> bool:
    """A Session Record (the operator's or auto-record's) or the L2 recorder holds the line."""
    from capture import feed_hold
    from l2 import recorder

    held = feed_hold.held(symbol)
    return bool(held and held.get("depth")) or recorder.is_recording(symbol)


def holder_of(symbol: str, *, loan_lines: set[str], auto_symbols: set[str]) -> str:
    from ibkr import depth

    if not depth.is_live(symbol):
        return HELD_BY_REPLAY
    if symbol in loan_lines:
        return HELD_BY_LOAN
    if symbol in auto_symbols:
        return HELD_BY_AUTO_RECORD
    if record_holds(symbol):
        return HELD_BY_RECORD
    return HELD_BY_TAB


def free_lines() -> int:
    from ibkr import depth

    busy = [s for s in depth.subscribed_symbols() if depth.viewer_count(s) > 0]
    return max(0, IBKR_MAX_DEPTH_SYMBOLS - len(busy))


def why_not_lend(symbol: str, *, focus: FocusRead, now: float, loan_lines: set[str],
                 auto_symbols: set[str], last_front_at: float | None, kept: frozenset[str] = frozenset()) -> str | None:
    """None when ``symbol``'s line may be lent now; else the reason it may not.

    ``last_front_at``: the last moment its tab was in front (a recall, or a tick that saw it there).
    ``kept``: symbols Nova needs a line on itself (a setup that may borrow, a trade Nova holds) --
    lending their line would blind the very setups lending is for.
    """
    from ibkr import depth

    held_by = holder_of(symbol, loan_lines=loan_lines, auto_symbols=auto_symbols)
    if held_by != HELD_BY_TAB:
        return f"held by {held_by.replace('_', '-')}"
    if symbol in kept:
        return "Nova needs this line for its own setup or trade"
    viewers = depth.viewer_count(symbol)
    if viewers <= 0:
        return "no tab holds it (the line is free)"
    if not sockets.only_tabs(symbol, viewers):
        return "a Level 2 outside a Trader tab, or a hold, watches it"
    if not focus.known:
        return "which tab is in front is unknown"
    if symbol not in focus.tabs:
        return "no window lists it as a Trader tab"
    if symbol in focus.front:
        return "its tab is in front"
    last = max(last_front_at or 0.0, sockets.front_seen(symbol) or 0.0)
    if now - last < LINE_LENDING_FRONT_COOLDOWN_SEC:
        return f"its tab was in front {now - last:.0f} s ago"
    return None


def pick_lender(*, focus: FocusRead, now: float, loan_lines: set[str], auto_symbols: set[str],
                last_front: dict[str, float], kept: frozenset[str] = frozenset()) -> str | None:
    """The lendable line whose tab the operator looked at least recently (ties: by symbol)."""
    from ibkr import depth

    ok = [s for s in depth.subscribed_symbols()
          if why_not_lend(s, focus=focus, now=now, loan_lines=loan_lines, auto_symbols=auto_symbols,
                          last_front_at=last_front.get(s), kept=kept) is None]
    if not ok:
        return None
    return min(ok, key=lambda s: (max(focus.last_shown.get(s, 0.0), last_front.get(s, 0.0)), s))


async def wait_released(symbol: str, timeout: float) -> bool:
    """Wait for the lender's sockets to close (they read the lent frame); False on the timeout."""
    from ibkr import depth

    deadline = time.monotonic() + timeout
    while depth.viewer_count(symbol) > 0:
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(LINE_LENDING_RELEASE_POLL_SEC)
    return True


async def free_line(symbol: str) -> None:
    """Let the lender's line go now (its sockets closed), unless something still wants it."""
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


async def hold_borrower(symbol: str) -> Held:
    """Open (or join) the borrower's depth line and hold it; its tape line too, best effort."""
    from ibkr import depth, tape_stream

    res = await depth.subscribe_async(symbol, live=True)
    if not res.get("ok") or not depth.is_live(symbol):
        return Held(depth=False, tape=False, error=res.get("error") or f"no Level 2 line opened for {symbol}")
    depth.ws_viewer_opened(symbol)
    tape_error: str | None = None
    try:
        if not tape_stream.is_subscribed(symbol):
            got = await tape_stream.subscribe_async(symbol)
            if not got.get("ok"):
                tape_error = got.get("error") or f"IBKR refused the tape line for {symbol}"
    except Exception as exc:
        logger.exception("line lending: the tape line for %s failed", symbol)
        tape_error = f"{type(exc).__name__}: {exc}"
    tape = False
    if tape_stream.is_subscribed(symbol):
        tape_stream.ws_viewer_opened(symbol)
        tape = True
    elif tape_error is None:
        tape_error = f"no tape line for {symbol}"
    if not tape:
        logger.warning("line lending: %s holds Level 2 without its tape (%s) -- the tape gate reads no prints",
                       symbol, tape_error)
    return Held(depth=True, tape=tape, tape_error=None if tape else tape_error)


def tape_state(symbol: str, *, held: bool, error: str | None) -> tuple[bool, str | None]:
    """Whether the borrower's tape line lives now, and why not. IBKR can end it after the request
    (error 10190: the tick-by-tick cap), so the flag a loan kept at its start is not enough."""
    from ibkr import tape_line, tape_stream

    try:
        if held and tape_stream.is_subscribed(symbol):
            return True, None
        ended = tape_line.ended(symbol)
    except Exception as exc:
        logger.warning("line lending: %s's tape line could not be read", symbol, exc_info=True)
        return False, f"the tape line could not be read ({type(exc).__name__})"
    if ended:
        return False, f"IBKR ended the tape line (error {ended.get('code')}: {ended.get('message')})"
    return False, error or (f"no tape line for {symbol}" if not held else "the tape line is gone")


def release_borrower(symbol: str, *, depth_held: bool, tape_held: bool) -> None:
    """Drop the loan's references; a line closes only when nothing else watches it."""
    from ibkr import depth, tape_stream
    from l2 import recorder

    if tape_held and tape_stream.ws_viewer_closed(symbol):
        tape_stream.unsubscribe(symbol)  # its linger, then IBKR's cancel if still idle
    if depth_held and depth.ws_viewer_closed(symbol) and not recorder.is_recording(symbol):
        depth.unsubscribe(symbol)
