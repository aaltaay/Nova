"""
Authoritative policy and thresholds for Nova.
Define scan cadence, filters, and tier rules here; import from this module in
`main.py` and elsewhere instead of scattering magic numbers.
"""
import re

# ── Market cap tiers (USD) ────────────────────────────────────────────────
SMALL_CAP_MIN = 300_000_000  # $300 M
SMALL_CAP_MAX = 2_000_000_000  # $2 B
MID_CAP_MIN = 2_000_000_000  # $2 B
MID_CAP_MAX = 10_000_000_000  # $10 B
LARGE_CAP_MIN = 10_000_000_000  # $10 B

# ── News flame thresholds (hours) ─────────────────────────────────────────
NEWS_FLAME_HOT_HOURS = 2   # red badge    (0 –  2 h)
NEWS_FLAME_WARM_HOURS = 12   # orange badge (2 – 12 h)
NEWS_FLAME_MAX_HOURS = 24   # yellow badge (12 – 24 h); hide above this

# ── Relative volume ────────────────────────────────────────────────────────
REL_VOLUME_HIGH = 2         # highlight threshold
RVOL_LOOKBACK_DAYS = 30     # trading days of history used to compute avg daily volume

# ── Client error telemetry (browser → API) ─────────────────────────────────
CLIENT_ERRORS_ENABLED = True
CLIENT_ERRORS_MAX_BODY_BYTES = 16_384
CLIENT_ERRORS_MAX_MESSAGE_CHARS = 2_000

# ── CORS ─────────────────────────────────────────────────────────────────────
# Local-dev default: Vite origins only (SEC-003). Override for deploys with
# NOVA_CORS_ALLOWED_ORIGINS (comma-separated exact origins, e.g.
# "https://nova.up.railway.app,https://nova.vercel.app").
CORS_ALLOWED_ORIGINS_DEFAULT = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# ── Minimum price filter ─────────────────────────────────────────────────────
# exclude any stock priced below $0.50 (applies to gappers and gainers)
SCANNER_MIN_PRICE = 0.50

# ── Gapper filter ───────────────────────────────────────────────────────────
# Gap is (last price − previous close) / previous close, expressed as % for this threshold.
GAPPER_MIN_GAP_PCT = 10.0   # exclude symbols below this gap %

# ── Scanner universe ─────────────────────────────────────────────────────────
# Exchanges scanned for pre-market gappers. Alpaca's /v2/assets accepts one
# exchange per call, so this list drives three parallel API calls.
# Excluded intentionally: ARCA/NYSEARCA (ETF-only venues), BATS (ETF listings), OTC.
SCAN_EXCHANGES = ("NYSE", "NASDAQ", "AMEX")

# When True, only include Alpaca assets with `tradable: true`. Some active listings are
# marked `tradable: false` (e.g. overnight halt / restriction) and are otherwise dropped
# from the scan universe. Override with env `NOVA_SCAN_REQUIRE_TRADABLE` (false | true).
SCAN_REQUIRE_TRADABLE = False

# Words found in Alpaca asset names that identify non-common-stock securities.
# Used exclusively inside _is_common_stock() in main.py — nowhere else.
EXCLUDED_NAME_KEYWORDS = (
    "ETF", "Fund", "Trust", "Index",  # passive vehicles
    "Warrant", "Rights",              # derivative securities
)

# Regex matching non-standard security symbols within primary exchanges:
# warrants (/W, /WS), units (/U), rights (/R), preferred shares (/P*, .P*),
# exchange-prefixed foreign tickers (TSX:DOO), and known Alpaca test symbols.
SYMBOL_EXCLUDE_RE = re.compile(r"[./:]|^ZVZZT$|^NTEST", re.IGNORECASE)

