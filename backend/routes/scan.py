"""
Scanner REST routes — gappers, movers, afterhours, catalysts, history.

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
from constants import NOVA_API_REV
from integrations_health import health_with_integrations
from runtime_state import get_runtime_state

router = APIRouter(tags=["scan"])


def _strip_blocked(rows: list[dict]) -> list[dict]:
    """Remove blocklisted symbols and attach listing ``exchange`` to each row."""
    out = [r for r in rows if not _hod_momo.is_blocked(r.get("symbol", ""))]
    return _exchanges.attach_exchanges(out)


def _scan_health() -> dict:
    return health_with_integrations(get_runtime_state().cached_health)


@router.get("/api/gappers")
def get_gappers():
    """Pre-market gapper list. Returns cached data instantly."""
    state = get_runtime_state()
    return {
        "rev": NOVA_API_REV,
        "mode": state.current_mode,
        "health": _scan_health(),
        "data_feed": _get_feed(),
        "gappers": _strip_blocked(state.gapper_cache),
        "last_scan": state.gapper_cache_ts,
    }


@router.get("/api/movers")
def get_movers():
    """Top gainers and losers. Returns cached data instantly."""
    state = get_runtime_state()
    return {
        "rev": NOVA_API_REV,
        "mode": state.current_mode,
        "health": _scan_health(),
        "gainers": _strip_blocked(state.gainer_cache),
        "losers": _strip_blocked(state.loser_cache),
        "last_scan": state.gainer_cache_ts,
    }


@router.get("/api/afterhours")
def get_afterhours():
    """After-hours gapper list (4–8 PM ET)."""
    state = get_runtime_state()
    return {
        "rev": NOVA_API_REV,
        "mode": state.current_mode,
        "health": _scan_health(),
        "afterhours": _strip_blocked(state.afterhours_cache),
        "last_scan": state.afterhours_cache_ts,
    }


@router.get("/api/news-catalysts")
def get_news_catalysts():
    """News-driven catalyst list."""
    state = get_runtime_state()
    return {
        "rev": NOVA_API_REV,
        "mode": state.current_mode,
        "health": _scan_health(),
        "catalysts": _strip_blocked(state.news_catalyst_cache),
        "last_scan": state.news_catalyst_cache_ts,
    }


@router.get("/api/scan/integrity")
def get_scan_integrity():
    """Fail-loud scanner cache / feed integrity."""
    from integrity_live import build_scanner_integrity_report
    return build_scanner_integrity_report()


@router.get("/api/integrity")
def get_all_integrity():
    """Combined HOD + scanner integrity (CLI / banner)."""
    from integrity_live import build_all_integrity_report, get_cached_integrity_report

    cached = get_cached_integrity_report()
    if cached is not None:
        return cached
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
