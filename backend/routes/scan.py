"""
Scanner REST routes — gappers, movers, afterhours, catalysts, large cap, history.

Endpoints:
  GET  /api/gappers
  GET  /api/movers
  GET  /api/afterhours
  GET  /api/large-cap
  GET  /api/large-cap/config
  POST /api/large-cap/config
  GET  /api/large-cap/alerts
  GET  /api/news-catalysts
  GET  /api/history/dates
  GET  /api/history/{cache_type}/{date}
"""
from __future__ import annotations

import re

from fastapi import APIRouter
from pydantic import BaseModel

import exchanges as _exchanges
import hod_momo as _hod_momo
import mover_enrich_view as _mover_enrich
from alpaca import _get_feed
from cache import list_history_dates, load_snapshot_for_date
from constants import NOVA_API_REV
from integrations_health import health_with_integrations
from runtime_state import get_runtime_state

router = APIRouter(tags=["scan"])


def _with_sim(rows: list[dict]) -> list[dict]:
    from sim.scan import with_sim_row

    return with_sim_row(rows)


def _strip_blocked(rows: list[dict]) -> list[dict]:
    """Remove blocklisted symbols, attach listing ``exchange``, fill reference columns.

    Reference columns (RVOL / float / short interest / market cap / NEWS)
    are decorated here rather than written into the cache so a frozen table's
    stored values stay immutable (ADR 008). See ``mover_enrich_view``.
    """
    out = [r for r in rows if not _hod_momo.is_blocked(r.get("symbol", ""))]
    return _mover_enrich.decorate_rows(_exchanges.attach_exchanges(out))


def _feed_error(state) -> str | None:
    err = (getattr(state, "ibkr_bridge_last_error", "") or "").strip()
    return err or None


def _roster_surface(table) -> dict:
    """Fail-loud roster fields so empty lists cannot look like a quiet market."""
    return {
        "table_state": table.state,
        "roster_ts": table.roster_ts,
    }


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
        "gappers": _with_sim(_strip_blocked(state.gapper_cache)),
        "last_scan": state.gapper_cache_ts,
        **_roster_surface(state.gapper_table),
        "feed_error": _feed_error(state),
    }


@router.get("/api/movers")
def get_movers():
    """Top gainers and losers. Returns cached data instantly."""
    state = get_runtime_state()
    return {
        "rev": NOVA_API_REV,
        "mode": state.current_mode,
        "health": _scan_health(),
        "gainers": _with_sim(_strip_blocked(state.gainer_cache)),
        "losers": _strip_blocked(state.loser_cache),
        "last_scan": state.gainer_cache_ts,
        **_roster_surface(state.gainer_table),
        "loser_table_state": state.loser_table.state,
        "loser_roster_ts": state.loser_table.roster_ts,
        "feed_error": _feed_error(state),
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
        **_roster_surface(state.afterhours_table),
        "feed_error": _feed_error(state),
    }


@router.get("/api/large-cap")
def get_large_cap():
    """Large Cap swing table (ADR 014). Always-live -- never freezes."""
    import large_cap_admin as _lc_admin
    import large_cap_metrics as _lc_metrics

    state = get_runtime_state()
    rows = _strip_blocked(state.large_cap_cache)
    rows = _lc_metrics.compute_scores(rows, weights=_lc_admin.get_score_weights())
    return {
        "rev": NOVA_API_REV,
        "mode": state.current_mode,
        "health": _scan_health(),
        "large_cap": rows,
        "last_scan": state.large_cap_cache_ts,
        **_roster_surface(state.large_cap_table),
        "feed_error": _feed_error(state),
    }


class LargeCapConfigPatch(BaseModel):
    market_cap_above: float | None = None
    above_volume: int | None = None
    scan_code: str | None = None
    stock_type_filter: str | None = None
    score_weights: dict[str, float] | None = None


@router.get("/api/large-cap/config")
def get_large_cap_config():
    import large_cap_admin as _lc_admin

    return _lc_admin.get_config()


@router.post("/api/large-cap/config")
def update_large_cap_config(patch: LargeCapConfigPatch):
    import large_cap_admin as _lc_admin
    from fastapi import HTTPException

    try:
        return _lc_admin.update_config(patch.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/large-cap/alerts")
def get_large_cap_alerts():
    import large_cap_alerts as _lc_alerts

    return {"alerts": _lc_alerts.get_alert_history()}


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


_HISTORY_CACHE_TYPES = {"gappers", "movers", "afterhours", "large_cap"}


@router.get("/api/history/dates")
def get_history_dates(type: str = "gappers"):
    """Return available past dates for a cache type. ?type=gappers|movers|afterhours|large_cap"""
    if type not in _HISTORY_CACHE_TYPES:
        return {"dates": []}
    return {"dates": list_history_dates(type)}


@router.get("/api/history/{cache_type}/{date}")
def get_history_snapshot(cache_type: str, date: str):
    """Return a historical snapshot for a specific cache type and date (YYYY-MM-DD)."""
    if cache_type not in _HISTORY_CACHE_TYPES:
        return {}
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return {}
    return load_snapshot_for_date(cache_type, date)