# ── US equity session clock (America/New_York) ──────────────────────────────
# Single source of truth for premarket / RTH / after-hours boundaries.
# Used by backend/market.py (scan mode) and mirrored in frontend
# constantGroups/market_ui.ts for chart session highlighting.
# Bounds are [start, end) in local ET minutes-from-midnight.
SESSION_PREMARKET_START_MIN_ET = 4 * 60          # 04:00
SESSION_RTH_OPEN_MIN_ET = 9 * 60 + 30            # 09:30
SESSION_RTH_CLOSE_MIN_ET = 16 * 60               # 16:00
SESSION_AFTERHOURS_END_MIN_ET = 20 * 60          # 20:00
# Volume-day for pace RVOL: premarket open → RTH close (not after-hours).
SESSION_VOLUME_DAY_END_MIN_ET = SESSION_RTH_CLOSE_MIN_ET

# ── Scanner sizing ──────────────────────────────────────────────────────────
NOVA_API_REV = "4"
# SCAN_CAP_DEFAULT is retained as an emergency env-var override only.
# Normal operation uses exchange-based filtering (SCAN_EXCHANGES) instead.
SCAN_CAP_DEFAULT = 800   # legacy; overridden by ALPACA_SCAN_SYMBOL_CAP env var if set
TOP_N_DEFAULT = 50       # max gappers returned / cap on movers API batching
SNAPSHOT_WORKERS = 10    # parallel threads for batch snapshot fetching
# Dedicated pool for scan_loop IBKR/Alpaca work, kept separate from asyncio's
# default ThreadPoolExecutor as a clean ownership boundary. NOTE: /api/health
# is async (Starlette/AnyIO's own worker pool), so it never actually shared
# this pool — see PROBLEM_LOG 2026-07-23 correction re-diagnosing API_WEDGED.
SCAN_EXECUTOR_WORKERS = 2
ASSETS_CACHE_TTL_SEC = 3600.0
# Event-loop lag sampler cadence (backend/loop_lag.py) — how often the
# background task measures actual vs expected wakeup time for /api/health.
LOOP_LAG_SAMPLE_INTERVAL_SEC = 2.0

# ── Scan intervals (seconds) ────────────────────────────────────────────────
# Real-time prices still come from the WebSocket; these control REST discovery cadence.
DISCOVERY_INTERVAL_SEC = 120.0   # full universe scan (pre-market)
FOCUS_INTERVAL_SEC = 30.0    # reconcile current gapper list
GAINERS_INTERVAL_SEC = 20.0    # market-hours screener refresh
CLOSED_INTERVAL_SEC = 60.0    # closed-hours background refresh
NEWS_CATALYST_INTERVAL_SEC = 60.0    # news-first catalyst scan interval
# full universe scan (after-hours, same cadence as pre-market)
AFTERHOURS_DISCOVERY_INTERVAL_SEC = 120.0
AFTERHOURS_FOCUS_INTERVAL_SEC = 30.0   # reconcile current after-hours list

# ── News catalyst scanner ────────────────────────────────────────────────────
NEWS_CATALYST_LOOKBACK_HOURS = 2      # how far back to scan for news articles
# max articles per news API call (Alpaca hard cap)
NEWS_CATALYST_ARTICLE_LIMIT = 50

# ── Historical snapshot retention ───────────────────────────────────────────
HISTORY_RETENTION_DAYS = 30   # delete dated cache files older than this many days

# ── Alpaca WebSocket stream ──────────────────────────────────────────────────
# Max retry backoff in seconds. 15 s keeps reconnect attempts frequent enough
# to recover quickly when Alpaca frees a stale connection slot (typically 30–60 s).
ALPACA_WS_BACKOFF_CAP = 60.0
# When discovery=ibkr, stream_loop idles instead of opening Alpaca's WS (one-slot limit).
ALPACA_WS_IDLE_POLL_SEC = 15.0

# ── Data feed ─────────────────────────────────────────────────────────────────
# "iex" is the free-tier Alpaca feed; "sip" requires a paid data subscription.
# Override at runtime via env var ALPACA_DATA_FEED or through the UI Settings panel.
DATA_FEED_DEFAULT = "iex"
DATA_FEED_OPTIONS = ("iex", "sip")

