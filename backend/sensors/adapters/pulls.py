"""Sensor 20: resting size filled vs pulled, and pull patterns (ADR 031, ``backend/book_watch/``)."""
from __future__ import annotations

from typing import Any

from sensors.envelope import build_envelope


def read_book_pulls(symbol: str) -> dict[str, Any]:
    from book_watch.view import book_pulls

    data, error = book_pulls(symbol)
    return build_envelope(sensor="book-pulls", symbol=symbol, status="live", data=data, error=error)
