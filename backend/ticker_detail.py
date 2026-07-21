"""Ticker detail assembly — fast/slow builders and REST composition."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from alpaca import _alpaca_headers, _env, _get_discovery_provider, _get_feed
from constants import TICKER_AVG_VOLUME_CACHE_ONLY, TICKER_SLOW_CACHE_TTL
from runtime_state import get_runtime_state
from listing_compare import alpaca_listing_from_asset, build_listing_compare
from ticker_alpaca import fetch_ticker_asset, fetch_ticker_news
from ticker_cache import _ticker_slow_cache, _ticker_slow_cache_ts

logger = logging.getLogger(__name__)


def fetch_ticker_avg_volume(symbol: str, headers: dict) -> float | None:
    """Return average daily volume for symbol.

    By default (TICKER_AVG_VOLUME_CACHE_ONLY) never blocks REST/WS on Alpaca
    bars — scanners already warm ``avg_volume_cache``. Cold miss → None.
    """
    state = get_runtime_state()
    avg_vol = state.avg_volume_cache.get(symbol)
    if avg_vol is not None or TICKER_AVG_VOLUME_CACHE_ONLY:
        return avg_vol
    from universe import ensure_avg_volume
    ensure_avg_volume([symbol], headers)
    return state.avg_volume_cache.get(symbol)


def rvol_5min_fields(
    symbol: str,
    avg_vol: float | None,
    daily_vol: int | float | None,
) -> dict[str, float | int | None]:
    """Warrior 5-min RVOL fields for the quote panel."""
    import hod_momo as _hod_momo
    import hod_momo_metrics as _metrics

    now = time.time()
    if daily_vol is not None:
        try:
            _metrics.update_cum_volume(symbol, int(daily_vol), now)
        except (TypeError, ValueError):
            logger.debug("Ignoring non-integer daily_vol for %s", symbol)
    vol_5m = _metrics.volume_in_window(symbol, ts=now)
    rvol5 = _hod_momo.peek_rvol_5min(symbol)
    if rvol5 is None:
        rvol5 = _metrics.compute_symbol_rvol_5min(symbol, avg_vol, ts=now)
    return {"volume_in_5min": vol_5m, "rvol_5min": rvol5}


def _snapshot_for_provider(symbol: str, headers: dict, feed: str) -> dict:
    """Composed TickerSnapshotPort — no silent Alpaca fallback when discovery=ibkr."""
    from composition.market_data_providers import get_ticker_snapshot_port

    return get_ticker_snapshot_port(headers, feed).fetch_snapshot(symbol)


def build_ticker_fast(symbol: str, base_url: str, headers: dict, feed: str) -> dict:
    """Fetch asset + snapshot concurrently — the fast subset of ticker detail.

    When DISCOVERY_PROVIDER=ibkr, Phase-1 WS must use the IBKR snapshot (same
    feed as the gappers/movers table). Using Alpaca here produced the dual-price
    bug: table showed IBKR last/gap while the quote panel showed Alpaca session.
    """
    state = get_runtime_state()
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_asset = pool.submit(fetch_ticker_asset, symbol, base_url, headers)
        f_snap = pool.submit(_snapshot_for_provider, symbol, headers, feed)
        asset = f_asset.result()
        snapshot = f_snap.result()

    avg_vol = state.avg_volume_cache.get(symbol)
    daily_vol = (snapshot.get("daily_bar") or {}).get("volume") or 0
    rel_vol = round(daily_vol / avg_vol, 2) if avg_vol and avg_vol > 0 and daily_vol > 0 else None
    rvol5 = rvol_5min_fields(symbol, avg_vol, daily_vol)

    return {
        "symbol": symbol,
        "asset": asset,
        "listing": {
            "symbol": symbol,
            "alpaca": alpaca_listing_from_asset(asset),
            "ibkr": None,  # filled on detail_update / REST full build
        },
        "avg_volume": avg_vol,
        "rel_volume": rel_vol,
        "snapshot": snapshot,
        **rvol5,
        "news": [],
        "fundamentals": {},
        "mode": state.current_mode,
    }


def build_ticker_slow(symbol: str, headers: dict) -> dict:
    """Fetch news + avg volume + fundamentals concurrently — the slow subset."""
    now = time.monotonic()
    cached_ts = _ticker_slow_cache_ts.get(symbol, 0.0)
    if symbol in _ticker_slow_cache and (now - cached_ts) < TICKER_SLOW_CACHE_TTL:
        return _ticker_slow_cache[symbol]

    from fundamentals import fetch_fundamentals as _fetch_fundamentals
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_news = pool.submit(fetch_ticker_news, symbol, headers)
        f_avg = pool.submit(fetch_ticker_avg_volume, symbol, headers)
        f_fund = pool.submit(_fetch_fundamentals, symbol)
        news = f_news.result()
        avg_vol = f_avg.result()
        fund = f_fund.result()

    result = {"news": news, "avg_volume": avg_vol, "fundamentals": fund}
    _ticker_slow_cache[symbol] = result
    _ticker_slow_cache_ts[symbol] = now
    return result


def build_ticker_detail(symbol: str) -> dict:
    """Fetch and assemble full ticker detail for a symbol. Used by the REST endpoint."""
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if not headers:
        return {"error": "API keys not configured"}

    feed = _get_feed()
    use_ibkr = _get_discovery_provider() == "ibkr"

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_fast = pool.submit(build_ticker_fast, symbol, base_url, headers, feed)
        f_slow = pool.submit(build_ticker_slow, symbol, headers)
        fast = f_fast.result()
        slow = f_slow.result()

    snapshot = fast.get("snapshot") or {}
    if use_ibkr and not snapshot:
        logger.warning(
            "ticker REST: IBKR snapshot empty for %s — returning empty (no Alpaca fallback)",
            symbol,
        )

    avg_vol = slow.get("avg_volume") if slow.get("avg_volume") is not None else fast.get("avg_volume")
    daily_vol = (snapshot.get("daily_bar") or {}).get("volume") or 0
    rel_vol = round(daily_vol / avg_vol, 2) if avg_vol and avg_vol > 0 and daily_vol > 0 else fast.get("rel_volume")
    news = slow.get("news") or []
    rvol5 = rvol_5min_fields(symbol, avg_vol, daily_vol)

    from news.enrich import build_ticker_news_impact

    asset = fast.get("asset") or {}
    return {
        "symbol": symbol,
        "asset": asset,
        "listing": build_listing_compare(symbol, asset),
        "snapshot": snapshot,
        "avg_volume": avg_vol,
        "rel_volume": rel_vol,
        **rvol5,
        "news": news,
        "fundamentals": slow.get("fundamentals") or {},
        "news_impact": build_ticker_news_impact(symbol, news, snapshot, rel_vol),
        "mode": fast.get("mode"),
    }
