"""The line Claude's seat takes when all 3 Level 2 lines are held (ADR 068 decision 3, amended 2026-10-27).

Only an **auto-record** line, and only one whose sole viewer is auto-record's own hold (``capture.feed_hold``) and
that the L2 recorder is not recording, so stopping it frees the line: a Trader tab, a Session Record the operator started, the L2 recorder and a loan are
never taken. Of those, the line the desk had in front least recently -- never in front counts as longest idle
(``line_lending.focus`` ``last_shown``, the Trader tab sockets' ``front_seen``) --, ties by auto-record's own lowest
rank (``leaderboard.auto_record.yield_to_agent``). Read-only here; auto-record stops its line.
"""
from __future__ import annotations

import logging
import time

from constants_ibkr import IBKR_MAX_DEPTH_SYMBOLS

logger = logging.getLogger(__name__)


def lines_full(symbol: str) -> bool:
    """Every Level 2 line IBKR gives the login is watched, and none is ``symbol``'s. A line no one watches any more
    is the depth door's to let go, and one Claude alone watches is let go when it moves (Codex review, PR #1247), so
    neither counts."""
    from agent_trader import lines
    from ibkr import depth

    up = depth.subscribed_symbols()
    busy = [s for s in up if depth.viewer_count(s) > 0 and not lines.claude_alone(s)]
    return (symbol or "").upper() not in up and len(busy) >= IBKR_MAX_DEPTH_SYMBOLS


def takeable(auto: list[str]) -> list[str]:
    """The auto-record lines stopping would free: up, watched by auto-record's hold alone, and not recorded by the L2
    recorder too (it keeps the line without a viewer, and the seat's subscribe would evict it mid-recording)."""
    from ibkr import depth
    from l2 import recorder

    up = set(depth.subscribed_symbols())
    return [s for s in auto if s in up and depth.viewer_count(s) <= 1 and not recorder.is_recording(s)]


def last_in_front(symbol: str, now: float | None = None) -> float:
    """When the desk last showed ``symbol`` in front; 0.0 when never (or the focus cannot be read)."""
    from line_lending import focus, sockets

    seen = 0.0
    try:
        seen = float(focus.read(now).last_shown.get(symbol) or 0.0)
    except Exception:
        logger.warning("AGENT room: the focus could not be read for %s", symbol, exc_info=True)
    return max(seen, float(sockets.front_seen(symbol) or 0.0))


def idlest(candidates: list[str], now: float | None = None) -> list[str]:
    """The candidates, idle longest first (ties keep the caller's order: auto-record's lowest rank first)."""
    return sorted(candidates, key=lambda s: last_in_front(s, now))


async def make_room(symbol: str, now: float | None = None) -> str | None:
    """All 3 lines held and none ``symbol``'s: have auto-record give one up; the symbol it gave, or None."""
    from leaderboard import auto_record

    sym = (symbol or "").strip().upper()
    if not sym or not lines_full(sym):
        return None
    t = time.time() if now is None else now
    return await auto_record.yield_to_agent(sym, lambda ranked: next(iter(idlest(takeable(ranked), t)), None))
