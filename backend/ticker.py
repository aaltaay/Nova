"""
Ticker detail service module.

Owns: per-symbol caches (asset, snapshot, slow), the ticker WS client registry,
and all fetcher/builder functions for ticker detail data.

Extracted from backend/main.py to comply with the 200-line main.py target.
Routes live in backend/routes/ticker.py.
"""
from __future__ import annotations

import logging
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from constants import (
    TICKER_ASSET_CACHE_TTL,
    TICKER_AVG_VOLUME_CACHE_ONLY,
    TICKER_HTTP_TIMEOUT_SEC,
    TICKER_IBKR_BRIDGE_TIMEOUT_SEC,
    TICKER_IBKR_SNAPSHOT_TIMEOUT_SEC,
    TICKER_SLOW_CACHE_TTL,
    TICKER_SNAPSHOT_CACHE_TTL,
)
from alpaca import (
    ALPACA_DATA_URL as _DATA_URL,
    _env,
    _alpaca_headers,
    _get_feed,
    _get_discovery_provider,
)
from market import now_et as _now_et
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)

# ── Ticker caches (owned by this module) ─────────────────────────────────────
_ticker_asset_cache: dict[str, dict] = {}
_ticker_asset_cache_ts: dict[str, float] = {}
_ticker_snapshot_cache: dict[str, dict] = {}
_ticker_snapshot_cache_ts: dict[str, float] = {}
_ticker_slow_cache: dict[str, dict] = {}
_ticker_slow_cache_ts: dict[str, float] = {}

# Maps symbol -> set of active WebSocket connections for that symbol's detail.
_ticker_ws_clients: dict[str, set] = {}


def get_detail_symbols() -> list[str]:
    """Return symbols that currently have live ticker-detail WebSocket connections."""
    return [sym for sym, clients in _ticker_ws_clients.items() if clients]


# ── _pick_prev_close (pure; only depends on market.now_et) ───────────────────

def _pick_prev_close(snap: dict) -> float:
    """Return the correct 'previous regular-session close' from an Alpaca snapshot dict.

    Alpaca's bar semantics differ by session:
      - Pre-market (before 9:30 ET): dailyBar is the *last completed* regular session
        (yesterday). prevDailyBar is the session before that (two days ago).
      - Market/after-hours: dailyBar is today's developing/completed bar.
        prevDailyBar is yesterday's completed bar.

    We detect which case we're in by comparing dailyBar's timestamp date to today.
    If dailyBar is from a prior date → it IS yesterday's close → return dailyBar.c.
    Otherwise → dailyBar is today's bar → yesterday's close is prevDailyBar.c.
    """
    daily_bar = snap.get("dailyBar") or {}
    prev_bar = snap.get("prevDailyBar") or {}
    daily_ts = daily_bar.get("t")
    if daily_ts:
        try:
            bar_date = daily_ts[:10]  # "YYYY-MM-DD"
            today = _now_et().date().isoformat()
            if bar_date < today:
                c = daily_bar.get("c")
                return float(c) if c else 0.0
        except Exception:
            logger.debug("_pick_prev_close: could not parse daily_bar timestamp %r", daily_ts)
    c = prev_bar.get("c")
    return float(c) if c else 0.0


# ── Fetcher functions ─────────────────────────────────────────────────────────

def _fetch_ticker_asset(symbol: str, base_url: str, headers: dict) -> dict:
    """Fetch asset metadata from Alpaca Trading API with short-lived TTL cache."""
    global _ticker_asset_cache, _ticker_asset_cache_ts
    now = time.monotonic()
    if symbol in _ticker_asset_cache and (now - _ticker_asset_cache_ts.get(symbol, 0.0)) < TICKER_ASSET_CACHE_TTL:
        return _ticker_asset_cache[symbol]
    asset: dict = {}
    try:
        r = requests.get(f"{base_url}/v2/assets/{symbol}", headers=headers, timeout=TICKER_HTTP_TIMEOUT_SEC)
        if r.status_code == 200:
            a = r.json()
            attrs = a.get("attributes")
            if not isinstance(attrs, list):
                attrs = []
            asset = {
                "name": a.get("name", ""),
                "exchange": a.get("exchange", ""),
                "asset_class": a.get("class", ""),
                "status": a.get("status", ""),
                "tradable": a.get("tradable", False),
                "marginable": a.get("marginable", False),
                "shortable": a.get("shortable", False),
                "easy_to_borrow": a.get("easy_to_borrow", False),
                "fractionable": a.get("fractionable", False),
                "maintenance_margin_requirement": a.get("maintenance_margin_requirement"),
                "margin_requirement_long": a.get("margin_requirement_long"),
                "margin_requirement_short": a.get("margin_requirement_short"),
                "attributes": [str(x) for x in attrs if x is not None],
            }
            _ticker_asset_cache[symbol] = asset
            _ticker_asset_cache_ts[symbol] = now
            if asset.get("exchange"):
                import exchanges as _exchanges
                _exchanges.update_from_assets([{"symbol": symbol, "exchange": asset["exchange"]}])
    except Exception:
        logger.warning("_fetch_ticker_asset failed for %s", symbol, exc_info=True)
    return asset


