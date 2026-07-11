from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import logging.handlers
import os
from dotenv import load_dotenv, set_key
import requests
from datetime import datetime, date, timedelta
import math
import re
import time
import asyncio
import json
from zoneinfo import ZoneInfo
import yfinance as yf
import websockets

logger = logging.getLogger(__name__)

# ── Persistent rotating log file ──────────────────────────────────────────────
from paths import env_file_path, log_dir as _nova_log_dir
from ibkr import client as _ibkr_client
from routes.trading import router as _trading_router, ws_router as _trading_ws_router
from routes.strategy import router as _strategy_router
from routes.journal import router as _journal_router
from routes.executor import router as _executor_router
from routes.l2 import router as _l2_router
from routes.news import router as _news_router
from news.enrich import enrich_catalyst_row, build_ticker_news_impact

_log_dir = str(_nova_log_dir())
_file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(_log_dir, "blast.log"),
    maxBytes=5_000_000,
    backupCount=3,
    # Without an explicit encoding, Python opens the file using the platform's
    # locale-preferred encoding (cp1252 on Windows) with strict error handling,
    # so any non-ASCII log character (e.g. an arrow in a status message) raises
    # UnicodeEncodeError. run_api.py's _force_utf8_io() only fixes console
    # stdio, not this file handler — it needs its own explicit encoding.
    encoding="utf-8",
    errors="backslashreplace",
)
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
)
logging.getLogger().addHandler(_file_handler)
logging.getLogger().setLevel(logging.INFO)

from constants import (
    AFTERHOURS_DISCOVERY_INTERVAL_SEC,
    AFTERHOURS_FOCUS_INTERVAL_SEC,
    ALPACA_WS_BACKOFF_CAP,
    CLOSED_INTERVAL_SEC,
    DATA_FEED_DEFAULT,
    DATA_FEED_OPTIONS,
    DISCOVERY_INTERVAL_SEC,
    EXCLUDED_NAME_KEYWORDS,
    FOCUS_INTERVAL_SEC,
    FUNDAMENTALS_CACHE_TTL,
    GAINERS_INTERVAL_SEC,
    GAPPER_MIN_GAP_PCT,
    HISTORY_RETENTION_DAYS,
    HOD_MOMO_UNIVERSE_INTERVAL_SEC,
    CHART_DEFAULT_BARS,
    CHART_DEFAULT_TIMEFRAME,
    NEWS_CATALYST_ARTICLE_LIMIT,
    NEWS_CATALYST_INTERVAL_SEC,
    NEWS_CATALYST_LOOKBACK_HOURS,
    RVOL_LOOKBACK_DAYS,
    SCAN_CAP_DEFAULT,
    SCAN_EXCHANGES,
    SCAN_REQUIRE_TRADABLE,
    SCANNER_MIN_PRICE,
    SNAPSHOT_WORKERS,
    SYMBOL_EXCLUDE_RE,
    TICKER_ASSET_CACHE_TTL,
    TICKER_SLOW_CACHE_TTL,
    TICKER_SNAPSHOT_CACHE_TTL,
    TOP_N_DEFAULT,
    YFINANCE_TIMEOUT_S,
)
import hod_momo_enrichment as _hod_momo_enrichment
from cache import (
    _migrate_legacy_files,
    cleanup_old_snapshots,
    list_history_dates,
    load_afterhours_snapshot,
    load_gapper_snapshot,
    load_movers_snapshot,
    load_snapshot_for_date,
    save_afterhours_snapshot,
    save_gapper_snapshot,
    save_movers_snapshot,
)
import hod_momo as _hod_momo
import strategy.risk as _risk
import strategy.setups_stream as _setups_stream
import strategy.executor as _executor
import journal.db as _journal_db
import l2.db as _l2_db
from bars import fetch_bars as _fetch_bars

load_dotenv(env_file_path())

_NOVA_REV = "4"
_ET = ZoneInfo("America/New_York")
_DATA_URL = "https://data.alpaca.markets"

# Scan intervals — authoritative values in `constants.py`
_DISCOVERY_INTERVAL = DISCOVERY_INTERVAL_SEC
_FOCUS_INTERVAL = FOCUS_INTERVAL_SEC
_GAINERS_INTERVAL = GAINERS_INTERVAL_SEC
_CLOSED_INTERVAL = CLOSED_INTERVAL_SEC
_AH_DISCOVERY_INTERVAL = AFTERHOURS_DISCOVERY_INTERVAL_SEC
_AH_FOCUS_INTERVAL = AFTERHOURS_FOCUS_INTERVAL_SEC

_SCAN_CAP = int(os.environ.get("ALPACA_SCAN_SYMBOL_CAP", str(SCAN_CAP_DEFAULT)))  # emergency override only
_MIN_GAP_PCT = float(os.environ.get("NOVA_MIN_GAP_PCT", os.environ.get("BLAST_MIN_GAP_PCT", str(GAPPER_MIN_GAP_PCT))))
_TOP_N = int(os.environ.get("NOVA_TOP_N", os.environ.get("BLAST_TOP_N", str(TOP_N_DEFAULT))))
_raw_scan_tradable = os.environ.get("NOVA_SCAN_REQUIRE_TRADABLE") or os.environ.get("BLAST_SCAN_REQUIRE_TRADABLE")
if _raw_scan_tradable is None or not str(_raw_scan_tradable).strip():
    _SCAN_REQUIRE_TRADABLE = SCAN_REQUIRE_TRADABLE
else:
    _SCAN_REQUIRE_TRADABLE = str(_raw_scan_tradable).strip().lower() in ("1", "true", "yes", "on")
_NEWS_CATALYST_INTERVAL = NEWS_CATALYST_INTERVAL_SEC

# ── Assets cache (1-hour TTL) ─────────────────────────────────────────────────
_assets_cache: list[str] = []
_assets_cache_set: set[str] = set()   # O(1) membership check used by all scanners
_assets_cache_ts: float = 0.0
_ASSETS_CACHE_TTL = 3600.0

# ── Gapper cache (pre-market) ─────────────────────────────────────────────────
_gapper_cache: list[dict] = []
_gapper_cache_ts: float = 0.0
_last_discovery_ts: float = 0.0

# ── After-hours cache (4–8 PM ET) ────────────────────────────────────────────
_afterhours_cache: list[dict] = []
_afterhours_cache_ts: float = 0.0
_last_afterhours_discovery_ts: float = 0.0

# ── Gainers cache (market hours) ──────────────────────────────────────────────
_gainer_cache: list[dict] = []
_gainer_cache_ts: float = 0.0

# ── Losers cache (market hours) ───────────────────────────────────────────────
_loser_cache: list[dict] = []
_loser_cache_ts: float = 0.0

# ── News catalyst cache (pre-market + market hours, news-first algorithm) ─────
_news_catalyst_cache: list[dict] = []
_news_catalyst_cache_ts: float = 0.0
_last_catalyst_scan_ts: float = 0.0

# ── Average daily volume cache (reset each day, lazy-filled for RVOL) ─────────
_avg_volume_cache: dict[str, float] = {}
_avg_volume_date: str = ""

# ── Fundamentals cache (TTL from constants, keyed by symbol) ──────────────────
_fundamentals_cache: dict[str, dict] = {}
_fundamentals_cache_ts: dict[str, float] = {}

# ── Ticker-detail sub-caches (asset + snapshot; TTLs from constants) ──────────
_ticker_asset_cache: dict[str, dict] = {}
_ticker_asset_cache_ts: dict[str, float] = {}
_ticker_snapshot_cache: dict[str, dict] = {}
_ticker_snapshot_cache_ts: dict[str, float] = {}
# Phase 2 ("slow") result cache: news + fundamentals + avg_vol bundled together.
# Short TTL so repeated clicks / tab-switches skip redundant external API calls.
_ticker_slow_cache: dict[str, dict] = {}
_ticker_slow_cache_ts: dict[str, float] = {}

# ── Health + mode ──────────────────────────────────────────────────────────────
_cached_health: dict = {"status": "loading", "latency_ms": 0}
_current_mode: str = "closed"   # "premarket" | "market" | "afterhours" | "closed"

# ── WebSocket streaming state ──────────────────────────────────────────────────
# The WS stream receives real-time trades and updates _gapper_cache / _gainer_cache
# in-place, decoupling price freshness from the REST scan cadence.
_ws_subscribed: set[str] = set()   # symbols the WS is currently subscribed to
_ws_needs_resub: bool = False       # scan loop sets True when symbol list changes

# ── Ticker detail WebSocket clients ───────────────────────────────────────────
# Maps symbol -> set of active WebSocket connections watching that symbol's detail.
_ticker_ws_clients: dict[str, set] = {}

# ── HOD Momo universe state ────────────────────────────────────────────────────
# Symbols currently subscribed for the HOD Momo engine (union of all common-stock
# symbols that pass the master-gate prefilter above min RVOL or are already being
# watched for other scanners).  Refreshed every HOD_MOMO_UNIVERSE_INTERVAL_SEC.
_hod_momo_universe: set[str] = set()
_hod_momo_universe_ts: float = 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name, default)
    if v is None:
        return None
    return v.strip().strip("'\"")


def _alpaca_headers() -> dict[str, str] | None:
    api_key = _env("APCA_API_KEY_ID")
    api_secret = _env("APCA_API_SECRET_KEY")
    if not api_key or not api_secret:
        return None
    return {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}


def _now_et() -> datetime:
    return datetime.now(_ET)


