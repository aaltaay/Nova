from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from dotenv import load_dotenv
import requests
from datetime import datetime, date
import math
import time
import asyncio

logger = logging.getLogger(__name__)

# ── Console + persistent rotating log file ────────────────────────────────────
from paths import env_file_path
from logging_setup import configure_logging
from ibkr import client as _ibkr_client
from ibkr import reprice as _ibkr_reprice
from ibkr import ticks as _ibkr_ticks
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
# Ticker state — live in ticker.py; imported here for IBKR reprice / HOD universe.
from ticker import (
    _ticker_ws_clients,
    _find_ibkr_cache_row,
)

configure_logging()

from constants import (
    AFTERHOURS_DISCOVERY_INTERVAL_SEC,
    AFTERHOURS_FOCUS_INTERVAL_SEC,
    CLOSED_INTERVAL_SEC,
    DISCOVERY_INTERVAL_SEC,
    FOCUS_INTERVAL_SEC,
    GAINERS_INTERVAL_SEC,
    GAPPER_MIN_GAP_PCT,
    HISTORY_RETENTION_DAYS,
    HOD_MOMO_FOCUS_REFRESH_SEC,
    HOD_MOMO_UNIVERSE_INTERVAL_SEC,
    HOD_MOMO_UNIVERSE_MODE,
    HOD_MOMO_UNIVERSE_MODE_BROAD,
    HOD_MOMO_UNIVERSE_MODE_FOCUS,
    IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC,
    IBKR_TABLE_REPRICE_MAX_SYMBOLS,
    NEWS_CATALYST_INTERVAL_SEC,
    SCAN_CAP_DEFAULT,
    SCAN_EXCHANGES,
    SCAN_REQUIRE_TRADABLE,
    TOP_N_DEFAULT,
)
import hod_momo_enrichment as _hod_momo_enrichment
from cache import (
    _migrate_legacy_files,
    cleanup_old_snapshots,
    load_afterhours_snapshot,
    load_gapper_snapshot,
    load_movers_snapshot,
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

load_dotenv(env_file_path())

_NOVA_REV = "4"
# Alpaca helpers — re-exported so callers via ``_main.*`` keep working.
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


# ── WebSocket streaming (state + stream loop live in websocket.py) ────────────
from websocket import (
    mark_resub as _ws_mark_resub,
    stream_loop as _ws_stream_loop,
    broadcast_trade_update as _broadcast_trade_update,
)

# ── Scan runners + orchestration (live in scan_runners.py / scan_loop.py) ─────
from scan_runners import (
    run_discovery_scan as _run_discovery_scan,
    run_focus_scan as _run_focus_scan,
    run_afterhours_discovery_scan as _run_afterhours_discovery_scan,
    run_afterhours_focus_scan as _run_afterhours_focus_scan,
    run_gainers_update as _run_gainers_update,
)
from scan_loop import (
    run_news_catalyst_scan as _run_news_catalyst_scan,
    scan_loop as _scan_loop,
)


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


def reset_scan_caches() -> None:
    """Invalidate all scanner caches — called by routes/health.py update_config."""
    global _assets_cache_ts, _assets_cache_set, _last_discovery_ts
    _assets_cache_ts = 0.0
    _assets_cache_set = set()
    _last_discovery_ts = 0.0


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


# ── HOD Momo universe refresh ────────────────────────────────────────────────

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

from routes.health import router as _health_router
from routes.scan import router as _scan_router
from routes.hod_momo import router as _hod_momo_router, ws_router as _hod_momo_ws_router

app.include_router(_health_router)
app.include_router(_scan_router)
app.include_router(_hod_momo_router)
app.include_router(_hod_momo_ws_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