def _fetch_ticker_snapshot(symbol: str, headers: dict, feed: str) -> dict:
    """Fetch latest snapshot from Alpaca Data API with short-lived TTL cache."""
    global _ticker_snapshot_cache, _ticker_snapshot_cache_ts
    now = time.monotonic()
    if symbol in _ticker_snapshot_cache and (now - _ticker_snapshot_cache_ts.get(symbol, 0.0)) < TICKER_SNAPSHOT_CACHE_TTL:
        return _ticker_snapshot_cache[symbol]

    def _session_px(v) -> float | None:
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if f > 0 else None

    def _bar(b: dict | None) -> dict | None:
        if not b:
            return None
        return {
            "open": _session_px(b.get("o")),
            "high": _session_px(b.get("h")),
            "low": _session_px(b.get("l")),
            "close": b.get("c"),
            "volume": b.get("v"),
            "trade_count": b.get("n"),
            "vwap": b.get("vw"),
            "timestamp": b.get("t"),
        }

    snapshot: dict = {}
    try:
        r = requests.get(
            f"{_DATA_URL}/v2/stocks/{symbol}/snapshot",
            headers=headers,
            params={"feed": feed},
            timeout=TICKER_HTTP_TIMEOUT_SEC,
        )
        if r.status_code == 200:
            raw = r.json()
            lt = raw.get("latestTrade") or {}
            lq = raw.get("latestQuote") or {}
            snapshot = {
                "latest_trade": {
                    "price": lt.get("p"),
                    "size": lt.get("s"),
                    "exchange": lt.get("x"),
                    "timestamp": lt.get("t"),
                } if lt else None,
                "latest_quote": {
                    "bid_price": lq.get("bp"),
                    "bid_size": lq.get("bs"),
                    "ask_price": lq.get("ap"),
                    "ask_size": lq.get("as"),
                    "timestamp": lq.get("t"),
                } if lq else None,
                "minute_bar": _bar(raw.get("minuteBar")),
                "daily_bar": _bar(raw.get("dailyBar")),
                "prev_daily_bar": _bar(raw.get("prevDailyBar")),
                "prev_close": _pick_prev_close(raw),
                "session_close": (raw.get("dailyBar") or {}).get("c"),
                "session_prev_close": (raw.get("prevDailyBar") or {}).get("c"),
            }
            _ticker_snapshot_cache[symbol] = snapshot
            _ticker_snapshot_cache_ts[symbol] = now
    except Exception:
        logger.warning("_fetch_ticker_snapshot failed for %s", symbol, exc_info=True)
    return snapshot


def _find_ibkr_cache_row(symbol: str) -> dict | None:
    """Look up a symbol's current row in whichever IBKR-sourced cache has it.

    Gainer/loser rows are checked before gapper rows: gappers stop refreshing
    once the market opens, so a symbol in both caches must resolve to the live
    gainer/loser row (see PROBLEM_LOG 2026-07-13).
    """
    state = get_runtime_state()
    for cache in (state.gainer_cache, state.loser_cache, state.gapper_cache):
        for row in cache:
            if row.get("symbol") == symbol:
                return row
    return None


