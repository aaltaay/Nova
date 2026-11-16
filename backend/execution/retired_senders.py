"""The retired senders (ADR 072): no strategy bot, Auto-entry, Approve, Nova exit, Live Trader or bot API order.

Nova has three traders -- you, Claude and the brain. The strategies only watch. The door refuses any new order whose
origin is a retired sender's, or any bot-sourced order that is not Claude's, in words. A protective source (a close,
KILL, a cancel) still goes, so a share a retired sender still holds can always be closed and its orders cancelled.
"""
from __future__ import annotations

from typing import Any

from constants_nova_os import RETIRED_SENDER_OPS, RETIRED_SENDER_ORIGINS
from ibkr import safety as _safety

_NAMES = {
    "bot": "The strategy bot",
    "auto_entry": "Auto-entry",
    "approve": "Approve",
    "nova_exit": "Nova's exit",
    "live_trader": "The Live Trader",
    "bot_api": "The bot API",
}
_AI_TRADERS = ("claude", "brain")   # their own door: a switched-off one is ``traders.door``'s


def refusal(cmd: Any) -> str | None:
    """Why the door refuses this order from a retired sender, or None."""
    if cmd.operation not in RETIRED_SENDER_OPS or cmd.source in _safety.PROTECTIVE_SOURCES:
        return None
    origin = cmd.origin
    if origin in _AI_TRADERS:
        return None
    if origin in RETIRED_SENDER_ORIGINS or cmd.source == "bot":
        who = _NAMES.get(str(origin), "A bot")
        if origin == "bot_api":
            return (f"{who} sends nothing until it becomes the brain's door (ADR 072). Nova has three traders: you, "
                    "Claude and the brain.")
        return (f"{who} is retired (ADR 072): the strategies only watch, and Nova has three traders -- you, Claude "
                "and the brain. Nothing was sent.")
    return None
