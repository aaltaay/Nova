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
# Asset metadata (name, exchange, tradability) rarely changes intraday.
TICKER_ASSET_CACHE_TTL = 900.0      # 15 minutes (extended from 5 min — static intraday)
# Snapshot (price, quote, bars) is live data; only cache briefly to de-dup rapid clicks.
TICKER_SNAPSHOT_CACHE_TTL = 10.0    # 10 seconds
# Short-lived cache for the full Phase 2 payload (news + fundamentals + avg_vol).
# Serves repeat clicks and rapid tab-switching without re-fetching from external APIs.
TICKER_SLOW_CACHE_TTL = 90.0        # 90 seconds


# ── Ticker chart (Alpaca bars) ────────────────────────────────────────────────
# Valid Alpaca timeframe strings accepted by GET /v2/stocks/{symbol}/bars.
CHART_TIMEFRAMES: tuple[str, ...] = (
    "1Min", "5Min", "15Min", "30Min", "1Hour", "4Hour", "1Day", "1Week", "1Month",
)
CHART_DEFAULT_TIMEFRAME = "5Min"

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


# ── HOD Momo Scanner ──────────────────────────────────────────────────────────

import os as _os

# Cache file keys / prefixes (kept in constants so cache.py and hod_momo.py share one source)
HOD_MOMO_ALERTS_PREFIX = "hod-momo"


def _hod_momo_cache_root() -> str:
    return (
        _os.environ.get("NOVA_CACHE_DIR")
        or _os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
        or _os.path.join(_os.path.dirname(__file__), ".cache")
    )


HOD_MOMO_CONFIG_FILE = _os.path.join(_hod_momo_cache_root(), "hod-momo-config.json")
HOD_MOMO_BLOCKLIST_FILE = _os.path.join(_hod_momo_cache_root(), "hod-momo-blocklist.json")

# Engine timing
HOD_MOMO_COOLDOWN_SEC = 60.0         # suppress re-alert for ticker+strategy after firing
HOD_MOMO_CONSOLIDATION_SEC = 5.0     # batch alerts for same ticker within this window
HOD_MOMO_UNIVERSE_INTERVAL_SEC = 300.0  # refresh HOD universe subscription every 5 min
HOD_MOMO_SESSION_RESET_HOUR_ET = 4   # reset session state at 4:00 AM ET

# Enrichment loop intervals
HOD_MOMO_ENRICH_INTERVAL_SEC = 30.0          # batch snapshot enrichment cadence
HOD_MOMO_FUNDAMENTALS_QUEUE_INTERVAL_SEC = 2.0  # fundamentals per-symbol drain cadence
HOD_MOMO_FUNDAMENTALS_BATCH_SIZE = 10            # symbols per fundamentals tick (warm up faster)

# Master gate defaults
HOD_MOMO_MASTER_HOD_REQUIRED = True
HOD_MOMO_MASTER_SURGE_PCT = 3.0      # price must rise this % within lookback window
HOD_MOMO_MASTER_SURGE_WINDOW_MIN = 5  # minutes
HOD_MOMO_MASTER_MIN_RVOL = 2.0
HOD_MOMO_MASTER_PREMARKET_MIN_RVOL = 1.0   # relaxed during 4–9:30 AM and 4–8 PM ET
HOD_MOMO_MASTER_AFTERHOURS_MIN_RVOL = 1.0

# RVOL fallback: when on IEX free tier, Alpaca historical bars are mostly empty.
# During warmup (first N seconds after startup), skip the RVOL master gate entirely
# so the scanner can fire while yfinance data loads progressively.
HOD_MOMO_RVOL_WARMUP_GRACE_SEC = 300            # 5 min: skip RVOL gate while yfinance warms up

