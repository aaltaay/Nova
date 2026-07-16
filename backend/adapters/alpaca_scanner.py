"""Alpaca discovery / movers adapter — used only when discovery=alpaca."""
from __future__ import annotations

import logging
import time

import requests

from alpaca import ALPACA_DATA_URL as _DATA_URL, _alpaca_headers, _env, _try_fallback_to_iex
from health_status import ping_health
from runtime_state import get_runtime_state
from scanner import _compute_gappers, _fetch_snapshots
from universe import get_tradable_symbols

logger = logging.getLogger(__name__)

# Short-lived cache so get_gainers + get_losers share one screener HTTP call.
_MOVERS_TTL_SEC = 2.0
_movers_cache: tuple[float, list[dict], list[dict]] | None = None


class AlpacaDiscoveryAdapter:
    """Implements ``DiscoveryPort`` for discovery=alpaca."""

    def get_gappers(self) -> list[dict]:
        headers = _alpaca_headers()
        if not headers:
            return []
        base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
        if not ping_health(base_url, headers):
            return []
        symbols = get_tradable_symbols(base_url, headers)
        if not symbols:
            return []
        snaps = _fetch_snapshots(symbols, headers)
        if not snaps and _try_fallback_to_iex("snapshot fetch returned empty on discovery scan"):
            snaps = _fetch_snapshots(symbols, headers)
        return list(_compute_gappers(snaps) or [])


class AlpacaMoversAdapter:
    """Implements ``MoversPort`` for discovery=alpaca (raw screener rows)."""

    def get_gainers(self) -> list[dict]:
        gainers, _ = self._fetch_movers()
        return gainers

    def get_losers(self) -> list[dict]:
        _, losers = self._fetch_movers()
        return losers

    def _fetch_movers(self) -> tuple[list[dict], list[dict]]:
        global _movers_cache
        now = time.monotonic()
        if _movers_cache is not None and (now - _movers_cache[0]) < _MOVERS_TTL_SEC:
            return _movers_cache[1], _movers_cache[2]

        headers = _alpaca_headers()
        if not headers:
            return [], []
        base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
        if not ping_health(base_url, headers):
            return [], []
        state = get_runtime_state()
        try:
            resp = requests.get(
                f"{_DATA_URL}/v1beta1/screener/stocks/movers",
                headers=headers,
                params={"top": min(state.config.top_n, 50)},
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("Alpaca movers API returned %s", resp.status_code)
                return [], []
            payload = resp.json()
            gainers = list(payload.get("gainers", []) or [])
            losers = list(payload.get("losers", []) or [])
            _movers_cache = (now, gainers, losers)
            return gainers, losers
        except Exception:
            logger.warning("Alpaca movers API error", exc_info=True)
            return [], []
