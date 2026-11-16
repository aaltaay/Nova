"""The bot API's door: what ``POST /api/bot/action`` checks before it sends (ADR 016, ADR 072).

ADR 072: the bots are retired and the bot API becomes the brain's door. Until the brain is built nothing opens it:
Activate is gone with the Bot switch, so ``assert_can_fire`` refuses (``BOT_REASON_NOT_ACTIVE``), and anything that
got past it would still be refused at the execution door (``execution.retired_senders``). The checks it keeps are the
ones a brain will meet too: never Live or a replay desk, never dark, the padlock, a fresh heartbeat.

Owner: none of its own -- it reads the desk venue (``sim.mode``), the bot session (``bot.persist``) and the loss
limit (``loss_limit.gate``). Every read fails closed: an unreadable venue counts as Live.
"""
from __future__ import annotations

import logging
from typing import Any

from bot.arming import assert_fresh_heartbeat, is_desk_active
from bot.errors import BotError
from bot.persist import load_session
from constants_bot import (
    BOT_BRAIN_DOOR_CLOSED_TEXT,
    BOT_LEVEL_OFF,
    BOT_LEVEL_STRATEGY,
    BOT_LIVE_NOT_BUILT_TEXT,
    BOT_REASON_L0_DARK,
    BOT_REASON_L1_NO_FIRE,
    BOT_REASON_LIVE_NOT_BUILT,
    BOT_REASON_NOT_ACTIVE,
)

logger = logging.getLogger(__name__)


def current_venue() -> str | None:
    """The desk venue (``live`` | ``paper`` | ``sim``); None when it cannot be read."""
    try:
        from sim.mode import venue

        return venue()
    except Exception:
        logger.warning("bot: the desk venue is unreadable -- it counts as Live", exc_info=True)
        return None


def venue_state() -> tuple[str | None, bool, bool]:
    """``(venue, live_edge, readable)``: the desk venue, whether Sim follows the wall clock, and
    whether both could be read (an unreadable venue counts as Live)."""
    current = current_venue()
    if current is None:
        return None, False, False
    try:
        from sim.mode import is_replay_desk

        edge = not bool(is_replay_desk())
    except Exception:
        logger.warning("bot: the Sim live edge is unreadable -- it counts as a replay", exc_info=True)
        return current, False, True
    return current, edge, True


def assert_not_live() -> None:
    """ADR 042 J: the bot API never touches Live, a venue Nova cannot read, or a replay desk."""
    from constants_sim import DESK_PRACTICE_VENUES

    venue, edge, readable = venue_state()
    if not readable or venue is None:
        why = "Nova cannot read the desk's venue, so it counts as Live"
    elif venue not in DESK_PRACTICE_VENUES:
        raise BotError(BOT_LIVE_NOT_BUILT_TEXT, 409, BOT_REASON_LIVE_NOT_BUILT)
    elif not edge:
        why = "a Sim replay: the bot API trades Paper and Sim at its live edge"
    else:
        return
    raise BotError(f"{BOT_LIVE_NOT_BUILT_TEXT} ({why})", 409, BOT_REASON_LIVE_NOT_BUILT)


def assert_not_dark(row: dict[str, Any] | None = None) -> dict[str, Any]:
    current = row or load_session()
    if int(current.get("level") or 0) <= BOT_LEVEL_OFF:
        raise BotError("bot is Level 0 -- fully dark", 409, BOT_REASON_L0_DARK)
    return current


def assert_can_fire(row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every check before a send, the first that fails raising: the venue, the level, the door (closed until the
    brain, ADR 072), the padlock and the brain's heartbeat."""
    from ibkr.trading_allowed import require_places_allowed

    assert_not_live()
    current = assert_not_dark(row)
    if int(current.get("level") or 0) < BOT_LEVEL_STRATEGY:
        raise BotError("Level 1 Eyes cannot place, cancel, or flatten -- human places", 409, BOT_REASON_L1_NO_FIRE)
    if not is_desk_active(current):
        raise BotError(BOT_BRAIN_DOOR_CLOSED_TEXT, 409, BOT_REASON_NOT_ACTIVE)
    require_places_allowed()          # the desk padlock (BOT_TRADING_LOCKED)
    assert_fresh_heartbeat(current)
    return current


def loss_limit(venue: str | None) -> dict[str, Any] | None:
    """The daily loss limit's No new buys for a bot entry on ``venue`` -- the Account line or the Bots line
    (ADR 056, ADR 061) -- or None while entries are open.

    One that cannot be read counts as holding (logged): an unknown is never read as open."""
    try:
        from constants_loss_limit import LOSS_LIMIT_LINE_BOTS
        from loss_limit.gate import stopped

        return stopped(venue, actor=LOSS_LIMIT_LINE_BOTS)
    except Exception as exc:
        logger.warning("bot: the daily loss limit could not be read -- entries count as stopped", exc_info=True)
        return {"text": f"the daily loss limit could not be read ({type(exc).__name__}): no new bot entry",
                "until": None, "tripped_at": None, "loss": None, "limit_usd": None}
