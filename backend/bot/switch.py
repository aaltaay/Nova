"""The Bot switch (ADR 044): one per venue, on the desk in place of the master dial and Activate.

- **ON** (``turn(True)``) puts the desk venue's master ``level`` at Strategy and activates, in one
  step. It is refused like Activate (``bot.activation.refusal``, with Activate's codes):
  ``BOT_LIVE_NOT_BUILT``, ``BOT_REPLAY_DESK``, ``BOT_VENUE_UNKNOWN`` and ``BOT_NO_SETUP_AT_STRATEGY``
  (no strategy is On). A refusal changes nothing.
- **ON needs the padlock unlocked** (``bot.padlock_gate``, operator decision 2026-10-20, replacing 2026-10-16's "ON
  neither unlocks nor needs it"): ON over a locked padlock is refused ``BOT_PADLOCK_LOCKED`` and the desk asks to
  unlock it; ON never unlocks it by itself. Locking it later leaves the switch on: no one places an order while it is
  locked -- the bots' gates read it before every send -- and the desk's switch reads LOCKED until it is unlocked.
- **On flows up** (``bot.cascade``, operator ask 2026-10-16): a strategy turned On, a host's key turned on or a
  family key turned on turns this switch on, by the same rules as a press.
- **OFF** (``turn(False)``) deactivates (``deactivated.reason: "operator"``) and puts the master at
  Eyes, so the strategies at Eyes or On keep proposing. While it is off no bot places any order, not even a
  sell (operator decision 2026-10-15; bot.md, "The three keys"): turning it off sells nothing. No loss limit
  turns it off (ADR 056).
- It is the top of three keys, in the header beside the padlock: under it each family has its key
  (``bot.family_keys``) and each bot its own.
- Each change is one ``bot_switch`` audit line, ``inputs: {on, from_level, to_level}``; pressing the
  switch into the state it is already in changes nothing and writes nothing.
- ``view(row)`` is the session view's ``bot_on`` (active with the master at Strategy) and
  ``switch: {on, venue, why_off}``.

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
)

logger = logging.getLogger(__name__)
_OFF_TEXT = "the bot is off: turn it on to let Nova buy the go triggers of the strategies that are On"


def is_on(row: dict[str, Any]) -> bool:
    """The switch reads ON: Activate on with the master at Strategy."""
    from bot.setup_levels import master

    return is_desk_active(row) and master(row) >= BOT_LEVEL_STRATEGY


def refusal(row: dict[str, Any]) -> BotError | None:
    """Why ON is refused now -- Activate's rules with the master already at Strategy, the padlock's included
    (``bot.padlock_gate``) -- in the switch's words."""
    trial = dict(row)
    trial["level"] = BOT_LEVEL_STRATEGY
    refused = activation.refusal(trial)
    if refused is None:
        return None
    message = refused.message
    if refused.reason == BOT_REASON_NO_SETUP_AT_STRATEGY:
        message = "no strategy is On and no Live Trader key is on -- turn one On, then turn the bot on"
    return BotError(message, refused.status_code, refused.reason)


def turn(on: bool) -> str | None:
    """Turn the bot on or off. Returns the new Activate token when it turned on (None otherwise);
    raises ``BotError`` with Activate's code when ON is refused."""
    from bot.setup_levels import master

    row = load_session()
    before = master(row)
    if on:
        if is_on(row):
            return None
        refused = refusal(row)
        if refused is not None:
            raise refused
        row["level"] = BOT_LEVEL_STRATEGY
        save_session(row)
        token = issue_arm_token()
        _audit(True, before, BOT_LEVEL_STRATEGY)
        return token
    if not is_desk_active(row) and before == BOT_LEVEL_EYES:
        return None
    activation.deactivate(row, "operator")
    row["level"] = BOT_LEVEL_EYES
    save_session(row)
    _audit(False, before, BOT_LEVEL_EYES)
    return None


def _audit(on: bool, before: int, after: int) -> None:
    from bot.audit import record

    if on:
        said = "the bot is on: Nova may buy the go triggers of the strategies that are On"
    else:
        said = "the bot is off: Eyes keep proposing, no bot places any order, not even a sell"
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
    said = activation.stamp_text(stamp) if isinstance(stamp, dict) else None
    return said or _OFF_TEXT


def view(row: dict[str, Any], venue: str | None) -> dict[str, Any]:
    """``{bot_on, switch: {on, venue, why_off}}`` for the session view."""
    on = is_on(row)
    return {"bot_on": on, "switch": {"on": on, "venue": venue, "why_off": why_off(row)}}
