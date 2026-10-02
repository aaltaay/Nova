"""A standing loan's AllLast line: said when it is down, asked for again (ADR 043 decision 6).

Seeing the tape at the trigger is the point of a loan, so the borrower's AllLast line
is never down in silence. Each tick, for every standing loan while IBKR is ready:

- a line IBKR refused or ended (10190, the tick-by-tick cap, and the rest) -- or one
  down ``LINE_LENDING_TAPE_SAY_AFTER_SEC`` without IBKR's word -- is a ``line_loan``
  line ``tape_refused`` with ``inputs.tape_error``, once per refusal, and
  ``loans[].tape_error`` on the lines view. The wait keeps a reconnect, which asks for
  every held line again, from reading as a refusal;
- it is asked for again every ``LINE_LENDING_TAPE_RETRY_SEC``, at most
  ``LINE_LENDING_TAPE_RETRIES`` times a loan, once IBKR's 15 s same-instrument rule
  allows (``tape_stream.guard_remaining``);
- a line that came up after a refusal is a ``line_loan`` line ``tape_opened``.
"""
from __future__ import annotations

import logging

from line_lending import line_moves
from line_lending.constants_line_lending import (
    LINE_LENDING_OUTCOME_TAPE_OPENED,
    LINE_LENDING_OUTCOME_TAPE_REFUSED,
    LINE_LENDING_TAPE_RETRIES,
    LINE_LENDING_TAPE_RETRY_SEC,
    LINE_LENDING_TAPE_SAY_AFTER_SEC,
    TAPE_REFUSED,
)
from line_lending.loan import Loan, audit

logger = logging.getLogger(__name__)


def refused_reason(loan: Loan, error: str | None) -> str:
    return f"{loan.borrower}'s {loan.setup_words()} has no Time & Sales line: {error}"


async def watch(loan: Loan, now: float) -> None:
    tape = line_moves.tape_state(loan.borrower, held=loan.tape_held, error=loan.tape_error)
    if tape.state != TAPE_REFUSED:
        loan.tape_down_since = None
        if loan.tape_said:
            loan.tape_said = False
            audit(loan, LINE_LENDING_OUTCOME_TAPE_OPENED, f"{loan.borrower}'s Time & Sales line is up")
        loan.tape_error = None
        return
    loan.tape_error = tape.error
    if loan.tape_down_since is None:
        loan.tape_down_since = now
    if not loan.tape_said and (tape.ibkr_ended or now - loan.tape_down_since >= LINE_LENDING_TAPE_SAY_AFTER_SEC):
        loan.tape_said = True
        audit(loan, LINE_LENDING_OUTCOME_TAPE_REFUSED, refused_reason(loan, tape.error), tape_error=tape.error)
    if loan.tape_said:
        await _ask_again(loan, now)


async def _ask_again(loan: Loan, now: float) -> None:
    from ibkr import tape_stream

    if loan.tape_tries >= LINE_LENDING_TAPE_RETRIES or now - loan.tape_asked_at < LINE_LENDING_TAPE_RETRY_SEC:
        return
    try:
        if tape_stream.guard_remaining(loan.borrower) > 0:
            return
    except Exception:
        logger.warning("line lending: IBKR's tape guard for %s could not be read", loan.borrower, exc_info=True)
        return
    loan.tape_tries += 1
    loan.tape_asked_at = now
    if loan.tape_held:                           # the reference stands; only the line is down
        error = await line_moves.open_tape(loan.borrower)
    else:
        taken = await line_moves.take_tape(loan.borrower)
        loan.tape_held = taken.held
        error = taken.error
    if error is not None:
        loan.tape_error = error
        logger.warning("line lending: %s's tape line asked again (%d of %d): %s", loan.borrower,
                       loan.tape_tries, LINE_LENDING_TAPE_RETRIES, error)
