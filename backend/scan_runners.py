"""
Scanner runner functions — discovery, focus, after-hours, and movers.

Extracted from ``main.py``. Mutates scanner caches via ``import main``.
Stateless helpers stay in ``scanner.py``; this module owns the orchestration
that fills ``_gapper_cache`` / ``_gainer_cache`` / ``_afterhours_cache``.
"""
from __future__ import annotations

import logging
import time

import requests

from alpaca import (
    ALPACA_DATA_URL as _DATA_URL,
    _alpaca_headers,
    _env,
    _get_discovery_provider,
    _try_fallback_to_iex,
)
from cache import (
    save_afterhours_snapshot,
    save_gapper_snapshot,
    save_movers_snapshot,
)
from constants import SCANNER_MIN_PRICE
from fundamentals import (
    _fundamentals_cache,
    fetch_fundamentals_batch as _fetch_fundamentals_batch,
)
from scanner import (
    _check_news,
    _compute_gappers,
    _fetch_snapshots,
    _pick_prev_close,
    _prune_gappers_below_min,
)
import afterhours_discovery as _ah_discovery
import exchanges as _exchanges
import hod_momo as _hod_momo
from ibkr import discovery as _ibkr_discovery

logger = logging.getLogger(__name__)


def _m():
    import main as _main
    return _main


# ── Pre-market ────────────────────────────────────────────────────────────────

def run_discovery_scan() -> None:
    """Full universe scan: filter gappers, enrich (Alpaca or IBKR)."""
    m = _m()
    headers = _alpaca_headers()
    provider = _get_discovery_provider()

    if provider == "ibkr":
        gappers = m._run_ibkr(_ibkr_discovery.get_gappers())
        if not headers:
            return
    else:
        base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
        if not headers:
            return
        if not m._ping_health(base_url, headers):
            return
        symbols = m._get_tradable_symbols(base_url, headers)
        if not symbols:
            return
        snaps = _fetch_snapshots(symbols, headers)
        if not snaps and _try_fallback_to_iex("snapshot fetch returned empty on discovery scan"):
            snaps = _fetch_snapshots(symbols, headers)
        gappers = _compute_gappers(snaps)

    gapper_syms = [g["symbol"] for g in gappers]
    m._ensure_avg_volume(gapper_syms, headers)
    news = _check_news(gapper_syms, headers)
    gappers = m._enrich_gappers(gappers, news)

    m._gapper_cache = gappers
    m._gapper_cache_ts = time.time()
    m._last_discovery_ts = time.monotonic()
    m._ws_mark_resub()
    save_gapper_snapshot(m._gapper_cache, m._gapper_cache_ts)


def run_focus_scan() -> None:
    """Re-price only current gapper candidates (fast refresh)."""
    m = _m()
    if not m._gapper_cache:
        run_discovery_scan()
        return
    if _get_discovery_provider() == "ibkr":
        return
    headers = _alpaca_headers()
    if not headers:
        return

    symbols = [g["symbol"] for g in m._gapper_cache]
    snaps = _fetch_snapshots(symbols, headers)
    if not snaps:
        return
    news = _check_news(symbols, headers)

    updated: list[dict] = []
    for g in m._gapper_cache:
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
        avg_vol = m._avg_volume_cache.get(sym)
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
    m._gapper_cache = updated
    m._gapper_cache_ts = time.time()
    save_gapper_snapshot(m._gapper_cache, m._gapper_cache_ts)


# ── After-hours ───────────────────────────────────────────────────────────────

