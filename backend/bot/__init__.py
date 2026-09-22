"""Localhost bot API (ADR 016). Brain-agnostic; never a second order door."""
from __future__ import annotations

from bot.rewind import reset_for_tests as _reset_rewind
from bot.session import get_session
from bot.session import reset_for_tests as _reset_session


def reset_for_tests() -> None:
    """Forget persisted session state and the process-local rewind notice."""
    _reset_session()
    _reset_rewind()


__all__ = ["get_session", "reset_for_tests"]
