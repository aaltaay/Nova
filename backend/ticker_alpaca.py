"""Alpaca ticker detail fetchers (metadata + snapshots + news)."""
from __future__ import annotations

import logging
import time

import requests

from alpaca import ALPACA_DATA_URL as _DATA_URL
from constants import (
    TICKER_ASSET_CACHE_TTL,
    TICKER_HTTP_TIMEOUT_SEC,
    TICKER_SNAPSHOT_CACHE_TTL,
)
from market import now_et as _now_et
from ticker_cache import (
    _ticker_asset_cache,
    _ticker_asset_cache_ts,
    _ticker_snapshot_cache,
    _ticker_snapshot_cache_ts,
)

logger = logging.getLogger(__name__)


def pick_prev_close(snap: dict) -> float:
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
            logger.debug("pick_prev_close: could not parse daily_bar timestamp %r", daily_ts)
    c = prev_bar.get("c")
    return float(c) if c else 0.0


def fetch_ticker_asset(symbol: str, base_url: str, headers: dict) -> dict:
    """Fetch asset metadata from Alpaca Trading API with short-lived TTL cache."""
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
        logger.warning("fetch_ticker_asset failed for %s", symbol, exc_info=True)
    return asset


def fetch_ticker_snapshot(symbol: str, headers: dict, feed: str) -> dict:
    """Fetch latest snapshot from Alpaca Data API with short-lived TTL cache."""
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
                "prev_close": pick_prev_close(raw),
                "session_close": (raw.get("dailyBar") or {}).get("c"),
                "session_prev_close": (raw.get("prevDailyBar") or {}).get("c"),
            }
            _ticker_snapshot_cache[symbol] = snapshot
            _ticker_snapshot_cache_ts[symbol] = now
    except Exception:
        logger.warning("fetch_ticker_snapshot failed for %s", symbol, exc_info=True)
    return snapshot


def fetch_ticker_news(symbol: str, headers: dict) -> list[dict]:
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
        logger.warning("fetch_ticker_news failed for %s", symbol, exc_info=True)
    return news
