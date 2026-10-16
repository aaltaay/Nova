"""On flows up (operator ask 2026-10-16): a bot's own key turned on turns its family's key and the Bot switch on.

"I don't want to be controlling 100 manual switches": turning a TraderTV host's Bot key on turns the LiveTrader Bots
key on, and the header's Bot switch; turning a strategy On does the same with the Strategy Bots key; turning a family
key on turns the Bot switch on. Off never flows: each key goes off only where it is pressed, and an upper key off still
stops every bot under it (bot.md, "The three keys"). The padlock is not part of it: nothing here unlocks or reads it --
locked, no one places an order, whatever the keys say.

A parent that cannot follow (Live, a replay desk, an unreadable keys file) stays as it is: the press that asked still
counts, and the parent's own ``why_off`` says why it did not turn on. Owner: this module (the order of the steps).
"""
from __future__ import annotations

import logging

from bot.errors import BotError

logger = logging.getLogger(__name__)


def switch_on() -> tuple[str | None, str | None]:
    """Turn the Bot switch on if it can. ``(token, why_not)``: the new Activate token when it turned on, else why it
    did not follow (None when it was already on)."""
    from bot import switch

    try:
        return switch.turn(True), None
    except BotError as exc:
        logger.info("bot cascade: the Bot switch did not follow (%s): %s", exc.reason, exc.message)
        return None, exc.message


def family_on(family: str) -> tuple[str | None, str | None]:
    """Turn ``family``'s key on, then the Bot switch. ``(token, why_not)`` as ``switch_on``."""
    from bot import family_keys

    try:
        family_keys.turn(family, True)
    except BotError as exc:
        logger.info("bot cascade: the %s key did not follow (%s): %s", family, exc.reason, exc.message)
        return None, exc.message
    return switch_on()
