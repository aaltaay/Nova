"""
Background scan orchestration + news-catalyst scanner.

Owns: ``scan_loop`` (mode-aware cadence) and ``run_news_catalyst_scan``.
Discovery / focus / movers runners live in ``scan_runners.py``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

import requests

from alpaca import (
    ALPACA_DATA_URL as _DATA_URL,
    _alpaca_headers,
    _get_discovery_provider,
)
from constants import (
    AFTERHOURS_DISCOVERY_INTERVAL_SEC,
    AFTERHOURS_FOCUS_INTERVAL_SEC,
    CLOSED_INTERVAL_SEC,
    DISCOVERY_INTERVAL_SEC,
    FOCUS_INTERVAL_SEC,
    GAINERS_INTERVAL_SEC,
    NEWS_CATALYST_ARTICLE_LIMIT,
    NEWS_CATALYST_INTERVAL_SEC,
    NEWS_CATALYST_LOOKBACK_HOURS,
    SCANNER_MIN_PRICE,
)
from market import (
    in_after_hours as _in_after_hours,
    in_market_hours as _in_market_hours,
    in_premarket as _in_premarket,
    now_et as _now_et,
)
from news.enrich import enrich_catalyst_row
from scanner import _fetch_snapshots
from ticker import _find_ibkr_cache_row
import exchanges as _exchanges
from scan_runners import (
    run_afterhours_discovery_scan,
    run_afterhours_focus_scan,
    run_discovery_scan,
    run_focus_scan,
    run_gainers_update,
)
from runtime_state import get_runtime_state
from universe import refresh_hod_momo_universe

logger = logging.getLogger(__name__)


def run_news_catalyst_scan() -> None:
    """News-first catalyst scanner — fills ``_news_catalyst_cache``."""
    state = get_runtime_state()
    headers = _alpaca_headers()
    if not headers:
        return

    try:
        now_et = _now_et()
        lookback_start = (now_et - timedelta(hours=NEWS_CATALYST_LOOKBACK_HOURS)).isoformat()
        resp = requests.get(
            f"{_DATA_URL}/v1beta1/news",
            headers=headers,
            params={"start": lookback_start, "limit": NEWS_CATALYST_ARTICLE_LIMIT},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(
                "[catalyst] news API error %s: %s",
                resp.status_code, resp.text[:200],
            )
            return

        articles = resp.json().get("news", [])
        logger.info("[catalyst] fetched %d articles", len(articles))
        if not articles:
            return

        symbol_to_article: dict[str, dict] = {}
        for article in articles:
            created_at = article.get("created_at", "")
            headline = article.get("headline", "")
            url = article.get("url", "")
            source = article.get("source", "")
            for sym in article.get("symbols", []):
                if sym not in symbol_to_article or created_at > symbol_to_article[sym]["created_at"]:
                    symbol_to_article[sym] = {
                        "created_at": created_at,
                        "headline": headline,
                        "url": url,
                        "source": source,
                    }

        universe = state.assets_cache_set
        news_symbols = [
            s for s in symbol_to_article.keys()
            if not universe or s in universe
        ]
        logger.info("[catalyst] %d unique symbols from news", len(news_symbols))
        if not news_symbols:
            return

        use_ibkr = _get_discovery_provider() == "ibkr"
        catalysts: list[dict] = []

        if use_ibkr:
            for sym in news_symbols:
                row = _find_ibkr_cache_row(sym)
                if not row:
                    continue
                price = row.get("current_price") or row.get("price") or 0
                prev_close = row.get("previous_close") or row.get("prev_close") or 0
                volume = row.get("volume", 0)
                if not price or not prev_close or price < SCANNER_MIN_PRICE:
                    continue
                gap_frac = (price - prev_close) / prev_close
                article_info = symbol_to_article.get(sym, {})
                catalysts.append(_exchanges.attach_exchange({
                    "symbol": sym,
                    "previous_close": prev_close,
                    "current_price": price,
                    "gap_percent": gap_frac,
                    "volume": volume,
                    "has_news": True,
                    "newest_headline_at": article_info.get("created_at"),
                    "catalyst_headline": article_info.get("headline"),
                    "catalyst_url": article_info.get("url"),
                    "catalyst_source": article_info.get("source"),
                }))
        else:
            snaps = _fetch_snapshots(news_symbols, headers)
            if not snaps:
                return
            for sym, snap in snaps.items():
                latest_trade = snap.get("latestTrade") or {}
                prev_bar = snap.get("prevDailyBar") or {}
                daily_bar = snap.get("dailyBar") or {}
                price = latest_trade.get("p") or daily_bar.get("c", 0)
                prev_close = prev_bar.get("c", 0)
                volume = daily_bar.get("v", 0)
                if not price or not prev_close:
                    continue
                if price < SCANNER_MIN_PRICE:
                    continue
                gap_frac = (price - prev_close) / prev_close
                article_info = symbol_to_article.get(sym, {})
                catalysts.append(_exchanges.attach_exchange({
                    "symbol": sym,
                    "previous_close": prev_close,
                    "current_price": price,
                    "gap_percent": gap_frac,
                    "volume": volume,
                    "has_news": True,
                    "newest_headline_at": article_info.get("created_at"),
                    "catalyst_headline": article_info.get("headline"),
                    "catalyst_url": article_info.get("url"),
                    "catalyst_source": article_info.get("source"),
                }))

        catalysts.sort(key=lambda x: abs(x["gap_percent"]), reverse=True)
        catalysts = [enrich_catalyst_row(c) for c in catalysts]
        logger.info("[catalyst] scan complete — %d catalysts", len(catalysts))
        state.news_catalyst_cache = catalysts
        state.news_catalyst_cache_ts = time.time()
        state.last_catalyst_scan_ts = time.monotonic()

    except Exception:
        logger.exception("[catalyst] news catalyst scan failed")


async def sleep_with_ibkr_reprice(loop: asyncio.AbstractEventLoop, total_seconds: float) -> None:
    """Sleep until the next full scan tick (table reprice is independent)."""
    await asyncio.sleep(total_seconds)


async def scan_loop() -> None:
    """Mode-aware background scanner (premarket / market / afterhours / closed)."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            state = get_runtime_state()
            mono = time.monotonic()
            catalyst_due = (mono - state.last_catalyst_scan_ts) > NEWS_CATALYST_INTERVAL_SEC
            await loop.run_in_executor(None, refresh_hod_momo_universe)

            if _in_premarket():
                state.current_mode = "premarket"
                if not state.gapper_cache or (mono - state.last_discovery_ts) > DISCOVERY_INTERVAL_SEC:
                    await loop.run_in_executor(None, run_discovery_scan)
                else:
                    await loop.run_in_executor(None, run_focus_scan)
                if not state.gainer_cache:
                    await loop.run_in_executor(None, run_gainers_update)
                if catalyst_due:
                    await loop.run_in_executor(None, run_news_catalyst_scan)
                await sleep_with_ibkr_reprice(loop, FOCUS_INTERVAL_SEC)
            elif _in_market_hours():
                state.current_mode = "market"
                await loop.run_in_executor(None, run_gainers_update)
                if catalyst_due:
                    await loop.run_in_executor(None, run_news_catalyst_scan)
                await sleep_with_ibkr_reprice(loop, GAINERS_INTERVAL_SEC)
            elif _in_after_hours():
                state.current_mode = "afterhours"
                await loop.run_in_executor(None, run_gainers_update)
                if _get_discovery_provider() == "ibkr" and state.gainer_cache:
                    await loop.run_in_executor(None, run_afterhours_discovery_scan)
                elif (
                    not state.afterhours_cache
                    or (mono - state.last_afterhours_discovery_ts)
                    > AFTERHOURS_DISCOVERY_INTERVAL_SEC
                ):
                    await loop.run_in_executor(None, run_afterhours_discovery_scan)
                else:
                    await loop.run_in_executor(None, run_afterhours_focus_scan)
                if catalyst_due:
                    await loop.run_in_executor(None, run_news_catalyst_scan)
                await asyncio.sleep(AFTERHOURS_FOCUS_INTERVAL_SEC)
            else:
                state.current_mode = "closed"
                await loop.run_in_executor(None, run_discovery_scan)
                await loop.run_in_executor(None, run_gainers_update)
                await asyncio.sleep(CLOSED_INTERVAL_SEC)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Scan loop iteration failed — retrying in 30s")
            await asyncio.sleep(30)
