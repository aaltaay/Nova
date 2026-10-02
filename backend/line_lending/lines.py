"""Which lines a loan may take: their holders, the free depth lines and the lender (ADR 044 decision 6).

Read-only, over ``ibkr.depth`` and ``ibkr.tape_stream`` (moving a line is ``line_moves``):

- a depth line's **holder**: a replay slot, a loan, auto-record, a Record hold, else a Trader tab;
- the **free** depth lines: ``IBKR_MAX_DEPTH_SYMBOLS`` less the lines a viewer holds. Depth
  only -- a loan records nothing, so the Session Record slots auto-record also counts
  (``auto_record.free_lines``) do not matter here;
- whether a line **may be lent**, and why not: only a live line whose every viewer is a
  Trader tab's socket (``line_lending.sockets``), on a tab the focus sensor knows and does
  not show, and that has not been in front in the last ``LINE_LENDING_FRONT_COOLDOWN_SEC``;
- whether its **AllLast line** goes with it: only while every viewer of that line is a
  Trader tab's Time & Sales socket. IBKR counts tick-by-tick lines like depth lines
  (three here), so a lender that can give both is chosen first.
"""
from __future__ import annotations

import logging

from constants_ibkr import IBKR_MAX_DEPTH_SYMBOLS
from line_lending import sockets
from line_lending.constants_line_lending import (
    HELD_BY_AUTO_RECORD,
    HELD_BY_LOAN,
    HELD_BY_RECORD,
    HELD_BY_REPLAY,
    HELD_BY_TAB,
    LINE_LENDING_FRONT_COOLDOWN_SEC,
)
from line_lending.focus import FocusRead

logger = logging.getLogger(__name__)


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


def tape_lendable(symbol: str) -> bool:
    """The symbol's AllLast line is live and every viewer of it is a Trader tab's Time & Sales."""
    from ibkr import tape_stream

    viewers = tape_stream.viewer_count(symbol)
    return tape_stream.is_subscribed(symbol) and viewers > 0 and sockets.only_tabs(symbol, viewers, sockets.TAPE)


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
                last_front: dict[str, float], kept: frozenset[str] = frozenset(),
                need_tape: bool = False) -> str | None:
    """The lendable line to take: one that can give its AllLast line too when the borrower needs one,
    then the tab the operator looked at least recently (ties: by symbol)."""
    from ibkr import depth

    ok = [s for s in depth.subscribed_symbols()
          if why_not_lend(s, focus=focus, now=now, loan_lines=loan_lines, auto_symbols=auto_symbols,
                          last_front_at=last_front.get(s), kept=kept) is None]
    if not ok:
        return None
    return min(ok, key=lambda s: (need_tape and not tape_lendable(s),
                                  max(focus.last_shown.get(s, 0.0), last_front.get(s, 0.0)), s))