def run_afterhours_discovery_scan() -> None:
    """After-hours movers: IBKR top % gainers when discovery=ibkr, else Alpaca."""
    m = _m()
    headers = _alpaca_headers()

    if _get_discovery_provider() == "ibkr":
        raw = list(m._gainer_cache) if m._gainer_cache else []
        if not raw:
            raw = m._run_ibkr(_ibkr_discovery.get_gainers()) or []
        rows = _ah_discovery.build_afterhours_rows_from_ibkr_gainers(raw)
        if not rows:
            logger.warning(
                "AH discovery (IBKR): empty (gainers=%d) — retrying next cycle; no Alpaca fallback",
                len(raw),
            )
            return
        from market import pace_relative_volume as _pace_rvol
        syms = [r["symbol"] for r in rows]
        news: dict = {}
        if headers:
            m._ensure_avg_volume(syms, headers)
            news = _check_news(syms, headers)
            _fetch_fundamentals_batch(syms)
        for r in rows:
            sym = r["symbol"]
            vol = int(r.get("volume") or 0)
            avg = m._avg_volume_cache.get(sym)
            fund = _fundamentals_cache.get(sym, {})
            paced = _pace_rvol(vol, avg) if avg and vol else None
            raw_rvol = round(vol / avg, 2) if avg and avg > 0 and vol > 0 else None
            gainer_rvol = None
            for g in m._gainer_cache:
                if g.get("symbol") == sym and g.get("rel_volume") is not None:
                    gainer_rvol = g.get("rel_volume")
                    break
            r["rel_volume"] = gainer_rvol if gainer_rvol is not None else (
                paced if paced is not None else raw_rvol
            )
            r["has_news"] = sym in news
            r["newest_headline_at"] = None
            r["market_cap"] = fund.get("market_cap")
            r["float"] = fund.get("float_shares")
            r["short_interest"] = fund.get("short_interest")
            r["short_ratio"] = fund.get("short_ratio")
            r["exchange"] = r.get("exchange") or fund.get("exchange")
        m._afterhours_cache = rows
        m._afterhours_cache_ts = time.time()
        m._last_afterhours_discovery_ts = time.monotonic()
        m._ws_mark_resub()
        save_afterhours_snapshot(m._afterhours_cache, m._afterhours_cache_ts)
        for r in rows:
            sym = r["symbol"]
            avg = m._avg_volume_cache.get(sym)
            try:
                _hod_momo.update_ticker_snapshot(
                    sym,
                    price=float(r["current_price"]),
                    rvol=r.get("rel_volume"),
                    volume=int(r.get("volume") or 0) or None,
                    change_pct=float(r["gap_percent"]) * 100.0 if r.get("gap_percent") is not None else None,
                    gap_pct=float(r["gap_percent"]) * 100.0 if r.get("gap_percent") is not None else None,
                    float_shares=r.get("float"),
                    rvol_source="ibkr_pace" if r.get("rel_volume") is not None else None,
                    avg_volume=float(avg) if avg else None,
                )
            except Exception:
                logger.debug("AH discovery: HOD snap seed failed for %s", sym, exc_info=True)
        m._hod_momo_universe_ts = 0.0
        m._refresh_hod_momo_universe()
        logger.info("AH discovery (IBKR): %d movers", len(rows))
        return

    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    if not headers:
        return
    if not m._ping_health(base_url, headers):
        return
    symbols = m._get_tradable_symbols(base_url, headers)
    if not symbols:
        return
    snaps = _fetch_snapshots(symbols, headers)
    rows = _compute_gappers(snaps, ref_bar_key="dailyBar")
    row_syms = [r["symbol"] for r in rows]
    m._ensure_avg_volume(row_syms, headers)
    news = _check_news(row_syms, headers)
    rows = m._enrich_gappers(rows, news)
    m._afterhours_cache = rows
    m._afterhours_cache_ts = time.time()
    m._last_afterhours_discovery_ts = time.monotonic()
    m._ws_mark_resub()
    save_afterhours_snapshot(m._afterhours_cache, m._afterhours_cache_ts)