def _in_premarket() -> bool:
    now = _now_et()
    start = now.replace(hour=4, minute=0, second=0, microsecond=0)
    open_ = now.replace(hour=9, minute=30, second=0, microsecond=0)
    return start <= now < open_


def _in_market_hours() -> bool:
    now = _now_et()
    open_ = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_ <= now < close


def _in_after_hours() -> bool:
    now = _now_et()
    start = now.replace(hour=16, minute=0, second=0, microsecond=0)
    end = now.replace(hour=20, minute=0, second=0, microsecond=0)
    return start <= now < end


# ── Active data feed tracking ─────────────────────────────────────────────────
# Tracks which feed is actually in use (may differ from configured if fallback fires).
_active_feed: str = ""  # set at first _get_feed() call
_feed_fell_back: bool = False  # True if SIP→IEX fallback was triggered this session


def _get_feed() -> str:
    """Return the active Alpaca data feed (iex or sip).

    Priority: _active_feed (runtime) > env ALPACA_DATA_FEED > DATA_FEED_DEFAULT.
    """
    global _active_feed
    if _active_feed:
        return _active_feed
    raw = (_env("ALPACA_DATA_FEED") or DATA_FEED_DEFAULT).lower()
    if raw not in DATA_FEED_OPTIONS:
        raw = DATA_FEED_DEFAULT
    _active_feed = raw
    return _active_feed


def _set_feed(feed: str) -> None:
    """Change the active data feed at runtime (e.g. from Settings or auto-fallback)."""
    global _active_feed, _feed_fell_back
    feed = feed.lower()
    if feed not in DATA_FEED_OPTIONS:
        feed = DATA_FEED_DEFAULT
    _active_feed = feed
    _feed_fell_back = False  # reset fallback flag when user explicitly changes
    logger.info("Data feed set to '%s'", _active_feed)


def _try_fallback_to_iex(context: str) -> bool:
    """If currently on SIP and a subscription error occurs, fall back to IEX.

    Returns True if the fallback was applied (caller should retry), False otherwise.
    """
    global _active_feed, _feed_fell_back
    if _active_feed == "sip" and not _feed_fell_back:
        logger.warning(
            "SIP feed rejected (%s) — falling back to IEX. "
            "Change feed in Settings or set ALPACA_DATA_FEED=sip if your plan supports it.",
            context,
        )
        _active_feed = "iex"
        _feed_fell_back = True
        return True
    return False


# ── Fundamentals (yfinance / Yahoo Finance) ───────────────────────────────────

