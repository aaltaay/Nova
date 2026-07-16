"""Select scanner/ticker adapters from the active discovery provider.

Wired only from facades / application entry — never from domain modules.
Explicit provider selection; no silent IBKR↔Alpaca price fallback.
"""
from __future__ import annotations

from alpaca import _alpaca_headers, _get_discovery_provider, _get_feed
from adapters.alpaca_scanner import AlpacaDiscoveryAdapter, AlpacaMoversAdapter
from adapters.alpaca_ticker import AlpacaTickerSnapshotAdapter
from adapters.ibkr_scanner import IbkrScannerAdapter
from adapters.ibkr_ticker import IbkrTickerSnapshotAdapter
from ports.scanner import DiscoveryPort, MoversPort
from ports.ticker import TickerSnapshotPort


def get_discovery_port() -> DiscoveryPort:
    if _get_discovery_provider() == "ibkr":
        return IbkrScannerAdapter()
    return AlpacaDiscoveryAdapter()


def get_movers_port() -> MoversPort:
    if _get_discovery_provider() == "ibkr":
        return IbkrScannerAdapter()
    return AlpacaMoversAdapter()


def get_ticker_snapshot_port(
    headers: dict | None = None,
    feed: str | None = None,
) -> TickerSnapshotPort:
    if _get_discovery_provider() == "ibkr":
        return IbkrTickerSnapshotAdapter()
    return AlpacaTickerSnapshotAdapter(
        headers if headers is not None else (_alpaca_headers() or {}),
        feed if feed is not None else _get_feed(),
    )
