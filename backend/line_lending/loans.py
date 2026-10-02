"""The loans: a hidden Trader tab's Level 2 and Time & Sales lines lent to a setup Nova may buy (ADR 044 d. 6).

Owner: this module's in-memory loans (keyed by the lender's symbol), the ended ones
kept for the view, and when each lender last came to the front. A restart forgets
them, as it closes every socket; nothing is persisted but the switch (``setting``).

**When.** Each tick (``LINE_LENDING_TICK_SEC``), while lending is on and the focus is
known: a borrower (``borrowers.wanted``: a setup of a strategy at On, on a stock whose
Buy is Nova, armed, near or in a trade, with the bot active) that holds no live line,
when no depth line is free, borrows the lines of a Trader tab no visible window shows
(``lines.pick_lender``) -- not one in front within ``LINE_LENDING_FRONT_COOLDOWN_SEC``,
and never one on a stock Nova needs a line on itself. One loan per lender; a lender's
lines go to one borrower.

**How.** The lender's Level 2 sockets -- and its Time & Sales sockets, when every viewer
of its AllLast line is one (``lines.tape_lendable``): IBKR counts tick-by-tick lines like
depth lines, so without it the borrower's tape is refused at the cap -- get ``{"type":
"lent", ...}`` and close, and do not reconnect by themselves; a new socket for it from a
tab not in front gets the same frame. Once they closed, both lines are let go at once
and the borrower's two are opened and held (``line_moves``) -- with auto-record's lock
held, so its tick never takes a line in between. A loan that cannot finish is dropped
with the reason (``last_error``); its tab finds no loan on its next poll and reconnects.
The borrower's AllLast line is watched for as long as the loan stands (``loan_tape``).

**Ends** (``setup_ended`` | ``trade_ended`` | ``recalled`` | ``lending_off``): the setup
fails or disarms (no longer armed, near or in a trade, or no longer one Nova may buy),
its trade ends (the scanner's scoring window and Nova's own trade on the stock are both
over), the tab comes to the front (a socket opened with ``front=1``, or the focus sensor
shows it), or lending is switched off. Both lines go back in one step: the borrower's
references are dropped and its lines cancelled at once; the tab reconnects on its poll,
or at once when it is brought to the front.

Every start and end is a ``line_loan`` line on the bot audit stream, ``inputs: {lender,
borrower, setup_type, setup_id, tape_lent?, tape_error?, end?}`` (``loan.audit``).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

from line_lending import borrowers as _borrowers
from line_lending import focus as _focus
from line_lending import line_moves, lines, loan_tape, setting
from line_lending.constants_line_lending import (
    LENDING_OFF_WHY,
    LINE_LENDING_OUTCOME_ENDED,
    LINE_LENDING_OUTCOME_LENT,
    LINE_LENDING_RECENT_KEEP,
    LINE_LENDING_RELEASE_WAIT_SEC,
    LINE_LENDING_TICK_SEC,
    LOAN_ACTIVE,
    LOAN_END_OFF,
    LOAN_END_RECALLED,
    LOAN_END_SETUP,
    LOAN_END_TRADE,
    LOAN_PENDING,
    WHY_TRADE,
)
from line_lending.loan import Loan, audit

logger = logging.getLogger(__name__)

_lock: asyncio.Lock | None = None
_loans: dict[str, Loan] = {}
_recent: deque[dict[str, Any]] = deque(maxlen=LINE_LENDING_RECENT_KEEP)
_last_front: dict[str, float] = {}   # symbol -> the last moment its tab was in front
_last_error: str | None = None   # the last loan that could not be made (cleared by the next one made)
_read_error: str | None = None   # this tick's unreadable input (the session, the scanner, the focus)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _note_error(text: str | None) -> None:
    global _last_error
    _last_error = text


# -- what a socket meets ------------------------------------------------------------
def lent_frame(symbol: str) -> dict[str, Any] | None:
    """The lent frame while a loan (pending or standing) names ``symbol`` as its lender."""
    loan = _loans.get(symbol.upper())
    return loan.frame() if loan is not None else None


def lenders() -> list[str]:
    return sorted(_loans)


def loan_lines() -> set[str]:
    """The symbols whose depth line a standing loan holds."""
    return {loan.borrower for loan in _loans.values() if loan.depth_held}


async def on_socket_open(symbol: str, *, front: bool, now: float | None = None) -> dict[str, Any] | None:
    """A Level 2 or Time & Sales socket for ``symbol`` opened: None to go ahead, or the lent frame
    to send before closing. A socket from the tab in front (``front``, or the focus sensor shows the
    symbol) recalls the loan -- both lines -- first."""
    from line_lending import sockets

    ts = time.time() if now is None else float(now)
    sym = symbol.upper()
    if front:
        sockets.seen_in_front(sym, ts)
    loan = _loans.get(sym)
    if loan is None:
        return None
    if front or _focus.read(ts).is_front(sym):
        await recall(sym, now=ts)
        return None
    return loan.frame()


async def recall(lender: str, *, now: float | None = None) -> bool:
    """The lender's tab came to the front: the borrower loses its lines. False when no loan stood."""
    ts = time.time() if now is None else float(now)
    sym = lender.upper()
    async with _get_lock():
        loan = _loans.get(sym)
        if loan is None:
            return False
        _last_front[sym] = ts
        _end(loan, LOAN_END_RECALLED, ts, loan.lost())
        return True


