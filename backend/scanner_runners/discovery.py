"""Pre-market discovery and focus scan orchestration."""
from __future__ import annotations

import logging
import time

from ibkr_bridge import IbkrBridgeError
from scanner_runners._facade import facade

logger = logging.getLogger(__name__)


def run_discovery_scan() -> None:
    """Full universe scan: filter gappers, enrich (Alpaca or IBKR)."""
    from ibkr import scanner_session as _ss
    from runtime_state.state import TABLE_STATE_FROZEN

    sr = facade()
    state = sr.get_runtime_state()
    if state.gapper_table.state == TABLE_STATE_FROZEN:
        logger.info("Gapper discovery skipped — table frozen (ADR 008)")
        return
    headers = sr._alpaca_headers()
    # Price rows come from the composed DiscoveryPort (IBKR or Alpaca).
    try:
        gappers = list(sr.get_discovery_port().get_gappers() or [])
    except IbkrBridgeError as exc:
        # Never wipe a live table because the thread bridge timed out.
        logger.error(
            "Gapper discovery bridge failed — keeping %d cached row(s): %s",
            len(state.gapper_cache),
            exc,
        )
        return

    gapper_syms = [g["symbol"] for g in gappers]
    news: dict = {}
    # Alpaca headers are optional listing/news metadata — never block IBKR prices.
    if headers:
        sr.ensure_avg_volume(gapper_syms, headers)
        news = sr._check_news(gapper_syms, headers)
    gappers = sr.enrich_gappers(gappers, news)

    state.gapper_cache = gappers
    state.gapper_cache_ts = time.time()
    state.last_discovery_ts = time.monotonic()
    _ss.ensure_session_key(state, _ss.TABLE_GAPPERS, source="discovery")
    if gappers:
        state.ibkr_bridge_last_error = ""
    sr.mark_resub()
    sr.save_gapper_snapshot(state.gapper_cache, state.gapper_cache_ts)


def run_focus_scan() -> None:
    """Re-price only current gapper candidates (fast refresh)."""
    sr = facade()
    state = sr.get_runtime_state()
    if not state.gapper_cache:
        run_discovery_scan()
        return
    if sr._get_discovery_provider() == "ibkr":
        return
    headers = sr._alpaca_headers()
    if not headers:
        return

    from constants import SCANNER_MIN_PRICE
    from scanner import _fetch_snapshots, _pick_prev_close, _prune_gappers_below_min

    symbols = [g["symbol"] for g in state.gapper_cache]
    snaps = _fetch_snapshots(symbols, headers)
    if not snaps:
        return
    news = sr._check_news(symbols, headers)

    updated: list[dict] = []
    for g in state.gapper_cache:
        sym = g["symbol"]
        snap = snaps.get(sym)
        if not snap:
            updated.append(g)
            continue
        latest_trade = snap.get("latestTrade") or {}
        daily_bar = snap.get("dailyBar") or {}
        price = latest_trade.get("p") or g["current_price"]
        if price < SCANNER_MIN_PRICE:
            continue
        prev_close = _pick_prev_close(snap) or g["previous_close"]
        volume = daily_bar.get("v") or g["volume"]
        gap_frac = (price - prev_close) / prev_close if price and prev_close else g["gap_percent"]
        avg_vol = state.avg_volume_cache.get(sym)
        change_abs = price - prev_close
        updated.append({
            **g,
            "price": price,
            "prev_close": prev_close,
            "change_pct": gap_frac,
            "change_abs": change_abs,
            "current_price": price,
            "previous_close": prev_close,
            "gap_percent": gap_frac,
            "volume": volume,
            "rel_volume": round(volume / avg_vol, 2) if avg_vol and avg_vol > 0 and volume > 0 else None,
            "has_news": sym in news,
            "newest_headline_at": news.get(sym),
        })

    updated.sort(key=lambda x: x["gap_percent"], reverse=True)
    updated = _prune_gappers_below_min(updated)
    state.gapper_cache = updated
    state.gapper_cache_ts = time.time()
    sr.save_gapper_snapshot(state.gapper_cache, state.gapper_cache_ts)
