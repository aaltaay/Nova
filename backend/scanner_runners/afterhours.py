"""After-hours discovery and focus scan orchestration."""
from __future__ import annotations

import logging
import time

from constants import SCANNER_MIN_PRICE
from fundamentals import _fundamentals_cache, fetch_fundamentals_batch as _fetch_fundamentals_batch
import afterhours_discovery as _ah_discovery
import hod_momo as _hod_momo
from scanner_runners._facade import facade

logger = logging.getLogger(__name__)


def run_afterhours_discovery_scan() -> None:
    """After-hours movers: IBKR top % gainers when discovery=ibkr, else Alpaca."""
    from runtime_state.state import TABLE_STATE_FROZEN

    sr = facade()
    state = sr.get_runtime_state()
    if state.afterhours_table.state == TABLE_STATE_FROZEN:
        logger.info("AH discovery skipped — table frozen (ADR 008)")
        return
    headers = sr._alpaca_headers()

    if sr._get_discovery_provider() == "ibkr":
        # Dedicated AH scan universe is the primary source. The gainer_cache
        # reshape is a fallback only for when TOP_AFTER_HOURS_PERC_GAIN is
        # empty (thin AH liquidity / IB scanner gaps) — never the primary
        # source, since it's really the intraday gainer list, not AH movers.
        raw = sr.run_ibkr(
            sr._ibkr_discovery.get_afterhours_gainers(),
            on_error="none",
            label="afterhours",
        )
        source = "ah_scan"
        if raw is None:
            logger.error(
                "AH discovery (IBKR): bridge failed — keeping last-good afterhours_cache (%d rows)",
                len(state.afterhours_cache or []),
            )
            return
        if not raw:
            raw = list(state.gainer_cache) if state.gainer_cache else []
            source = "gainer_reshape"
            if not raw:
                cold = sr.run_ibkr(
                    sr._ibkr_discovery.get_gainers(),
                    on_error="none",
                    label="afterhours_gainer_fallback",
                )
                if cold is None:
                    logger.error(
                        "AH discovery (IBKR): gainer fallback bridge failed — "
                        "keeping last-good afterhours_cache (%d rows)",
                        len(state.afterhours_cache or []),
                    )
                    return
                raw = cold
                source = "gainer_reshape_cold"
        rows = _ah_discovery.build_afterhours_rows_from_ibkr_gainers(raw)
        if not rows:
            logger.warning(
                "AH discovery (IBKR): empty (source=%s raw=%d) — retrying next cycle; no Alpaca fallback",
                source, len(raw),
            )
            return
        logger.info("AH discovery (IBKR): source=%s raw=%d rows=%d", source, len(raw), len(rows))
        from market import pace_relative_volume as _pace_rvol

        syms = [r["symbol"] for r in rows]
        news: dict = {}
        if headers:
            sr.ensure_avg_volume(syms, headers)
            news = sr._check_news(syms, headers)
            _fetch_fundamentals_batch(syms)
        for r in rows:
            sym = r["symbol"]
            vol = int(r.get("volume") or 0)
            avg = state.avg_volume_cache.get(sym)
            fund = _fundamentals_cache.get(sym, {})
            paced = _pace_rvol(vol, avg) if avg and vol else None
            raw_rvol = round(vol / avg, 2) if avg and avg > 0 and vol > 0 else None
            gainer_rvol = None
            for g in state.gainer_cache:
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
        state.afterhours_cache = rows
        state.afterhours_cache_ts = time.time()
        state.last_afterhours_discovery_ts = time.monotonic()
        sr.mark_resub()
        sr.save_afterhours_snapshot(state.afterhours_cache, state.afterhours_cache_ts)
        # Clear sticky bridge error on a successful AH refresh (mirrors
        # movers.py) — this scan re-runs every AH cycle, but nothing ever
        # cleared the flag for the "afterhours" label, so one bridge timeout
        # painted Integrity fail for the rest of the session even while AH
        # rows kept landing every cycle (see PROBLEM_LOG 2026-07-23).
        state.ibkr_bridge_last_error = ""
        for r in rows:
            sym = r["symbol"]
            avg = state.avg_volume_cache.get(sym)
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
        state.hod_momo_universe_ts = 0.0
        from universe import refresh_hod_momo_universe
        refresh_hod_momo_universe()
        return

    from alpaca import _env
    from health_status import ping_health
    from scanner import _compute_gappers, _fetch_snapshots
    from universe import enrich_gappers, get_tradable_symbols

    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    if not headers:
        return
    if not ping_health(base_url, headers):
        return
    symbols = get_tradable_symbols(base_url, headers)
    if not symbols:
        return
    snaps = _fetch_snapshots(symbols, headers)
    rows = _compute_gappers(snaps, ref_bar_key="dailyBar")
    row_syms = [r["symbol"] for r in rows]
    sr.ensure_avg_volume(row_syms, headers)
    news = sr._check_news(row_syms, headers)
    rows = enrich_gappers(rows, news)
    state.afterhours_cache = rows
    state.afterhours_cache_ts = time.time()
    state.last_afterhours_discovery_ts = time.monotonic()
    sr.mark_resub()
    sr.save_afterhours_snapshot(state.afterhours_cache, state.afterhours_cache_ts)


def run_afterhours_focus_scan() -> None:
    """Re-price current after-hours candidates."""
    sr = facade()
    state = sr.get_runtime_state()
    if not state.afterhours_cache:
        run_afterhours_discovery_scan()
        return

    if sr._get_discovery_provider() == "ibkr":
        symbols = [r["symbol"] for r in state.afterhours_cache]
        quotes = sr.run_ibkr(
            sr._ibkr_discovery.snapshot_quotes(symbols, require_success=True),
            on_error="none",
            label="afterhours_focus",
        )
        if not isinstance(quotes, dict) or not quotes:
            logger.error(
                "AH focus (IBKR): snapshot failed/empty — keeping last-good prices (%d rows)",
                len(state.afterhours_cache),
            )
            return
        state.afterhours_cache = _ah_discovery.reprice_afterhours_rows_ibkr(
            state.afterhours_cache, quotes, state.avg_volume_cache,
        )
        state.afterhours_cache_ts = time.time()
        sr.save_afterhours_snapshot(state.afterhours_cache, state.afterhours_cache_ts)
        state.ibkr_bridge_last_error = ""
        return

    headers = sr._alpaca_headers()
    if not headers:
        return
    from scanner import _fetch_snapshots, _prune_gappers_below_min

    symbols = [r["symbol"] for r in state.afterhours_cache]
    snaps = _fetch_snapshots(symbols, headers)
    if not snaps:
        return
    news = sr._check_news(symbols, headers)

    updated: list[dict] = []
    for r in state.afterhours_cache:
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
        avg_vol = state.avg_volume_cache.get(sym)
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
    state.afterhours_cache = updated
    state.afterhours_cache_ts = time.time()
    sr.save_afterhours_snapshot(state.afterhours_cache, state.afterhours_cache_ts)
