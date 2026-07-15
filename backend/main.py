from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import os
from dotenv import load_dotenv, set_key
import requests
from datetime import datetime, date, timedelta, timezone
import math
import re
import time
import asyncio
import json
import websockets

logger = logging.getLogger(__name__)

# ── Console + persistent rotating log file ────────────────────────────────────
from paths import env_file_path
from logging_setup import configure_logging
from ibkr import client as _ibkr_client
from ibkr import discovery as _ibkr_discovery
from ibkr import reprice as _ibkr_reprice
from ibkr import ticks as _ibkr_ticks
from chart_bars import fetch_chart_bars as _fetch_chart_bars
from fundamentals import (
    _fundamentals_cache,
    _fundamentals_cache_ts,
    fetch_fundamentals as _fetch_fundamentals,
    fetch_fundamentals_batch as _fetch_fundamentals_batch,
)
from routes.trading import router as _trading_router, ws_router as _trading_ws_router
from routes.strategy import router as _strategy_router
from routes.journal import router as _journal_router
from routes.executor import router as _executor_router
from routes.l2 import router as _l2_router
from routes.news import router as _news_router
from routes.ticker import router as _ticker_router
from scanner_push import broadcast as _scanner_broadcast, router as _scanner_ws_router
from news.enrich import enrich_catalyst_row
# Ticker state and helpers — live in ticker.py; imported here so existing
# code in main.py (reprice, WS stream, HOD block) can reference them unchanged.
from ticker import (
    _ticker_ws_clients,
    _find_ibkr_cache_row,
)

configure_logging()

