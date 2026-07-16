"""IBKR discovery / movers adapter — never falls back to Alpaca prices."""
from __future__ import annotations

from ibkr import discovery as _ibkr_discovery
from ibkr_bridge import run_ibkr


class IbkrScannerAdapter:
    """Implements ``DiscoveryPort`` + ``MoversPort`` for discovery=ibkr."""

    def get_gappers(self) -> list[dict]:
        return list(run_ibkr(_ibkr_discovery.get_gappers()) or [])

    def get_gainers(self) -> list[dict]:
        return list(run_ibkr(_ibkr_discovery.get_gainers()) or [])

    def get_losers(self) -> list[dict]:
        return list(run_ibkr(_ibkr_discovery.get_losers()) or [])
