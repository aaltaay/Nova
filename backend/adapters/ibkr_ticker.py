"""IBKR ticker snapshot adapter — never falls back to Alpaca prices."""
from __future__ import annotations

from ticker_ibkr import fetch_ticker_snapshot_ibkr


class IbkrTickerSnapshotAdapter:
    """Implements ``TickerSnapshotPort`` for discovery=ibkr."""

    def fetch_snapshot(self, symbol: str) -> dict:
        return fetch_ticker_snapshot_ibkr(symbol)
