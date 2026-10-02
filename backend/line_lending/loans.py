"""The loans: a hidden Trader tab's Level 2 line lent to a setup Nova may buy (ADR 043 decision 6).

Owner: this module's in-memory loans (keyed by the lender's symbol), the ended ones
kept for the view, and when each lender last came to the front. A restart forgets
them, as it closes every socket; nothing is persisted but the switch (``setting``).

**When.** Each tick (``LINE_LENDING_TICK_SEC``), while lending is on and the focus is
known: a borrower (``borrowers.wanted``: a setup of a strategy at On, on a stock whose
Buy is Nova, armed, near or in a trade, with the bot active) that holds no live line,
when no depth line is free, borrows the line of a Trader tab no visible window shows
(``lines.pick_lender``) -- not one in front within ``LINE_LENDING_FRONT_COOLDOWN_SEC``,
and never one on a stock Nova needs a line on itself. One loan per lender; a lender's
line goes to one borrower.

**How.** The lender's sockets get ``{"type": "lent", ...}`` and close, and do not
reconnect by themselves; a new socket for it from a tab not in front gets the same
frame. Once they closed, its line is let go and the borrower's is opened and held
(``lines.hold_borrower``) -- with auto-record's lock held, so its tick never takes the
line in between. A loan that cannot finish is dropped with the reason
(``last_error``); its tab finds no loan on its next poll and reconnects.

**Ends** (``setup_ended`` | ``trade_ended`` | ``recalled`` | ``lending_off``): the setup
fails or disarms (no longer armed, near or in a trade, or no longer one Nova may buy),
its trade ends (the scanner's scoring window and Nova's own trade on the stock are both
over), the tab comes to the front (a socket opened with ``front=1``, or the focus sensor
shows it), or lending is switched off. The borrower's references are dropped; the
tab reconnects on its poll, or at once when it is brought to the front.

Every start and end is a ``line_loan`` line on the bot audit stream, ``inputs: {lender,
borrower, setup_type, setup_id, end?}``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from line_lending import borrowers as _borrowers
from line_lending import focus as _focus
from line_lending import lines, setting
from line_lending.constants_line_lending import (
    LENDING_OFF_WHY,
    LENT_TEXT,
    LENT_TEXT_NO_WHY,
    LINE_LENDING_AUDIT_ACTION,
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
    SETUP_WORDS,
    WHY_TRADE,
    WHY_WORDS,
)

logger = logging.getLogger(__name__)

_lock: asyncio.Lock | None = None
_loans: dict[str, "Loan"] = {}
_recent: deque[dict[str, Any]] = deque(maxlen=LINE_LENDING_RECENT_KEEP)
_last_front: dict[str, float] = {}   # symbol -> the last moment its tab was in front
_last_error: str | None = None   # the last loan that could not be made (cleared by the next one made)
_read_error: str | None = None   # this tick's unreadable input (the session, the scanner, the focus)


@dataclass
class Loan:
    lender: str
    borrower: str
    setup_type: str
    setup_id: str | None
    why: str
    since: float
    state: str = LOAN_PENDING
    depth_held: bool = False
    tape_held: bool = False
    tape_error: str | None = None
    traded: bool = False

    def text(self) -> str:
        words = WHY_WORDS.get(self.why)
        template = LENT_TEXT if words else LENT_TEXT_NO_WHY
        return template.format(symbol=self.borrower, setup=self.setup_words(), why=words)

    def setup_words(self) -> str:
        return SETUP_WORDS.get(self.setup_type, self.setup_type.replace("_", " "))

    def back(self, why: str) -> str:
        """The sentence a loan that gives the line back ends with."""
        return f"{self.lender}'s Level 2 goes back from {self.borrower}'s {self.setup_words()}: {why}"

    def lost(self) -> str:
        """The sentence a recalled loan ends with: the setup lost its line."""
        return f"{self.borrower}'s {self.setup_words()} lost its Level 2 line: {self.lender} came to the front"

    def lent(self) -> str:
        """The sentence a loan starts with, on the audit stream."""
        words = WHY_WORDS.get(self.why, self.why)
        return f"{self.lender}'s Level 2 lent to {self.borrower}'s {self.setup_words()} ({words})"

    def frame(self) -> dict[str, Any]:
        """What the lender's Level 2 socket sends before it closes."""
        return {"type": "lent", "symbol": self.lender,
                "to": {"symbol": self.borrower, "setup_type": self.setup_type, "setup_id": self.setup_id},
                "why": WHY_WORDS.get(self.why, self.why), "tier": self.why, "since": self.since, "text": self.text()}

    def public(self) -> dict[str, Any]:
        tape, tape_error = lines.tape_state(self.borrower, held=self.tape_held, error=self.tape_error)
        return {"lender": self.lender, "borrower": self.borrower, "setup_type": self.setup_type,
                "setup_id": self.setup_id, "since": self.since, "why": WHY_WORDS.get(self.why, self.why),
                "tier": self.why, "state": self.state, "tape": tape, "tape_error": tape_error, "text": self.text()}


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _note_error(text: str | None) -> None:
    global _last_error
    _last_error = text


