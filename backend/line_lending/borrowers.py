"""Which setups may borrow a Level 2 line (ADR 043 decision 6).

A **borrower** is a setup of the template in play (``SetupEngine.playing_lanes``)
that is armed, near its trigger or in a trade (auto-record's tiers: the trade's
scoring window, ``lane.trades``), when:

- its strategy is at effective On (``bot.setup_levels.effective`` >= Strategy);
- the venue's bot is active (``bot.arming.is_desk_active``);
- Nova may buy on this venue (``stock_mode.model.locks``: never Live, never a replay desk);
- the stock's Buy is Nova: on this venue's bot list (Nova / Nova) or switched to
  Auto-entry (Nova / You).

One borrower per symbol, its best tier first (trade, near, armed).

A loan already standing is also kept while Nova holds a live trade on the stock
(the bot's, or a stock-mode trade), so the flush exit and the tape keep their book
until the trade ends (``nova_trade``).

Every read fails closed: an unreadable session, venue or scanner lends nothing,
and says why.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from constants_bot import BOT_LEVEL_STRATEGY
from constants_setups import SETUP_STATE_NEAR
from constants_stock_mode import STOCK_MODE_SIDE_NOVA, STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING
from line_lending.constants_line_lending import (
    BOT_TRADE_LIVE_STATES,
    SETUP_WORDS,
    WHY_ARMED,
    WHY_NEAR,
    WHY_ORDER,
    WHY_TRADE,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Borrower:
    symbol: str
    setup_type: str
    setup_id: str | None
    why: str


@dataclass(frozen=True)
class Wanted:
    """The borrowers now, best first.

    ``error``: a read failed, so nothing is known (a standing loan is never ended on it);
    ``blocked``: why no setup may borrow now (the bot is not active, Nova may not buy here);
    ``nova_buys`` / ``levels``: what was read, so an ending loan can say which rule let it go.
    """
    borrowers: tuple[Borrower, ...] = ()
    error: str | None = None
    blocked: str | None = None
    nova_buys: frozenset[str] = frozenset()
    levels: dict[str, int] = field(default_factory=dict)

    def get(self, symbol: str) -> Borrower | None:
        return next((b for b in self.borrowers if b.symbol == symbol), None)

    def why_gone(self, symbol: str, setup_type: str) -> str:
        """Why a loan's borrower is no longer one, in a few words."""
        if self.blocked:
            return self.blocked
        if symbol not in self.nova_buys:
            return f"Buy on {symbol} is no longer Nova"
        if int(self.levels.get(setup_type, 0) or 0) < BOT_LEVEL_STRATEGY:
            return f"the {SETUP_WORDS.get(setup_type, setup_type)} is no longer On"
        return "it is no longer armed, near its trigger or in a trade"


def rank(why: str) -> int:
    return WHY_ORDER.index(why) if why in WHY_ORDER else len(WHY_ORDER)


def pick(lanes: Iterable[Any], levels: dict[str, int], nova_buys: set[str], now: float) -> list[Borrower]:
    """Pure: the borrowers among the lanes, one per symbol, best tier first."""
    best: dict[str, Borrower] = {}
    for lane in lanes:
        setup = str(getattr(lane, "setup", "") or "")
        if int(levels.get(setup, 0) or 0) < BOT_LEVEL_STRATEGY:
            continue
        found: list[Borrower] = []
        for sid in lane.trades(now):
            sym = str((lane.rows.get(sid) or {}).get("symbol") or "").upper()
            if sym:
                found.append(Borrower(sym, setup, sid, WHY_TRADE))
        for sym in lane.watching():
            state = getattr(lane.det.get(sym), "state", None)
            found.append(Borrower(str(sym).upper(), setup, lane.active_id.get(sym),
                                  WHY_NEAR if state == SETUP_STATE_NEAR else WHY_ARMED))
        for b in found:
            if b.symbol not in nova_buys:
                continue
            cur = best.get(b.symbol)
            if cur is None or rank(b.why) < rank(cur.why):
                best[b.symbol] = b
    return sorted(best.values(), key=lambda b: (rank(b.why), b.symbol))


def nova_buys(row: dict[str, Any], switches: dict[str, dict[str, Any]]) -> set[str]:
    """The stocks whose Buy is Nova on this venue: the bot list, and every Auto-entry switch."""
    from bot.eligibility import normalize_symbols

    listed = set(normalize_symbols(row.get("symbol_allowlist")))
    return listed | {str(s).upper() for s, sw in switches.items() if (sw or {}).get("buy") == STOCK_MODE_SIDE_NOVA}


def _lanes() -> list[Any]:
    from setup_scanner.engine import get_engine

    return get_engine().playing_lanes()


def wanted(now: float | None = None) -> Wanted:
    """Every borrower now (empty with the reason when Nova may not buy, or a read failed)."""
    from bot.arming import is_desk_active
    from bot.persist import load_session
    from bot.setup_levels import effective
    from stock_mode import gates, model, store

    ts = time.time() if now is None else float(now)
    try:
        row = load_session()
    except Exception as exc:
        logger.warning("line lending: the bot session could not be read", exc_info=True)
        return Wanted(error=f"the bot session could not be read ({type(exc).__name__})")
    if not is_desk_active(row):
        return Wanted(blocked="the bot is off")
    venue, replay = gates.venue_state()
    lock = model.locks(venue, replay)["buy"]
    if lock is not None:
        return Wanted(blocked=lock)
    store.sync_venue(venue)
    levels = effective(row)
    buys = nova_buys(row, store.switches())
    try:
        lanes = _lanes()
    except Exception as exc:
        logger.warning("line lending: the setup scanner could not be read", exc_info=True)
        return Wanted(error=f"the setup scanner could not be read ({type(exc).__name__})")
    return Wanted(borrowers=tuple(pick(lanes, levels, buys, ts)), nova_buys=frozenset(buys), levels=dict(levels))


def nova_trade(symbol: str) -> bool:
    """Nova holds a live trade on ``symbol`` on the desk's venue (the bot's, or a stock-mode trade).

    Unreadable counts as a trade: a loan is never ended on a read that failed.
    """
    from bot.persist import load_session
    from stock_mode import gates, store

    sym = symbol.upper()
    try:
        venue, _replay = gates.venue_state()
        bot_trade = load_session().get("trade")
        if (isinstance(bot_trade, dict) and str(bot_trade.get("symbol") or "").upper() == sym
                and bot_trade.get("state") in BOT_TRADE_LIVE_STATES and bot_trade.get("venue") in (None, venue)):
            return True
        mine = store.trade(venue, sym)
        return bool(mine and mine.get("state") in (STOCK_MODE_TRADE_ENTERING, STOCK_MODE_TRADE_HOLDING))
    except Exception:
        logger.warning("line lending: Nova's trades on %s could not be read -- the loan stands", sym, exc_info=True)
        return True