def _fetch_ticker_snapshot_ibkr(symbol: str) -> dict:
    """IBKR counterpart to _fetch_ticker_snapshot.

    Reuses the IBKR scanner cache row for symbols already tracked by discovery
    (avoids a redundant IB API call and the stale CLOSE tick issue on repeated
    queries — see PROBLEM_LOG 2026-07-13). Falls back to a live snapshot only
    for symbols not in any scanner cache.
    """
    cached_row = _find_ibkr_cache_row(symbol)
    if cached_row:
        price = cached_row.get("current_price") or cached_row.get("price")
        prev_close = cached_row.get("previous_close") or cached_row.get("prev_close")
        volume = cached_row.get("volume", 0)
        exchange = cached_row.get("exchange")
        open_price = None
    else:
        from ibkr import client as _ibkr_client
        from ibkr import discovery as _ibkr_discovery
        try:
            quotes = _ibkr_client.run_coro(
                _ibkr_discovery.snapshot_quotes(
                    [symbol], timeout_sec=TICKER_IBKR_SNAPSHOT_TIMEOUT_SEC
                ),
                timeout=TICKER_IBKR_BRIDGE_TIMEOUT_SEC,
            ) or {}
        except Exception as exc:
            logger.warning("ticker IBKR snapshot failed for %s: %s", symbol, exc)
            return {}
        q = quotes.get(symbol)
        if not q:
            return {}
        price, prev_close = q["price"], q.get("prev_close")
        volume = q.get("volume", 0)
        exchange = q.get("exchange")
        open_price = q.get("open")

    if price is None or prev_close is None:
        return {}
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "latest_trade": {"price": price, "size": None, "exchange": exchange, "timestamp": now_iso},
        "latest_quote": None,
        "minute_bar": None,
        "daily_bar": {
            "open": open_price if open_price and open_price > 0 else None,
            "high": None,
            "low": None,
            "close": price,
            "volume": volume, "trade_count": None, "vwap": None, "timestamp": now_iso,
        },
        "prev_daily_bar": {
            "open": None, "high": None, "low": None, "close": prev_close,
            "volume": None, "trade_count": None, "vwap": None, "timestamp": None,
        },
        "prev_close": prev_close,
        "session_close": prev_close,
        "session_prev_close": None,
    }


def _fetch_ticker_news(symbol: str, headers: dict) -> list[dict]:
    """Fetch today's news articles for a symbol from Alpaca Data API."""
    news: list[dict] = []
    try:
        today = _now_et().date().isoformat()
        r = requests.get(
            f"{_DATA_URL}/v1beta1/news",
            headers=headers,
            params={"symbols": symbol, "start": today, "limit": 10},
            timeout=TICKER_HTTP_TIMEOUT_SEC,
        )
        if r.status_code == 200:
            for article in r.json().get("news", []):
                news.append({
                    "headline": article.get("headline", ""),
                    "summary": article.get("summary", ""),
                    "author": article.get("author", ""),
                    "source": article.get("source", ""),
                    "url": article.get("url", ""),
                    "created_at": article.get("created_at", ""),
                    "symbols": article.get("symbols", []),
                    "images": article.get("images", []),
                })
    except Exception:
        logger.warning("_fetch_ticker_news failed for %s", symbol, exc_info=True)
    return news


def _fetch_ticker_avg_volume(symbol: str, headers: dict) -> float | None:
    """Return average daily volume for symbol.

    By default (TICKER_AVG_VOLUME_CACHE_ONLY) never blocks REST/WS on Alpaca
    bars — scanners already warm ``_avg_volume_cache``. Cold miss → None.
    """
    state = get_runtime_state()
    avg_vol = state.avg_volume_cache.get(symbol)
    if avg_vol is not None or TICKER_AVG_VOLUME_CACHE_ONLY:
        return avg_vol
    from universe import ensure_avg_volume
    ensure_avg_volume([symbol], headers)
    return state.avg_volume_cache.get(symbol)


def _rvol_5min_fields(
    symbol: str,
    avg_vol: float | None,
    daily_vol: int | float | None,
) -> dict[str, float | int | None]:
    """Warrior 5-min RVOL fields for the quote panel.

    Seeds the shared cum-vol buffer from today's cumulative volume so an open
    ticker starts tracking immediately; returns None when history is too thin.
    """
    import time
    import hod_momo as _hod_momo
    import hod_momo_metrics as _metrics

    now = time.time()
    if daily_vol is not None:
        try:
            _metrics.update_cum_volume(symbol, int(daily_vol), now)
        except (TypeError, ValueError):
            pass
    vol_5m = _metrics.volume_in_window(symbol, ts=now)
    rvol5 = _hod_momo.peek_rvol_5min(symbol)
    if rvol5 is None:
        rvol5 = _metrics.compute_symbol_rvol_5min(symbol, avg_vol, ts=now)
    return {"volume_in_5min": vol_5m, "rvol_5min": rvol5}


# ── Builder functions ─────────────────────────────────────────────────────────

