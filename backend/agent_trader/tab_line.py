"""The line Claude's seat takes from a hidden Trader tab (ADR 068 decision 14, operator 2026-10-27).

The last resort, after a free line and an auto-record line (``room``): with all 3 Level 2 lines held, the seat
borrows a hidden Trader tab's Level 2 and Time & Sales by a bot loan's rule (``line_lending.claude_loan``). The
operator approved the desk's words in design ``F:\\Nova\\design\\claude-seat\\v3``: the tab reads "Level 2 lent to
Claude (watching RUNR)", and **bringing it to the front does not take it back** -- "the point is not to disturb
Claude while it learns from level 2". Only the operator's right-click on the tab (Take my Level 2 back from
Claude, ``take_back``) or the seat letting its line go returns it.

Owner: which tabs the operator took back (not taken again while their tab is open; the desk's request for their
line is admitted past the reservation, ``may_return``), and the short hold after a take-back so the seat never
grabs the freed line before the tab reconnects. In memory: a restart closes every socket and ends every loan.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from agent_trader import clock
from agent_trader.constants_agent_trader import AGENT_TAB_LINE_HOLD_SEC, AGENT_TAB_LINE_TRY_SEC, AGENT_TAB_TIER_SEC

logger = logging.getLogger(__name__)

_taken_back: set[str] = set()   # tabs the operator took back: never taken again while open
_hold_until = 0.0               # the seat asks for no line before this (a take-back's tab reconnects first)
_tried_at = 0.0                 # the last time a tab was looked for
_tier_at = 0.0                  # the last time the loan's words were brought up to date


def reset_for_tests() -> None:
    global _hold_until, _tried_at, _tier_at
    _taken_back.clear()
    _hold_until = _tried_at = _tier_at = 0.0


def lent_from() -> str | None:
    """The tab whose line Claude holds now, or None."""
    from line_lending import loans
    from line_lending.constants_line_lending import LOAN_ACTIVE

    loan = loans.claude_loan()
    return loan.lender if loan is not None and loan.state == LOAN_ACTIVE else None


def taken_back() -> list[str]:
    return sorted(_taken_back)


def may_return(symbol: str) -> bool:
    """The operator took ``symbol``'s tab line back from Claude: its Level 2 is admitted past the reservation."""
    return (symbol or "").upper() in _taken_back


def on_hold(now: float | None = None) -> bool:
    """Right after a take-back: the seat asks for no line, so the tab gets the one it was given back."""
    return (clock.now() if now is None else now) < _hold_until


def tier(symbol: str | None) -> str:
    """What Claude does on its stock, for the tab's words: in a trade, a buy set, or watching."""
    from agent_trader import ledger, seat
    from line_lending.constants_line_lending import CLAUDE_BUY_SET, CLAUDE_IN_TRADE, CLAUDE_WATCHING

    sym = (symbol or "").upper()
    try:
        if any(q > 0 for q in ledger.positions().values()):
            return CLAUDE_IN_TRADE
        working = [r for r in ledger.working() if str(r.get("symbol") or "").upper() == sym]
    except ledger.ReadError:
        logger.warning("AGENT tab line: Paper could not be read; the tab's words stay as they were")
        return ""
    if working or any(b.get("symbol") == sym for b in seat.breaks()):
        return CLAUDE_BUY_SET
    return CLAUDE_WATCHING


async def take(symbol: str, now: float | None = None) -> str | None:
    """All 3 lines held and none ``symbol``'s: borrow a hidden tab's lines for Claude. The tab, or None."""
    global _tried_at
    from agent_trader import lines, seat
    from line_lending import claude_loan

    t = clock.now() if now is None else now
    if t - _tried_at < AGENT_TAB_LINE_TRY_SEC or lent_from() is not None:
        return None
    _tried_at = t
    sym = (symbol or "").upper()
    lender = claude_loan.lender_for(sym, skip=_taken_back, now=time.time())
    if lender is None:
        return None
    loan = await claude_loan.lend(lender, sym, tier(sym) or "watching", lambda: lines.acquire(sym))
    if loan is None:
        return None
    seat.event("tab_line", f"took your hidden {loan.lender} tab's line · {loan.why_words() or sym}", t)
    return loan.lender


async def take_back(symbol: str, now: float | None = None) -> str | None:
    """The operator's right-click: ``symbol``'s tab gets its lines back now, Claude waits for another. Why not, or
    None. Claude's orders stay as they are: its stop and targets rest on Paper."""
    global _hold_until
    from agent_trader import lines, seat
    from line_lending import claude_loan
    from line_lending.constants_line_lending import LOAN_END_TAKEN_BACK

    t = clock.now() if now is None else now
    sym = (symbol or "").strip().upper()
    if lent_from() != sym:
        return f"{sym}'s Level 2 is not lent to Claude"
    held = lines.held_symbol()
    if held and held in lines.desk_lines():
        # A tab of yours watches Claude's stock too: that line is the desk's, and letting Claude go frees nothing
        # (Codex review, PR #1250). Said, never a take-back that leaves the tab refused at the cap.
        return (f"Claude's line on {held} is shared with your {held} tab, so letting Claude go frees no line for "
                f"{sym}. Close {held}'s Level 2 in your tab, then take {sym}'s back again.")
    _taken_back.add(sym)
    _hold_until = t + AGENT_TAB_LINE_HOLD_SEC
    await lines.release(at_once=True)            # the free line is the tab's: it reconnects at once
    await claude_loan.end(LOAN_END_TAKEN_BACK, "you took it back")
    shares = _holds_shares()
    tail = f" · {held} stop and sell still rest" if held and shares else ""
    seat.event("tab_line_back", f"You took {sym}'s line back from Claude{tail}", t)
    return None


def _holds_shares() -> bool:
    from agent_trader import ledger

    try:
        return any(q > 0 for q in ledger.positions().values())
    except ledger.ReadError:
        return False


async def keep(now: float | None = None) -> None:
    """Each watcher pass: end the loan once Claude let its line go or the tab closed; bring its words up to date;
    forget taken-back tabs no window lists any more."""
    global _tier_at
    from agent_trader import lines
    from line_lending import claude_loan
    from line_lending import focus as _focus
    from line_lending.constants_line_lending import LOAN_END_CLAUDE_LET_GO, LOAN_END_TAB_CLOSED

    t = clock.now() if now is None else now
    lender = lent_from()
    focus = _focus.read(time.time()) if (lender or _taken_back) else None
    if focus is not None and focus.known:
        _taken_back.intersection_update(focus.tabs)
    if lender is None:
        return
    held = lines.held_symbol()
    if held is None:
        await claude_loan.end(LOAN_END_CLAUDE_LET_GO, "Claude let its line go")
        return
    if focus is not None and focus.known and lender not in focus.tabs:
        await claude_loan.end(LOAN_END_TAB_CLOSED, "its tab closed")
        return
    if t - _tier_at >= AGENT_TAB_TIER_SEC:
        _tier_at = t
        claude_loan.follow(held, tier(held))


def describe() -> dict[str, Any]:
    return {"lent_from": lent_from(), "taken_back": taken_back(), "hold_until": _hold_until or None}
