"""
Scanner REST routes — gappers, movers, afterhours, catalysts, history.

Extracted from ``main.py`` — all handlers read from main.py's in-memory caches
via lazy import and return immediately (no blocking I/O).

Endpoints:
  GET /api/gappers
  GET /api/movers
  GET /api/afterhours
  GET /api/news-catalysts
  GET /api/history/dates
  GET /api/history/{cache_type}/{date}
"""
from __future__ import annotations

import re

from fastapi import APIRouter

import exchanges as _exchanges
import hod_momo as _hod_momo
from alpaca import _get_feed
from cache import list_history_dates, load_snapshot_for_date

router = APIRouter(tags=["scan"])


def _m():
    """Lazy accessor for main.py module to avoid circular imports at load time."""
    import main as _main
    return _main


def _strip_blocked(rows: list[dict]) -> list[dict]:
    """Remove blocklisted symbols and attach listing ``exchange`` to each row."""
    out = [r for r in rows if not _hod_momo.is_blocked(r.get("symbol", ""))]
    return _exchanges.attach_exchanges(out)


@router.get("/api/gappers")
def get_gappers():
    """Pre-market gapper list. Returns cached data instantly."""
    m = _m()
    return {
        "rev": m._NOVA_REV,
        "mode": m._current_mode,
        "health": m._cached_health,
        "data_feed": _get_feed(),
        "gappers": _strip_blocked(m._gapper_cache),
        "last_scan": m._gapper_cache_ts,
    }


@router.get("/api/movers")
def get_movers():
    """Top gainers and losers. Returns cached data instantly."""
    m = _m()
    return {
        "rev": m._NOVA_REV,
        "mode": m._current_mode,
        "health": m._cached_health,
        "gainers": _strip_blocked(m._gainer_cache),
        "losers": _strip_blocked(m._loser_cache),
        "last_scan": m._gainer_cache_ts,
    }


@router.get("/api/afterhours")
def get_afterhours():
    """After-hours gapper list (4–8 PM ET)."""
    m = _m()
    return {
        "rev": m._NOVA_REV,
        "mode": m._current_mode,
        "health": m._cached_health,
        "afterhours": _strip_blocked(m._afterhours_cache),
        "last_scan": m._afterhours_cache_ts,
    }


@router.get("/api/news-catalysts")
def get_news_catalysts():
    """News-driven catalyst list."""
    m = _m()
    return {
        "rev": m._NOVA_REV,
        "mode": m._current_mode,
        "health": m._cached_health,
        "catalysts": _strip_blocked(m._news_catalyst_cache),
        "last_scan": m._news_catalyst_cache_ts,
    }


@router.get("/api/scan/integrity")
def get_scan_integrity():
    """Fail-loud scanner cache / feed integrity."""
    from integrity_live import build_scanner_integrity_report
    return build_scanner_integrity_report()


@router.get("/api/integrity")
def get_all_integrity():
    """Combined HOD + scanner integrity (CLI / banner)."""
    from integrity_live import build_all_integrity_report
    return build_all_integrity_report()


@router.get("/api/history/dates")
def get_history_dates(type: str = "gappers"):
    """Return available past dates for a cache type. ?type=gappers|movers|afterhours"""
    if type not in {"gappers", "movers", "afterhours"}:
        return {"dates": []}
    return {"dates": list_history_dates(type)}


@router.get("/api/history/{cache_type}/{date}")
def get_history_snapshot(cache_type: str, date: str):
    """Return a historical snapshot for a specific cache type and date (YYYY-MM-DD)."""
    if cache_type not in {"gappers", "movers", "afterhours"}:
        return {}
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return {}
    return load_snapshot_for_date(cache_type, date)
