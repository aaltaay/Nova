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

# ── Scanner sizing ──────────────────────────────────────────────────────────
# SCAN_CAP_DEFAULT is retained as an emergency env-var override only.
# Normal operation uses exchange-based filtering (SCAN_EXCHANGES) instead.
SCAN_CAP_DEFAULT = 800   # legacy; overridden by ALPACA_SCAN_SYMBOL_CAP env var if set
TOP_N_DEFAULT = 50       # max gappers returned / cap on movers API batching
SNAPSHOT_WORKERS = 10    # parallel threads for batch snapshot fetching

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

# ── Ticker detail caches ──────────────────────────────────────────────────────
# Fundamentals (yfinance/Yahoo) are slow; cache aggressively.
FUNDAMENTALS_CACHE_TTL = 900.0      # 15 minutes
# Hard timeout for a single yfinance .info call; prevents Yahoo stalls from blocking Phase 2.
# On timeout, stale cached data (if any) is returned; otherwise an empty dict is used.
YFINANCE_TIMEOUT_S = 5.0
# Asset metadata (name, exchange, tradability) rarely changes intraday.
TICKER_ASSET_CACHE_TTL = 900.0      # 15 minutes (extended from 5 min — static intraday)
# Snapshot (price, quote, bars) is live data; only cache briefly to de-dup rapid clicks.
TICKER_SNAPSHOT_CACHE_TTL = 10.0    # 10 seconds
# Short-lived cache for the full Phase 2 payload (news + fundamentals + avg_vol).
# Serves repeat clicks and rapid tab-switching without re-fetching from external APIs.
TICKER_SLOW_CACHE_TTL = 90.0        # 90 seconds