# ── Ticker detail caches ──────────────────────────────────────────────────────
# Fundamentals (yfinance/Yahoo) are slow; cache aggressively.
FUNDAMENTALS_CACHE_TTL = 900.0      # 15 minutes
# Hard timeout for a single yfinance .info call; prevents Yahoo stalls from blocking Phase 2.
# On timeout, stale cached data (if any) is returned; otherwise an empty dict is used.
YFINANCE_TIMEOUT_S = 5.0
# Cap symbols per /api/earnings-today request (scanner party badges).
EARNINGS_TODAY_MAX_SYMBOLS = 25
# Asset metadata (name, exchange, tradability) rarely changes intraday.
TICKER_ASSET_CACHE_TTL = 900.0      # 15 minutes (extended from 5 min — static intraday)
# Snapshot (price, quote, bars) is live data; only cache briefly to de-dup rapid clicks.
TICKER_SNAPSHOT_CACHE_TTL = 10.0    # 10 seconds
# Short-lived cache for the full Phase 2 payload (news + fundamentals + avg_vol).
# Serves repeat clicks and rapid tab-switching without re-fetching from external APIs.
TICKER_SLOW_CACHE_TTL = 90.0        # 90 seconds
# Short timeouts for ticker asset/news HTTP (IBKR snapshot dominates wall time).
TICKER_HTTP_TIMEOUT_SEC = 4.0
# Cache-only avg volume on ticker path — do not block REST on Alpaca bars.
TICKER_AVG_VOLUME_CACHE_ONLY = True
# Single-symbol IBKR snapshot budget (table discovery keeps the longer 15s/25s).
TICKER_IBKR_SNAPSHOT_TIMEOUT_SEC = 4.0
TICKER_IBKR_BRIDGE_TIMEOUT_SEC = 6.0


# ── Ticker chart (Alpaca bars) ────────────────────────────────────────────────
# Valid Alpaca timeframe strings accepted by GET /v2/stocks/{symbol}/bars.
CHART_TIMEFRAMES: tuple[str, ...] = (
    "1Min", "5Min", "15Min", "30Min", "1Hour", "4Hour", "1Day", "1Week", "1Month",
)
CHART_DEFAULT_TIMEFRAME = "1Min"

# How many calendar days to look back when no explicit `start` is passed.
# SIP bars include extended hours (pre-market + after-hours), so actual bar
# counts per day are higher than regular-session-only estimates.
CHART_LOOKBACK_DAYS: dict[str, int] = {
    "1Min":  5,
    "5Min":  10,
    "15Min": 30,
    "30Min": 60,
    "1Hour": 90,
    "4Hour": 180,
    "1Day":  1825,   # ~5 years
    "1Week": 3650,   # ~10 years
    "1Month": 7300,  # ~20 years
}
CHART_DEFAULT_BARS = 500   # bars returned when caller doesn't specify limit
CHART_MAX_BARS     = 5000  # hard ceiling — prevents runaway requests

# IBKR historical bars (reqHistoricalData) — used when discovery_provider=ibkr
# so the chart matches IBKR live quotes instead of Alpaca IEX.
IBKR_BAR_SIZE: dict[str, str] = {
    "1Min": "1 min",
    "5Min": "5 mins",
    "15Min": "15 mins",
    "30Min": "30 mins",
    "1Hour": "1 hour",
    "4Hour": "4 hours",
    "1Day": "1 day",
    "1Week": "1 week",
    "1Month": "1 month",
}
IBKR_BAR_DURATION: dict[str, str] = {
    # Keep 1Min short — 5 D of extended-hours 1-min bars is huge and often times out
    # when Gateway is also serving scanners / setups_stream.
    "1Min": "1 D",
    "5Min": "5 D",
    "15Min": "1 M",
    "30Min": "2 M",
    "1Hour": "3 M",
    "4Hour": "6 M",
    "1Day": "5 Y",
    "1Week": "10 Y",
    "1Month": "20 Y",
}
IBKR_HISTORICAL_USE_RTH = False          # include extended hours (match chart live session)
IBKR_HISTORICAL_TIMEOUT_SEC = 20.0       # interactive chart budget (fail loud, don't spin forever)
IBKR_HISTORICAL_BACKGROUND_TIMEOUT_SEC = 12.0  # setups_stream / non-UI fetches
IBKR_HISTORICAL_WHAT_TO_SHOW = "TRADES"


