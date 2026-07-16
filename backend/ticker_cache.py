"""Per-symbol ticker detail caches and WebSocket client registry."""
from __future__ import annotations

_ticker_asset_cache: dict[str, dict] = {}
_ticker_asset_cache_ts: dict[str, float] = {}
_ticker_snapshot_cache: dict[str, dict] = {}
_ticker_snapshot_cache_ts: dict[str, float] = {}
_ticker_slow_cache: dict[str, dict] = {}
_ticker_slow_cache_ts: dict[str, float] = {}

# Maps symbol -> set of active WebSocket connections for that symbol's detail.
_ticker_ws_clients: dict[str, set] = {}


def get_detail_symbols() -> list[str]:
    """Return symbols that currently have live ticker-detail WebSocket connections."""
    return [sym for sym, clients in _ticker_ws_clients.items() if clients]