# Strategy names (canonical order 1–11)
HOD_MOMO_STRATEGY_NAMES: dict[int, str] = {
    1:  "Former Momo Stock",
    2:  "Squeeze Alert - 52wk Breakout",
    3:  "Low Float - Med Rel Vol",
    4:  "Low Float - High Rel Vol - Price $20+",
    5:  "Low Float Volatility Hunter",
    6:  "Medium Float - High Rel Vol - Price under $20",
    7:  "Low Float - High Rel Vol",
    8:  "Medium Float - High Rel Vol - Price $20+",
    9:  "Medium Float - Med Rel Vol - Price $20+",
    10: "Squeeze Alert - Up 10% in 10min",
    11: "Squeeze Alert - Up 5% in 5min",
}

# Strategy default colors (hex)
HOD_MOMO_STRATEGY_COLORS: dict[int, str] = {
    1:  "#FF9100",
    2:  "#FFD600",
    3:  "#66BB6A",
    4:  "#00BFA5",
    5:  "#FF5252",
    6:  "#B388FF",
    7:  "#00E676",
    8:  "#448AFF",
    9:  "#78909C",
    10: "#00E5FF",
    11: "#40C4FF",
}

# Audio ON by default for all except 8 and 9
HOD_MOMO_STRATEGY_AUDIO_DEFAULT: dict[int, bool] = {
    1: True, 2: True, 3: True, 4: True, 5: True,
    6: True, 7: True, 8: False, 9: False, 10: True, 11: True,
}

# Per-strategy default config values.
# Keys match StrategyConfig field names. Missing keys use the universal 0-disabled default.
HOD_MOMO_STRATEGY_DEFAULTS: dict[int, dict] = {
    1: {  # Former Momo Stock
        "min_rvol": 2.0,
    },
    2: {  # Squeeze Alert - 52wk Breakout
        "proximity_52wk_pct": 1.0,
        "min_rvol": 1.5,
        "surge_pct": 3.0,
        "surge_window_min": 5,
    },
    3: {  # Low Float - Med Rel Vol
        "max_float": 10_000_000,
        "min_rvol": 2.0,
        "max_rvol": 4.9,
    },
    4: {  # Low Float - High Rel Vol - Price $20+
        "max_float": 10_000_000,
        "min_rvol": 5.0,
        "min_price": 20.0,
    },
    5: {  # Low Float Volatility Hunter
        "max_float": 10_000_000,
        "min_rvol": 3.0,
        "min_change_pct": 5.0,
    },
    6: {  # Medium Float - High Rel Vol - Price under $20
        "min_float": 10_000_000,
        "max_float": 50_000_000,
        "min_rvol": 5.0,
        "max_price": 19.99,
    },
    7: {  # Low Float - High Rel Vol
        "max_float": 10_000_000,
        "min_rvol": 5.0,
    },
    8: {  # Medium Float - High Rel Vol - Price $20+
        "min_float": 10_000_000,
        "max_float": 50_000_000,
        "min_rvol": 5.0,
        "min_price": 20.0,
    },
    9: {  # Medium Float - Med Rel Vol - Price $20+
        "min_float": 10_000_000,
        "max_float": 50_000_000,
        "min_rvol": 2.0,
        "max_rvol": 4.9,
        "min_price": 20.0,
    },
    10: {  # Squeeze Alert - Up 10% in 10min
        "surge_pct": 10.0,
        "surge_window_min": 10,
    },
    11: {  # Squeeze Alert - Up 5% in 5min
        "surge_pct": 5.0,
        "surge_window_min": 5,
    },
}

# ── Desktop (Electron) local API ──────────────────────────────────────────────
# Sidecar binds here; Electron UI always talks to this loopback address.
NOVA_DESKTOP_API_HOST = "127.0.0.1"
NOVA_DESKTOP_API_PORT = 8000

# ── Interactive Brokers (optional trading module) ──────────────────────────────
# Set IBKR_ENABLED=true in .env to activate. Defaults to paper trading.
# For live money, ALSO set IBKR_LIVE_TRADING_CONFIRMED=true.
IBKR_HOST = "127.0.0.1"
IBKR_PAPER_PORT = 4002       # IB Gateway paper trading port
IBKR_LIVE_PORT = 4001        # IB Gateway live trading port
IBKR_CLIENT_ID = 1
IBKR_MAX_DEPTH_SYMBOLS = 3   # IBKR plan cap: 3 simultaneous Level 2 streams
IBKR_ACCOUNT_POLL_SEC = 5    # How often to refresh account/positions
IBKR_RECONNECT_DELAY_SEC = 10  # Delay before reconnect attempt

