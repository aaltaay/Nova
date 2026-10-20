"""No bot turns on while the desk padlock is locked -- the one rule, for every bot (operator decision 2026-10-20).

"If we activate any of the bots, it shows us a screen that says, do you want to unlock the lock? ... not just the
livetrader bots, ALL bots, strategy bots and future bots. Single source of truth." Before this, a bot could read ON
over a locked padlock and skip every trade (2026-10-20: the Bot switch on at 08:27 over a padlock the venue change had
locked, the Live Trader skipping IBIT, DRAM, CRWV until the padlock was unlocked).

Every press that turns a bot on calls ``require_unlocked()`` before it changes anything: the Bot switch
(``bot.switch`` through ``bot.activation.refusal``), Activate, a family key (``POST /api/bot/session/keys``), a
strategy set On (``PATCH /api/bot/session {setup_levels}``) and a TraderTV host's Bot key
(``PATCH /api/bot/live-traders/{name} {key: true}``). A bot added later turns on through one of these, or its own
press calls this first. Refused: 409 ``BOT_PADLOCK_LOCKED``, nothing changed; the desk asks "Unlock the padlock and
turn it on?" (``frontend/src/bot/padlockPrompt.ts``), unlocks through ``POST /api/ibkr/arm`` and presses again.

Only where a bot trades (Paper, Sim at its edge or with a replay loaded): on Live or an unreadable venue the bot trades
nothing and the other rules refuse, so this never asks for the Live PIN. Turning off is never refused. Locking the
padlock after a bot is on leaves its keys as they are (2026-10-16); no one places an order while it is locked, and
the desk's Bot switch reads LOCKED, never ON. Owner: this module (the rule and its words).
"""
from __future__ import annotations

from bot.errors import BotError
from constants_bot import BOT_REASON_PADLOCK_LOCKED


def refusal() -> BotError | None:
    """Why no bot may turn on now because of the padlock, else None (unlocked, or a venue where no bot trades)."""
    from bot import activation

    if activation.venue_block(*activation.venue_state()) is not None:
        return None
    ok, why = activation.padlock()
    if ok:
        return None
    return BotError(f"the desk padlock is locked ({why}) -- unlock it to turn a bot on: no bot places an order while "
                    "it is locked", 409, BOT_REASON_PADLOCK_LOCKED)


def require_unlocked() -> None:
    """Raise ``BOT_PADLOCK_LOCKED`` while the padlock is locked on a venue where bots trade."""
    refused = refusal()
    if refused is not None:
        raise refused
