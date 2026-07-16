"""Market-hours gainers/losers scan orchestration."""
from __future__ import annotations

import logging
import time

import requests

from alpaca import ALPACA_DATA_URL as _DATA_URL, _env
from constants import SCANNER_MIN_PRICE
from fundamentals import _fundamentals_cache, fetch_fundamentals_batch as _fetch_fundamentals_batch
import exchanges as _exchanges
from health_status import ping_health
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


def _run_gainers_update_ibkr(headers: dict) -> tuple[list[dict], list[dict]] | None:
    sr = facade()
    gainers_rows = sr.run_ibkr(sr._ibkr_discovery.get_gainers())
    losers_rows = sr.run_ibkr(sr._ibkr_discovery.get_losers())
    if not gainers_rows and not losers_rows:
        return None
    all_symbols = list({r["symbol"] for r in gainers_rows + losers_rows})
    sr.ensure_avg_volume(all_symbols, headers)
    news = sr._check_news(all_symbols, headers)
    _fetch_fundamentals_batch(all_symbols)
    gainers = [sr.enrich_ibkr_mover(r, news) for r in gainers_rows]
    losers = [sr.enrich_ibkr_mover(r, news) for r in losers_rows]
    return gainers, losers


def run_gainers_update() -> None:
    """Fetch top gainers and losers, enrich with snapshots + RVOL + news."""
    sr = facade()
    state = sr.get_runtime_state()
    headers = sr._alpaca_headers()
    if not headers:
        return

    if sr._get_discovery_provider() == "ibkr":
        result = _run_gainers_update_ibkr(headers)
        if result is None:
            return
        gainers, losers = result
    else:
        base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
        if not ping_health(base_url, headers):
            return
        try:
            resp = requests.get(
                f"{_DATA_URL}/v1beta1/screener/stocks/movers",
                headers=headers,
                params={"top": min(state.config.top_n, 50)},
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

    state.gainer_cache = gainers
    state.gainer_cache_ts = time.time()
    state.loser_cache = losers
    state.loser_cache_ts = time.time()
    sr.save_movers_snapshot(state.gainer_cache, state.loser_cache, state.gainer_cache_ts)
    sr.mark_resub()
