"""
Universe helpers — tradable assets cache, avg-volume, gapper enrich, HOD watch set.
"""
from __future__ import annotations

import logging
import time
from datetime import date

import requests

import exchanges as _exchanges
import hod_momo as _hod_momo
import hod_momo_universe as _hod_uni
from alpaca import ALPACA_DATA_URL as _DATA_URL, _alpaca_headers, _env
from constants import (
    ASSETS_CACHE_TTL_SEC,
    HOD_MOMO_FOCUS_REFRESH_SEC,
    HOD_MOMO_UNIVERSE_INTERVAL_SEC,
    HOD_MOMO_UNIVERSE_MODE,
    HOD_MOMO_UNIVERSE_MODE_BROAD,
    HOD_MOMO_UNIVERSE_MODE_FOCUS,
    SCAN_EXCHANGES,
)
from fundamentals import (
    _fundamentals_cache,
    fetch_fundamentals_batch as _fetch_fundamentals_batch,
)
from scanner import _is_common_stock, fetch_avg_volume_batch
from runtime_state import get_runtime_state
from websocket import mark_resub as _ws_mark_resub

logger = logging.getLogger(__name__)


def invalidate_universe_cache() -> None:
    """Force the next get_tradable_symbols call to re-fetch (e.g. after blocklist change)."""
    state = get_runtime_state()
    state.assets_cache_ts = 0.0
    _exchanges.clear()
    _ws_mark_resub()


def reset_scan_caches() -> None:
    """Invalidate scanner discovery caches — called by routes/health update_config."""
    state = get_runtime_state()
    state.assets_cache_ts = 0.0
    state.assets_cache_set = set()
    state.last_discovery_ts = 0.0


def get_tradable_symbols(base_url: str, headers: dict) -> list[str]:
    """Fetch common-stock symbols for scanning, cached for one hour."""
    state = get_runtime_state()
    now = time.monotonic()
    if state.assets_cache and (now - state.assets_cache_ts) < ASSETS_CACHE_TTL_SEC:
        return state.assets_cache
    try:
        all_assets: list[dict] = []
        for exchange in SCAN_EXCHANGES:
            resp = requests.get(
                f"{_DATA_URL}/v2/assets",
                headers=headers,
                params={"status": "active", "asset_class": "us_equity", "exchange": exchange},
                timeout=20,
            )
            if resp.status_code == 200:
                all_assets.extend(resp.json())
        if not all_assets:
            return state.assets_cache
        kept = [a for a in all_assets if _is_common_stock(a)]
        symbols = [a["symbol"] for a in kept]
        _exchanges.update_from_assets(kept)
        state.assets_cache = symbols
        state.assets_cache_set = set(symbols)
        state.assets_cache_ts = now
        return state.assets_cache
    except Exception:
        logger.warning("get_tradable_symbols failed — returning stale cache", exc_info=True)
        return state.assets_cache


def ensure_avg_volume(symbols: list[str], headers: dict) -> None:
    """Lazily populate ``_avg_volume_cache`` for any symbols not yet cached today."""
    state = get_runtime_state()
    today = date.today().isoformat()
    if state.avg_volume_date != today:
        state.avg_volume_cache = {}
        state.avg_volume_date = today
    fetch_avg_volume_batch(symbols, headers, state.avg_volume_cache)


def enrich_gappers(gappers: list[dict], news: dict[str, str]) -> list[dict]:
    state = get_runtime_state()
    symbols = [g["symbol"] for g in gappers]
    _fetch_fundamentals_batch(symbols)
    for g in gappers:
        sym = g["symbol"]
        avg_vol = state.avg_volume_cache.get(sym)
        vol = g["volume"]
        g["rel_volume"] = round(vol / avg_vol, 2) if avg_vol and avg_vol > 0 and vol > 0 else None
        g["has_news"] = sym in news
        g["newest_headline_at"] = news.get(sym)
        fund = _fundamentals_cache.get(sym, {})
        g["market_cap"] = fund.get("market_cap")
        g["float"] = fund.get("float_shares")
        g["short_interest"] = fund.get("short_interest")
        g["short_ratio"] = fund.get("short_ratio")
        _exchanges.attach_exchange(g)
    return gappers


def refresh_hod_momo_universe() -> None:
    """Rebuild the HOD Momo trade-watch set and nudge Alpaca WS to resubscribe."""
    state = get_runtime_state()
    now = time.monotonic()
    mode = (HOD_MOMO_UNIVERSE_MODE or HOD_MOMO_UNIVERSE_MODE_FOCUS).strip().lower()
    interval = (
        HOD_MOMO_FOCUS_REFRESH_SEC
        if mode == HOD_MOMO_UNIVERSE_MODE_FOCUS
        else HOD_MOMO_UNIVERSE_INTERVAL_SEC
    )
    if state.hod_momo_universe and (now - state.hod_momo_universe_ts) < interval:
        return

    if mode == HOD_MOMO_UNIVERSE_MODE_BROAD:
        base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
        headers = _alpaca_headers()
        if not headers:
            return
        try:
            symbols = set(get_tradable_symbols(base_url, headers))
        except Exception as exc:
            logger.warning("HOD Momo broad universe refresh failed: %s", exc)
            return
    else:
        try:
            import hod_momo_former as _former

            extras = _former.former_momo_priority_symbols()
        except Exception:
            extras = []
        # ADR 008: watch universe mirrors HOD eligibility exactly — Gappers ∪
        # Gainers ∪ Afterhours ∪ Former Momo. No Losers, no open-ticker
        # priority (open ticker L1 already has its own dedicated owner).
        symbols = _hod_uni.build_focus_universe(
            gapper_rows=state.gapper_cache,
            gainer_rows=state.gainer_cache,
            afterhours_rows=state.afterhours_cache,
            extra_symbols=extras,
            is_blocked=_hod_momo.is_blocked,
        )

    changed = symbols != state.hod_momo_universe
    state.hod_momo_universe = symbols
    state.hod_momo_universe_ts = now
    if changed:
        _ws_mark_resub()
        logger.info(
            "HOD Momo: universe refreshed mode=%s — %d symbols subscribed",
            mode,
            len(state.hod_momo_universe),
        )


def get_hod_momo_universe() -> set[str]:
    """Expose the current HOD Momo universe to hod_momo_enrichment.py."""
    return get_runtime_state().hod_momo_universe
