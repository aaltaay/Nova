"""The desk's gates on a Nova send for one stock (ADR 037 decision 5).

Every read here fails closed: a venue Nova cannot read counts as Live, and a gate that cannot be read
keeps Nova from sending, with the reason.
"""
from __future__ import annotations

import logging

from constants_sim import DESK_PRACTICE_VENUES
from constants_stock_mode import (
    STOCK_MODE_BLOCK_BOT_TRIP,
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


def venue_block(venue: str | None, replay: bool) -> tuple[str, str] | None:
    if venue is None:
        return STOCK_MODE_LIVE, STOCK_MODE_WHY_VENUE_UNKNOWN
    if venue not in DESK_PRACTICE_VENUES:
        return STOCK_MODE_LIVE, STOCK_MODE_WHY_LIVE_BUY
    if replay:
        return STOCK_MODE_REPLAY, STOCK_MODE_WHY_REPLAY
    return None


def _soft_breaker_fired() -> bool:
    from bot.persist import load_session

    return bool(load_session().get("soft_breaker_fired"))


def desk_block() -> tuple[str, str] | None:
    """The first desk gate that keeps Nova from sending a buy now: ``(code, why)``, else None.

    The padlock (``places_allowed``), the kill switch, the day lock and the bot trip. The execution
    door checks the padlock and the kill switch again; asking first lets the runner skip with the
    reason instead of sending into a refusal.
    """
    checks = (
        (STOCK_MODE_BLOCK_DISARMED, STOCK_MODE_WHY_DISARMED, _disarmed),
        (STOCK_MODE_BLOCK_KILL, STOCK_MODE_WHY_KILL, _kill_tripped),
        (STOCK_MODE_BLOCK_DAY_LOCK, STOCK_MODE_WHY_DAY_LOCK, _day_locked),
        (STOCK_MODE_BLOCK_BOT_TRIP, STOCK_MODE_WHY_BOT_TRIP, _soft_breaker_fired),
    )
    for code, why, blocked in checks:
        try:
            if blocked():
                return code, why
        except Exception:
            logger.warning("stock mode: the %s gate could not be read -- Nova sends nothing", code, exc_info=True)
            return code, f"{why} (Nova could not read it, so it counts as closed)"
    return None


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
    """Whether the setup scanner follows the stock (only followed stocks can trigger); None when unknown."""
    try:
        from setup_scanner.engine import get_engine

        return symbol in get_engine().universe
    except Exception:
        logger.warning("stock mode: the setup scanner's universe could not be read", exc_info=True)
        return None