# ── Strategy: Five Pillars of Stock Selection ─────────────────────────────────
# Signal-only thresholds (see backend/strategy/five_pillars.py). These never place
# orders — they only score a candidate dict (same shape as gapper/gainer cache rows).
# Source: knowledge/obsidian/02-Strategies/Five-Pillars-and-Gap-and-Go-Spec.md
FIVE_PILLARS_MIN_PRICE = 2.0            # Pillar 1: price floor
FIVE_PILLARS_MAX_PRICE = 20.0           # Pillar 1: price ceiling
FIVE_PILLARS_MIN_CHANGE_PCT = 10.0      # Pillar 2: % up vs prior close (or vs LOD on continuation)
FIVE_PILLARS_MIN_REL_VOLUME = 5.0       # Pillar 3: relative volume multiple
FIVE_PILLARS_MAX_FLOAT_SHARES = 20_000_000  # Pillar 5: float ceiling (shares)

# ── Strategy: Gap and Go setup ────────────────────────────────────────────────
# Codeable rules only — tape-reading / Level 2 nuance is intentionally NOT encoded.
GAP_AND_GO_WINDOW_START_ET = (9, 30)    # session open
GAP_AND_GO_WINDOW_END_ET = (10, 0)      # end of the Gap and Go entry window
GAP_AND_GO_MAX_STOP_DOLLARS = 0.20      # max risk per share (stop distance)
GAP_AND_GO_MIN_PROFIT_LOSS_RATIO = 2.0  # target = entry + risk * this ratio

# ── Bull Flag setup (Phase B) ────────────────────────────────────────────────
# Source: SS101 Ch.5 — flagpole of green candles, shallow pullback holding the
# 9 EMA, entry on break back above the flagpole high.
BULL_FLAG_LOOKBACK_BARS = 30       # recent 1-min bars scanned for the pattern
BULL_FLAG_MIN_FLAGPOLE_CANDLES = 3  # consecutive green candles forming the pole
BULL_FLAG_MIN_PULLBACK_CANDLES = 2  # consecutive pullback candles forming the flag
BULL_FLAG_EMA_PERIOD = 9
BULL_FLAG_MAX_RETRACE_PCT = 0.50    # pullback must retrace less than this of the pole
BULL_FLAG_MIN_PROFIT_LOSS_RATIO = 2.0

# ── ABCD setup (Phase B) ─────────────────────────────────────────────────────
# Source: SS101 Ch.5 — A-to-B impulsive move, C pullback holding the 9 EMA,
# entry D on break back above point B.
ABCD_LOOKBACK_BARS = 40            # recent 1-min bars scanned for A/B/C points
ABCD_MIN_AB_MOVE_PCT = 5.0         # minimum % move from A to B to qualify as impulsive
ABCD_EMA_PERIOD = 9
ABCD_MAX_RETRACE_PCT = 0.50        # C must retrace less than this of the A-B move
ABCD_MAX_STOP_DOLLARS = 0.20
ABCD_MIN_PROFIT_LOSS_RATIO = 2.0

# ── Watchlist composite ranking (Phase A) ───────────────────────────────────
# Weighted 0-100 score layered on top of the Five Pillars pass/fail chips.
# Symbols that pass all 5 pillars are always ranked above ones that don't;
# the composite score only breaks ties within each group.
WATCHLIST_WEIGHT_CHANGE_PCT = 0.30
WATCHLIST_WEIGHT_REL_VOLUME = 0.30
WATCHLIST_WEIGHT_FLOAT = 0.20
WATCHLIST_WEIGHT_CATALYST = 0.20
WATCHLIST_CHANGE_PCT_SCORE_CAP = 200.0   # % change that maps to a perfect sub-score
WATCHLIST_REL_VOLUME_SCORE_CAP = 50.0    # RVOL multiple that maps to a perfect sub-score
WATCHLIST_CATALYST_FRESH_MINUTES = 60.0  # headline age considered "fully fresh"
WATCHLIST_CATALYST_STALE_MINUTES = 24 * 60.0  # headline age at which freshness hits 0
WATCHLIST_MAX_ROWS = 60                  # cap on rows returned to the UI

