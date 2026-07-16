"""Ticker snapshot port — quote-panel price payload for one symbol."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TickerSnapshotPort(Protocol):
    """Narrow port: one symbol's price snapshot for the quote panel."""

    def fetch_snapshot(self, symbol: str) -> dict: ...
