"""
Nova API entry point — app factory, scanner cache state, and re-exports.

Business logic lives in purpose-built modules (see backend-modularity rule).
This file owns mutable scanner caches (so attribute rebinding is visible to all
callers) and wires FastAPI routers + lifespan.
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI

from paths import env_file_path
from logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

load_dotenv(env_file_path())

from constants import (
    AFTERHOURS_DISCOVERY_INTERVAL_SEC,
    AFTERHOURS_FOCUS_INTERVAL_SEC,
    CLOSED_INTERVAL_SEC,
    DISCOVERY_INTERVAL_SEC,
    FOCUS_INTERVAL_SEC,
    GAINERS_INTERVAL_SEC,
    GAPPER_MIN_GAP_PCT,
    NEWS_CATALYST_INTERVAL_SEC,
    SCAN_CAP_DEFAULT,
    SCAN_REQUIRE_TRADABLE,
    TOP_N_DEFAULT,
)

# ── Alpaca helpers (re-exported for callers via ``_main.*``) ──────────────────
from alpaca import (  # noqa: E402
    ALPACA_DATA_URL as _DATA_URL,
    _env,
    _alpaca_headers,
    _get_feed,
    _set_feed,
    _try_fallback_to_iex,
    _get_discovery_provider,
    _set_discovery_provider,
)

# ── Scanner helpers (re-exported for ``_main.*`` / hod_momo_enrichment) ───────
from scanner import (  # noqa: E402
    _fetch_snapshots,
    _check_news,
    _pick_prev_close,
    _is_common_stock,
    _gapper_meets_min_gap,
    _prune_gappers_below_min,
    _compute_gappers,
)

# ── Fundamentals caches (compat re-exports) ───────────────────────────────────
from fundamentals import (  # noqa: E402
    _fundamentals_cache,
    _fundamentals_cache_ts,
    fetch_fundamentals as _fetch_fundamentals,
    fetch_fundamentals_batch as _fetch_fundamentals_batch,
)

# ── Extracted domain modules (re-export under legacy ``_`` names) ─────────────
from websocket import (  # noqa: E402
    mark_resub as _ws_mark_resub,
    stream_loop as _ws_stream_loop,
    broadcast_trade_update as _broadcast_trade_update,
)
from scan_runners import (  # noqa: E402
    run_discovery_scan as _run_discovery_scan,
    run_focus_scan as _run_focus_scan,
    run_afterhours_discovery_scan as _run_afterhours_discovery_scan,
    run_afterhours_focus_scan as _run_afterhours_focus_scan,
    run_gainers_update as _run_gainers_update,
)
from scan_loop import (  # noqa: E402
    run_news_catalyst_scan as _run_news_catalyst_scan,
    scan_loop as _scan_loop,
)
from ibkr_bridge import (  # noqa: E402
    run_ibkr as _run_ibkr,
    enrich_ibkr_mover as _enrich_ibkr_mover,
    get_ibkr_detail_symbols as _get_ibkr_detail_symbols,
    table_reprice_symbols as _table_reprice_symbols,
    apply_table_quotes as _apply_table_quotes,
)
from universe import (  # noqa: E402
    invalidate_universe_cache,
    reset_scan_caches,
    get_tradable_symbols as _get_tradable_symbols,
    ensure_avg_volume as _ensure_avg_volume,
    enrich_gappers as _enrich_gappers,
    refresh_hod_momo_universe as _refresh_hod_momo_universe,
    get_hod_momo_universe,
)
from health_status import (  # noqa: E402
    set_health_broker_keys_missing as _set_health_broker_keys_missing,
    ping_health as _ping_health,
)
from app_lifespan import configure_cors, lifespan  # noqa: E402

# ── Tunables (env overrides; defaults from constants.py) ──────────────────────
_NOVA_REV = "4"
_DISCOVERY_INTERVAL = DISCOVERY_INTERVAL_SEC
_FOCUS_INTERVAL = FOCUS_INTERVAL_SEC
_GAINERS_INTERVAL = GAINERS_INTERVAL_SEC
_CLOSED_INTERVAL = CLOSED_INTERVAL_SEC
_AH_DISCOVERY_INTERVAL = AFTERHOURS_DISCOVERY_INTERVAL_SEC
_AH_FOCUS_INTERVAL = AFTERHOURS_FOCUS_INTERVAL_SEC
_SCAN_CAP = int(os.environ.get("ALPACA_SCAN_SYMBOL_CAP", str(SCAN_CAP_DEFAULT)))
_MIN_GAP_PCT = float(
    os.environ.get("NOVA_MIN_GAP_PCT", os.environ.get("BLAST_MIN_GAP_PCT", str(GAPPER_MIN_GAP_PCT)))
)
_TOP_N = int(os.environ.get("NOVA_TOP_N", os.environ.get("BLAST_TOP_N", str(TOP_N_DEFAULT))))
_raw_scan_tradable = os.environ.get("NOVA_SCAN_REQUIRE_TRADABLE") or os.environ.get(
    "BLAST_SCAN_REQUIRE_TRADABLE"
)
if _raw_scan_tradable is None or not str(_raw_scan_tradable).strip():
    _SCAN_REQUIRE_TRADABLE = SCAN_REQUIRE_TRADABLE
else:
    _SCAN_REQUIRE_TRADABLE = str(_raw_scan_tradable).strip().lower() in ("1", "true", "yes", "on")
_NEWS_CATALYST_INTERVAL = NEWS_CATALYST_INTERVAL_SEC

# ── Scanner caches (owned here — attribute rebinding must be visible globally) ─
_assets_cache: list[str] = []
_assets_cache_set: set[str] = set()
_assets_cache_ts: float = 0.0
_ASSETS_CACHE_TTL = 3600.0

_gapper_cache: list[dict] = []
_gapper_cache_ts: float = 0.0
_last_discovery_ts: float = 0.0

_afterhours_cache: list[dict] = []
_afterhours_cache_ts: float = 0.0
_last_afterhours_discovery_ts: float = 0.0

_gainer_cache: list[dict] = []
_gainer_cache_ts: float = 0.0

_loser_cache: list[dict] = []
_loser_cache_ts: float = 0.0

_news_catalyst_cache: list[dict] = []
_news_catalyst_cache_ts: float = 0.0
_last_catalyst_scan_ts: float = 0.0

_avg_volume_cache: dict[str, float] = {}
_avg_volume_date: str = ""

_cached_health: dict = {"status": "loading", "latency_ms": 0}
_current_mode: str = "closed"

_hod_momo_universe: set[str] = set()
_hod_momo_universe_ts: float = 0.0

# ── App factory ───────────────────────────────────────────────────────────────
from routes.trading import router as _trading_router, ws_router as _trading_ws_router  # noqa: E402
from routes.strategy import router as _strategy_router  # noqa: E402
from routes.journal import router as _journal_router  # noqa: E402
from routes.executor import router as _executor_router  # noqa: E402
from routes.l2 import router as _l2_router  # noqa: E402
from routes.news import router as _news_router  # noqa: E402
from routes.ticker import router as _ticker_router  # noqa: E402
from scanner_push import router as _scanner_ws_router  # noqa: E402
from routes.health import router as _health_router  # noqa: E402
from routes.scan import router as _scan_router  # noqa: E402
from routes.hod_momo import router as _hod_momo_router, ws_router as _hod_momo_ws_router  # noqa: E402
from routes.client_errors import router as _client_errors_router  # noqa: E402

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
app.include_router(_health_router)
app.include_router(_scan_router)
app.include_router(_hod_momo_router)
app.include_router(_hod_momo_ws_router)
app.include_router(_client_errors_router)

configure_cors(app)