# -- start and end ----------------------------------------------------------------------
async def _lend(lender: str, b: _borrowers.Borrower, now: float) -> Loan | None:
    from ibkr import tape_stream
    from ibkr.depth import state as depth_state
    from leaderboard import auto_record

    loan = Loan(lender=lender, borrower=b.symbol, setup_type=b.setup_type, setup_id=b.setup_id, why=b.why,
                since=now, traded=b.why == WHY_TRADE)
    _loans[lender] = loan                       # from here a socket for the lender meets the lent frame
    try:
        # The tape goes with the book unless the borrower already has a tape line, or the lender's is not only its tab's.
        loan.tape_lent = lines.tape_lendable(lender) and not tape_stream.is_subscribed(b.symbol)
        frame = loan.frame()
        depth_state.push_lent(lender, frame)
        if loan.tape_lent:
            tape_stream.push_lent(lender, frame)
        if not await line_moves.wait_released(lender, LINE_LENDING_RELEASE_WAIT_SEC, tape=loan.tape_lent):
            return _drop(loan, f"{lender}'s {loan.lines_words()} did not close within "
                               f"{LINE_LENDING_RELEASE_WAIT_SEC:.0f} s")
        async with auto_record.lines_lock():    # auto-record's tick never takes a line in between
            await line_moves.free_depth(lender)
            if loan.tape_lent and not line_moves.free_tape(lender, f"lent to {b.symbol}'s {loan.setup_words()}"):
                loan.tape_lent = False          # a viewer came back to it: it stays
            depth = await line_moves.take_depth(b.symbol)
            loan.depth_held = depth.held
            if not depth.held:
                return _drop(loan, f"{b.symbol} got no Level 2 line: {depth.error}")
            tape = await line_moves.take_tape(b.symbol)
            loan.tape_held, loan.tape_error = tape.held, tape.error
        loan.tape_said, loan.tape_asked_at = not tape.held, now
        loan.state = LOAN_ACTIVE
    except Exception as exc:
        logger.exception("line lending: lending %s's lines to %s failed", lender, b.symbol)
        return _drop(loan, f"{type(exc).__name__}: {exc}")
    finally:
        if loan.state == LOAN_PENDING and _loans.get(lender) is loan:
            _loans.pop(lender, None)            # never a pending loan left behind (a cancelled task included)
    _note_error(None)
    extra: dict[str, Any] = {"tape_lent": loan.tape_lent}
    reason = loan.lent()
    if not loan.tape_held:
        extra["tape_error"] = loan.tape_error
        reason += f"; {b.symbol} has no Time & Sales line: {loan.tape_error}"
    audit(loan, LINE_LENDING_OUTCOME_LENT, reason, **extra)
    logger.info("line lending: %s's %s lent to %s (%s, %s)", lender, loan.lines_words(), b.symbol, b.setup_type, b.why)
    return loan


def _drop(loan: Loan, error: str) -> None:
    """A loan that could not finish: forget it, give back what it took, say why. Its tab finds no
    loan on its next poll and reconnects."""
    if _loans.get(loan.lender) is loan:
        _loans.pop(loan.lender, None)
    if loan.depth_held or loan.tape_held:
        try:
            line_moves.give_back(loan.borrower, depth_held=loan.depth_held, tape_held=loan.tape_held)
        except Exception:
            logger.exception("line lending: could not let %s's lines go after a failed loan", loan.borrower)
        loan.depth_held = loan.tape_held = False
    _note_error(f"Could not lend {loan.lender}'s {loan.lines_words()} to {loan.borrower}: {error}")
    logger.warning("line lending: %s", _last_error)
    return None


