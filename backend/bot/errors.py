"""Typed bot refusals -- always loud, never silent."""
from __future__ import annotations


class BotError(Exception):
    def __init__(self, message: str, status_code: int = 409, reason: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason
        self.message = message
