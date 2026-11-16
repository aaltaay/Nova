"""The door refuses a switched-off AI trader's new order (ADR 072 decision 6, ``TRADER_OFF``).

Asked by ``execution.service`` beside the retired senders. A cancel, and a protective source (KILL, Flatten, a
cancel of working orders), always go; so does a trader's own loss line's Auto sell (``loss_limit_claude``,
``loss_limit_brain``), which closes and never opens. A handed stock is the owners' rules' (``OWNERS_TRADERS_STOCK``).
"""
from __future__ import annotations

from typing import Any

from constants_nova_os import RETIRED_SENDER_OPS
from constants_owners import AI_TRADERS, OWNER_NAMES


def refusal(cmd: Any) -> str | None:
    """Why the door refuses this order from Claude or the brain while its switch is Off, or None."""
    from ibkr import safety

    if cmd.operation not in RETIRED_SENDER_OPS or cmd.source in safety.PROTECTIVE_SOURCES:
        return None
    if cmd.origin not in AI_TRADERS:
        return None
    from traders import switches

    if switches.is_on(str(cmd.origin)):
        return None
    name = OWNER_NAMES[str(cmd.origin)]
    return f"{name} is switched off: it sends no new order until you switch it On. Nothing was sent."
