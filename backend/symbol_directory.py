"""Listed-symbol directory: every active US equity listing with its name.

Feeds the header ticker search (``GET /api/symbols/directory``) so the operator
can find a symbol by company name, prefix, wildcard or regex -- not only the
symbols the desk already holds. Listing metadata comes from Alpaca
``/v2/assets`` (Alpaca is listing metadata only; no price is read here).

Unlike the scan universe (``universe.get_tradable_symbols``), nothing is
excluded by kind: ETFs, units and preferreds are real symbols an operator may
want to open. Only non-US-exchange listings (OTC) are left out.

The directory is cached in process for ``SYMBOL_DIRECTORY_TTL_SEC``. A failed
fetch keeps serving the last good directory and says why in ``error``.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

from alpaca import _alpaca_headers, _env
from constants_symbols import (
    SYMBOL_DIRECTORY_EXCHANGES,
    SYMBOL_DIRECTORY_HTTP_TIMEOUT_SEC,
    SYMBOL_DIRECTORY_NO_KEYS_ERROR,
    SYMBOL_DIRECTORY_RETRY_SEC,
    SYMBOL_DIRECTORY_SCHEMA_VERSION,
    SYMBOL_DIRECTORY_SOURCE,
    SYMBOL_DIRECTORY_TTL_SEC,
)

logger = logging.getLogger(__name__)

Entry = tuple[str, str, str]

_lock = threading.Lock()
_entries: list[Entry] = []
_fetched_at: float | None = None  # epoch seconds of the last good fetch
_fetched_mono = 0.0
_error: str | None = None
_error_mono = 0.0


def normalize_assets(assets: list[Any]) -> list[Entry]:
    """Pure: Alpaca asset dicts -> sorted ``(symbol, name, exchange)`` rows.

    Keeps active US equities listed on a desk exchange; one row per symbol.
    """
    allowed = set(SYMBOL_DIRECTORY_EXCHANGES)
    rows: dict[str, Entry] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        symbol = str(asset.get("symbol") or "").strip().upper()
        exchange = str(asset.get("exchange") or "").strip().upper()
        if not symbol or exchange not in allowed:
            continue
        if asset.get("status", "active") != "active":
            continue
        if asset.get("class", "us_equity") != "us_equity":
            continue
        name = " ".join(str(asset.get("name") or "").split())
        rows[symbol] = (symbol, name, exchange)
    return [rows[s] for s in sorted(rows)]


def _fetch() -> list[Entry]:
    headers = _alpaca_headers()
    if not headers:
        raise RuntimeError(SYMBOL_DIRECTORY_NO_KEYS_ERROR)
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    resp = requests.get(
        f"{base_url.rstrip('/')}/v2/assets",
        headers=headers,
        params={"status": "active", "asset_class": "us_equity"},
        timeout=SYMBOL_DIRECTORY_HTTP_TIMEOUT_SEC,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Alpaca /v2/assets answered HTTP {resp.status_code}")
    body = resp.json()
    if not isinstance(body, list):
        raise RuntimeError("Alpaca /v2/assets answered a non-list body")
    return normalize_assets(body)


def refresh(force: bool = False) -> None:
    """Fetch the directory when it is missing or older than the TTL."""
    global _entries, _fetched_at, _fetched_mono, _error, _error_mono
    with _lock:
        now = time.monotonic()
        fresh = _fetched_at is not None and (now - _fetched_mono) < SYMBOL_DIRECTORY_TTL_SEC
        backing_off = _error is not None and (now - _error_mono) < SYMBOL_DIRECTORY_RETRY_SEC
        if not force and (fresh or backing_off):
            return
        try:
            entries = _fetch()
        except Exception as exc:  # network, auth, shape -- keep the last good directory
            logger.warning("symbol directory fetch failed: %s", exc)
            _error = str(exc) or type(exc).__name__
            _error_mono = now
            return
        if not entries:
            _error = "Alpaca /v2/assets listed no symbols"
            _error_mono = now
            logger.warning("symbol directory fetch returned no listings")
            return
        _entries = entries
        _fetched_at = time.time()
        _fetched_mono = now
        _error = None


def snapshot() -> dict[str, Any]:
    """The wire payload (AGENTS.md section 3, "Symbol directory")."""
    with _lock:
        return {
            "schema_version": SYMBOL_DIRECTORY_SCHEMA_VERSION,
            "source": SYMBOL_DIRECTORY_SOURCE,
            "fetched_at": _fetched_at,
            "count": len(_entries),
            "error": _error,
            "symbols": [list(e) for e in _entries],
        }


def reset_for_tests() -> None:
    global _entries, _fetched_at, _fetched_mono, _error, _error_mono
    with _lock:
        _entries = []
        _fetched_at = None
        _fetched_mono = 0.0
        _error = None
        _error_mono = 0.0
