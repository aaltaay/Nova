"""Localhost bot API (ADR 016). Brain-agnostic; never a second order door."""
from __future__ import annotations

from bot.session import get_session, reset_for_tests

__all__ = ["get_session", "reset_for_tests"]
