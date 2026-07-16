"""
Ticker detail service module — strangler facade (Phase 8B).

Implementation: ``ticker_cache``, ``ticker_alpaca``, ``ticker_ibkr``,
``ticker_detail``. Price snapshots go through ``ports.ticker`` /
``composition.market_data_providers``. Routes live in ``backend/routes/ticker.py``.

Facade owner: Phase 8B / close-remediation Phase 4.
Removal criterion: no production caller imports private ``_build_*`` /
``_fetch_*`` aliases from this module; prefer ``ticker_detail`` + ports.
"""
from __future__ import annotations

from ticker_alpaca import fetch_ticker_news, pick_prev_close
from ticker_cache import _ticker_ws_clients, get_detail_symbols
from ticker_detail import build_ticker_detail, build_ticker_fast, build_ticker_slow
from ticker_ibkr import find_ibkr_cache_row, fetch_ticker_snapshot_ibkr

# Legacy private names used by routes/tests/callers
_pick_prev_close = pick_prev_close
_fetch_ticker_news = fetch_ticker_news
_find_ibkr_cache_row = find_ibkr_cache_row
_fetch_ticker_snapshot_ibkr = fetch_ticker_snapshot_ibkr
_build_ticker_fast = build_ticker_fast
_build_ticker_slow = build_ticker_slow
_build_ticker_detail = build_ticker_detail

__all__ = [
    "get_detail_symbols",
    "_ticker_ws_clients",
    "_pick_prev_close",
    "_fetch_ticker_news",
    "_find_ibkr_cache_row",
    "_fetch_ticker_snapshot_ibkr",
    "_build_ticker_fast",
    "_build_ticker_slow",
    "_build_ticker_detail",
]
