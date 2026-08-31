"""Finnhub company logos for the Earnings tab (profile2 ``logo`` URL).

Owner of ``EARNINGS_LOGO_CACHE_FILE`` (persisted-state.mdc). Invalidation:
per-entry hit/miss TTL, or ``EARNINGS_LOGO_SCHEMA_VERSION`` bump.

``/calendar/earnings`` has no logos -- each symbol needs
``GET /stock/profile2``. Read path is cache-only (never blocks HTTP on
Finnhub). ``warm()`` paces background fetches so free-tier rate limits
(~60/min) are not blown when a week/month view queues dozens of names.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

import requests

from constants import (
    EARNINGS_LOGO_CACHE_FILE,
    EARNINGS_LOGO_FETCH_PACING_SEC,
    EARNINGS_LOGO_HIT_TTL_SEC,
    EARNINGS_LOGO_HTTP_TIMEOUT_SEC,
    EARNINGS_LOGO_MISS_TTL_SEC,
    EARNINGS_LOGO_SCHEMA_VERSION,
    FINNHUB_PROFILE2_URL,
)

logger = logging.getLogger(__name__)

# symbol -> {"logo_url": str|None, "ts": float}
_entries: dict[str, dict] | None = None
_lock = threading.Lock()
_pending: set[str] = set()
_worker: threading.Thread | None = None


def _ensure_loaded() -> None:
    global _entries
    if _entries is not None:
        return
    _entries = {}
    try:
        with open(EARNINGS_LOGO_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return
    except Exception:
        logger.warning("earnings_logos: disk cache unreadable", exc_info=True)
        return
    if int(data.get("schema_version") or 0) != EARNINGS_LOGO_SCHEMA_VERSION:
        logger.warning(
            "earnings_logos: refusing cache with unknown schema_version=%s",
            data.get("schema_version"),
        )
        return
    raw = data.get("entries")
    if isinstance(raw, dict):
        for sym, entry in raw.items():
            if isinstance(entry, dict) and isinstance(sym, str):
                _entries[sym.strip().upper()] = entry


def _persist() -> None:
    if _entries is None:
        return
    try:
        directory = os.path.dirname(EARNINGS_LOGO_CACHE_FILE)
        os.makedirs(directory, exist_ok=True)
        tmp = EARNINGS_LOGO_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "schema_version": EARNINGS_LOGO_SCHEMA_VERSION,
                    "entries": _entries,
                },
                f,
            )
        os.replace(tmp, EARNINGS_LOGO_CACHE_FILE)
    except Exception:
        logger.warning("earnings_logos: failed to persist cache", exc_info=True)


def _fresh(entry: dict, now: float) -> bool:
    ts = float(entry.get("ts") or 0.0)
    age = now - ts
    if entry.get("logo_url"):
        return age < EARNINGS_LOGO_HIT_TTL_SEC
    return age < EARNINGS_LOGO_MISS_TTL_SEC


def get_cached_logo_url(symbol: str) -> str | None:
    """Cache-only logo URL. Never hits the network."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    with _lock:
        _ensure_loaded()
        assert _entries is not None
        entry = _entries.get(sym)
        if not entry or not _fresh(entry, time.time()):
            return None
        url = entry.get("logo_url")
        return url if isinstance(url, str) and url.strip() else None


def _fetch_one(symbol: str, api_key: str) -> str | None:
    try:
        resp = requests.get(
            FINNHUB_PROFILE2_URL,
            params={"symbol": symbol, "token": api_key},
            timeout=EARNINGS_LOGO_HTTP_TIMEOUT_SEC,
        )
    except Exception:
        logger.warning("earnings_logos: profile2 failed for %s", symbol, exc_info=True)
        return None
    if resp.status_code != 200:
        logger.warning(
            "earnings_logos: profile2 HTTP %s for %s", resp.status_code, symbol,
        )
        return None
    try:
        payload = resp.json()
    except Exception:
        return None
    url = payload.get("logo") if isinstance(payload, dict) else None
    if isinstance(url, str) and url.strip().startswith("http"):
        return url.strip()
    return None


def warm(symbols: list[str] | set[str]) -> None:
    """Queue symbols for a paced background profile2 logo warm."""
    global _worker
    api_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not api_key:
        return
    syms = {s.strip().upper() for s in symbols if s and s.strip()}
    if not syms:
        return
    now = time.time()
    with _lock:
        _ensure_loaded()
        assert _entries is not None
        need = {
            s for s in syms
            if s not in _entries or not _fresh(_entries[s], now)
        }
        if not need:
            return
        _pending.update(need)
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(
            target=_drain, args=(api_key,), daemon=True, name="earnings_logo_warm",
        )
        _worker.start()


def _drain(api_key: str) -> None:
    global _worker
    while True:
        with _lock:
            if not _pending:
                _worker = None
                return
            symbol = sorted(_pending)[0]
            _pending.discard(symbol)
        url = _fetch_one(symbol, api_key)
        with _lock:
            _ensure_loaded()
            assert _entries is not None
            _entries[symbol] = {"logo_url": url, "ts": time.time()}
            _persist()
        time.sleep(EARNINGS_LOGO_FETCH_PACING_SEC)


def reset_for_testing() -> None:
    """Test-only: clear memory cache and queue (does not delete disk)."""
    global _entries, _worker
    with _lock:
        _entries = None
        _pending.clear()
        _worker = None
