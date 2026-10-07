"""Who wants an auto-record line, best first (ADR 023, ADR 041) -- pure picks over the live lists.

``leaderboard.auto_record`` decides who holds a line; this says who wants one and how much:
a setup in a trade, then near its trigger, then armed, then a leader of the Gainers board
(the same ranking playback applies to the recorded minute). ``left``: on neither list now.

A short setup (ADR 049) wants a line only while its strategy is On on the desk's venue (#778 step 5): the
bot then trades it, and a trigger without a line reads BLIND. At Eyes or Off it wants none -- the lines serve
the trials that read long setups (ADR 041), and a short's On is decided by its five-year test.
"""
from __future__ import annotations

import logging
from typing import Any

from constants_leaderboard import LEADERBOARD_AUTO_RECORD_TOP_N, LEADERBOARD_BOARD_GAINERS
from constants_setups import SETUP_STATE_NEAR
from leaderboard.ranking import LEADERS_RULES, leader_symbols
from leaderboard.rows import from_desk_row

logger = logging.getLogger(__name__)

# Why a symbol holds (or wants) an auto line, best first. ``left``: it is on neither list now.
WHY_TRADE, WHY_NEAR, WHY_ARMED, WHY_LEADER, WHY_LEFT = "trade", "near", "armed", "leader", "left"
TIERS = (WHY_TRADE, WHY_NEAR, WHY_ARMED, WHY_LEADER, WHY_LEFT)
SETUP_TIERS = (WHY_TRADE, WHY_NEAR, WHY_ARMED)


def pick_leaders(surfaced_gainers: list[dict], now: float) -> list[str]:
    """The same ranking playback applies to the recorded Gainers minute."""
    minute_ts = int(now) // 60 * 60
    rows = []
    for position, raw in enumerate(surfaced_gainers, start=1):
        try:
            rows.append(from_desk_row(raw, minute_ts=minute_ts, board=LEADERBOARD_BOARD_GAINERS, rank=position))
        except (TypeError, ValueError):
            continue
    return leader_symbols(rows, LEADERS_RULES)[:LEADERBOARD_AUTO_RECORD_TOP_N]


def shorts_on() -> set[str]:
    """The short setups whose strategy is On on the desk's venue (the bot trades them); none when unread."""
    try:
        from bot.persist import load_session
        from bot.setup_levels import effective
        from constants_bot import BOT_LEVEL_STRATEGY, SIDE_SHORT, setup_side

        return {s for s, level in effective(load_session()).items()
                if level >= BOT_LEVEL_STRATEGY and setup_side(s) == SIDE_SHORT}
    except Exception:
        logger.warning("auto-record: which short strategies are On could not be read -- none takes a line",
                       exc_info=True)
        return set()


def pick_setups(lanes: list[Any], now: float) -> list[tuple[str, str]]:
    """``(symbol, why)`` for every setup of the templates in play: in a trade, near, then armed. A short
    setup counts only while its strategy is On (``shorts_on``)."""
    best: dict[str, str] = {}
    on: set[str] | None = None
    for lane in lanes:
        params = getattr(lane, "p", None)
        if getattr(params, "short", False):
            on = shorts_on() if on is None else on
            if getattr(params, "setup", None) not in on:
                continue                       # a short at Eyes or Off takes no line (ADR 049)
        found = [(s, WHY_TRADE) for s in lane.trade_symbols(now)]
        for sym in lane.watching():
            state = getattr(lane.det.get(sym), "state", None)
            found.append((sym, WHY_NEAR if state == SETUP_STATE_NEAR else WHY_ARMED))
        for sym, why in found:
            if sym not in best or TIERS.index(why) < TIERS.index(best[sym]):
                best[sym] = why
    return sorted(best.items(), key=lambda item: (TIERS.index(item[1]), item[0]))
