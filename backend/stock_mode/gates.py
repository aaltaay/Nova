"""The desk's gates on a Nova send for one stock (ADR 037 decision 5).

Every read here fails closed: a venue Nova cannot read counts as Live, and a gate that cannot be read
keeps Nova from sending, with the reason.
"""
from __future__ import annotations

import logging

from constants_sim import DESK_PRACTICE_VENUES
from constants_stock_mode import (
    STOCK_MODE_BLOCK_BOT_TRIP,
    STOCK_MODE_BOT,
    STOCK_MODE_BLOCK_DAY_LOCK,
    STOCK_MODE_BLOCK_DISARMED,
    STOCK_MODE_BLOCK_KILL,
    STOCK_MODE_LIVE,
    STOCK_MODE_REPLAY,
    STOCK_MODE_WHY_BOT_TRIP,
    STOCK_MODE_WHY_DAY_LOCK,
    STOCK_MODE_WHY_DISARMED,
    STOCK_MODE_WHY_KILL,
    STOCK_MODE_WHY_LIVE_BUY,
    STOCK_MODE_WHY_REPLAY,
    STOCK_MODE_WHY_VENUE_UNKNOWN,
)

logger = logging.getLogger(__name__)


def venue_state() -> tuple[str | None, bool]:
    """``(venue, replay)``: the desk's venue (None when unreadable) and whether it is a replay desk."""
    from sim import mode as _mode

    try:
        current = _mode.venue()
    except Exception:
        logger.warning("stock mode: the desk's venue could not be read -- it counts as Live", exc_info=True)
        return None, False
    try:
        replay = bool(_mode.is_replay_desk())
    except Exception:
        logger.warning("stock mode: the live edge could not be read -- the desk counts as a replay", exc_info=True)
        replay = True
    return current, replay


def replay_key() -> list | None:
    """The loaded replay the Sim desk shows (``bot.replay_desk.desk``: its key); None at the live edge, on another
    venue, or with nothing loaded. A replay's trades and approvals are kept under it (``store.place``)."""
    from bot.replay_desk import desk

    here = desk()
    return list(here["key"]) if here is not None else None


def venue_block(venue: str | None, replay: bool, mode: str | None = None,
                loaded: bool | None = None) -> tuple[str, str] | None:
    """Why Nova may not take a stock in ``mode`` on this venue (None: it may). A Sim replay is traded like Paper
    once something is loaded (ADR 052 and its amendment, #815); with nothing loaded off the edge only Bot is
    taken -- the bot's Activate says why it waits. ``loaded`` None reads the desk."""
    if venue is None:
        return STOCK_MODE_LIVE, STOCK_MODE_WHY_VENUE_UNKNOWN
    if venue not in DESK_PRACTICE_VENUES:
        return STOCK_MODE_LIVE, STOCK_MODE_WHY_LIVE_BUY
    if replay and mode != STOCK_MODE_BOT and not (replay_key() is not None if loaded is None else loaded):
        return STOCK_MODE_REPLAY, STOCK_MODE_WHY_REPLAY
    return None


def _soft_breaker_fired() -> bool:
    from bot.persist import load_session

    from bot.clock import soft_latched

    return soft_latched(load_session())


def desk_blocks() -> list[tuple[str, str]]:
    """Every desk gate that keeps Nova from sending a buy now: ``[(code, why)]`` (empty: none).

    The padlock (``places_allowed``), the kill switch, this venue's day lock and bot trip. The
    execution door checks the padlock and the kill switch again; asking first lets the runner skip
    with the reason instead of sending into a refusal. A gate that cannot be read counts as closed.
    """
    checks = (
        (STOCK_MODE_BLOCK_DISARMED, STOCK_MODE_WHY_DISARMED, _disarmed),
        (STOCK_MODE_BLOCK_KILL, STOCK_MODE_WHY_KILL, _kill_tripped),
        (STOCK_MODE_BLOCK_DAY_LOCK, STOCK_MODE_WHY_DAY_LOCK, _day_locked),
        (STOCK_MODE_BLOCK_BOT_TRIP, STOCK_MODE_WHY_BOT_TRIP, _soft_breaker_fired),
    )
    out: list[tuple[str, str]] = []
    for code, why, blocked in checks:
        try:
            if blocked():
                out.append((code, why))
        except Exception:
            logger.warning("stock mode: the %s gate could not be read -- Nova sends nothing", code, exc_info=True)
            out.append((code, f"{why} (Nova could not read it, so it counts as closed)"))
    return out


def desk_block() -> tuple[str, str] | None:
    """The first desk gate that keeps Nova from sending a buy now: ``(code, why)``, else None."""
    found = desk_blocks()
    return found[0] if found else None


def _disarmed() -> bool:
    from ibkr.trading_allowed import places_allowed

    ok, _reason = places_allowed()
    return not ok


def _kill_tripped() -> bool:
    import kill_switch

    return bool(kill_switch.is_tripped())


def _day_locked() -> bool:
    from bot.buy_lock import day_lock_active

    return bool(day_lock_active())


def followed(symbol: str) -> bool | None:
    """Whether the setup scanner follows the stock (only followed stocks can trigger); None when unknown. On a Sim
    replay the Sim eyes follow the loaded symbol only (ADR 052)."""
    try:
        from bot.replay_desk import desk

        here = desk()
        if here is not None:
            return symbol == here["symbol"]
        from setup_scanner.engine import get_engine

        return symbol in get_engine().universe
    except Exception:
        logger.warning("stock mode: the setup scanner's universe could not be read", exc_info=True)
        return None
