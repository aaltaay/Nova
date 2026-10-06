"""Whether the setup scanner follows a listed name, and why not (ADR 044). Reads memory only.

The stocks the bot buys (``bot_buy_symbols``), then listed names, share HOD Momo's reserved block with Former
Momo (``hod_momo_active.build_active_set``), ``HOD_MOMO_FORMER_MOMO_MAX_SLOTS`` slots in all. The setup scanner
follows the active set, so a name past the block -- or one IBKR cannot stream -- is not followed, and every
reader says why instead of showing it as quietly unwatched.
"""
from __future__ import annotations

import logging

from constants_hod_momo import HOD_MOMO_FORMER_MOMO_MAX_SLOTS
from constants_hot_list import (
    BOT_BUY_ACTIVE_L1_BLOCKED,
    BOT_BUY_ACTIVE_OVER_RESERVED,
    HOT_LIST_ACTIVE_L1_BLOCKED,
    HOT_LIST_ACTIVE_OVER_RESERVED,
)
from constants_stock_mode import STOCK_MODE_SIDE_NOVA

logger = logging.getLogger(__name__)

RESERVED_FULL = f"HOD Momo's {HOD_MOMO_FORMER_MOMO_MAX_SLOTS} reserved slots are full"
L1_BLOCKED = "IBKR could not open its L1 line; Nova asks for it again after a cooldown"
NEXT_PASS = "HOD Momo admitted it; the setup scanner picks it up at its next pass"
NOT_REBUILT = "HOD Momo's active set has not been rebuilt since it was listed; its next pass takes it"
SCANNER_UNREAD = "the setup scanner could not be read, so whether it follows this name is unknown"


def bot_buy_symbols() -> list[str]:
    """The stocks whose Buy is the bot's on the desk's venue: its bot list in order, then each Auto-entry
    switch, sorted. Memory reads (the bot session is cached; the switches live in memory)."""
    from bot.eligibility import normalize_symbols
    from bot.persist import load_session
    from stock_mode import store

    names = list(normalize_symbols(load_session().get("symbol_allowlist")))
    names += sorted(str(s).upper() for s, sw in store.switches().items()
                    if (sw or {}).get("buy") == STOCK_MODE_SIDE_NOVA)
    return list(dict.fromkeys(names))


def universe() -> set[str] | None:
    """The names the setup scanner follows now, or None when it cannot be read (unknown, never "none")."""
    try:
        from setup_scanner.engine import get_engine

        return set(get_engine().universe)
    except Exception:
        logger.warning("hot list: the setup scanner's universe could not be read", exc_info=True)
        return None


def reason_not_followed(sym: str) -> str:
    """Why a name the setup scanner does not follow is left out, from HOD Momo's last admission."""
    import hod_momo_active as active

    why = active.get_priority_reason(sym)
    if why in (HOT_LIST_ACTIVE_OVER_RESERVED, BOT_BUY_ACTIVE_OVER_RESERVED):
        return RESERVED_FULL
    if why in (HOT_LIST_ACTIVE_L1_BLOCKED, BOT_BUY_ACTIVE_L1_BLOCKED):
        return L1_BLOCKED
    if why is not None and sym in active.get_active_symbols():
        return NEXT_PASS
    return NOT_REBUILT


def status(sym: str, followed_now: set[str] | None) -> tuple[bool | None, str | None]:
    """``(followed, why_not_followed)`` for one listed name against the scanner's universe."""
    if followed_now is None:
        return None, SCANNER_UNREAD
    if sym in followed_now:
        return True, None
    return False, reason_not_followed(sym)


def listed_note(sym: str) -> str | None:
    """The setup view's note for a name the bot buys, or a listed one, that it does not follow; None for any
    other name."""
    from hot_list.store import is_listed

    try:
        bot_buys = sym in bot_buy_symbols()
    except Exception:
        logger.warning("hot list: the bot's stocks could not be read for %s's note", sym, exc_info=True)
        bot_buys = False
    if bot_buys:
        return f"{sym} is set to bot buy, but no lane reads it: {reason_not_followed(sym)}"
    if not is_listed(sym):
        return None
    return f"{sym} is on today's hot list, but no lane reads it: {reason_not_followed(sym)}"
