"""A hidden Trader tab's lines lent to Claude's seat (ADR 068 decision 14, operator 2026-10-27).

When all 3 Level 2 lines are held and no auto-record line can be given up (``agent_trader.room``), the seat
takes the lines of a Trader tab the operator is not looking at, picked by the rule a bot loan uses
(``lines.pick_lender``: hidden, not in front in the last ``LINE_LENDING_FRONT_COOLDOWN_SEC``, the tab looked at
least recently, one that can give its Time & Sales too first). The tab's sockets read the lent frame and close,
both its lines are let go at once (``line_moves``), and the seat takes the free line itself (``take``) -- under
auto-record's lock, so no tick takes it in between. The loan holds no line: the seat's own references do.

Unlike a bot loan, **the front never ends it** (the operator: "the point is not to disturb Claude while it learns
from level 2"): a socket from the tab in front meets the lent frame too. It ends when

- the operator right-clicks the tab, Take my Level 2 back from Claude (``taken_back``);
- Claude's seat lets its line go -- off, given up, gone quiet, its day's end (``claude_let_go``);
- no window lists the tab any more (``tab_closed``): there is nothing to give back.

Lending's switch neither makes nor ends it: that switch is the bots'. Every start and end is a ``line_loan`` line
on the bot audit stream, as a bot loan's.
"""
from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from line_lending import focus as _focus
from line_lending import line_moves, lines, loans
from line_lending.constants_line_lending import (
    BORROWER_CLAUDE,
    LINE_LENDING_OUTCOME_LENT,
    LINE_LENDING_RELEASE_WAIT_SEC,
    LOAN_ACTIVE,
    LOAN_PENDING,
)
from line_lending.loan import Loan, audit

logger = logging.getLogger(__name__)

# Claude's seat takes the freed line: None when it holds it, else why not (``agent_trader.lines.acquire``).
Take = Callable[[], Awaitable[str | None]]


def lender_for(symbol: str, *, skip: set[str], now: float | None = None) -> str | None:
    """The hidden tab whose lines Claude's ``symbol`` may take now, by a bot loan's rule; None when none may.

    ``skip``: tabs the operator took back from Claude (not taken again while they are open). A stock a bot's
    setup or Nova's own trade needs is never taken, as for a bot loan."""
    from ibkr import depth, tape_stream
    from line_lending import borrowers

    ts = time.time() if now is None else float(now)
    focus = _focus.read(ts)
    if not focus.known:
        return None
    wanted = borrowers.wanted(ts)
    if wanted.error is not None:
        return None                              # unreadable: never guess which tab Nova needs
    kept = frozenset({b.symbol for b in wanted.borrowers}
                     | {s for s in depth.subscribed_symbols() if borrowers.nova_trade(s)}
                     | {s.upper() for s in skip})
    return lines.pick_lender(focus=focus, now=ts, loan_lines=loans.loan_lines(),
                             auto_symbols=lines.auto_record_symbols(), last_front=loans.last_front(), kept=kept,
                             need_tape=not tape_stream.is_subscribed(symbol))


async def lend(lender: str, symbol: str, tier: str, take: Take, now: float | None = None) -> Loan | None:
    """Lend ``lender``'s tab lines to Claude's ``symbol``: the tab's sockets close, its lines go, the seat takes
    the free one (``take``). The loan, or None when it could not finish (the reason is on the lines view)."""
    from ibkr import tape_stream
    from ibkr.depth import state as depth_state
    from leaderboard import auto_record

    ts = time.time() if now is None else float(now)
    lender, symbol = lender.upper(), symbol.upper()
    async with loans.lock():
        if loans.get(lender) is not None or loans.claude_loan() is not None:
            return None
        loan = Loan(lender=lender, borrower=symbol, setup_type=BORROWER_CLAUDE, setup_id=None, why=tier, since=ts)
        loans.put(loan)
        try:
            loan.tape_lent = lines.tape_lendable(lender) and not tape_stream.is_subscribed(symbol)
            frame = loan.frame()
            depth_state.push_lent(lender, frame)
            if loan.tape_lent:
                tape_stream.push_lent(lender, frame)
            if not await line_moves.wait_released(lender, LINE_LENDING_RELEASE_WAIT_SEC, tape=loan.tape_lent):
                loans.drop(loan, f"{lender}'s {loan.lines_words()} did not close within "
                                 f"{LINE_LENDING_RELEASE_WAIT_SEC:.0f} s")
                return None
            async with auto_record.lines_lock():    # auto-record's tick never takes the line in between
                await line_moves.free_depth(lender)
                if loan.tape_lent and not line_moves.free_tape(lender, "lent to Claude"):
                    loan.tape_lent = False          # a viewer came back to it: it stays
                why = await take()
            if why is not None:
                loans.drop(loan, f"Claude got no Level 2 line on {symbol}: {why}")
                return None
            loan.state = LOAN_ACTIVE
        except Exception as exc:
            logger.exception("line lending: lending %s's lines to Claude failed", lender)
            loans.drop(loan, f"{type(exc).__name__}: {exc}")
            return None
        finally:
            if loan.state == LOAN_PENDING and loans.get(lender) is loan:
                loans.drop(loan, "the loan to Claude did not finish")
    audit(loan, LINE_LENDING_OUTCOME_LENT, loan.lent(), tape_lent=loan.tape_lent)
    logger.info("line lending: %s's %s lent to Claude's %s", lender, loan.lines_words(), symbol)
    return loan


async def end(end_kind: str, why: str, now: float | None = None) -> Loan | None:
    """End the loan to Claude, if one stands: its tab may take its lines back. The loan ended, or None."""
    async with loans.lock():
        loan = loans.claude_loan()
        if loan is None or loan.state != LOAN_ACTIVE:
            return None
        loans.end(loan, end_kind, loan.back(why), now)
        return loan


def follow(symbol: str | None, tier: str) -> None:
    """The seat's stock and what it does there, on the standing loan's words (the lines poll reads them). An empty
    ``tier`` (Paper could not be read) keeps the words as they were."""
    loan = loans.claude_loan()
    if loan is None or loan.state != LOAN_ACTIVE:
        return
    if symbol:
        loan.borrower = symbol.upper()
    if tier:
        loan.why = tier