from constants import (
    AFTERHOURS_DISCOVERY_INTERVAL_SEC,
    AFTERHOURS_FOCUS_INTERVAL_SEC,
    ALPACA_WS_BACKOFF_CAP,
    CLOSED_INTERVAL_SEC,
    DATA_FEED_DEFAULT,
    DATA_FEED_OPTIONS,
    DISCOVERY_INTERVAL_SEC,
    DISCOVERY_PROVIDER_DEFAULT,
    DISCOVERY_PROVIDER_OPTIONS,
    EXCLUDED_NAME_KEYWORDS,
    FOCUS_INTERVAL_SEC,
    GAINERS_INTERVAL_SEC,
    GAPPER_MIN_GAP_PCT,
    HISTORY_RETENTION_DAYS,
    HOD_MOMO_ALPACA_SUBSCRIBE_CHUNK,
    HOD_MOMO_FOCUS_REFRESH_SEC,
    HOD_MOMO_UNIVERSE_INTERVAL_SEC,
    HOD_MOMO_UNIVERSE_MODE,
    HOD_MOMO_UNIVERSE_MODE_BROAD,
    HOD_MOMO_UNIVERSE_MODE_FOCUS,
    IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC,
    IBKR_REPRICE_INTERVAL_SEC,
    IBKR_TABLE_REPRICE_MAX_SYMBOLS,
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
    TOP_N_DEFAULT,
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
import hod_momo_universe as _hod_uni
import hod_momo_seed as _hod_momo_seed
import afterhours_discovery as _ah_discovery
import exchanges as _exchanges
import strategy.risk as _risk
import strategy.setups_stream as _setups_stream
import strategy.executor as _executor
import journal.db as _journal_db
import l2.db as _l2_db
from market import (
    ET as _ET,
    now_et as _now_et,
    in_premarket as _in_premarket,
    in_market_hours as _in_market_hours,
    in_after_hours as _in_after_hours,
)

load_dotenv(env_file_path())

_NOVA_REV = "4"
# Alpaca helpers and provider state live in alpaca.py (importable without
# triggering a full main.py load by other modules).
from alpaca import (
    ALPACA_DATA_URL as _DATA_URL,
    _env,
    _alpaca_headers,
    _get_feed,
    _set_feed,
    _try_fallback_to_iex,
    _get_discovery_provider,
    _set_discovery_provider,
)

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

# ── Scanner helpers (stateless) — live in scanner.py, imported here so
# existing code via _main.* continues to work unchanged.
from scanner import (
    _fetch_snapshots,
    _check_news,
    _pick_prev_close,
    _is_common_stock,
    _gapper_meets_min_gap,
    _prune_gappers_below_min,
    _compute_gappers,
)

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

# Fundamentals cache lives in fundamentals.py (imported above as
# _fundamentals_cache / _fundamentals_cache_ts for hod_momo_enrichment compat).

# ── Health + mode ──────────────────────────────────────────────────────────────
_cached_health: dict = {"status": "loading", "latency_ms": 0}
_current_mode: str = "closed"   # "premarket" | "market" | "afterhours" | "closed"

# ── WebSocket streaming state ──────────────────────────────────────────────────
# The WS stream receives real-time trades and updates _gapper_cache / _gainer_cache
# in-place, decoupling price freshness from the REST scan cadence.
_ws_subscribed: set[str] = set()   # symbols the WS is currently subscribed to
_ws_needs_resub: bool = False       # scan loop sets True when symbol list changes

# ── HOD Momo universe state ────────────────────────────────────────────────────
# Symbols currently subscribed for the HOD Momo engine (union of all common-stock
# symbols that pass the master-gate prefilter above min RVOL or are already being
# watched for other scanners).  Refreshed every HOD_MOMO_UNIVERSE_INTERVAL_SEC.
_hod_momo_universe: set[str] = set()
_hod_momo_universe_ts: float = 0.0




def _run_ibkr(coro):
    """Bridge an ibkr/discovery.py coroutine into this thread; [] on any failure
    (disconnected Gateway, timeout, etc.) so callers degrade like an empty scan."""
    try:
        return _ibkr_client.run_coro(coro, timeout=IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC)
    except Exception as exc:
        logger.warning("IBKR discovery bridge failed: %s", exc)
        return []


def _enrich_ibkr_mover(entry: dict, news: dict[str, str]) -> dict:
    """Attach RVOL / news / fundamentals / exchange to an ibkr.discovery mover row.

    Mirrors what _build_mover_entry does for the Alpaca path, reading the same
    module-level caches (already populated by _ensure_avg_volume /
    _fetch_fundamentals_batch before this is called).
    """
    sym = entry["symbol"]
    avg_vol = _avg_volume_cache.get(sym)
    vol = entry["volume"]
    fund = _fundamentals_cache.get(sym, {})
    entry["rel_volume"] = round(vol / avg_vol, 2) if avg_vol and avg_vol > 0 and vol > 0 else None
    entry["has_news"] = sym in news
    entry["newest_headline_at"] = news.get(sym)
    entry["market_cap"] = fund.get("market_cap")
    entry["float"] = fund.get("float_shares")
    entry["short_interest"] = fund.get("short_interest")
    entry["short_ratio"] = fund.get("short_ratio")
    return _exchanges.attach_exchange(entry)


def _get_ibkr_detail_symbols() -> list[str]:
    """Symbols with an open ticker-detail WebSocket right now (usually 0-2)."""
    return [sym for sym, clients in _ticker_ws_clients.items() if clients]


def _table_reprice_symbols() -> list[str]:
    """Symbols for the 1Hz table snapshot — scanner rows only (fast path).

    HOD seed symbols are enriched separately; mixing them into this list made
    one reqTickersAsync span 100 names and feel 7–10s stale on Gainers/Gappers.
    """
    if _current_mode == "afterhours" and _afterhours_cache:
        rows = _afterhours_cache + _gainer_cache + _loser_cache
    elif _gainer_cache or _loser_cache:
        rows = _gainer_cache + _loser_cache
    else:
        rows = _gapper_cache
    # Preserve first-seen order (top gainers first) while deduping.
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        sym = (r.get("symbol") or "").strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
        if len(out) >= IBKR_TABLE_REPRICE_MAX_SYMBOLS:
            break
    return out


def _apply_table_quotes(quotes: dict) -> dict | None:
    """Apply async snapshot quotes onto scanner caches; return WS price_patch or None.

    Also feeds HOD Momo: with discovery=ibkr, Alpaca IEX trades are too thin to
    drive the alert engine alone — 1Hz IBKR table snapshots are the Ross shortlist
    tape substitute for HOD / surge evaluation.
    """
    global _gapper_cache, _gapper_cache_ts, _gainer_cache, _gainer_cache_ts
    global _loser_cache, _loser_cache_ts, _afterhours_cache, _afterhours_cache_ts
    gapper_in = [] if (_gainer_cache or _loser_cache) else _gapper_cache
    result = _ibkr_reprice.apply_quote_patches(gapper_in, _gainer_cache, _loser_cache, quotes)
    if result is None:
        return None
    gapper_cache, gainer_cache, loser_cache, now, rows = result
    if gapper_in and _gapper_cache:
        _gapper_cache = gapper_cache
        _gapper_cache_ts = now
    if _gainer_cache:
        _gainer_cache = gainer_cache
        _gainer_cache_ts = now
    if _loser_cache:
        _loser_cache = loser_cache
        _loser_cache_ts = now
    if _afterhours_cache and _current_mode == "afterhours":
        _afterhours_cache = _ah_discovery.reprice_afterhours_rows_ibkr(
            _afterhours_cache, quotes, _avg_volume_cache,
        )
        _afterhours_cache_ts = now
        by_sym = {r["symbol"]: r for r in rows}
        for r in _afterhours_cache:
            by_sym[r["symbol"]] = {
                "symbol": r["symbol"],
                "price": r.get("price") or r.get("current_price"),
                "change_pct": r.get("change_pct"),
                "change_abs": r.get("change_abs"),
                "volume": r.get("volume"),
                "gap_percent": r.get("gap_percent"),
            }
        rows = list(by_sym.values())

    trade_ts = time.time()
    for sym, q in quotes.items():
        price = (q or {}).get("price")
        if price is None:
            continue
        vol = (q or {}).get("volume")
        try:
            _hod_momo.on_trade_update(
                sym,
                float(price),
                trade_ts,
                volume=int(vol) if vol is not None else None,
            )
        except Exception:
            logger.exception("HOD Momo: IBKR table tick failed for %s", sym)

    return {"type": "price_patch", "ts": now, "stale": False, "rows": rows}


# ── Tradable assets ───────────────────────────────────────────────────────────

def invalidate_universe_cache() -> None:
    """Force the next _get_tradable_symbols call to re-fetch (e.g. after blocklist change)."""
    global _assets_cache_ts
    _assets_cache_ts = 0.0
    _exchanges.clear()
    _ws_mark_resub()


def _get_tradable_symbols(base_url: str, headers: dict) -> list[str]:
    """Fetch common-stock symbols for scanning, cached for one hour."""
    global _assets_cache, _assets_cache_set, _assets_cache_ts
    now = time.monotonic()
    if _assets_cache and (now - _assets_cache_ts) < _ASSETS_CACHE_TTL:
        return _assets_cache
    try:
        all_assets: list[dict] = []
        for exchange in SCAN_EXCHANGES:
            resp = requests.get(
                f"{_DATA_URL}/v2/assets",
                headers=headers,
                params={"status": "active", "asset_class": "us_equity", "exchange": exchange},
                timeout=20,
            )
            if resp.status_code == 200:
                all_assets.extend(resp.json())
        if not all_assets:
            return _assets_cache
        kept = [a for a in all_assets if _is_common_stock(a)]
        symbols = [a["symbol"] for a in kept]
        _exchanges.update_from_assets(kept)
        _assets_cache = symbols
        _assets_cache_set = set(symbols)
        _assets_cache_ts = now
        return _assets_cache
    except Exception:
        logger.warning("_get_tradable_symbols failed — returning stale cache", exc_info=True)
        return _assets_cache


def _ensure_avg_volume(symbols: list[str], headers: dict) -> None:
    """Lazily populate _avg_volume_cache for any symbols not yet cached today."""
    global _avg_volume_cache, _avg_volume_date
    from scanner import fetch_avg_volume_batch
    today = date.today().isoformat()
    if _avg_volume_date != today:
        _avg_volume_cache = {}
        _avg_volume_date = today
    fetch_avg_volume_batch(symbols, headers, _avg_volume_cache)


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
        _exchanges.attach_exchange(g)
    return gappers


# ── WebSocket helpers ─────────────────────────────────────────────────────────

def _ws_mark_resub() -> None:
    """Signal the WebSocket loop to sync subscriptions on next iteration."""
    global _ws_needs_resub
    _ws_needs_resub = True


def _refresh_hod_momo_universe() -> None:
    """Rebuild the HOD Momo trade-watch set and nudge Alpaca WS to resubscribe.

    Default ``focus`` mode (Ross-style): Top Gainer/Gapper/Loser/AH shortlist +
    open ticker-detail symbols. Free Alpaca IEX cannot stream ~6k symbols —
    that path produced ``total_trades_seen=0`` and an empty HOD tab.

    ``broad`` mode keeps the legacy full common-stock asset list (SIP only).
    """
    global _hod_momo_universe, _hod_momo_universe_ts
    now = time.monotonic()
    mode = (HOD_MOMO_UNIVERSE_MODE or HOD_MOMO_UNIVERSE_MODE_FOCUS).strip().lower()
    interval = (
        HOD_MOMO_FOCUS_REFRESH_SEC
        if mode == HOD_MOMO_UNIVERSE_MODE_FOCUS
        else HOD_MOMO_UNIVERSE_INTERVAL_SEC
    )
    if _hod_momo_universe and (now - _hod_momo_universe_ts) < interval:
        return

    if mode == HOD_MOMO_UNIVERSE_MODE_BROAD:
        base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
        headers = _alpaca_headers()
        if not headers:
            return
        try:
            symbols = set(_get_tradable_symbols(base_url, headers))
        except Exception as exc:
            logger.warning("HOD Momo broad universe refresh failed: %s", exc)
            return
    else:
        detail = [sym for sym, clients in _ticker_ws_clients.items() if clients]
        symbols = _hod_uni.build_focus_universe(
            gapper_rows=_gapper_cache,
            gainer_rows=_gainer_cache,
            loser_rows=_loser_cache,
            afterhours_rows=_afterhours_cache,
            detail_symbols=detail,
            is_blocked=_hod_momo.is_blocked,
        )

    changed = symbols != _hod_momo_universe
    _hod_momo_universe = symbols
    _hod_momo_universe_ts = now
    if changed:
        _ws_mark_resub()
        logger.info(
            "HOD Momo: universe refreshed mode=%s — %d symbols subscribed",
            mode,
            len(_hod_momo_universe),
        )


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

    # Alpaca's WS trade stream only overlays live price onto Alpaca-sourced cache
    # rows. IBKR-provider rows carry change_pct/change_abs computed from IBKR's own
    # snapshot basis; letting a separate feed's ticks overwrite just the price field
    # would desync those from prev_close without a matching recompute basis. IBKR
    # rows instead refresh on the normal scan cadence (see ibkr/discovery.py).
    if _get_discovery_provider() == "ibkr":
        return None

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
    prev_close: float | None = None,
) -> None:
    """Push a lightweight trade update to all ticker detail WS clients watching this symbol."""
    clients = _ticker_ws_clients.get(sym)
    if not clients:
        return
    payload_obj: dict = {
        "type": "trade_update",
        "symbol": sym,
        "price": price,
        "size": size,
        "timestamp": timestamp,
        "volume": volume,
    }
    if prev_close is not None:
        payload_obj["prev_close"] = prev_close
    payload = json.dumps(payload_obj)
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
    """Full universe scan: filter gappers, enrich.

    Provider-switchable: Alpaca (default, free IEX universe snapshot) or IBKR
    (live market scanner, see ibkr/discovery.py). News + fundamentals + RVOL
    enrichment is identical either way — only the raw symbol/price source differs.
    """
    global _gapper_cache, _gapper_cache_ts, _last_discovery_ts
    headers = _alpaca_headers()  # still used for avg-volume / news even on IBKR provider
    provider = _get_discovery_provider()

    if provider == "ibkr":
        gappers = _run_ibkr(_ibkr_discovery.get_gappers())
        if not headers:
            return
    else:
        base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
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
    if _get_discovery_provider() == "ibkr":
        # IBKR-sourced rows are repriced by the fast _reprice_ibkr_caches tick
        # in _scan_loop's sleep, not this Alpaca-only reconcile.
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
    """After-hours movers: IBKR top % gainers when discovery=ibkr, else Alpaca.

    Warrior AH HOD watches live % gainers after the close. The Alpaca IEX
    full-universe AH scan often returns 0–2 rows and starves HOD of ATHE/TRT/XCUR.

    When discovery=ibkr, never silently fall back to Alpaca (single-feed rule).
    Prefer the already-fetched ``_gainer_cache`` so we do not race IBKR connect
    with a second empty ``get_gainers`` call at startup.
    """
    global _afterhours_cache, _afterhours_cache_ts, _last_afterhours_discovery_ts
    global _hod_momo_universe_ts
    headers = _alpaca_headers()

    if _get_discovery_provider() == "ibkr":
        raw = list(_gainer_cache) if _gainer_cache else []
        if not raw:
            raw = _run_ibkr(_ibkr_discovery.get_gainers()) or []
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
            _ensure_avg_volume(syms, headers)
            news = _check_news(syms, headers)
            _fetch_fundamentals_batch(syms)
        for r in rows:
            sym = r["symbol"]
            vol = int(r.get("volume") or 0)
            avg = _avg_volume_cache.get(sym)
            fund = _fundamentals_cache.get(sym, {})
            paced = _pace_rvol(vol, avg) if avg and vol else None
            raw_rvol = round(vol / avg, 2) if avg and avg > 0 and vol > 0 else None
            # Prefer RVOL already computed on the gainer row when present.
            gainer_rvol = None
            for g in _gainer_cache:
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
        _afterhours_cache = rows
        _afterhours_cache_ts = time.time()
        _last_afterhours_discovery_ts = time.monotonic()
        _ws_mark_resub()
        save_afterhours_snapshot(_afterhours_cache, _afterhours_cache_ts)
        for r in rows:
            sym = r["symbol"]
            avg = _avg_volume_cache.get(sym)
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
        _hod_momo_universe_ts = 0.0
        _refresh_hod_momo_universe()
        logger.info("AH discovery (IBKR): %d movers", len(rows))
        return

    base_url = _env("APCA_API_BASE_URL", "https://api.alpaca.markets") or "https://api.alpaca.markets"
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
    """Re-price current after-hours candidates (IBKR snapshots when discovery=ibkr)."""
    global _afterhours_cache, _afterhours_cache_ts
    if not _afterhours_cache:
        _run_afterhours_discovery_scan()
        return

    if _get_discovery_provider() == "ibkr":
        symbols = [r["symbol"] for r in _afterhours_cache]
        quotes = _run_ibkr(_ibkr_discovery.snapshot_quotes(symbols)) or {}
        _afterhours_cache = _ah_discovery.reprice_afterhours_rows_ibkr(
            _afterhours_cache, quotes, _avg_volume_cache,
        )
        _afterhours_cache_ts = time.time()
        save_afterhours_snapshot(_afterhours_cache, _afterhours_cache_ts)
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
    entry = {
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
    return _exchanges.attach_exchange(entry)


def _run_gainers_update_ibkr(headers: dict) -> tuple[list[dict], list[dict]] | None:
    """IBKR-provider path: live market scanner instead of Alpaca's movers endpoint."""
    gainers_rows = _run_ibkr(_ibkr_discovery.get_gainers())
    losers_rows = _run_ibkr(_ibkr_discovery.get_losers())
    if not gainers_rows and not losers_rows:
        return None

    all_symbols = list({r["symbol"] for r in gainers_rows + losers_rows})
    _ensure_avg_volume(all_symbols, headers)
    news = _check_news(all_symbols, headers)
    _fetch_fundamentals_batch(all_symbols)

    gainers = [_enrich_ibkr_mover(r, news) for r in gainers_rows]
    losers = [_enrich_ibkr_mover(r, news) for r in losers_rows]
    return gainers, losers


def _run_gainers_update() -> None:
    """Fetch top gainers and losers, enrich with snapshots + RVOL + news.

    Provider-switchable: Alpaca Screener Movers API (default) or IBKR market
    scanner (see ibkr/discovery.py). News/fundamentals stay on Alpaca/yfinance
    either way — headers must still be present for those.
    """
    global _gainer_cache, _gainer_cache_ts, _loser_cache, _loser_cache_ts
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
                logger.warning("Alpaca movers API returned %s", resp.status_code)
                return
            movers_json = resp.json()
            gainers_raw = movers_json.get("gainers", [])
            losers_raw = movers_json.get("losers", [])
        except Exception:
            logger.warning("_run_gainers_update: Alpaca movers API error", exc_info=True)
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
                            for chunk in _hod_uni.chunk_symbols(
                                to_add, HOD_MOMO_ALPACA_SUBSCRIBE_CHUNK
                            ):
                                await ws.send(json.dumps({"action": "subscribe", "trades": chunk}))
                        if to_remove:
                            for chunk in _hod_uni.chunk_symbols(
                                to_remove, HOD_MOMO_ALPACA_SUBSCRIBE_CHUNK
                            ):
                                await ws.send(json.dumps({"action": "unsubscribe", "trades": chunk}))
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
                                # Same reasoning as _handle_trade's IBKR guard: don't let
                                # Alpaca ticks update a ticker-detail panel whose prev_close
                                # basis came from IBKR (see PROBLEM_LOG 2026-07-13). The
                                # IBKR-native reprice tick (_reprice_ibkr_caches) covers it.
                                if (
                                    sym and sym in _ticker_ws_clients and _ticker_ws_clients[sym]
                                    and _get_discovery_provider() != "ibkr"
                                ):
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
            source = article.get("source", "")
            for sym in article.get("symbols", []):
                if sym not in symbol_to_article or created_at > symbol_to_article[sym]["created_at"]:
                    symbol_to_article[sym] = {
                        "created_at": created_at,
                        "headline": headline,
                        "url": url,
                        "source": source,
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

        use_ibkr = _get_discovery_provider() == "ibkr"
        catalysts: list[dict] = []

        if use_ibkr:
            # When discovery=ibkr, pull prices exclusively from IBKR scanner caches.
            # Alpaca snapshot prices here would disagree with every other IBKR surface.
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
        # Attach explicit news-impact verdicts (rules-first; see news/impact.py).
        catalysts = [enrich_catalyst_row(c) for c in catalysts]
        print(f"[catalyst] scan complete — {len(catalysts)} catalysts", flush=True)
        _news_catalyst_cache = catalysts
        _news_catalyst_cache_ts = time.time()
        _last_catalyst_scan_ts = time.monotonic()

    except Exception:
        logger.exception("[catalyst] news catalyst scan failed")


# ── Background scan loop ──────────────────────────────────────────────────────

async def _sleep_with_ibkr_reprice(loop: asyncio.AbstractEventLoop, total_seconds: float) -> None:
    """Sleep until the next full scan tick.

    Table price freshness is owned by ``table_reprice_loop`` (1Hz snapshots),
    not by mid-sleep reprice here — nesting reprice inside the scan loop was
    what froze "updated Xs ago" for 10–12+ seconds during a movers scan.
    """
    await asyncio.sleep(total_seconds)


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
                await _sleep_with_ibkr_reprice(loop, _FOCUS_INTERVAL)
            elif _in_market_hours():
                _current_mode = "market"
                await loop.run_in_executor(None, _run_gainers_update)
                if catalyst_due:
                    await loop.run_in_executor(None, _run_news_catalyst_scan)
                await _sleep_with_ibkr_reprice(loop, _GAINERS_INTERVAL)
            elif _in_after_hours():
                _current_mode = "afterhours"
                # Warrior keeps Top Gainers live after the close; HOD watches those names.
                await loop.run_in_executor(None, _run_gainers_update)
                # With IBKR, reshape AH from the gainers we just fetched every cycle
                # (avoids startup race + stale 2-row Alpaca snapshot).
                if _get_discovery_provider() == "ibkr" and _gainer_cache:
                    await loop.run_in_executor(None, _run_afterhours_discovery_scan)
                elif not _afterhours_cache or (mono - _last_afterhours_discovery_ts) > _AH_DISCOVERY_INTERVAL:
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
            logger.exception("Scan loop iteration failed — retrying in 30s")
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
    hod_seed_task = asyncio.create_task(
        _hod_momo_seed.seed_refresh_loop(_get_discovery_provider)
    )
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
    # Independent fast timer for the ticker-detail panel — decoupled from
    # _scan_loop so a slow full IBKR discovery/movers scan can never delay it
    # (see PROBLEM_LOG 2026-07-14, "Detail panel updates every ~30s instead
    # of every tick").
    # IBKR client — best-effort, never blocks the Alpaca scan loop
    await _ibkr_client.startup()
    _ibkr_ticks.configure(_broadcast_trade_update, _find_ibkr_cache_row)
    detail_reprice_task = asyncio.create_task(_ibkr_reprice.detail_reprice_loop(
        _get_ibkr_detail_symbols, _run_ibkr, _broadcast_trade_update, _find_ibkr_cache_row,
    ))
    table_reprice_task = asyncio.create_task(_ibkr_reprice.table_reprice_loop(
        _get_discovery_provider, _table_reprice_symbols, _apply_table_quotes, _scanner_broadcast,
    ))
    yield
    try:
        _hod_momo.flush_pending_alert_save()
    except Exception:
        logger.exception("HOD Momo: final alert flush failed")
    detail_reprice_task.cancel()
    table_reprice_task.cancel()
    scan_task.cancel()
    ws_task.cancel()
    hod_flush_task.cancel()
    hod_reset_task.cancel()
    hod_enrich_task.cancel()
    hod_fund_task.cancel()
    hod_seed_task.cancel()
    setups_scan_task.cancel()
    risk_reset_task.cancel()
    executor_fill_task.cancel()
    l2_flush_task.cancel()
    l2_retention_task.cancel()
    for t in (
        detail_reprice_task, table_reprice_task, scan_task, ws_task,
        hod_flush_task, hod_reset_task, hod_enrich_task, hod_fund_task, hod_seed_task,
    ):
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
app.include_router(_scanner_ws_router)
app.include_router(_strategy_router)
app.include_router(_journal_router)
app.include_router(_executor_router)
app.include_router(_l2_router)
app.include_router(_news_router)
app.include_router(_ticker_router)

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
    discovery_provider: str = DISCOVERY_PROVIDER_DEFAULT


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
        "discovery_provider": _get_discovery_provider(),
        "discovery_provider_options": list(DISCOVERY_PROVIDER_OPTIONS),
        "ibkr_connected": _ibkr_client.is_connected(),
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
    set_key(env_path, "NOVA_DISCOVERY_PROVIDER", config.discovery_provider)
    load_dotenv(env_path, override=True)
    _set_feed(config.data_feed)
    _set_discovery_provider(config.discovery_provider)
    _assets_cache_ts = 0.0
    _assets_cache_set = set()
    _exchanges.clear()
    _last_discovery_ts = 0.0
    _ws_mark_resub()  # WS stream URL changes with feed
    return {
        "status": "success",
        "data_feed": _get_feed(),
        "discovery_provider": _get_discovery_provider(),
    }


@app.get("/api/mode")
def get_mode():
    return {
        "mode": _current_mode,
        "health": _cached_health,
        "last_gapper_scan": _gapper_cache_ts,
        "last_gainer_scan": _gainer_cache_ts,
    }


def _strip_blocked(rows: list[dict]) -> list[dict]:
    """Remove blocklisted symbols and ensure each row has listing ``exchange``."""
    out = [r for r in rows if not _hod_momo.is_blocked(r.get("symbol", ""))]
    return _exchanges.attach_exchanges(out)


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
    out = _hod_momo.get_debug_counters()
    out["watch_universe_size"] = len(_hod_momo_universe)
    out["watch_universe_mode"] = (
        (HOD_MOMO_UNIVERSE_MODE or HOD_MOMO_UNIVERSE_MODE_FOCUS).strip().lower()
    )
    out["watch_seed_size"] = len(_hod_uni.get_seed_symbols())
    return out


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
        # Send newest slice only — full day stays on disk / REST (avoids UI freeze).
        initial = json.dumps(_hod_momo.get_ws_initial_payload())
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

