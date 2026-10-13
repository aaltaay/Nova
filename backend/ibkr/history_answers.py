"""Whether IBKR's chart history is answering: a second witness that a tape stall is IBKR's (#722).

2026-10-13 07:59:22 ET: every live tape line stopped printing, and in the same second IBKR's chart
history stopped answering -- every SCNI request from then to 08:03 timed out at 12 s, while a 5-minute
request had answered at 07:59:22.468. IBKR's own word (2105 ``ushmds`` broken) came at 08:03:22, and
the prints were back at 08:03:29. A tape silence beside history that stopped answering is not one
quiet line.

``ibkr/bars.py`` reports each history answer and each timeout here. ``unanswered_since`` is the send
time of the first request that timed out with no history answer since, or None. A request that was
sent before the last answer and timed out after it was slow alone, so it is not counted. Memory only:
it asks IBKR for nothing, and a restart starts it empty.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_last_answer_at: float | None = None
_unanswered_since: float | None = None


def reset_for_tests() -> None:
    global _last_answer_at, _unanswered_since
    with _lock:
        _last_answer_at = None
        _unanswered_since = None


def note_answered(at: float) -> None:
    """IBKR's history answered a request at ``at`` (epoch seconds): it is answering."""
    global _last_answer_at, _unanswered_since
    with _lock:
        if _last_answer_at is None or at > _last_answer_at:
            _last_answer_at = at
        _unanswered_since = None


def note_timed_out(sent_at: float) -> None:
    """A history request sent at ``sent_at`` timed out with no answer."""
    global _unanswered_since
    with _lock:
        if _last_answer_at is not None and _last_answer_at >= sent_at:
            return  # history answered after this was sent: this request was slow alone
        if _unanswered_since is None or sent_at < _unanswered_since:
            _unanswered_since = sent_at


def unanswered_since() -> float | None:
    with _lock:
        return _unanswered_since


def unanswered_near(since: float, *, window: float) -> float | None:
    """When history stopped answering, if that began from ``window`` before ``since`` on, else None."""
    stopped = unanswered_since()
    if stopped is None or stopped < since - window:
        return None
    return stopped
