"""Who wants an auto-record line, best first (ADR 023, ADR 041) -- pure picks over the live lists.

``leaderboard.auto_record`` decides who holds a line; this says who wants one and how much:
a setup in a trade, then near its trigger, then armed, then a leader of the Gainers board
(the same ranking playback applies to the recorded minute). ``left``: on neither list now.
"""
from __future__ import annotations

from typing import Any

from constants_leaderboard import LEADERBOARD_AUTO_RECORD_TOP_N, LEADERBOARD_BOARD_GAINERS
from constants_setups import SETUP_STATE_NEAR
from leaderboard.ranking import LEADERS_RULES, leader_symbols
from leaderboard.rows import from_desk_row

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


def pick_setups(lanes: list[Any], now: float) -> list[tuple[str, str]]:
    """``(symbol, why)`` for every setup of the templates in play: in a trade, near, then armed."""
    best: dict[str, str] = {}
    for lane in lanes:
        found = [(s, WHY_TRADE) for s in lane.trade_symbols(now)]
        for sym in lane.watching():
            state = getattr(lane.det.get(sym), "state", None)
            found.append((sym, WHY_NEAR if state == SETUP_STATE_NEAR else WHY_ARMED))
        for sym, why in found:
            if sym not in best or TIERS.index(why) < TIERS.index(best[sym]):
                best[sym] = why
    return sorted(best.items(), key=lambda item: (TIERS.index(item[1]), item[0]))