# ── Setup signal stream (Phase B, /ws/strategy) ─────────────────────────────
SETUPS_SCAN_INTERVAL_SEC = 15.0     # how often the background loop re-scans the watchlist
SETUPS_SCAN_TOP_N = 15              # only fetch bars for this many top-ranked watchlist symbols
SETUPS_ALERT_COOLDOWN_SEC = 120.0   # suppress a repeat alert for the same symbol+setup
SETUPS_MAX_HISTORY = 200            # cap on in-memory signal history for the initial WS payload

# ── Risk / discipline engine (Phase C) ──────────────────────────────────────
# Source: SS101 Ch.2, Ch.12; Basics Ch.15. This is a pure state machine — no
# orders are ever placed by backend/strategy/risk.py.
RISK_DAILY_GOAL_DOLLARS = 500.0       # daily profit target; also the daily max-loss walk-away trigger
                                       # NOTE: placeholder default — should become a per-user Settings
                                       # value once the journal/execution phases exist.
RISK_BASE_SHARE_BLOCK = 100           # standard position size, in shares
RISK_QUARTER_SIZE_MULTIPLIER = 0.25   # size used before the profit cushion is reached
RISK_PROFIT_CUSHION_FRACTION = 0.25   # fraction of daily goal that unlocks full size
RISK_SIZE_CUT_LOSS_FRACTION_OF_GOAL = 0.10  # losing this fraction of the daily goal cuts size
RISK_SIZE_CUT_MULTIPLIER = 0.5        # size multiplier applied while in a loss-cut state
RISK_MIN_PROFIT_LOSS_RATIO = 1.0      # absolute floor — never trade below 1:1
RISK_TARGET_PROFIT_LOSS_RATIO = 2.0   # target ratio the setups aim for
RISK_MAX_STOP_DOLLARS = 0.20          # hard ceiling on stop distance for scalps
RISK_PREFERRED_STOP_DOLLARS_LOW = 0.05
RISK_PREFERRED_STOP_DOLLARS_HIGH = 0.10
RISK_MAX_CONSECUTIVE_LOSSES = 3       # walk-away guardrail: 3 losses in a row halts the day
RISK_MAX_GIVEBACK_FRACTION_OF_PEAK = 0.50  # walk-away guardrail: gave back half of today's peak profit
RISK_SESSION_RESET_HOUR_ET = 4        # daily state resets at 4:00 AM ET, mirrors HOD_MOMO_SESSION_RESET_HOUR_ET

# ── Journal (Phase E) ────────────────────────────────────────────────────────
JOURNAL_DB_FILENAME = "journal.db"      # lives under paths.cache_dir(), not git-tracked
JOURNAL_SIGNALS_DEFAULT_LIMIT = 100
JOURNAL_TRADES_DEFAULT_LIMIT = 200
JOURNAL_MIN_TRADES_FOR_GO_LIVE = 100     # go/no-go bar: minimum sample size before trusting the stats
JOURNAL_MOCK_TRADE_COUNT = 12            # rows generated by journal/mock_data.py for UI/logic testing only

# ── Paper execution / Arm Automation (Phase D) ──────────────────────────────
# backend/strategy/executor.py places IBKR bracket orders ONLY when armed
# (always resets to disarmed on backend restart) AND risk.can_trade() AND
# risk.validate_trade_plan() both approve the signal. Every current setup
# (Gap and Go, Bull Flag, ABCD) is long-only, so the entry side is fixed.
EXECUTOR_ENTRY_SIDE_IBKR = "BUY"        # ibkr.orders.OrderSide used for every bracket entry
EXECUTOR_ENTRY_SIDE_JOURNAL = "long"    # journal.store side convention ("long"/"short")
EXECUTOR_FILL_POLL_INTERVAL_SEC = 10.0  # how often the background loop checks for bracket fills
