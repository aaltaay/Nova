"""Market-hours gainers/losers scan orchestration."""
from __future__ import annotations

import logging
import time

from constants import SCANNER_MIN_PRICE
from fundamentals import _fundamentals_cache, fetch_fundamentals_batch as _fetch_fundamentals_batch
import exchanges as _exchanges
from ibkr_bridge import IbkrBridgeError
from scanner import _check_news, _fetch_snapshots
from scanner_runners._facade import facade
from universe import ensure_avg_volume

logger = logging.getLogger(__name__)


def _build_mover_entry(raw: dict, snaps: dict, premarket_gap_map: dict) -> dict:
    """Build an enriched mover dict from a raw movers API item and snapshot data."""
    state = facade().get_runtime_state()
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

    avg_vol = state.avg_volume_cache.get(sym)
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


def _run_gainers_update_ibkr(headers: dict | None) -> tuple[list[dict], list[dict]] | None:
    sr = facade()
    state = sr.get_runtime_state()
    port = sr.get_movers_port()
    gainers_rows: list[dict] | None
    losers_rows: list[dict] | None
    try:
        gainers_rows = list(port.get_gainers() or [])
    except IbkrBridgeError as exc:
        logger.error(
            "Gainers bridge failed — keeping %d cached row(s): %s",
            len(state.gainer_cache),
            exc,
        )
        gainers_rows = None
    try:
        losers_rows = list(port.get_losers() or [])
    except IbkrBridgeError as exc:
        logger.error(
            "Losers bridge failed — keeping %d cached row(s): %s",
            len(state.loser_cache),
            exc,
        )
        losers_rows = None
    if gainers_rows is None and losers_rows is None:
        return None
    if gainers_rows is None:
        gainers_rows = list(state.gainer_cache or [])
    if losers_rows is None:
        losers_rows = list(state.loser_cache or [])
    if not gainers_rows and not losers_rows:
        return None
    all_symbols = list({r["symbol"] for r in gainers_rows + losers_rows})
    news: dict = {}
    # Alpaca headers are optional listing/news metadata — never required for IBKR prices.
    if headers:
        sr.ensure_avg_volume(all_symbols, headers)
        news = sr._check_news(all_symbols, headers)
        _fetch_fundamentals_batch(all_symbols)
    gainers = [sr.enrich_ibkr_mover(r, news) for r in gainers_rows]
    losers = [sr.enrich_ibkr_mover(r, news) for r in losers_rows]
    return gainers, losers


def _run_gainers_update_alpaca(headers: dict) -> tuple[list[dict], list[dict]] | None:
    sr = facade()
    state = sr.get_runtime_state()
    port = sr.get_movers_port()
    gainers_raw = [r for r in (port.get_gainers() or []) if r.get("price", 0) >= SCANNER_MIN_PRICE]
    losers_raw = [r for r in (port.get_losers() or []) if r.get("price", 0) >= SCANNER_MIN_PRICE]
    if not gainers_raw and not losers_raw:
        return None

    all_symbols = list({r["symbol"] for r in gainers_raw + losers_raw})
    snaps = _fetch_snapshots(all_symbols, headers)
    ensure_avg_volume(all_symbols, headers)
    news = _check_news(all_symbols, headers)
    _fetch_fundamentals_batch(all_symbols)
    premarket_gap_map = {g["symbol"]: g.get("gap_percent") for g in state.gapper_cache}

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
    return gainers, losers


def run_gainers_update() -> None:
    """Fetch top gainers and losers, enrich with snapshots + RVOL + news."""
    from ibkr import scanner_session as _ss
    from runtime_state.state import TABLE_STATE_FROZEN

    sr = facade()
    state = sr.get_runtime_state()
    headers = sr._alpaca_headers()

    if sr._get_discovery_provider() == "ibkr":
        result = _run_gainers_update_ibkr(headers)
    else:
        if not headers:
            return
        result = _run_gainers_update_alpaca(headers)
    if result is None:
        return
    gainers, losers = result

    gainer_frozen = state.gainer_table.state == TABLE_STATE_FROZEN
    loser_frozen = state.loser_table.state == TABLE_STATE_FROZEN
    if not gainer_frozen:
        state.gainer_cache = gainers
        state.gainer_cache_ts = time.time()
        _ss.ensure_session_key(state, _ss.TABLE_GAINERS, source="movers")
        sr.save_gainer_snapshot(state.gainer_cache, state.gainer_cache_ts)
    if not loser_frozen:
        state.loser_cache = losers
        state.loser_cache_ts = time.time()
        _ss.ensure_session_key(state, _ss.TABLE_LOSERS, source="movers")
        sr.save_loser_snapshot(state.loser_cache, state.loser_cache_ts)
    # Clear sticky bridge error on a successful movers refresh — RTH never
    # re-runs gappers discovery, so leaving this set after a one-shot
    # TOP_PERC_GAIN timeout (or a disconnect-window failure) kept painting
    # Integrity fail all day. Either side landing rows proves the bridge is
    # live again — don't require both gainers and losers to be non-empty.
    if (not gainer_frozen and gainers) or (not loser_frozen and losers):
        state.ibkr_bridge_last_error = ""
    sr.mark_resub()
