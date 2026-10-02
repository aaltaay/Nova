"""The Bot switch (ADR 043): one per venue, on the desk in place of the master dial and Activate.

- **ON** (``turn(True)``) puts the desk venue's master ``level`` at Strategy and activates, in one
  step. It is refused like Activate (``bot.activation.refusal``, with Activate's codes):
  ``BOT_LIVE_NOT_BUILT``, ``BOT_REPLAY_DESK``, ``BOT_VENUE_UNKNOWN``, ``BOT_PADLOCK_LOCKED``,
  ``BOT_NO_SETUP_AT_STRATEGY`` (no strategy is On) and ``BOT_TRIP_LATCHED`` unless ``reenable`` --
  which clears the bot trip's latch, as Activate's re-enable does. A refusal changes nothing.
- **OFF** (``turn(False)``) deactivates (``deactivated.reason: "operator"``) and puts the master at
  Eyes, so the strategies at Eyes or On keep proposing. The bot trip leaves it the same way
  (``bot.autonomy.drop_to_eyes``).
- Each change is one ``bot_switch`` audit line, ``inputs: {on, from_level, to_level}``; pressing the
  switch into the state it is already in changes nothing and writes nothing.
- ``view(row)`` is the session view's ``bot_on`` (active with the master at Strategy) and
  ``switch: {on, venue, why_off, latched: {at, pnl, until} | null}``.

The localhost bot API keeps reading ``level``, and ``PATCH /api/bot/session {level}`` and ``POST
/api/bot/session/arm`` keep working. Owner: this module (the rules; the session file is
``bot.persist``'s).
"""
from __future__ import annotations

import logging
from typing import Any

from bot import activation
from bot.arming import is_desk_active, issue_arm_token
from bot.errors import BotError
from bot.persist import load_session, save_session
from constants_bot import (
    BOT_AUDIT_ACTION_SWITCH,
    BOT_LEVEL_EYES,
    BOT_LEVEL_STRATEGY,
    BOT_REASON_NO_SETUP_AT_STRATEGY,
    BOT_REASON_PADLOCK_LOCKED,
    BOT_REASON_TRIP_LATCHED,
)

logger = logging.getLogger(__name__)
_ON_WORDS = "Turn the bot on"
_OFF_TEXT = "the bot is off: turn it on to let Nova buy the go triggers of the strategies that are On"


def is_on(row: dict[str, Any]) -> bool:
    """The switch reads ON: Activate on with the master at Strategy."""
    from bot.setup_levels import master

    return is_desk_active(row) and master(row) >= BOT_LEVEL_STRATEGY


def refusal(row: dict[str, Any], *, reenable: bool = False) -> BotError | None:
    """Why ON is refused now -- Activate's rules with the master already at Strategy -- in the switch's words."""
    trial = dict(row)
    trial["level"] = BOT_LEVEL_STRATEGY
    refused = activation.refusal(trial, reenable=reenable)
    if refused is None:
        return None
    message = refused.message
    if refused.reason == BOT_REASON_NO_SETUP_AT_STRATEGY:
        message = "no strategy is On -- turn one strategy On, then turn the bot on"
    elif refused.reason == BOT_REASON_TRIP_LATCHED:
        message = activation.trip_text(row, _ON_WORDS)
    elif refused.reason == BOT_REASON_PADLOCK_LOCKED:
        message = message.replace("then Activate", "then turn the bot on")
    return BotError(message, refused.status_code, refused.reason)


def turn(on: bool, *, reenable: bool = False) -> str | None:
    """Turn the bot on or off. Returns the new Activate token when it turned on (None otherwise);
    raises ``BotError`` with Activate's code when ON is refused."""
    from bot.setup_levels import master

    row = load_session()
    before = master(row)
    if on:
        if is_on(row) and not reenable:
            return None
        refused = refusal(row, reenable=reenable)
        if refused is not None:
            raise refused
        row["level"] = BOT_LEVEL_STRATEGY
        save_session(row)
        token = issue_arm_token(reenable=reenable)
        _audit(True, before, BOT_LEVEL_STRATEGY, reenable=reenable)
        return token
    if not is_desk_active(row) and before == BOT_LEVEL_EYES:
        return None
    activation.deactivate(row, "operator")
    row["level"] = BOT_LEVEL_EYES
    save_session(row)
    _audit(False, before, BOT_LEVEL_EYES)
    return None


def _audit(on: bool, before: int, after: int, *, reenable: bool = False) -> None:
    from bot.audit import record

    if on:
        said = ("the bot is on: Nova may buy the go triggers of the strategies that are On"
                + (" (the bot trip was re-enabled by you)" if reenable else ""))
    else:
        said = "the bot is off: Eyes keep proposing, Nova buys nothing by itself"
    try:
        record(action=BOT_AUDIT_ACTION_SWITCH, outcome="on" if on else "off", reason=said,
               inputs={"on": on, "from_level": before, "to_level": after})
    except Exception:
        logger.warning("bot audit: the Bot switch (%s) was not recorded", "on" if on else "off", exc_info=True)


def why_off(row: dict[str, Any]) -> str | None:
    """Why the switch reads OFF, and what turns it on (None while it is on)."""
    if is_on(row):
        return None
    refused = refusal(row)
    if refused is not None:
        return refused.message
    stamp = row.get("deactivated")
    if isinstance(stamp, dict) and stamp.get("text"):
        return str(stamp["text"])
    return _OFF_TEXT


def view(row: dict[str, Any], venue: str | None) -> dict[str, Any]:
    """``{bot_on, switch: {on, venue, why_off, latched}}`` for the session view."""
    from bot.clock import soft_latched

    on = is_on(row)
    latched = None
    if soft_latched(row):
        latched = {"at": row.get("soft_breaker_at"), "pnl": row.get("soft_breaker_pnl"),
                   "until": row.get("soft_breaker_until")}
    return {"bot_on": on, "switch": {"on": on, "venue": venue, "why_off": why_off(row), "latched": latched}}
