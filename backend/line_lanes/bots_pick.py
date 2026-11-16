"""The setups a bot may buy now, best first: who wants the bots' lane (ADR 071 decision 6, operator 2026-11-13).

ADR 072 retired the bots: no strategy trades on any venue, Auto-entry and the bot list's writers are gone, and lane 3
becomes the brain's in a later build. So ``wanted`` names no candidate and says why (``blocked``), and ``nova_trade``
is never true -- the lane stays empty. ``pick`` keeps the rule the lane followed, pure:

A **candidate** is a setup of the template in play (``SetupEngine.playing_lanes``) that is armed, near its trigger
or in a trade (its scoring window, ``lane.trades``), when its strategy is at effective On (a watch-only setup never,
#847) and the stock's Buy is Nova. One candidate per symbol, its best tier first (trade, near, armed).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from constants_bot import BOT_LEVEL_STRATEGY, watch_only
from constants_setups import SETUP_STATE_NEAR
from line_lanes.constants_lanes import SETUP_WORDS, WHY_ARMED, WHY_NEAR, WHY_ORDER, WHY_TRADE

logger = logging.getLogger(__name__)

BOTS_RETIRED_TEXT = "the bots are retired (ADR 072): no strategy trades, so the bots' lane follows no setup"


@dataclass(frozen=True)
class Candidate:
    symbol: str
    setup_type: str
    setup_id: str | None
    why: str


@dataclass(frozen=True)
class Wanted:
    """The candidates now, best first.

    ``error``: a read failed, so nothing is known (the lane is never moved on it);
    ``blocked``: why no setup may have the lane now (the bot is not active, Nova may not buy here);
    ``nova_buys`` / ``levels``: what was read, so the lane can say which rule let a stock go.
    """
    candidates: tuple[Candidate, ...] = ()
    error: str | None = None
    blocked: str | None = None
    nova_buys: frozenset[str] = frozenset()
    levels: dict[str, int] = field(default_factory=dict)

    def get(self, symbol: str) -> Candidate | None:
        return next((c for c in self.candidates if c.symbol == symbol), None)

    def why_gone(self, symbol: str, setup_type: str) -> str:
        """Why a stock no longer wants the bots' lane, in a few words."""
        if self.blocked:
            return self.blocked
        if symbol not in self.nova_buys:
            return f"Buy on {symbol} is no longer Nova"
        if int(self.levels.get(setup_type, 0) or 0) < BOT_LEVEL_STRATEGY:
            return f"the {setup_words(setup_type)} is no longer On"
        return "it is no longer armed, near its trigger or in a trade"


def setup_words(setup: str) -> str:
    """The setup's name in a sentence ("5-minute flat top")."""
    return SETUP_WORDS.get(setup, setup) if setup else "setup"


def rank(why: str) -> int:
    return WHY_ORDER.index(why) if why in WHY_ORDER else len(WHY_ORDER)


def pick(lanes: Iterable[Any], levels: dict[str, int], nova_buys: set[str], now: float) -> list[Candidate]:
    """Pure: the candidates among the setup lanes, one per symbol, best tier first."""
    best: dict[str, Candidate] = {}
    for lane in lanes:
        setup = str(getattr(lane, "setup", "") or "")
        if watch_only(setup) or int(levels.get(setup, 0) or 0) < BOT_LEVEL_STRATEGY:
            continue
        found: list[Candidate] = []
        for sid in lane.trades(now):
            sym = str((lane.rows.get(sid) or {}).get("symbol") or "").upper()
            if sym:
                found.append(Candidate(sym, setup, sid, WHY_TRADE))
        for sym in lane.watching():
            state = getattr(lane.det.get(sym), "state", None)
            found.append(Candidate(str(sym).upper(), setup, lane.active_id.get(sym),
                                  WHY_NEAR if state == SETUP_STATE_NEAR else WHY_ARMED))
        for b in found:
            if b.symbol not in nova_buys:
                continue
            cur = best.get(b.symbol)
            if cur is None or rank(b.why) < rank(cur.why):
                best[b.symbol] = b
    return sorted(best.values(), key=lambda b: (rank(b.why), b.symbol))


def wanted(now: float | None = None) -> Wanted:
    """No candidate: the bots are retired (ADR 072), so the bots' lane follows no setup."""
    del now
    return Wanted(blocked=BOTS_RETIRED_TEXT)


def nova_trade(symbol: str) -> bool:
    """Never: Nova holds no trade of its own since the bots retired (ADR 072)."""
    del symbol
    return False
