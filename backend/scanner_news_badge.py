"""Read-time NEWS-column decoration for IBKR scanner rosters (D-001).

Under ``discovery=ibkr`` the Alpaca movers/discovery runners return before they
can stamp ``has_news`` / ``newest_headline_at``. This module owns a side cache
of today's Alpaca headlines for current roster symbols and stamps them at
serialization time (``mover_enrich_view.decorate_rows``). It never writes into
the frozen roster (ADR 008). Large Cap is in the headline roster so it can
share the Gainers News flame; it is still excluded from HOD admission.

Owner: this module (in-memory only). Invalidation: ET date rollover, or
process start. No disk ``schema_version`` -- the cache is not persisted.
"""
from __future__ import annotations

import asyncio
import logging
import threading

from alpaca import _alpaca_headers
from constants import NEWS_BADGE_INTERVAL_SEC, NEWS_BADGE_SYMBOL_BATCH
from ibkr import scanner_session as _ss
from market import now_et as _now_et
from runtime_state import get_runtime_state
from scanner import _check_news

logger = logging.getLogger(__name__)

_NEWS_TABLES = frozenset({
    _ss.TABLE_GAPPERS,
    _ss.TABLE_GAINERS,
    _ss.TABLE_LOSERS,
    _ss.TABLE_AFTERHOURS,
    _ss.TABLE_LARGE_CAP,
})

_lock = threading.Lock()
_headlines: dict[str, str] = {}
_pending: set[str] = set()
_worker: threading.Thread | None = None
_cache_date: str | None = None
_warned_no_keys = False


def _discovery_ibkr() -> bool:
    from alpaca import _get_discovery_provider
    return _get_discovery_provider() == "ibkr"


def _ensure_today() -> None:
    global _cache_date
    today = _now_et().date().isoformat()
    if _cache_date != today:
        _headlines.clear()
        _cache_date = today


def record(news: dict[str, str] | None) -> None:
    """Merge Alpaca ``{symbol: created_at}`` into today's headline cache."""
    _ensure_today()
    for sym, created in (news or {}).items():
        key = (sym or "").strip().upper()
        if not key or not created:
            continue
        stamp = str(created)
        prev = _headlines.get(key)
        if prev is None or stamp > prev:
            _headlines[key] = stamp


def headline_for(symbol: str) -> str | None:
    _ensure_today()
    key = (symbol or "").strip().upper()
    if not key:
        return None
    return _headlines.get(key)


def stamp_row(entry: dict) -> None:
    """Fill news fields on a copied row. Never call this on a cache row."""
    if entry.get("newest_headline_at"):
        if entry.get("has_news") is None:
            entry["has_news"] = True
        return
    sym = (entry.get("symbol") or "").strip().upper()
    headline = headline_for(sym) if sym else None
    if headline:
        entry["newest_headline_at"] = headline
        entry["has_news"] = True
    elif entry.get("has_news") is None:
        entry["has_news"] = False
        entry["newest_headline_at"] = None


def roster_symbols() -> set[str]:
    """Current scanner-table names, including Large Cap.

    Large Cap shares the Gainers News flame (``newest_headline_at``). HOD
    admission still excludes Large Cap (ADR 008) -- this set is headlines only.
    """
    state = get_runtime_state()
    out: set[str] = set()
    for cache in (
        state.gapper_cache,
        state.gainer_cache,
        state.loser_cache,
        state.afterhours_cache,
        state.large_cap_cache,
    ):
        for row in cache or []:
            sym = (row.get("symbol") or "").strip().upper()
            if sym:
                out.add(sym)
    return out


def on_roster_commit(table: str, rows: list[dict]) -> None:
    """Queue this table's symbols after an IBKR roster commit."""
    if not _discovery_ibkr() or table not in _NEWS_TABLES:
        return
    symbols = {
        (r.get("symbol") or "").strip().upper()
        for r in rows
        if (r.get("symbol") or "").strip()
    }
    _queue(symbols)


def queue_current_roster() -> None:
    if not _discovery_ibkr():
        return
    _queue(roster_symbols())


def _queue(symbols: set[str]) -> None:
    global _worker
    symbols = {s for s in symbols if s}
    if not symbols:
        return
    with _lock:
        _pending.update(symbols)
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(
            target=_drain, daemon=True, name="scanner_news_badge",
        )
        _worker.start()


def _drain() -> None:
    global _worker, _warned_no_keys
    headers = _alpaca_headers()
    if not headers:
        if not _warned_no_keys:
            logger.warning(
                "scanner_news_badge: no Alpaca keys -- NEWS column stays empty",
            )
            _warned_no_keys = True
        with _lock:
            _pending.clear()
            _worker = None
        return
    while True:
        with _lock:
            batch = sorted(_pending)[:NEWS_BADGE_SYMBOL_BATCH]
            for sym in batch:
                _pending.discard(sym)
            if not batch:
                _worker = None
                return
        try:
            record(_check_news(batch, headers))
        except Exception:
            logger.exception(
                "scanner_news_badge: _check_news failed for %d symbol(s)",
                len(batch),
            )


async def refresh_loop() -> None:
    """Re-check current roster headlines so a frozen table can still light NEWS."""
    while True:
        try:
            queue_current_roster()
        except Exception:
            logger.exception("scanner_news_badge: roster refresh failed")
        await asyncio.sleep(NEWS_BADGE_INTERVAL_SEC)


def reset_for_testing() -> None:
    """Test-only: drop in-memory headline state."""
    global _worker, _cache_date, _warned_no_keys
    with _lock:
        _headlines.clear()
        _pending.clear()
        _worker = None
        _cache_date = None
        _warned_no_keys = False
