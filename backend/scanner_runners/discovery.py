"""Pre-market discovery and focus scan orchestration."""
from __future__ import annotations

import time

from scanner_runners._facade import facade


def run_discovery_scan() -> None:
    """Full universe scan: filter gappers, enrich (Alpaca or IBKR)."""
    sr = facade()
    state = sr.get_runtime_state()
    headers = sr._alpaca_headers()
    provider = sr._get_discovery_provider()

    if provider == "ibkr":
        gappers = sr.run_ibkr(sr._ibkr_discovery.get_gappers())
        # Alpaca headers are optional listing/news metadata only — never block IBKR prices.
    else:
        from alpaca import _env, _try_fallback_to_iex
        from health_status import ping_health
        from scanner import _compute_gappers, _fetch_snapshots
        from universe import get_tradable_symbols

        base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
        if not headers:
            return
        if not ping_health(base_url, headers):
            return
        symbols = get_tradable_symbols(base_url, headers)
        if not symbols:
            return
        snaps = _fetch_snapshots(symbols, headers)
        if not snaps and _try_fallback_to_iex("snapshot fetch returned empty on discovery scan"):
            snaps = _fetch_snapshots(symbols, headers)
        gappers = _compute_gappers(snaps)

    gapper_syms = [g["symbol"] for g in gappers]
    news: dict = {}
    if headers:
        sr.ensure_avg_volume(gapper_syms, headers)
        news = sr._check_news(gapper_syms, headers)
    gappers = sr.enrich_gappers(gappers, news)

    state.gapper_cache = gappers
    state.gapper_cache_ts = time.time()
    state.last_discovery_ts = time.monotonic()
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