def _audit(loan: Loan, outcome: str, reason: str, end: str | None = None) -> None:
    from bot.audit import record

    inputs: dict[str, Any] = {"lender": loan.lender, "borrower": loan.borrower, "setup_type": loan.setup_type,
                              "setup_id": loan.setup_id}
    if end is not None:
        inputs["end"] = end
    try:
        record(action=LINE_LENDING_AUDIT_ACTION, outcome=outcome, reason=reason, inputs=inputs)
    except Exception:
        logger.exception("line lending: the audit line for %s -> %s could not be written", loan.lender, loan.borrower)


# -- what a socket meets ------------------------------------------------------------
def lent_frame(symbol: str) -> dict[str, Any] | None:
    """The lent frame while a loan (pending or standing) names ``symbol`` as its lender."""
    loan = _loans.get(symbol.upper())
    return loan.frame() if loan is not None else None


def lenders() -> list[str]:
    return sorted(_loans)


def loan_lines() -> set[str]:
    """The symbols whose line a standing loan holds."""
    return {loan.borrower for loan in _loans.values() if loan.depth_held}


async def on_socket_open(symbol: str, *, front: bool, now: float | None = None) -> dict[str, Any] | None:
    """A Level 2 socket for ``symbol`` opened: None to go ahead, or the lent frame to send before closing.

    A socket from the tab in front (``front``, or the focus sensor shows the symbol) recalls the loan.
    """
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
    """The lender's tab came to the front: the borrower loses its line. False when no loan stood."""
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
    from ibkr.depth import state as depth_state
    from leaderboard import auto_record

    loan = Loan(lender=lender, borrower=b.symbol, setup_type=b.setup_type, setup_id=b.setup_id, why=b.why,
                since=now, traded=b.why == WHY_TRADE)
    _loans[lender] = loan                       # from here a socket for the lender meets the lent frame
    try:
        depth_state.push_lent(lender, loan.frame())
        if not await lines.wait_released(lender, LINE_LENDING_RELEASE_WAIT_SEC):
            return _drop(loan, f"{lender}'s Level 2 did not close within {LINE_LENDING_RELEASE_WAIT_SEC:.0f} s")
        async with auto_record.lines_lock():    # auto-record's tick never takes the line in between
            await lines.free_line(lender)
            held = await lines.hold_borrower(b.symbol)
        if not held.depth:
            return _drop(loan, f"{b.symbol} got no Level 2 line: {held.error}")
        loan.depth_held, loan.tape_held, loan.tape_error = True, held.tape, held.tape_error
        loan.state = LOAN_ACTIVE
    except Exception as exc:
        logger.exception("line lending: lending %s's Level 2 to %s failed", lender, b.symbol)
        return _drop(loan, f"{type(exc).__name__}: {exc}")
    finally:
        if loan.state == LOAN_PENDING and _loans.get(lender) is loan:
            _loans.pop(lender, None)            # never a pending loan left behind (a cancelled task included)
    _note_error(None)
    _audit(loan, LINE_LENDING_OUTCOME_LENT, loan.lent() + ("" if held.tape else f"; no tape line ({held.tape_error})"))
    logger.info("line lending: %s's Level 2 lent to %s (%s, %s)", lender, b.symbol, b.setup_type, b.why)
    return loan


def _drop(loan: Loan, error: str) -> None:
    """A loan that could not finish: forget it, say why. Its tab finds no loan and reconnects."""
    if _loans.get(loan.lender) is loan:
        _loans.pop(loan.lender, None)
    _note_error(f"Could not lend {loan.lender}'s Level 2 to {loan.borrower}: {error}")
    logger.warning("line lending: %s", _last_error)
    return None


def _end(loan: Loan, end: str, now: float, reason: str) -> None:
    """End a standing loan: the borrower's references go, the tab may take its line back."""
    if _loans.get(loan.lender) is loan:
        _loans.pop(loan.lender, None)
    try:
        lines.release_borrower(loan.borrower, depth_held=loan.depth_held, tape_held=loan.tape_held)
    except Exception:
        logger.exception("line lending: could not let %s's line go -- it may stay open until its next release",
                         loan.borrower)
    loan.depth_held = loan.tape_held = False
    _recent.appendleft({"lender": loan.lender, "borrower": loan.borrower, "setup_type": loan.setup_type,
                        "setup_id": loan.setup_id, "since": loan.since, "ended": now, "end": end, "text": reason})
    _audit(loan, LINE_LENDING_OUTCOME_ENDED, reason, end=end)
    logger.info("line lending: loan of %s's Level 2 to %s ended (%s)", loan.lender, loan.borrower, end)


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
    from ibkr import client, depth

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
                                       auto_symbols=lines.auto_record_symbols(), last_front=_last_front, kept=kept)
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
