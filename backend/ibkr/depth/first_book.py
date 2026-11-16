"""Whether a symbol's live Level 2 line has delivered its first book (ADR 045 amendment 2026-10-27, #913).

A depth socket can say ``subscribed`` and beat every 0.25 s while IBKR never sends a row (BKYI, 2026-10-13,
after Gateway connectivity drops): no silence, no lag, and the ticket stayed open. Until the line's current
request has delivered a book with a row, ``waiting`` says so, and the order gate locks the symbol
(``market_view.gate.desk_lock``, ``BOOK_WAITING``). Each new request, retry or reconnect starts again.

Past ``MARKET_VIEW_FIRST_BOOK_WAIT_SEC`` the words say what IBKR has done with the request -- not answered it,
granted it without rows, refused it -- and the log says so once per request. Information only: nothing here
cancels a request, frees its slot or restarts anything (``ibkr/depth/release.py`` owns every cancel).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants_market_view import MARKET_VIEW_FIRST_BOOK_WAIT_SEC
from ibkr.depth import release, state

logger = logging.getLogger(__name__)

WAITING = "waiting"          # within the wait: nothing to say about IBKR yet
UNANSWERED = "unanswered"    # IBKR has not answered the request
GRANTED = "granted"          # IBKR granted it and has sent no row
REFUSED = "refused"          # IBKR refused it; the line is being let go
L1_WAITING = "l1_waiting"    # the Level 1 fallback has no bid or ask yet

_TEXT = {
    WAITING: "{symbol}'s Level 2 is open but has sent no book yet.",
    UNANSWERED: "IBKR has not answered {symbol}'s Level 2 request in {wait:g} s.",
    GRANTED: "IBKR granted {symbol}'s Level 2 but has sent no rows in {wait:g} s.",
    REFUSED: "IBKR refused {symbol}'s Level 2 request.",
    L1_WAITING: "{symbol}'s Level 1 fallback has sent no bid or ask in {wait:g} s.",
}

# symbol -> the request (its ``requested_at``) whose overdue wait was last logged: one line per request.
_logged: dict[str, float] = {}


def _replay_desk() -> bool:
    from sim.mode import is_replay_desk

    return bool(is_replay_desk())


def _answer(symbol: str) -> str | None:
    return release.line_answer(state._line_ibs.get(symbol), state._contracts.get(symbol))


def _state_of(symbol: str) -> str:
    book = state.current_book(symbol) or {}
    if state.is_shared_l1(symbol) or book.get("l1_fallback"):
        return L1_WAITING
    answer = _answer(symbol)
    if answer == release.GRANTED:
        return GRANTED
    if answer == release.REFUSED:
        return REFUSED
    return UNANSWERED


def waiting(symbol: str, now: float | None = None) -> dict[str, Any] | None:
    """``{since, state, overdue, text}`` while *symbol*'s live line has no first book, else None.

    None with no live IBKR line (a replay slot, no line at all) and on a Sim desk off the live edge, whose
    market is the replay: a paused replay is not an unanswered request.
    """
    symbol = (symbol or "").upper()
    if not symbol or _replay_desk():
        return None
    since = state.requested_at(symbol)
    if since is None or state.first_rows_at(symbol) is not None:
        return None
    t = time.time() if now is None else now
    overdue = t - since >= MARKET_VIEW_FIRST_BOOK_WAIT_SEC
    kind = _state_of(symbol) if overdue else WAITING
    text = _TEXT[kind].format(symbol=symbol, wait=MARKET_VIEW_FIRST_BOOK_WAIT_SEC)
    if overdue and _logged.get(symbol) != since:
        _logged[symbol] = since
        logger.warning("Level 2 first book: %s %s (requested %.1f s ago) -- %s", symbol, kind, t - since, text)
    return {"since": since, "state": kind, "overdue": overdue, "text": text}


def reset_for_tests() -> None:
    _logged.clear()