def _end(loan: Loan, end: str, now: float, reason: str) -> None:
    """End a standing loan: both of the borrower's lines go back at once, the tab may take its own back."""
    if _loans.get(loan.lender) is loan:
        _loans.pop(loan.lender, None)
    try:
        line_moves.give_back(loan.borrower, depth_held=loan.depth_held, tape_held=loan.tape_held)
    except Exception:
        logger.exception("line lending: could not let %s's lines go -- they may stay open until their next release",
                         loan.borrower)
    loan.depth_held = loan.tape_held = False
    _recent.appendleft({"lender": loan.lender, "borrower": loan.borrower, "setup_type": loan.setup_type,
                        "setup_id": loan.setup_id, "since": loan.since, "ended": now, "end": end, "text": reason,
                        "tape_lent": loan.tape_lent})
    audit(loan, LINE_LENDING_OUTCOME_ENDED, reason, end=end, tape_lent=loan.tape_lent)
    logger.info("line lending: loan of %s's %s to %s ended (%s)", loan.lender, loan.lines_words(), loan.borrower, end)


async def end_all(end: str, why: str, now: float | None = None) -> int:
    """End every loan (lending switched off); how many ended."""
    ts = time.time() if now is None else float(now)
    async with _get_lock():
        standing = [loan for loan in _loans.values() if loan.state == LOAN_ACTIVE]
        for loan in standing:
            _end(loan, end, ts, loan.back(why))
        return len(standing)


# -- the tick ------------------------------------------------------------------------------
def _judge(loan: Loan, wanted: _borrowers.Wanted, focus: _focus.FocusRead, now: float) -> tuple[str, str] | None:
    """``(end, reason)`` when a standing loan ends now, else None (and its reason is brought up to date)."""
    if focus.is_front(loan.lender):
        _last_front[loan.lender] = now
        return LOAN_END_RECALLED, loan.lost()
    b = wanted.get(loan.borrower) if wanted.error is None else None
    if b is not None:
        loan.why = b.why
        loan.traded = loan.traded or b.why == WHY_TRADE
    if _borrowers.nova_trade(loan.borrower):
        loan.traded = True
        return None
    if b is not None or wanted.error is not None:
        return None                              # still wanted, or unknown: a failed read never ends a loan
    if loan.traded:
        return LOAN_END_TRADE, loan.back("its trade ended")
    return LOAN_END_SETUP, loan.back(wanted.why_gone(loan.borrower, loan.setup_type))


async def tick(now: float | None = None) -> None:
    from ibkr import client, depth, tape_stream

    ts = time.time() if now is None else float(now)
    on, setting_error = setting.is_on()
    if not on:
        if setting_error is None:                # switched off; an unreadable switch ends nothing (the view says why)
            await end_all(LOAN_END_OFF, LENDING_OFF_WHY, ts)
        return
    global _read_error
    async with _get_lock():
        focus = _focus.read(ts)
        for sym in focus.front:                  # a tab the operator just left is not lent at once either
            _last_front[sym] = ts
        wanted = _borrowers.wanted(ts)
        for loan in [x for x in _loans.values() if x.state == LOAN_ACTIVE]:
            verdict = _judge(loan, wanted, focus, ts)
            if verdict is not None:
                _end(loan, verdict[0], ts, verdict[1])
            elif client.is_ready():
                await loan_tape.watch(loan, ts)
        _read_error = wanted.error or focus.error
        if _read_error is not None:
            return
        if not focus.known or not client.is_ready():
            return
        taken = {x.borrower for x in _loans.values()}
        kept: frozenset[str] | None = None
        for b in wanted.borrowers:
            if b.symbol in taken or depth.is_live(b.symbol):
                continue
            if lines.free_lines() > 0:
                break                            # a line is free: no tab loses its line for nothing
            if kept is None:                     # a tab on a stock Nova itself needs never lends
                kept = frozenset({x.symbol for x in wanted.borrowers}
                                 | {s for s in depth.subscribed_symbols() if _borrowers.nova_trade(s)})
            lender = lines.pick_lender(focus=focus, now=ts, loan_lines=loan_lines(),
                                       auto_symbols=lines.auto_record_symbols(), last_front=_last_front, kept=kept,
                                       need_tape=not tape_stream.is_subscribed(b.symbol))
            if lender is None:
                break
            if await _lend(lender, b, ts) is not None:
                taken.add(b.symbol)


async def run() -> None:
    """Background task entry (``app_runtime_tasks``)."""
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _note_error(f"{type(exc).__name__}: {exc}")
            logger.exception("line lending: tick failed")
        await asyncio.sleep(LINE_LENDING_TICK_SEC)


# -- what the lines view reads ---------------------------------------------------------------
def view() -> dict[str, Any]:
    on, setting_error = setting.is_on()
    return {"on": on, "loans": [loan.public() for loan in sorted(_loans.values(), key=lambda x: x.since)],
            "recent": [dict(row) for row in _recent], "error": setting_error or _read_error or _last_error}


def reset_for_tests() -> None:
    global _lock, _last_error, _read_error
    _loans.clear()
    _recent.clear()
    _last_front.clear()
    _lock = None
    _last_error = None
    _read_error = None
