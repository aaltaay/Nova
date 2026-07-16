"""Alpaca ticker snapshot adapter — used only when discovery=alpaca."""
from __future__ import annotations

from ticker_alpaca import fetch_ticker_snapshot


class AlpacaTickerSnapshotAdapter:
    """Implements ``TickerSnapshotPort`` for discovery=alpaca."""

    def __init__(self, headers: dict, feed: str) -> None:
        self._headers = headers
        self._feed = feed

    def fetch_snapshot(self, symbol: str) -> dict:
        return fetch_ticker_snapshot(symbol, self._headers, self._feed)
