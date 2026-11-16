"""The localhost bot API (ADR 016): the brain's door to be (ADR 072), the bot session and the bot audit stream.

ADR 072 retired Nova's own bot (ADR 030, ADR 042), Auto-entry and the Live Trader: the strategies only watch. What
stays is the session file (each venue's dial, its sleeve and the brain's claim), the bot API's door (``actions``,
refused until the brain is built), its working-order TTL, the commission hold, Flatten's close path and the audit
stream. Brain-agnostic; never a second order door.
"""
from __future__ import annotations

from bot.rewind import reset_for_tests as _reset_rewind
from bot.session import get_session
from bot.session import reset_for_tests as _reset_session


def reset_for_tests() -> None:
    """Forget persisted session state and the process-local rewind notice."""
    _reset_session()
    _reset_rewind()


__all__ = ["get_session", "reset_for_tests"]
