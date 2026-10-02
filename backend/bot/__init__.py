"""Localhost bot API (ADR 016) and Nova's own bot (ADR 030, ADR 042). Brain-agnostic; never a second order door."""
from __future__ import annotations

from bot.rewind import reset_for_tests as _reset_rewind
from bot.session import get_session
from bot.session import reset_for_tests as _reset_session


def reset_for_tests() -> None:
    """Forget persisted session state, the process-local rewind notice, stock mode's memory
    (the bot list's owner, ADR 042) and the triggers audit's journal tail (ADR 043)."""
    _reset_session()
    _reset_rewind()
    from stock_mode import store as _stock_mode

    _stock_mode.reset_for_tests()
    from bot import trigger_inputs

    trigger_inputs.reset_for_tests()


__all__ = ["get_session", "reset_for_tests"]
