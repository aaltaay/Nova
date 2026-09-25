"""A refused stock-mode write (ADR 037): ``{detail: {reason, error, field}}``."""
from __future__ import annotations

from typing import Any


class StockModeError(Exception):
    def __init__(self, reason: str, message: str, *, status: int = 409, field: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.status = status
        self.field = field

    def detail(self) -> dict[str, Any]:
        return {"reason": self.reason, "error": self.message, "field": self.field}