def run_afterhours_focus_scan() -> None:
    """Re-price current after-hours candidates."""
    m = _m()
    if not m._afterhours_cache:
        run_afterhours_discovery_scan()
        return

    if _get_discovery_provider() == "ibkr":
        symbols = [r["symbol"] for r in m._afterhours_cache]
        quotes = m._run_ibkr(_ibkr_discovery.snapshot_quotes(symbols)) or {}
        m._afterhours_cache = _ah_discovery.reprice_afterhours_rows_ibkr(
            m._afterhours_cache, quotes, m._avg_volume_cache,
        )
        m._afterhours_cache_ts = time.time()
        save_afterhours_snapshot(m._afterhours_cache, m._afterhours_cache_ts)
        return

    headers = _alpaca_headers()
    if not headers:
        return
    symbols = [r["symbol"] for r in m._afterhours_cache]
    snaps = _fetch_snapshots(symbols, headers)
    if not snaps:
        return
    news = _check_news(symbols, headers)

    updated: list[dict] = []
    for r in m._afterhours_cache:
        sym = r["symbol"]
        snap = snaps.get(sym)
        if not snap:
            updated.append(r)
            continue
        latest_trade = snap.get("latestTrade") or {}
        ref_bar = snap.get("dailyBar") or {}
        daily_bar = snap.get("dailyBar") or {}
        price = latest_trade.get("p") or r["current_price"]
        if price < SCANNER_MIN_PRICE:
            continue
        prev_close = ref_bar.get("c") or r["previous_close"]
        volume = daily_bar.get("v") or r["volume"]
        gap_frac = (price - prev_close) / prev_close if price and prev_close else r["gap_percent"]
        avg_vol = m._avg_volume_cache.get(sym)
        change_abs = price - prev_close
        updated.append({
            **r,
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
    m._afterhours_cache = updated
    m._afterhours_cache_ts = time.time()
    save_afterhours_snapshot(m._afterhours_cache, m._afterhours_cache_ts)


# ── Market-hours movers ───────────────────────────────────────────────────────

def _build_mover_entry(raw: dict, snaps: dict, premarket_gap_map: dict) -> dict:
    """Build an enriched mover dict from a raw movers API item and snapshot data."""
    m = _m()
    sym = raw["symbol"]
    snap = snaps.get(sym, {})
    daily_bar = snap.get("dailyBar") or {}
    prev_bar = snap.get("prevDailyBar") or {}
    volume = daily_bar.get("v", 0)
    prev_close = prev_bar.get("c", 0)

    if sym in premarket_gap_map and premarket_gap_map[sym] is not None:
        gap_pct = premarket_gap_map[sym]
    elif prev_close:
        open_price = daily_bar.get("o", 0)
        gap_pct = (open_price - prev_close) / prev_close if open_price and prev_close else None
    else:
        gap_pct = None

    avg_vol = m._avg_volume_cache.get(sym)
    fund = _fundamentals_cache.get(sym, {})
    entry = {
        "symbol": sym,
        "price": raw.get("price", 0),
        "change_pct": raw.get("percent_change", 0) / 100.0,
        "change_abs": raw.get("change", 0),
        "volume": volume,
        "gap_percent": gap_pct,
        "rel_volume": round(volume / avg_vol, 2) if avg_vol and avg_vol > 0 and volume > 0 else None,
        "has_news": False,
        "newest_headline_at": None,
        "market_cap": fund.get("market_cap"),
        "float": fund.get("float_shares"),
        "short_interest": fund.get("short_interest"),
        "short_ratio": fund.get("short_ratio"),
        "prev_close": prev_close,
    }
    return _exchanges.attach_exchange(entry)


def _run_gainers_update_ibkr(headers: dict) -> tuple[list[dict], list[dict]] | None:
    m = _m()
    gainers_rows = m._run_ibkr(_ibkr_discovery.get_gainers())
    losers_rows = m._run_ibkr(_ibkr_discovery.get_losers())
    if not gainers_rows and not losers_rows:
        return None
    all_symbols = list({r["symbol"] for r in gainers_rows + losers_rows})
    m._ensure_avg_volume(all_symbols, headers)
    news = _check_news(all_symbols, headers)
    _fetch_fundamentals_batch(all_symbols)
    gainers = [m._enrich_ibkr_mover(r, news) for r in gainers_rows]
    losers = [m._enrich_ibkr_mover(r, news) for r in losers_rows]
    return gainers, losers


def run_gainers_update() -> None:
    """Fetch top gainers and losers, enrich with snapshots + RVOL + news."""
    m = _m()
    headers = _alpaca_headers()
    if not headers:
        return

    if _get_discovery_provider() == "ibkr":
        result = _run_gainers_update_ibkr(headers)
        if result is None:
            return
        gainers, losers = result
    else:
        base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
        if not m._ping_health(base_url, headers):
            return
        try:
            resp = requests.get(
                f"{_DATA_URL}/v1beta1/screener/stocks/movers",
                headers=headers,
                params={"top": min(m._TOP_N, 50)},
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("Alpaca movers API returned %s", resp.status_code)
                return
            movers_json = resp.json()
            gainers_raw = movers_json.get("gainers", [])
            losers_raw = movers_json.get("losers", [])
        except Exception:
            logger.warning("run_gainers_update: Alpaca movers API error", exc_info=True)
            return

        if not gainers_raw and not losers_raw:
            return

        gainers_raw = [r for r in gainers_raw if r.get("price", 0) >= SCANNER_MIN_PRICE]
        losers_raw = [r for r in losers_raw if r.get("price", 0) >= SCANNER_MIN_PRICE]
        all_symbols = list({r["symbol"] for r in gainers_raw + losers_raw})
        snaps = _fetch_snapshots(all_symbols, headers)
        m._ensure_avg_volume(all_symbols, headers)
        news = _check_news(all_symbols, headers)
        _fetch_fundamentals_batch(all_symbols)
        premarket_gap_map = {g["symbol"]: g.get("gap_percent") for g in m._gapper_cache}

        gainers = []
        for raw in gainers_raw:
            entry = _build_mover_entry(raw, snaps, premarket_gap_map)
            sym = entry["symbol"]
            entry["has_news"] = sym in news
            entry["newest_headline_at"] = news.get(sym)
            gainers.append(entry)

        losers = []
        for raw in losers_raw:
            entry = _build_mover_entry(raw, snaps, premarket_gap_map)
            sym = entry["symbol"]
            entry["has_news"] = sym in news
            entry["newest_headline_at"] = news.get(sym)
            losers.append(entry)

    m._gainer_cache = gainers
    m._gainer_cache_ts = time.time()
    m._loser_cache = losers
    m._loser_cache_ts = time.time()
    save_movers_snapshot(m._gainer_cache, m._loser_cache, m._gainer_cache_ts)
    m._ws_mark_resub()