def _fetch_fundamentals(symbol: str) -> dict:
    """Fetch fundamental data for a single symbol via yfinance with TTL caching."""
    global _fundamentals_cache, _fundamentals_cache_ts
    now = time.monotonic()
    cached_ts = _fundamentals_cache_ts.get(symbol, 0.0)
    if symbol in _fundamentals_cache and (now - cached_ts) < FUNDAMENTALS_CACHE_TTL:
        return _fundamentals_cache[symbol]
    try:
        # yfinance has no built-in timeout; a stalled Yahoo request can block for 15-20s.
        # Run it in a dedicated thread so we can cap the wait at YFINANCE_TIMEOUT_S.
        # On timeout, fall through to the stale-cache / empty-dict fallback below.
        with ThreadPoolExecutor(max_workers=1) as _yf_pool:
            _yf_future = _yf_pool.submit(lambda: yf.Ticker(symbol).info)
            try:
                info = _yf_future.result(timeout=YFINANCE_TIMEOUT_S)
            except Exception:
                stale = _fundamentals_cache.get(symbol)
                if stale is not None:
                    logger.warning("yfinance timeout/error for %s — returning stale cache", symbol)
                    return stale
                raise

        # Earnings date: yfinance returns a list of timestamps or a single Timestamp
        earnings_date: str | None = None
        raw_ed = info.get("earningsDate") or info.get("earningsTimestamp")
        if raw_ed is not None:
            try:
                # May be a list (next + last) or a single value; take the first
                if isinstance(raw_ed, (list, tuple)) and len(raw_ed) > 0:
                    raw_ed = raw_ed[0]
                # pandas Timestamp or epoch int
                if hasattr(raw_ed, "strftime"):
                    earnings_date = raw_ed.strftime("%Y-%m-%d")
                else:
                    earnings_date = datetime.fromtimestamp(int(raw_ed)).strftime("%Y-%m-%d")
            except Exception:
                earnings_date = None

        # Recent split: combine factor + date if available
        recent_split: str | None = None
        split_factor = info.get("lastSplitFactor")
        split_date = info.get("lastSplitDate")
        if split_factor:
            if split_date:
                try:
                    if hasattr(split_date, "strftime"):
                        date_str = split_date.strftime("%Y-%m-%d")
                    else:
                        date_str = datetime.fromtimestamp(int(split_date)).strftime("%Y-%m-%d")
                    recent_split = f"{split_factor} ({date_str})"
                except Exception:
                    recent_split = str(split_factor)
            else:
                recent_split = str(split_factor)

        fundamentals = {
            "market_cap": info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "float_shares": info.get("floatShares"),
            "short_interest": info.get("sharesShort"),
            "short_ratio": info.get("shortRatio"),
            "short_percent_of_float": info.get("shortPercentOfFloat"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps": info.get("trailingEps"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "earnings_date": earnings_date,
            "recent_split": recent_split,
            "average_volume": info.get("averageVolume"),
            "current_volume": info.get("volume"),
        }
        _fundamentals_cache[symbol] = fundamentals
        _fundamentals_cache_ts[symbol] = now
        return fundamentals
    except Exception:
        empty: dict = {
            "market_cap": None, "shares_outstanding": None, "float_shares": None,
            "short_interest": None, "short_ratio": None, "short_percent_of_float": None,
            "pe_ratio": None, "forward_pe": None, "eps": None, "sector": None,
            "industry": None, "fifty_two_week_high": None, "fifty_two_week_low": None,
            "dividend_yield": None, "beta": None, "earnings_date": None, "recent_split": None,
            "average_volume": None, "current_volume": None,
        }
        _fundamentals_cache[symbol] = empty
        _fundamentals_cache_ts[symbol] = now
        return empty


def _fetch_fundamentals_batch(symbols: list[str]) -> None:
    """Populate the fundamentals cache for a list of symbols (skips already-cached ones)."""
    now = time.monotonic()
    missing = [
        s for s in symbols
        if s not in _fundamentals_cache
        or (now - _fundamentals_cache_ts.get(s, 0.0)) >= FUNDAMENTALS_CACHE_TTL
    ]
    for sym in missing:
        _fetch_fundamentals(sym)


# ── Tradable assets ───────────────────────────────────────────────────────────

def _is_common_stock(asset: dict) -> bool:
    """Single source of truth: should this Alpaca asset appear in any scan?

    All symbol-exclusion rules live here. To add a new exclusion, add it here.
    To remove one, remove it here. No other function should make this decision.
    """
    if _SCAN_REQUIRE_TRADABLE and not asset.get("tradable"):
        return False
    sym = asset.get("symbol", "")
    if SYMBOL_EXCLUDE_RE.search(sym):                                    # structural: slashes, test symbols
        return False
    name = (asset.get("name") or "").lower()
    if any(kw.lower() in name for kw in EXCLUDED_NAME_KEYWORDS):        # semantic: Warrant, ETF, etc.
        return False
    if _hod_momo.is_blocked(sym):                                        # user blocklist
        return False
    return True


def invalidate_universe_cache() -> None:
    """Force the next _get_tradable_symbols call to re-fetch (e.g. after blocklist change)."""
    global _assets_cache_ts
    _assets_cache_ts = 0.0
    _ws_mark_resub()


def _get_tradable_symbols(base_url: str, headers: dict) -> list[str]:
    """Fetch common-stock symbols for scanning, cached for one hour.

    Uses exchange-based filtering (NYSE, NASDAQ, AMEX) so that any listed
    common stock can appear as a gapper (~3,500–4,000 symbols). All exclusion
    logic (ETFs, warrants, rights, test symbols, etc.) is centralised in
    _is_common_stock(); do not add filter conditions here.
    """
    global _assets_cache, _assets_cache_set, _assets_cache_ts
    now = time.monotonic()
    if _assets_cache and (now - _assets_cache_ts) < _ASSETS_CACHE_TTL:
        return _assets_cache
    try:
        all_assets: list[dict] = []
        for exchange in SCAN_EXCHANGES:
            resp = requests.get(
                f"{base_url}/v2/assets",
                headers=headers,
                params={"status": "active", "asset_class": "us_equity", "exchange": exchange},
                timeout=20,
            )
            if resp.status_code == 200:
                all_assets.extend(resp.json())

        if not all_assets:
            return _assets_cache

        symbols = [a["symbol"] for a in all_assets if _is_common_stock(a)]
        _assets_cache = symbols
        _assets_cache_set = set(symbols)
        _assets_cache_ts = now
        return _assets_cache
    except Exception:
        return _assets_cache


# ── Snapshots ─────────────────────────────────────────────────────────────────

def _fetch_snapshots(symbols: list[str], headers: dict) -> dict:
    """Fetch snapshots for a list of symbols in parallel batches of 100.

    Uses a thread pool so that large universes (~4,000 symbols = ~40 batches)
    complete in ~1 second instead of ~8 seconds sequential.
    """
    if not symbols:
        return {}
    feed = _get_feed()
    chunks = [symbols[i: i + 100] for i in range(0, len(symbols), 100)]

    def _fetch_chunk(chunk: list[str]) -> dict:
        try:
            resp = requests.get(
                f"{_DATA_URL}/v2/stocks/snapshots",
                headers=headers,
                params={"symbols": ",".join(chunk), "feed": feed},
                timeout=15,
            )
            return resp.json() if resp.status_code == 200 else {}
        except Exception:
            return {}

    result: dict = {}
    with ThreadPoolExecutor(max_workers=SNAPSHOT_WORKERS) as pool:
        futures = {pool.submit(_fetch_chunk, c): c for c in chunks}
        for fut in as_completed(futures):
            try:
                result.update(fut.result())
            except Exception:
                continue
    return result


# ── Average daily volume ──────────────────────────────────────────────────────

def _ensure_avg_volume(symbols: list[str], headers: dict) -> None:
    """Lazily populate avg_volume_cache for any symbols not yet cached today."""
    global _avg_volume_cache, _avg_volume_date
    today = date.today().isoformat()
    if _avg_volume_date != today:
        _avg_volume_cache = {}
        _avg_volume_date = today
    missing = [s for s in symbols if s not in _avg_volume_cache]
    if not missing:
        return
    feed = _get_feed()
    for i in range(0, len(missing), 100):
        chunk = missing[i: i + 100]
        try:
            resp = requests.get(
                f"{_DATA_URL}/v2/stocks/bars",
                headers=headers,
                params={
                    "symbols": ",".join(chunk),
                    "timeframe": "1Day",
                    "limit": RVOL_LOOKBACK_DAYS,
                    "start": (date.today() - timedelta(days=45)).isoformat(),
                    "end": date.today().isoformat(),
                    "feed": feed,
                },
                timeout=20,
            )
            if resp.status_code == 403 and "sip" in resp.text.lower():
                    if _try_fallback_to_iex("avg_volume bars 403 SIP rejection"):
                        feed = _get_feed()
                        # Retry this chunk with the new feed
                        resp = requests.get(
                            f"{_DATA_URL}/v2/stocks/bars",
                            headers=headers,
                            params={
                                "symbols": ",".join(chunk),
                                "timeframe": "1Day",
                                "limit": RVOL_LOOKBACK_DAYS,
                                "start": (date.today() - timedelta(days=45)).isoformat(),
                                "end": date.today().isoformat(),
                                "feed": feed,
                            },
                            timeout=20,
                        )
                        if resp.status_code != 200:
                            logger.warning("avg_volume bars API returned %s after fallback: %s", resp.status_code, resp.text[:200])
                            continue
                    else:
                        logger.warning("avg_volume bars API returned %s: %s", resp.status_code, resp.text[:200])
                        continue
            elif resp.status_code != 200:
                logger.warning("avg_volume bars API returned %s: %s", resp.status_code, resp.text[:200])
                continue
            bars_data = resp.json().get("bars", {})
            for sym, bars in bars_data.items():
                vols = [b.get("v", 0) for b in bars if b.get("v", 0) > 0]
                if vols:
                    _avg_volume_cache[sym] = sum(vols) / len(vols)
        except Exception:
            logger.exception("avg_volume fetch failed for chunk %s", chunk)


# ── News ──────────────────────────────────────────────────────────────────────

def _check_news(symbols: list[str], headers: dict) -> dict[str, str]:
    """Return dict mapping symbol -> newest article created_at (ISO string) for articles today (ET date)."""
    if not symbols:
        return {}
    today = _now_et().date().isoformat()
    try:
        resp = requests.get(
            f"{_DATA_URL}/v1beta1/news",
            headers=headers,
            params={"symbols": ",".join(symbols[:50]), "start": today, "limit": 50},
            timeout=10,
        )
        if resp.status_code != 200:
            return {}
        out: dict[str, str] = {}
        for article in resp.json().get("news", []):
            created_at = article.get("created_at", "")
            for s in article.get("symbols", []):
                # Keep the most recent created_at per symbol
                if s not in out or created_at > out[s]:
                    out[s] = created_at
        return out
    except Exception:
        return {}


# ── Health ping ───────────────────────────────────────────────────────────────


def _set_health_broker_keys_missing() -> None:
    """Alpaca headers unavailable — scans cannot run; avoid leaving /api/health stuck on 'loading'."""
    global _cached_health
    _cached_health = {
        "status": "error",
        "latency_ms": 0,
        "message": (
            "Broker API keys are not set on this server. "
            "In Railway (Backend service → Variables), add APCA_API_KEY_ID and "
            "APCA_API_SECRET_KEY, then redeploy or restart. "
            "Until then, /api/health stays in this state instead of 'loading'."
        ),
    }


def _ping_health(base_url: str, headers: dict) -> bool:
    global _cached_health
    start = datetime.now()
    try:
        r = requests.get(f"{base_url}/v2/account", headers=headers, timeout=5)
        latency = math.floor((datetime.now() - start).total_seconds() * 1000)
        if r.status_code == 200:
            _cached_health = {"status": "connected", "latency_ms": latency}
            return True
        _cached_health = {"status": "error", "latency_ms": latency,
                          "message": f"Alpaca HTTP {r.status_code}: {(r.text or '')[:200]}"}
        return False
    except Exception as e:
        _cached_health = {"status": "disconnected", "latency_ms": 0, "message": str(e)}
        return False


# ── Gapper helpers ────────────────────────────────────────────────────────────

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
            ts = datetime.fromisoformat(daily_ts.replace("Z", "+00:00"))
            if ts.astimezone(_ET).date() < _now_et().date():
                return daily_bar.get("c") or 0
        except (ValueError, AttributeError):
            pass
    return prev_bar.get("c") or 0


def _gapper_meets_min_gap(gap_frac: float | None) -> bool:
    """True if gap as a fraction (e.g. 0.1 = 10%) is at or above the configured floor."""
    if gap_frac is None:
        return False
    return gap_frac * 100 >= _MIN_GAP_PCT


def _prune_gappers_below_min(gappers: list[dict]) -> list[dict]:
    return [g for g in gappers if _gapper_meets_min_gap(g.get("gap_percent"))]


def _compute_gappers(snaps: dict, ref_bar_key: str = "prevDailyBar") -> list[dict]:
    """Compute gap entries from snapshot data.

    ref_bar_key controls which bar supplies the reference close price:
    - "prevDailyBar" (default): gap vs previous session close — used for pre-market.
      Uses _pick_prev_close() which detects whether dailyBar is yesterday's or today's
      bar based on its timestamp, resolving the Alpaca pre-market bar ambiguity.
    - "dailyBar": gap vs today's regular-session close — used for after-hours.
    """
    gappers: list[dict] = []
    for sym, snap in snaps.items():
        latest_trade = snap.get("latestTrade") or {}
        daily_bar = snap.get("dailyBar") or {}
        # Prefer the latest executed trade price; fall back to the current
        # session's bar close (dailyBar.c) for stocks that have price
        # movement reflected in bid/ask but no executed trade yet.
        price = latest_trade.get("p") or daily_bar.get("c", 0)
        if ref_bar_key == "prevDailyBar":
            # Use timestamp-aware helper: during pre-market dailyBar IS yesterday's close.
            prev_close = _pick_prev_close(snap)
        else:
            prev_close = (snap.get(ref_bar_key) or {}).get("c", 0)
        volume = daily_bar.get("v", 0)
        if not price or not prev_close:
            continue
        if price < SCANNER_MIN_PRICE:
            continue
        gap_frac = (price - prev_close) / prev_close
        if not _gapper_meets_min_gap(gap_frac):
            continue
        change_abs = price - prev_close
        change_pct = gap_frac  # same ratio as gap for gappers
        gappers.append({
            "symbol": sym,
            "price": price,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "change_abs": change_abs,
            "previous_close": prev_close,   # kept for WS handler compat
            "current_price": price,         # kept for WS handler compat
            "gap_percent": gap_frac,
            "volume": volume,
        })
    gappers.sort(key=lambda x: x["gap_percent"], reverse=True)
    return gappers[:_TOP_N]


def _enrich_gappers(gappers: list[dict], news: dict[str, str]) -> list[dict]:
    symbols = [g["symbol"] for g in gappers]
    _fetch_fundamentals_batch(symbols)
    for g in gappers:
        sym = g["symbol"]
        avg_vol = _avg_volume_cache.get(sym)
        vol = g["volume"]
        g["rel_volume"] = round(vol / avg_vol, 2) if avg_vol and avg_vol > 0 and vol > 0 else None
        g["has_news"] = sym in news
        g["newest_headline_at"] = news.get(sym)
        fund = _fundamentals_cache.get(sym, {})
        g["market_cap"] = fund.get("market_cap")
        g["float"] = fund.get("float_shares")
        g["short_interest"] = fund.get("short_interest")
        g["short_ratio"] = fund.get("short_ratio")
    return gappers


# ── WebSocket helpers ─────────────────────────────────────────────────────────

def _ws_mark_resub() -> None:
    """Signal the WebSocket loop to sync subscriptions on next iteration."""
    global _ws_needs_resub
    _ws_needs_resub = True


def _refresh_hod_momo_universe() -> None:
    """Populate _hod_momo_universe with the full common-stock universe so the HOD Momo
    engine receives trade updates for all eligible symbols.

    Uses the existing asset cache (_get_tradable_symbols) so it does not issue
    extra Alpaca API calls when the cache is warm.  Only runs when the interval
    has elapsed to avoid hammering the API during active scans.
    """
    global _hod_momo_universe, _hod_momo_universe_ts
    now = time.monotonic()
    if _hod_momo_universe and (now - _hod_momo_universe_ts) < HOD_MOMO_UNIVERSE_INTERVAL_SEC:
        return
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if not headers:
        return
    try:
        symbols = _get_tradable_symbols(base_url, headers)
        _hod_momo_universe = set(symbols)
        _hod_momo_universe_ts = now
        _ws_mark_resub()
        logger.info("HOD Momo: universe refreshed — %d symbols subscribed", len(_hod_momo_universe))
    except Exception as exc:
        logger.warning("HOD Momo universe refresh failed: %s", exc)


def get_hod_momo_universe() -> set[str]:
    """Expose the current HOD Momo universe to hod_momo_enrichment.py."""
    return _hod_momo_universe


def _ws_current_symbols() -> set[str]:
    """Return the union of all symbols across all scanner caches, open ticker WS clients,
    and the HOD Momo universe."""
    syms: set[str] = set()
    for g in _gapper_cache:
        syms.add(g["symbol"])
    for g in _afterhours_cache:
        syms.add(g["symbol"])
    for g in _gainer_cache:
        syms.add(g["symbol"])
    for g in _loser_cache:
        syms.add(g["symbol"])
    # Ticker detail WS clients are kept even if blocked (needed for unblock workflow).
    for sym, clients in _ticker_ws_clients.items():
        if clients:
            syms.add(sym)
    syms.update(_hod_momo_universe)
    # Strip blocked symbols from trade subscriptions (except open detail clients above).
    syms = {s for s in syms if not _hod_momo.is_blocked(s) or s in _ticker_ws_clients}
    return syms


def _apply_trade_to_mover_list(cache: list[dict], sym: str, price: float, size: int = 0) -> bool:
    """Update price/change/volume fields for a symbol in a mover list (gainers or losers).

    Evicts the entry if the new price falls below SCANNER_MIN_PRICE — keeping the
    cache consistent with the scan-time filter without waiting for the next poll.
    Returns True if the symbol was found (updated or evicted), False if not present.
    """
    for i, g in enumerate(cache):
        if g["symbol"] == sym:
            if price < SCANNER_MIN_PRICE:
                del cache[i]
                return True
            prev_close = g.get("prev_close") or 0.0
            if prev_close:
                new_change_abs = price - prev_close
                new_change_pct = new_change_abs / prev_close
            else:
                new_change_abs = g.get("change_abs", 0)
                new_change_pct = g.get("change_pct", 0)
            cache[i] = {
                **g,
                "price": price,
                "change_abs": new_change_abs,
                "change_pct": new_change_pct,
                "volume": g.get("volume", 0) + size,
            }
            return True
    return False


def _handle_trade(msg: dict) -> int | None:
    """Apply a real-time trade message to the in-memory caches.

    Returns the updated cumulative volume for the symbol from whichever cache
    was touched, or None if the symbol was not found in any cache.
    """
    global _gapper_cache, _gapper_cache_ts, _afterhours_cache, _afterhours_cache_ts
    global _gainer_cache, _gainer_cache_ts, _loser_cache, _loser_cache_ts
    sym = msg.get("S")
    price = msg.get("p")
    if not sym or not price:
        return None
    size = int(msg.get("s") or 0)
    now = time.time()
    updated_volume: int | None = None

    # Update gappers — only during pre-market; after 9:30 the list is preserved as-is.
    if _current_mode == "premarket":
        for i, g in enumerate(_gapper_cache):
            if g["symbol"] == sym:
                prev_close = g["previous_close"]
                new_gap = (price - prev_close) / prev_close if prev_close else g["gap_percent"]
                if price < SCANNER_MIN_PRICE or not _gapper_meets_min_gap(new_gap):
                    del _gapper_cache[i]
                else:
                    new_vol = g.get("volume", 0) + size
                    _gapper_cache[i] = {
                        **g,
                        "price": price,
                        "current_price": price,
                        "change_pct": new_gap,
                        "change_abs": price - prev_close,
                        "gap_percent": new_gap,
                        "volume": new_vol,
                    }
                    updated_volume = new_vol
                _gapper_cache_ts = now
                save_gapper_snapshot(_gapper_cache, _gapper_cache_ts)
                break

    # Update after-hours list — only during after-hours; list is preserved after 8 PM.
    if _current_mode == "afterhours":
        for i, g in enumerate(_afterhours_cache):
            if g["symbol"] == sym:
                prev_close = g["previous_close"]
                new_gap = (price - prev_close) / prev_close if prev_close else g["gap_percent"]
                if price < SCANNER_MIN_PRICE or not _gapper_meets_min_gap(new_gap):
                    del _afterhours_cache[i]
                else:
                    new_vol = g.get("volume", 0) + size
                    _afterhours_cache[i] = {
                        **g,
                        "price": price,
                        "current_price": price,
                        "change_pct": new_gap,
                        "change_abs": price - prev_close,
                        "gap_percent": new_gap,
                        "volume": new_vol,
                    }
                    updated_volume = new_vol
                _afterhours_cache_ts = now
                save_afterhours_snapshot(_afterhours_cache, _afterhours_cache_ts)
                break

    # Update gainers — always apply.
    gainer_updated = _apply_trade_to_mover_list(_gainer_cache, sym, price, size)
    if gainer_updated:
        _gainer_cache_ts = now
        if updated_volume is None:
            entry = next((g for g in _gainer_cache if g["symbol"] == sym), None)
            if entry:
                updated_volume = entry.get("volume")

    # Update losers — always apply.
    loser_updated = _apply_trade_to_mover_list(_loser_cache, sym, price, size)
    if loser_updated:
        _loser_cache_ts = now
        if updated_volume is None:
            entry = next((g for g in _loser_cache if g["symbol"] == sym), None)
            if entry:
                updated_volume = entry.get("volume")

    if gainer_updated or loser_updated:
        save_movers_snapshot(_gainer_cache, _loser_cache, now)

    return updated_volume


async def _broadcast_trade_update(
    sym: str,
    price: float,
    size: int | None,
    timestamp: str | None,
    volume: int | None = None,
) -> None:
    """Push a lightweight trade update to all ticker detail WS clients watching this symbol."""
    clients = _ticker_ws_clients.get(sym)
    if not clients:
        return
    payload = json.dumps({
        "type": "trade_update",
        "price": price,
        "size": size,
        "timestamp": timestamp,
        "volume": volume,
    })
    dead: list = []
    for ws in list(clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


# ── Pre-market scan functions ─────────────────────────────────────────────────

def _run_discovery_scan() -> None:
    """Full universe scan: fetch all NYSE/NASDAQ/AMEX common stocks (~3,500–4,000), filter gappers, enrich."""
    global _gapper_cache, _gapper_cache_ts, _last_discovery_ts
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if not headers:
        return
    if not _ping_health(base_url, headers):
        return

    symbols = _get_tradable_symbols(base_url, headers)
    if not symbols:
        return

    snaps = _fetch_snapshots(symbols, headers)

    # Auto-fallback: if SIP returned nothing and we haven't fallen back yet, try IEX
    if not snaps and _try_fallback_to_iex("snapshot fetch returned empty on discovery scan"):
        snaps = _fetch_snapshots(symbols, headers)

    gappers = _compute_gappers(snaps)
    gapper_syms = [g["symbol"] for g in gappers]
    _ensure_avg_volume(gapper_syms, headers)
    news = _check_news(gapper_syms, headers)
    gappers = _enrich_gappers(gappers, news)

    _gapper_cache = gappers
    _gapper_cache_ts = time.time()      # wall-clock for frontend display
    _last_discovery_ts = time.monotonic()  # monotonic for internal TTL check
    _ws_mark_resub()  # notify WebSocket loop to subscribe to newly discovered symbols
    save_gapper_snapshot(_gapper_cache, _gapper_cache_ts)


def _run_focus_scan() -> None:
    """Re-price only current gapper candidates (fast 20-sec refresh)."""
    global _gapper_cache, _gapper_cache_ts
    if not _gapper_cache:
        _run_discovery_scan()
        return
    headers = _alpaca_headers()
    if not headers:
        return

    symbols = [g["symbol"] for g in _gapper_cache]
    snaps = _fetch_snapshots(symbols, headers)
    if not snaps:
        return
    news = _check_news(symbols, headers)

    updated: list[dict] = []
    for g in _gapper_cache:
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
        avg_vol = _avg_volume_cache.get(sym)
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
    _gapper_cache = updated
    _gapper_cache_ts = time.time()
    save_gapper_snapshot(_gapper_cache, _gapper_cache_ts)


# ── After-hours scan functions ────────────────────────────────────────────────

def _run_afterhours_discovery_scan() -> None:
    """Full universe scan for after-hours movers: same pipeline as pre-market gappers
    but gap is computed vs today's regular-session close (dailyBar.c)."""
    global _afterhours_cache, _afterhours_cache_ts, _last_afterhours_discovery_ts
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if not headers:
        return
    if not _ping_health(base_url, headers):
        return

    symbols = _get_tradable_symbols(base_url, headers)
    if not symbols:
        return

    snaps = _fetch_snapshots(symbols, headers)
    rows = _compute_gappers(snaps, ref_bar_key="dailyBar")
    row_syms = [r["symbol"] for r in rows]
    _ensure_avg_volume(row_syms, headers)
    news = _check_news(row_syms, headers)
    rows = _enrich_gappers(rows, news)

    _afterhours_cache = rows
    _afterhours_cache_ts = time.time()
    _last_afterhours_discovery_ts = time.monotonic()
    _ws_mark_resub()
    save_afterhours_snapshot(_afterhours_cache, _afterhours_cache_ts)


def _run_afterhours_focus_scan() -> None:
    """Re-price only current after-hours candidates (fast 30-sec refresh)."""
    global _afterhours_cache, _afterhours_cache_ts
    if not _afterhours_cache:
        _run_afterhours_discovery_scan()
        return
    headers = _alpaca_headers()
    if not headers:
        return

    symbols = [r["symbol"] for r in _afterhours_cache]
    snaps = _fetch_snapshots(symbols, headers)
    if not snaps:
        return
    news = _check_news(symbols, headers)

    updated: list[dict] = []
    for r in _afterhours_cache:
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
        avg_vol = _avg_volume_cache.get(sym)
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
    _afterhours_cache = updated
    _afterhours_cache_ts = time.time()
    save_afterhours_snapshot(_afterhours_cache, _afterhours_cache_ts)


# ── Market-hours gainers ──────────────────────────────────────────────────────

def _build_mover_entry(raw: dict, snaps: dict, premarket_gap_map: dict) -> dict:
    """Build an enriched mover dict from a raw movers API item and snapshot data."""
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

    avg_vol = _avg_volume_cache.get(sym)
    fund = _fundamentals_cache.get(sym, {})
    return {
        "symbol": sym,
        "price": raw.get("price", 0),
        "change_pct": raw.get("percent_change", 0) / 100.0,
        "change_abs": raw.get("change", 0),
        "volume": volume,
        "gap_percent": gap_pct,
        "rel_volume": round(volume / avg_vol, 2) if avg_vol and avg_vol > 0 and volume > 0 else None,
        "has_news": False,   # filled in by caller after news check
        "newest_headline_at": None,
        "market_cap": fund.get("market_cap"),
        "float": fund.get("float_shares"),
        "short_interest": fund.get("short_interest"),
        "short_ratio": fund.get("short_ratio"),
        "prev_close": prev_close,
    }


def _run_gainers_update() -> None:
    """Fetch top gainers and losers via Alpaca Screener Movers API, enrich with snapshots + RVOL + news."""
    global _gainer_cache, _gainer_cache_ts, _loser_cache, _loser_cache_ts
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if not headers:
        return
    if not _ping_health(base_url, headers):
        return

    # 1. Movers API — 1 call, returns top N gainers AND losers market-wide
    try:
        resp = requests.get(
            f"{_DATA_URL}/v1beta1/screener/stocks/movers",
            headers=headers,
            params={"top": min(_TOP_N, 50)},   # endpoint max is 50
            timeout=10,
        )
        if resp.status_code != 200:
            return
        movers_json = resp.json()
        gainers_raw = movers_json.get("gainers", [])
        losers_raw = movers_json.get("losers", [])
    except Exception:
        return

    if not gainers_raw and not losers_raw:
        return

    # Apply price floor early — before any enrichment calls — so we never fetch
    # snapshots, fundamentals, or news for sub-threshold stocks.
    gainers_raw = [r for r in gainers_raw if r.get("price", 0) >= SCANNER_MIN_PRICE]
    losers_raw  = [r for r in losers_raw  if r.get("price", 0) >= SCANNER_MIN_PRICE]

    all_symbols = list({r["symbol"] for r in gainers_raw + losers_raw})

    # 2. Snapshot enrichment — 1 call for all mover symbols
    snaps = _fetch_snapshots(all_symbols, headers)

    # 3. Average volume for RVOL (lazy, cached per day)
    _ensure_avg_volume(all_symbols, headers)

    # 4. News check — 1 call covering all symbols
    news = _check_news(all_symbols, headers)

    # 5. Fetch fundamentals for all mover symbols
    _fetch_fundamentals_batch(all_symbols)

    # 6. Build enriched lists
    premarket_gap_map = {g["symbol"]: g.get("gap_percent") for g in _gapper_cache}

    gainers: list[dict] = []
    for raw in gainers_raw:
        entry = _build_mover_entry(raw, snaps, premarket_gap_map)
        sym = entry["symbol"]
        entry["has_news"] = sym in news
        entry["newest_headline_at"] = news.get(sym)
        gainers.append(entry)

    losers: list[dict] = []
    for raw in losers_raw:
        entry = _build_mover_entry(raw, snaps, premarket_gap_map)
        sym = entry["symbol"]
        entry["has_news"] = sym in news
        entry["newest_headline_at"] = news.get(sym)
        losers.append(entry)

    _gainer_cache = gainers
    _gainer_cache_ts = time.time()
    _loser_cache = losers
    _loser_cache_ts = time.time()
    save_movers_snapshot(_gainer_cache, _loser_cache, _gainer_cache_ts)
    _ws_mark_resub()  # notify WebSocket loop to subscribe to newly discovered symbols


# ── WebSocket streaming loop ──────────────────────────────────────────────────

async def _ws_stream_loop() -> None:
    """Persistent WebSocket connection to Alpaca's real-time SIP feed.

    Subscribes to trades for all symbols in the gapper/gainer caches and
    applies each trade message to the in-memory cache instantly, giving the
    frontend sub-second price freshness on every 1s poll.

    Auto-reconnects with exponential backoff on any failure.
    """
    global _ws_subscribed, _ws_needs_resub
    backoff = 1.0

    while True:
        try:
            api_key = _env("APCA_API_KEY_ID")
            api_secret = _env("APCA_API_SECRET_KEY")
            if not api_key or not api_secret:
                logger.warning("Alpaca WS: no API keys configured, sleeping 10s")
                await asyncio.sleep(10)
                continue

            feed = _get_feed()
            url = f"wss://stream.data.alpaca.markets/v2/{feed}"
            logger.info("Alpaca WS connecting to %s", url)

            async with websockets.connect(url, ping_interval=20, open_timeout=15) as ws:
                # Receive the initial "connected" banner
                await ws.recv()

                # Authenticate
                await ws.send(json.dumps({"action": "auth", "key": api_key, "secret": api_secret}))
                auth_msgs = json.loads(await ws.recv())
                if not any(m.get("T") == "success" and m.get("msg") == "authenticated"
                           for m in auth_msgs):
                    # Check if the failure is a subscription-level error (409 = insufficient subscription)
                    is_sub_error = any(m.get("code") == 409 for m in auth_msgs)
                    if is_sub_error and _try_fallback_to_iex("WS auth 409 insufficient subscription"):
                        backoff = 1.0  # reset backoff since we're trying a different feed
                        continue
                    # Auth failed — back off and retry (keys may have just changed)
                    logger.warning("Alpaca WS auth failed (response: %s), retrying in %.1fs", auth_msgs, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, ALPACA_WS_BACKOFF_CAP)
                    continue

                # Successfully connected and authenticated — reset backoff
                logger.info("Alpaca WS authenticated")
                backoff = 1.0
                _ws_subscribed = set()
                _ws_needs_resub = True  # subscribe to whatever is cached right now

                while True:
                    # Sync subscriptions whenever the scan loop adds/removes symbols
                    if _ws_needs_resub:
                        _ws_needs_resub = False
                        wanted = _ws_current_symbols()
                        to_add = wanted - _ws_subscribed
                        to_remove = _ws_subscribed - wanted
                        if to_add or to_remove:
                            logger.info(
                                "Alpaca WS subscribing +%d / -%d symbols (total %d)",
                                len(to_add), len(to_remove), len(wanted),
                            )
                        if to_add:
                            await ws.send(json.dumps({"action": "subscribe", "trades": list(to_add)}))
                        if to_remove:
                            await ws.send(json.dumps({"action": "unsubscribe", "trades": list(to_remove)}))
                        _ws_subscribed = wanted

                    # Wait for the next message (1s timeout lets us check _ws_needs_resub)
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        msgs = json.loads(raw)
                        for msg in msgs:
                            if msg.get("T") == "t":
                                updated_vol = _handle_trade(msg)
                                sym = msg.get("S")
                                price = msg.get("p")
                                if sym and price:
                                    trade_ts = time.time()
                                    # Feed HOD Momo engine (non-blocking — runs in same thread)
                                    _hod_momo.on_trade_update(
                                        sym,
                                        float(price),
                                        trade_ts,
                                        volume=updated_vol,
                                    )
                                    # Local tape recorder for watched L2/session symbols
                                    try:
                                        from l2 import tape as _l2_tape
                                        _l2_tape.on_alpaca_trade(
                                            sym,
                                            float(price),
                                            float(msg.get("s") or 0),
                                            trade_ts,
                                            exchange=msg.get("x"),
                                        )
                                    except Exception:
                                        logger.exception("l2.tape: ingest failed for %s", sym)
                                if sym and sym in _ticker_ws_clients and _ticker_ws_clients[sym]:
                                    asyncio.create_task(_broadcast_trade_update(
                                        sym,
                                        msg.get("p"),
                                        msg.get("s"),
                                        msg.get("t"),
                                        updated_vol,
                                    ))
                    except asyncio.TimeoutError:
                        pass  # no message arrived; loop back to check resub flag

        except asyncio.CancelledError:
            logger.info("Alpaca WS shutting down cleanly")
            raise
        except Exception as exc:
            logger.warning("Alpaca WS disconnected: %s, retrying in %.1fs", exc, backoff)
            _ws_subscribed = set()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, ALPACA_WS_BACKOFF_CAP)


# ── News catalyst scan ────────────────────────────────────────────────────────

def _run_news_catalyst_scan() -> None:
    """News-first catalyst scanner.

    Queries Alpaca news with no symbol filter to get all recent market-wide
    articles, extracts every ticker mentioned, fetches their snapshots, and
    stores any with a non-trivial gap vs prior close in _news_catalyst_cache.
    This catches IMMP-type situations that the universe-based scanner misses
    because those stocks are not in any pre-screened list until news breaks.
    """
    global _news_catalyst_cache, _news_catalyst_cache_ts, _last_catalyst_scan_ts
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
            print(
                f"[catalyst] news API error {resp.status_code}: {resp.text[:200]}",
                flush=True,
            )
            return

        articles = resp.json().get("news", [])
        print(f"[catalyst] fetched {len(articles)} articles", flush=True)
        if not articles:
            return

        # Build: symbol → most recent article for that symbol
        symbol_to_article: dict[str, dict] = {}
        for article in articles:
            created_at = article.get("created_at", "")
            headline = article.get("headline", "")
            url = article.get("url", "")
            for sym in article.get("symbols", []):
                if sym not in symbol_to_article or created_at > symbol_to_article[sym]["created_at"]:
                    symbol_to_article[sym] = {
                        "created_at": created_at,
                        "headline": headline,
                        "url": url,
                    }

        # Trust the validated universe set — no per-scanner filter logic here.
        # Falls back to allowing all symbols on cold start (set not yet populated).
        universe = _assets_cache_set
        news_symbols = [
            s for s in symbol_to_article.keys()
            if not universe or s in universe
        ]
        print(f"[catalyst] {len(news_symbols)} unique symbols from news", flush=True)
        if not news_symbols:
            return

        snaps = _fetch_snapshots(news_symbols, headers)
        if not snaps:
            return

        catalysts: list[dict] = []
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
            catalysts.append({
                "symbol": sym,
                "previous_close": prev_close,
                "current_price": price,
                "gap_percent": gap_frac,
                "volume": volume,
                "has_news": True,
                "newest_headline_at": article_info.get("created_at"),
                "catalyst_headline": article_info.get("headline"),
                "catalyst_url": article_info.get("url"),
            })

        catalysts.sort(key=lambda x: abs(x["gap_percent"]), reverse=True)
        # Attach explicit news-impact verdicts (rules-first; see news/impact.py).
        catalysts = [enrich_catalyst_row(c) for c in catalysts]
        print(f"[catalyst] scan complete — {len(catalysts)} catalysts", flush=True)
        _news_catalyst_cache = catalysts
        _news_catalyst_cache_ts = time.time()
        _last_catalyst_scan_ts = time.monotonic()

    except Exception as exc:
        print(f"[catalyst] scan exception: {exc}", flush=True)


# ── Background scan loop ──────────────────────────────────────────────────────

async def _scan_loop() -> None:
    global _current_mode
    loop = asyncio.get_event_loop()
    while True:
        try:
            mono = time.monotonic()
            catalyst_due = (mono - _last_catalyst_scan_ts) > _NEWS_CATALYST_INTERVAL
            # Refresh HOD Momo trade universe periodically (uses cached asset list — cheap)
            await loop.run_in_executor(None, _refresh_hod_momo_universe)

            if _in_premarket():
                _current_mode = "premarket"
                if not _gapper_cache or (mono - _last_discovery_ts) > _DISCOVERY_INTERVAL:
                    await loop.run_in_executor(None, _run_discovery_scan)
                else:
                    await loop.run_in_executor(None, _run_focus_scan)
                # Populate movers/gainers with previous day's data during pre-market.
                # Alpaca returns the prior session's movers until the next market open.
                if not _gainer_cache:
                    await loop.run_in_executor(None, _run_gainers_update)
                if catalyst_due:
                    await loop.run_in_executor(None, _run_news_catalyst_scan)
                await asyncio.sleep(_FOCUS_INTERVAL)
            elif _in_market_hours():
                _current_mode = "market"
                await loop.run_in_executor(None, _run_gainers_update)
                if catalyst_due:
                    await loop.run_in_executor(None, _run_news_catalyst_scan)
                await asyncio.sleep(_GAINERS_INTERVAL)
            elif _in_after_hours():
                _current_mode = "afterhours"
                if not _afterhours_cache or (mono - _last_afterhours_discovery_ts) > _AH_DISCOVERY_INTERVAL:
                    await loop.run_in_executor(None, _run_afterhours_discovery_scan)
                else:
                    await loop.run_in_executor(None, _run_afterhours_focus_scan)
                if catalyst_due:
                    await loop.run_in_executor(None, _run_news_catalyst_scan)
                await asyncio.sleep(_AH_FOCUS_INTERVAL)
            else:
                _current_mode = "closed"
                await loop.run_in_executor(None, _run_discovery_scan)
                await loop.run_in_executor(None, _run_gainers_update)
                await asyncio.sleep(_CLOSED_INTERVAL)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Migrate old fixed-name cache files to date-stamped format, then prune old ones.
    _migrate_legacy_files()
    cleanup_old_snapshots(HISTORY_RETENTION_DAYS)

    # Restore gapper snapshot from disk so the pre-market list survives restarts
    # during market hours (when the scan loop never re-runs discovery).
    global _gapper_cache, _gapper_cache_ts, _afterhours_cache, _afterhours_cache_ts
    global _gainer_cache, _gainer_cache_ts, _loser_cache, _loser_cache_ts
    restored, restored_ts = load_gapper_snapshot()
    if restored:
        _gapper_cache = restored
        _gapper_cache_ts = restored_ts

    # Restore after-hours snapshot so the list survives restarts after 8 PM.
    ah_restored, ah_restored_ts = load_afterhours_snapshot()
    if ah_restored:
        _afterhours_cache = ah_restored
        _afterhours_cache_ts = ah_restored_ts

    # Restore movers snapshot so gainers/losers survive restarts during the
    # after-hours window (4-8 PM ET) when the scan loop does not refresh them.
    mv_gainers, mv_losers, mv_ts = load_movers_snapshot()
    if mv_gainers or mv_losers:
        _gainer_cache = mv_gainers
        _loser_cache = mv_losers
        _gainer_cache_ts = mv_ts
        _loser_cache_ts = mv_ts

    # Load HOD Momo persisted state (configs, blocklist, today's alerts)
    _hod_momo.load_state()
    _journal_db.init_db()
    _l2_db.init_db()
    # Wire invalidation so blocklist add/remove flushes the universe cache.
    _hod_momo._on_blocklist_changed = invalidate_universe_cache

    # Ping Alpaca health immediately at startup so the frontend never sits on
    # "loading" status during closed-market hours when no scan would run.
    loop = asyncio.get_event_loop()
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if headers:
        await loop.run_in_executor(None, lambda: _ping_health(base_url, headers))
    else:
        _set_health_broker_keys_missing()
        logger.warning(
            "Alpaca credentials missing (APCA_API_KEY_ID / APCA_API_SECRET_KEY); "
            "scanner cannot run until they are set in the host environment."
        )
    scan_task = asyncio.create_task(_scan_loop())
    ws_task = asyncio.create_task(_ws_stream_loop())
    hod_flush_task = asyncio.create_task(_hod_momo.flush_consolidated_loop())
    hod_reset_task = asyncio.create_task(_hod_momo.session_reset_loop())
    hod_enrich_task = asyncio.create_task(_hod_momo_enrichment.universe_enrichment_loop())
    hod_fund_task = asyncio.create_task(_hod_momo_enrichment.fundamentals_enrichment_loop())
    setups_scan_task = asyncio.create_task(_setups_stream.scan_loop())
    risk_reset_task = asyncio.create_task(_risk.session_reset_loop())
    executor_fill_task = asyncio.create_task(_executor.fill_poll_loop())
    from l2 import batch as _l2_batch
    from constants import L2_RETENTION_SWEEP_INTERVAL_SEC

    async def _l2_retention_loop() -> None:
        while True:
            try:
                await asyncio.sleep(L2_RETENTION_SWEEP_INTERVAL_SEC)
                _l2_db.purge_older_than()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("l2 retention sweep failed")

    l2_flush_task = asyncio.create_task(_l2_batch.flush_loop())
    l2_retention_task = asyncio.create_task(_l2_retention_loop())
    # IBKR client — best-effort, never blocks the Alpaca scan loop
    await _ibkr_client.startup()
    yield
    scan_task.cancel()
    ws_task.cancel()
    hod_flush_task.cancel()
    hod_reset_task.cancel()
    hod_enrich_task.cancel()
    hod_fund_task.cancel()
    setups_scan_task.cancel()
    risk_reset_task.cancel()
    executor_fill_task.cancel()
    l2_flush_task.cancel()
    l2_retention_task.cancel()
    for t in (scan_task, ws_task, hod_flush_task, hod_reset_task, hod_enrich_task, hod_fund_task):
        try:
            await t
        except asyncio.CancelledError:
            pass
    try:
        _l2_batch.flush()
    except Exception:
        logger.exception("l2.batch: final flush failed")
    await _ibkr_client.shutdown()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Nova API", lifespan=lifespan)

app.include_router(_trading_router)
app.include_router(_trading_ws_router)
app.include_router(_strategy_router)
app.include_router(_journal_router)
app.include_router(_executor_router)
app.include_router(_l2_router)
app.include_router(_news_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConfigUpdate(BaseModel):
    api_key: str
    api_secret: str
    base_url: str
    data_feed: str = DATA_FEED_DEFAULT


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/")
def root():
    """Human-friendly root when someone opens the API host in a browser (not an error)."""
    return {
        "service": "Nova API",
        "ok": True,
        "health": "/api/health",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "note": "REST routes live under /api/… A 404 here used to confuse operators; use /api/health to verify connectivity.",
    }


@app.get("/api/health")
def health_check():
    return {
        **_cached_health,
        "data_feed": _get_feed(),
        "feed_fell_back": _feed_fell_back,
    }


@app.get("/api/config")
def get_config():
    return {
        "api_key": _env("APCA_API_KEY_ID") or "",
        "api_secret": _env("APCA_API_SECRET_KEY") or "",
        "base_url": _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets",
        "data_feed": _get_feed(),
        "data_feed_options": list(DATA_FEED_OPTIONS),
    }


@app.post("/api/config")
def update_config(config: ConfigUpdate):
    global _assets_cache_ts, _assets_cache_set, _last_discovery_ts
    env_path = str(env_file_path())
    os.makedirs(os.path.dirname(env_path) or ".", exist_ok=True)
    set_key(env_path, "APCA_API_KEY_ID", config.api_key)
    set_key(env_path, "APCA_API_SECRET_KEY", config.api_secret)
    set_key(env_path, "APCA_API_BASE_URL", config.base_url)
    set_key(env_path, "ALPACA_DATA_FEED", config.data_feed)
    load_dotenv(env_path, override=True)
    _set_feed(config.data_feed)
    _assets_cache_ts = 0.0
    _assets_cache_set = set()
    _last_discovery_ts = 0.0
    _ws_mark_resub()  # WS stream URL changes with feed
    return {"status": "success", "data_feed": _get_feed()}


@app.get("/api/mode")
def get_mode():
    return {
        "mode": _current_mode,
        "health": _cached_health,
        "last_gapper_scan": _gapper_cache_ts,
        "last_gainer_scan": _gainer_cache_ts,
    }


def _strip_blocked(rows: list[dict]) -> list[dict]:
    """Remove any rows whose symbol is on the global blocklist."""
    return [r for r in rows if not _hod_momo.is_blocked(r.get("symbol", ""))]


@app.get("/api/gappers")
def get_gappers():
    """Pre-market gapper list. Returns cached data instantly."""
    return {
        "rev": _NOVA_REV,
        "mode": _current_mode,
        "health": _cached_health,
        "data_feed": _get_feed(),
        "gappers": _strip_blocked(_gapper_cache),
        "last_scan": _gapper_cache_ts,
    }


@app.get("/api/movers")
def get_movers():
    """Top gainers and losers from the Alpaca screener. Returns cached data instantly."""
    return {
        "rev": _NOVA_REV,
        "mode": _current_mode,
        "health": _cached_health,
        "gainers": _strip_blocked(_gainer_cache),
        "losers": _strip_blocked(_loser_cache),
        "last_scan": _gainer_cache_ts,
    }


@app.get("/api/afterhours")
def get_afterhours():
    """After-hours gapper list (4–8 PM ET). Gap computed vs today's regular-session close."""
    return {
        "rev": _NOVA_REV,
        "mode": _current_mode,
        "health": _cached_health,
        "afterhours": _strip_blocked(_afterhours_cache),
        "last_scan": _afterhours_cache_ts,
    }


@app.get("/api/history/dates")
def get_history_dates(type: str = "gappers"):
    """Return available past dates for a cache type. ?type=gappers|movers|afterhours"""
    allowed = {"gappers", "movers", "afterhours"}
    if type not in allowed:
        return {"dates": []}
    return {"dates": list_history_dates(type)}


@app.get("/api/history/{cache_type}/{date}")
def get_history_snapshot(cache_type: str, date: str):
    """Return a historical snapshot for a specific cache type and date (YYYY-MM-DD)."""
    allowed = {"gappers", "movers", "afterhours"}
    if cache_type not in allowed:
        return {}
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return {}
    return load_snapshot_for_date(cache_type, date)


@app.get("/api/news-catalysts")
def get_news_catalysts():
    """News-driven catalyst list. Returns all news-mentioned tickers with price data.

    Unlike the gapper scanner (which scans a fixed universe), this endpoint
    surfaces any ticker that appeared in recent market news regardless of
    exchange or size — the news event is the selection criterion.
    """
    return {
        "rev": _NOVA_REV,
        "mode": _current_mode,
        "health": _cached_health,
        "catalysts": _strip_blocked(_news_catalyst_cache),
        "last_scan": _news_catalyst_cache_ts,
    }


# ── HOD Momo endpoints ────────────────────────────────────────────────────────

@app.get("/api/hod-momo/alerts")
def hod_momo_get_alerts():
    """Today's HOD Momo alert feed (newest first)."""
    return {"date": _hod_momo._current_date_et(), "alerts": _hod_momo.get_today_alerts()}


@app.get("/api/hod-momo/history/dates")
def hod_momo_history_dates():
    """Past dates for which HOD Momo alert snapshots exist."""
    from cache import list_history_dates as _list_dates
    return {"dates": _list_dates("hod-momo")}


@app.get("/api/hod-momo/history/{date}")
def hod_momo_history_snapshot(date: str):
    """HOD Momo alerts for a historical date (YYYY-MM-DD)."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return {}
    return _hod_momo.get_history_alerts(date)


@app.get("/api/hod-momo/config")
def hod_momo_get_config():
    """Return all strategy configs + master gate config."""
    return _hod_momo.get_configs()


class HodMomoConfigPatch(BaseModel):
    scope: str                   # "master" | "strategy" | "all"
    strategy_id: int | None = None
    patch: dict | None = None


@app.post("/api/hod-momo/config")
def hod_momo_update_config(body: HodMomoConfigPatch):
    """Update a strategy config, the master gate, or reset everything.

    scope="master"   → patch applied to master gate
    scope="strategy" → patch applied to strategy_id (required)
    scope="reset_one"→ reset strategy_id to defaults
    scope="reset_all"→ reset all strategies + master gate to defaults
    """
    if body.scope == "reset_all":
        return _hod_momo.reset_all()
    if body.scope == "reset_one":
        if body.strategy_id is None:
            return {"error": "strategy_id required"}
        result = _hod_momo.reset_config(body.strategy_id)
        if result is None:
            return {"error": "unknown strategy_id"}
        return result
    if body.scope == "master":
        return _hod_momo.update_master(body.patch or {})
    if body.scope == "strategy":
        if body.strategy_id is None:
            return {"error": "strategy_id required"}
        result = _hod_momo.update_config(body.strategy_id, body.patch or {})
        if result is None:
            return {"error": "unknown strategy_id"}
        return result
    return {"error": "unknown scope"}


@app.get("/api/hod-momo/blocklist")
def hod_momo_get_blocklist():
    return {"symbols": _hod_momo.get_blocklist()}


class HodMomoBlocklistUpdate(BaseModel):
    symbol: str


@app.post("/api/hod-momo/blocklist")
def hod_momo_add_block(body: HodMomoBlocklistUpdate):
    return {"symbols": _hod_momo.add_block(body.symbol)}


@app.delete("/api/hod-momo/blocklist/{symbol}")
def hod_momo_remove_block(symbol: str):
    return {"symbols": _hod_momo.remove_block(symbol)}


# ── HOD Momo debug endpoints ──────────────────────────────────────────────────

@app.get("/api/hod-momo/debug/counters")
def hod_momo_debug_counters():
    """Gate counters, universe size, and snaps populated — polled by the Debug panel."""
    return _hod_momo.get_debug_counters()


@app.get("/api/hod-momo/debug/symbol/{sym}")
def hod_momo_debug_symbol(sym: str):
    """Current snapshot + last 20 decisions for a specific symbol."""
    return _hod_momo.get_debug_symbol(sym.upper())


@app.get("/api/hod-momo/debug/recent")
def hod_momo_debug_recent(limit: int = 100):
    """Last N decisions across all symbols."""
    return {"decisions": _hod_momo.get_debug_recent(min(limit, 500))}


@app.get("/api/hod-momo/debug/snaps")
def hod_momo_debug_snaps(limit: int = 50):
    """Top-N most-recently enriched snapshots (sanity-check for the enrichment loop)."""
    return {"snaps": _hod_momo.get_debug_snaps(min(limit, 200))}


@app.websocket("/ws/hod-momo")
async def ws_hod_momo(websocket: WebSocket):
    """WebSocket endpoint: sends today's alerts on connect, then pushes live alerts."""
    await websocket.accept()
    _hod_momo.add_ws_client(websocket)
    try:
        # Send initial payload with all of today's alerts
        initial = json.dumps({
            "type": "initial",
            "alerts": _hod_momo.get_today_alerts(),
        })
        await websocket.send_text(initial)
        # Keep the connection alive until the client disconnects
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a keepalive ping
                await websocket.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _hod_momo.remove_ws_client(websocket)


@app.websocket("/ws/strategy")
async def ws_strategy(websocket: WebSocket):
    """WebSocket endpoint: sends recent setup signal history on connect, then
    pushes newly-eligible Gap and Go / Bull Flag / ABCD signals live.
    Signal only — never places, modifies, or cancels an order."""
    await websocket.accept()
    _setups_stream.add_ws_client(websocket)
    try:
        initial = json.dumps({
            "type": "initial",
            "note": "Signal only. This stream never places, modifies, or cancels orders.",
            "signals": _setups_stream.get_signal_history(),
        })
        await websocket.send_text(initial)
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _setups_stream.remove_ws_client(websocket)


def _fetch_ticker_asset(symbol: str, base_url: str, headers: dict) -> dict:
    """Fetch asset metadata from Alpaca Trading API with short-lived TTL cache."""
    global _ticker_asset_cache, _ticker_asset_cache_ts
    now = time.monotonic()
    if symbol in _ticker_asset_cache and (now - _ticker_asset_cache_ts.get(symbol, 0.0)) < TICKER_ASSET_CACHE_TTL:
        return _ticker_asset_cache[symbol]
    asset: dict = {}
    try:
        r = requests.get(f"{base_url}/v2/assets/{symbol}", headers=headers, timeout=10)
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
    except Exception:
        pass
    return asset


def _fetch_ticker_snapshot(symbol: str, headers: dict, feed: str) -> dict:
    """Fetch latest snapshot from Alpaca Data API with short-lived TTL cache."""
    global _ticker_snapshot_cache, _ticker_snapshot_cache_ts
    now = time.monotonic()
    if symbol in _ticker_snapshot_cache and (now - _ticker_snapshot_cache_ts.get(symbol, 0.0)) < TICKER_SNAPSHOT_CACHE_TTL:
        return _ticker_snapshot_cache[symbol]

    def _bar(b: dict | None) -> dict | None:
        if not b:
            return None
        return {
            "open": b.get("o"),
            "high": b.get("h"),
            "low": b.get("l"),
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
            timeout=10,
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
                # Correctly resolved previous regular-session close (timestamp-aware).
                # During pre-market dailyBar is yesterday's completed bar, so
                # _pick_prev_close returns dailyBar.c.  During market/after-hours it
                # returns prevDailyBar.c.  Frontends should use this for change math.
                "prev_close": _pick_prev_close(raw),
                # Last completed regular-session close (always dailyBar.c).
                # Used by the frontend as the "main line" price in the Webull-style
                # two-row quote during pre-market / after-hours.
                "session_close": (raw.get("dailyBar") or {}).get("c"),
                # Close of the session prior to session_close (always prevDailyBar.c).
                # Used to compute the main line's change (session_close - session_prev_close).
                "session_prev_close": (raw.get("prevDailyBar") or {}).get("c"),
            }
            _ticker_snapshot_cache[symbol] = snapshot
            _ticker_snapshot_cache_ts[symbol] = now
    except Exception:
        pass
    return snapshot


def _fetch_ticker_news(symbol: str, headers: dict) -> list[dict]:
    """Fetch today's news articles for a symbol from Alpaca Data API."""
    news: list[dict] = []
    try:
        today = _now_et().date().isoformat()
        r = requests.get(
            f"{_DATA_URL}/v1beta1/news",
            headers=headers,
            params={"symbols": symbol, "start": today, "limit": 10},
            timeout=10,
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
        pass
    return news


def _fetch_ticker_avg_volume(symbol: str, headers: dict) -> float | None:
    """Return average daily volume for symbol, fetching bars from Alpaca if needed."""
    avg_vol = _avg_volume_cache.get(symbol)
    if avg_vol is None:
        _ensure_avg_volume([symbol], headers)
        avg_vol = _avg_volume_cache.get(symbol)
    return avg_vol


def _build_ticker_fast(symbol: str, base_url: str, headers: dict, feed: str) -> dict:
    """Fetch asset + snapshot concurrently — the fast subset of ticker detail."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_asset = pool.submit(_fetch_ticker_asset, symbol, base_url, headers)
        f_snap  = pool.submit(_fetch_ticker_snapshot, symbol, headers, feed)
        asset    = f_asset.result()
        snapshot = f_snap.result()

    avg_vol  = _avg_volume_cache.get(symbol)
    daily_vol = (snapshot.get("daily_bar") or {}).get("volume") or 0
    rel_vol  = round(daily_vol / avg_vol, 2) if avg_vol and avg_vol > 0 and daily_vol > 0 else None

    return {
        "symbol": symbol,
        "asset": asset,
        "snapshot": snapshot,
        "avg_volume": avg_vol,
        "rel_volume": rel_vol,
        "news": [],
        "fundamentals": {},
        # Expose current session mode so the frontend can choose which quote layout to render.
        "mode": _current_mode,
    }


def _build_ticker_slow(symbol: str, headers: dict) -> dict:
    """Fetch news + avg volume bars + fundamentals concurrently — the slow subset.

    Results are cached for TICKER_SLOW_CACHE_TTL seconds so rapid re-clicks and
    tab-switches skip redundant external API calls entirely.
    """
    global _ticker_slow_cache, _ticker_slow_cache_ts
    now = time.monotonic()
    cached_ts = _ticker_slow_cache_ts.get(symbol, 0.0)
    if symbol in _ticker_slow_cache and (now - cached_ts) < TICKER_SLOW_CACHE_TTL:
        return _ticker_slow_cache[symbol]

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
    """Fetch and assemble full ticker detail for a symbol. Used by the REST endpoint."""
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()
    if not headers:
        return {"error": "API keys not configured"}

    feed = _get_feed()

    with ThreadPoolExecutor(max_workers=5) as pool:
        f_asset = pool.submit(_fetch_ticker_asset, symbol, base_url, headers)
        f_snap  = pool.submit(_fetch_ticker_snapshot, symbol, headers, feed)
        f_news  = pool.submit(_fetch_ticker_news, symbol, headers)
        f_avg   = pool.submit(_fetch_ticker_avg_volume, symbol, headers)
        f_fund  = pool.submit(_fetch_fundamentals, symbol)
        asset    = f_asset.result()
        snapshot = f_snap.result()
        news     = f_news.result()
        avg_vol  = f_avg.result()
        fundamentals = f_fund.result()

    daily_vol = (snapshot.get("daily_bar") or {}).get("volume") or 0
    rel_vol = round(daily_vol / avg_vol, 2) if avg_vol and avg_vol > 0 and daily_vol > 0 else None

    return {
        "symbol": symbol,
        "asset": asset,
        "snapshot": snapshot,
        "avg_volume": avg_vol,
        "rel_volume": rel_vol,
        "news": news,
        "fundamentals": fundamentals,
        "news_impact": build_ticker_news_impact(symbol, news, snapshot, rel_vol),
    }


@app.get("/api/ticker/{symbol}")
def get_ticker_detail(symbol: str):
    """Fetch full detail for a single symbol: asset info, snapshot, news, avg volume."""
    return _build_ticker_detail(symbol.upper())


@app.get("/api/ticker/{symbol}/bars")
def get_ticker_bars(
    symbol: str,
    timeframe: str = CHART_DEFAULT_TIMEFRAME,
    limit: int = CHART_DEFAULT_BARS,
):
    """Fetch OHLCV bars for a symbol. Powered by the Alpaca Data API."""
    return _fetch_bars(symbol.upper(), timeframe, limit)


@app.websocket("/ws/ticker/{symbol}")
async def ws_ticker_detail(websocket: WebSocket, symbol: str):
    """WebSocket endpoint: sends full detail on connect, then streams real-time trade updates.

    Two-phase send for perceived speed:
      1. 'initial' — fast data (asset + snapshot + cached avg volume) sent first (~300 ms).
      2. 'detail_update' — slow data (news + fresh avg volume + fundamentals) sent when ready.
    """
    symbol = symbol.upper()
    await websocket.accept()

    if symbol not in _ticker_ws_clients:
        _ticker_ws_clients[symbol] = set()
    _ticker_ws_clients[symbol].add(websocket)
    _ws_mark_resub()

    loop = asyncio.get_event_loop()
    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
    headers = _alpaca_headers()

    try:
        if not headers:
            await websocket.send_text(json.dumps({"type": "initial", "error": "API keys not configured"}))
        else:
            feed = _get_feed()

            # Start both phases immediately so Phase 2 runs while Phase 1 is awaited.
            fast_task = loop.run_in_executor(
                None, lambda: _build_ticker_fast(symbol, base_url, headers, feed)
            )
            slow_task = loop.run_in_executor(
                None, lambda: _build_ticker_slow(symbol, headers)
            )

            # Phase 1 result arrives first — send immediately so the UI can render price/asset.
            fast = await fast_task
            await websocket.send_text(json.dumps({"type": "initial", **fast}))

            # Phase 2 has been running in parallel; await whatever remains.
            slow = await slow_task
            # Recompute rel_volume with freshly fetched avg_vol
            avg_vol = slow.get("avg_volume")
            daily_vol = (fast.get("snapshot", {}).get("daily_bar") or {}).get("volume") or 0
            rel_vol = round(daily_vol / avg_vol, 2) if avg_vol and avg_vol > 0 and daily_vol > 0 else fast.get("rel_volume")
            news_impact = build_ticker_news_impact(
                symbol, slow.get("news") or [], fast.get("snapshot"), rel_vol
            )
            await websocket.send_text(json.dumps({
                "type": "detail_update",
                "news": slow["news"],
                "fundamentals": slow["fundamentals"],
                "avg_volume": avg_vol,
                "rel_volume": rel_vol,
                "news_impact": news_impact,
            }))

        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _ticker_ws_clients.get(symbol, set()).discard(websocket)
        if not _ticker_ws_clients.get(symbol):
            _ticker_ws_clients.pop(symbol, None)
        _ws_mark_resub()
