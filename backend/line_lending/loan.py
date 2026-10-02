"""One loan: what it holds, the words it says and its audit lines (ADR 043 decision 6).

A loan takes a hidden Trader tab's Level 2 line -- and its AllLast line, when every
viewer of that line is the tab's Time & Sales -- for a setup Nova may buy, and holds the
borrower's two lines. ``frame`` is what the lender's sockets read before they close;
``public`` is its row on ``GET /api/ibkr/depth/lines``; ``audit`` writes its ``line_loan``
lines on the bot audit stream.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from line_lending import line_moves
from line_lending.constants_line_lending import (
    LENT_TEXT,
    LENT_TEXT_NO_WHY,
    LINE_LENDING_AUDIT_ACTION,
    LOAN_PENDING,
    SETUP_WORDS,
    TAPE_RECEIVING,
    WHY_WORDS,
)

logger = logging.getLogger(__name__)


@dataclass
class Loan:
    lender: str
    borrower: str
    setup_type: str
    setup_id: str | None
    why: str
    since: float
    state: str = LOAN_PENDING
    traded: bool = False
    depth_held: bool = False      # Nova holds a viewer reference on the borrower's depth line
    tape_lent: bool = False       # the lender's AllLast line went with its Level 2 line
    tape_held: bool = False       # Nova holds a viewer reference on the borrower's AllLast line
    tape_error: str | None = None  # why the borrower's AllLast line is down (a refusal, IBKR's end)
    tape_said: bool = False       # that refusal is on the audit stream (said again after the line came up)
    tape_down_since: float | None = None  # when the borrower's AllLast line was first seen down
    tape_tries: int = 0           # times the borrower's AllLast line was asked for again (not the first ask)
    tape_asked_at: float = 0.0    # when it was last asked for

    def setup_words(self) -> str:
        return SETUP_WORDS.get(self.setup_type, self.setup_type.replace("_", " "))

    def lines_words(self) -> str:
        return "Level 2 and Time & Sales" if self.tape_lent else "Level 2"

    def text(self) -> str:
        """The lent frame's sentence (the contract's words; the desk builds its own per pane)."""
        words = WHY_WORDS.get(self.why)
        template = LENT_TEXT if words else LENT_TEXT_NO_WHY
        return template.format(symbol=self.borrower, setup=self.setup_words(), why=words)

    def lent(self) -> str:
        """The sentence a loan starts with, on the audit stream."""
        words = WHY_WORDS.get(self.why, self.why)
        return f"{self.lender}'s {self.lines_words()} lent to {self.borrower}'s {self.setup_words()} ({words})"

    def back(self, why: str) -> str:
        """The sentence a loan that gives the lines back ends with."""
        verb = "go" if self.tape_lent else "goes"
        return f"{self.lender}'s {self.lines_words()} {verb} back from {self.borrower}'s {self.setup_words()}: {why}"

    def lost(self) -> str:
        """The sentence a recalled loan ends with: the setup lost its lines."""
        return (f"{self.borrower}'s {self.setup_words()} lost its Level 2"
                f"{' and Time & Sales lines' if self.tape_held else ' line'}: {self.lender} came to the front")

    def frame(self) -> dict[str, Any]:
        """What the lender's Level 2 and Time & Sales sockets send before they close."""
        return {"type": "lent", "symbol": self.lender,
                "to": {"symbol": self.borrower, "setup_type": self.setup_type, "setup_id": self.setup_id},
                "why": WHY_WORDS.get(self.why, self.why), "tier": self.why, "since": self.since, "text": self.text()}

    def public(self) -> dict[str, Any]:
        tape = line_moves.tape_state(self.borrower, held=self.tape_held, error=self.tape_error)
        return {"lender": self.lender, "borrower": self.borrower, "setup_type": self.setup_type,
                "setup_id": self.setup_id, "since": self.since, "why": WHY_WORDS.get(self.why, self.why),
                "tier": self.why, "state": self.state, "text": self.text(),
                "tape": tape.state == TAPE_RECEIVING, "tape_state": tape.state, "tape_error": tape.error,
                "tape_lent": self.tape_lent, "tape_last_print": tape.last_print}


def audit(loan: Loan, outcome: str, reason: str, **extra: Any) -> None:
    """A ``line_loan`` line: ``inputs: {lender, borrower, setup_type, setup_id, ...extra}``."""
    from bot.audit import record

    inputs: dict[str, Any] = {"lender": loan.lender, "borrower": loan.borrower, "setup_type": loan.setup_type,
                              "setup_id": loan.setup_id, **extra}
    try:
        record(action=LINE_LENDING_AUDIT_ACTION, outcome=outcome, reason=reason, inputs=inputs)
    except Exception:
        logger.exception("line lending: the audit line for %s -> %s could not be written", loan.lender, loan.borrower)