def _build_ticker_fast(symbol: str, base_url: str, headers: dict, feed: str) -> dict:
    """Fetch asset + snapshot concurrently — the fast subset of ticker detail.

    When DISCOVERY_PROVIDER=ibkr, Phase-1 WS must use the IBKR snapshot (same
    feed as the gappers/movers table). Using Alpaca here produced the dual-price
    bug: table showed IBKR last/gap while the quote panel showed Alpaca session.
    """
    state = get_runtime_state()
    use_ibkr = _get_discovery_provider() == "ibkr"
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_asset = pool.submit(_fetch_ticker_asset, symbol, base_url, headers)
        f_snap = (
            pool.submit(_fetch_ticker_snapshot_ibkr, symbol) if use_ibkr
            else pool.submit(_fetch_ticker_snapshot, symbol, headers, feed)
        )
        asset    = f_asset.result()
        snapshot = f_snap.result()

    avg_vol = state.avg_volume_cache.get(symbol)
    daily_vol = (snapshot.get("daily_bar") or {}).get("volume") or 0
    rel_vol = round(daily_vol / avg_vol, 2) if avg_vol and avg_vol > 0 and daily_vol > 0 else None
    rvol5 = _rvol_5min_fields(symbol, avg_vol, daily_vol)

    return {
        "symbol": symbol,
        "asset": asset,
        "snapshot": snapshot,
        "avg_volume": avg_vol,
        "rel_volume": rel_vol,
        **rvol5,
        "news": [],
        "fundamentals": {},
        "mode": state.current_mode,
    }


def _build_ticker_slow(symbol: str, headers: dict) -> dict:
    """Fetch news + avg volume + fundamentals concurrently — the slow subset.

    Results are cached for TICKER_SLOW_CACHE_TTL seconds so rapid re-clicks and
    tab-switches skip redundant external API calls entirely.
    """
    global _ticker_slow_cache, _ticker_slow_cache_ts
    now = time.monotonic()
    cached_ts = _ticker_slow_cache_ts.get(symbol, 0.0)
    if symbol in _ticker_slow_cache and (now - cached_ts) < TICKER_SLOW_CACHE_TTL:
        return _ticker_slow_cache[symbol]

    from fundamentals import fetch_fundamentals as _fetch_fundamentals
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_news  = pool.submit(_fetch_ticker_news, symbol, headers)
        f_avg   = pool.submit(_fetch_ticker_avg_volume, symbol, headers)
        f_fund  = pool.submit(_fetch_fundamentals, symbol)
        news    = f_news.result()
        avg_vol = f_avg.result()
        fund    = f_fund.result()

    result = {"news": news, "avg_volume": avg_vol, "fundamentals": fund}
    _ticker_slow_cache[symbol] = result
    _ticker_slow_cache_ts[symbol] = now
    return result


def _build_ticker_detail(symbol: str) -> dict:
    """Fetch and assemble full ticker detail for a symbol. Used by the REST endpoint.

    Composes the same fast + slow builders as the WS path so the slow-cache
    hits, and wall time is max(fast, slow) rather than a cold avg-volume fetch
    blocking the critical path.
    """
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if not headers:
        return {"error": "API keys not configured"}

    feed = _get_feed()
    use_ibkr = _get_discovery_provider() == "ibkr"

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_fast = pool.submit(_build_ticker_fast, symbol, base_url, headers, feed)
        f_slow = pool.submit(_build_ticker_slow, symbol, headers)
        fast = f_fast.result()
        slow = f_slow.result()

    snapshot = fast.get("snapshot") or {}
    # Single-feed rule: when discovery=ibkr, do NOT fall back to Alpaca if IBKR
    # returns an empty snapshot.
    if use_ibkr and not snapshot:
        logger.warning("ticker REST: IBKR snapshot empty for %s — returning empty (no Alpaca fallback)", symbol)

    avg_vol = slow.get("avg_volume") if slow.get("avg_volume") is not None else fast.get("avg_volume")
    daily_vol = (snapshot.get("daily_bar") or {}).get("volume") or 0
    rel_vol = round(daily_vol / avg_vol, 2) if avg_vol and avg_vol > 0 and daily_vol > 0 else fast.get("rel_volume")
    news = slow.get("news") or []
    rvol5 = _rvol_5min_fields(symbol, avg_vol, daily_vol)

    from news.enrich import build_ticker_news_impact
    return {
        "symbol": symbol,
        "asset": fast.get("asset") or {},
        "snapshot": snapshot,
        "avg_volume": avg_vol,
        "rel_volume": rel_vol,
        **rvol5,
        "news": news,
        "fundamentals": slow.get("fundamentals") or {},
        "news_impact": build_ticker_news_impact(symbol, news, snapshot, rel_vol),
        "mode": fast.get("mode"),
    }
