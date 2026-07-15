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
# Local dev default: any origin (Vite runs on a fixed localhost port, no
# cookies/credentials are used). Override for non-local deploys with the
# NOVA_CORS_ALLOWED_ORIGINS env var (comma-separated exact origins, e.g.
# "https://nova.up.railway.app,https://nova.vercel.app").
CORS_ALLOWED_ORIGINS_DEFAULT = ["*"]

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
HOD_MOMO_CONSOLIDATION_SEC = 5.0     # batch same-ticker alerts into one row (Warrior "N in Xs")
# Persist at most this often — writing the full day list on every emit freezes the API.
HOD_MOMO_ALERT_SAVE_INTERVAL_SEC = 5.0
HOD_MOMO_UNIVERSE_INTERVAL_SEC = 300.0  # refresh cadence for broad (full-asset) mode
# Ross-style focus: Top Gainer/Gapper shortlist + IBKR volume seeds — not the
# full US tape. Broad mode subscribed ~6k IEX symbols → zero trades (empty tab).
# Warrior Day Trade Dash scans the whole market; Nova approximates that by
# unioning Top % Gain/Lose with HOT_BY_VOLUME / TOP_VOLUME_RATE / MOST_ACTIVE.
HOD_MOMO_UNIVERSE_MODE_FOCUS = "focus"
HOD_MOMO_UNIVERSE_MODE_BROAD = "broad"
HOD_MOMO_UNIVERSE_MODE = HOD_MOMO_UNIVERSE_MODE_FOCUS
HOD_MOMO_FOCUS_REFRESH_SEC = 5.0     # how often to rebuild focus set from scanner caches
HOD_MOMO_ALPACA_SUBSCRIBE_CHUNK = 200  # max symbols per Alpaca WS subscribe message
HOD_MOMO_SESSION_RESET_HOUR_ET = 4   # reset session state at 4:00 AM ET
HOD_MOMO_SEED_REFRESH_SEC = 30.0     # IBKR volume-scanner seed cadence
# Squeeze surge cold-start: live ticks alone start empty, so strategy 10/11 get
# surge:None (or ~0%) when a name first joins the focus universe mid-move.
# Seed the rolling price buffer from recent 1-min bars once per symbol/session.
HOD_MOMO_SURGE_SEED_TIMEFRAME = "1Min"
HOD_MOMO_SURGE_SEED_BARS = 15          # last ~15 minutes of 1-min OHLCV
HOD_MOMO_SURGE_SEED_POLL_SEC = 1.0     # drain pending seed queue
HOD_MOMO_SURGE_SEED_MAX_PER_TICK = 2   # IBKR historical pacing — keep low
# Integrity / fail-loud data-flow checks (invisible-bug detectors).
HOD_MOMO_INTEGRITY_TICK_STALE_SEC = 15.0       # no HOD ticks while universe non-empty → fail
HOD_MOMO_INTEGRITY_WARMUP_SEC = 45.0           # grace after process start before tick check fails
HOD_MOMO_INTEGRITY_SURGE_MIN_SPAN_SEC = 240.0  # buffer span for "ready" (4 of 5 min window)
HOD_MOMO_INTEGRITY_SURGE_READY_MIN_PCT = 40.0  # % of buffered symbols that must be ready
HOD_MOMO_INTEGRITY_SEED_WARN_AFTER_SEC = 90.0  # ibkr + empty volume seeds after this → warn
HOD_MOMO_INTEGRITY_POLL_SEC = 20.0             # background integrity logger cadence
HOD_MOMO_INTEGRITY_ENRICHED_MIN_PCT = 30.0     # snaps with rvol vs tracked snaps
SCANNER_INTEGRITY_CACHE_STALE_SEC = 120.0      # gappers/gainers/losers cache age → warn/fail
HOD_MOMO_FORMER_MOMO_STRATEGY_ID = 1  # empty former_momo_list → never fire
HOD_MOMO_RUNNING_UP_STRATEGY_ID = 12  # Warrior Running Up — no HOD required
HOD_MOMO_STRATEGY_ID_MAX = 12

# Enrichment loop intervals
HOD_MOMO_ENRICH_INTERVAL_SEC = 30.0          # batch snapshot enrichment cadence
HOD_MOMO_FUNDAMENTALS_QUEUE_INTERVAL_SEC = 2.0  # fundamentals per-symbol drain cadence
HOD_MOMO_FUNDAMENTALS_BATCH_SIZE = 10            # symbols per fundamentals tick (warm up faster)

# Master gate defaults.
# Warrior HOD Momo = new HOD + *per-strategy* momentum (float/RVOL/surge bands).
# Master surge is OFF by default so Medium Float / Low Float Rel Vol strategies
# are not double-gated by a global 3%/5min filter that Warrior does not apply.
HOD_MOMO_MASTER_HOD_REQUIRED = True
HOD_MOMO_MASTER_SURGE_PCT = 0.0      # 0 = disabled; squeeze strategies keep their own surge
HOD_MOMO_MASTER_SURGE_WINDOW_MIN = 5  # minutes (used only when surge_pct > 0)
HOD_MOMO_MASTER_MIN_RVOL = 2.0
HOD_MOMO_MASTER_PREMARKET_MIN_RVOL = 1.0   # relaxed during 4–9:30 AM and 4–8 PM ET
HOD_MOMO_MASTER_AFTERHOURS_MIN_RVOL = 1.0

# Pace RVOL (Warrior "Relative Volume (Daily Rate)"): today_vol / (avg * elapsed_frac).
# Floor = ~14 min of the 04:00–16:00 ET volume day — avoids insane RVOL at 4:01.
HOD_MOMO_RVOL_PACE_FLOOR = 0.02
HOD_MOMO_RVOL_USE_PACE = True
# Warrior "Relative Volume (5 min %)": last-5m vol ÷ (avg_daily / bars_in_session).
# Session = 04:00–16:00 ET (720 min → 144 five-minute bars), matching pace RVOL day.
HOD_MOMO_RVOL_5MIN_WINDOW_SEC = 300
HOD_MOMO_RVOL_5MIN_SESSION_MINUTES = 720.0
# When True, typical 5-min volume uses a coarse ET time-of-day curve (open/close heavy).
HOD_MOMO_RVOL_5MIN_USE_TOD = True
# Cumulative fraction of daily volume by ET minute-of-day (midnight=0). Coarse U-shape.
# Interpolated between knots; last knot should be ~1.0 at end of extended session.
HOD_MOMO_RVOL_5MIN_TOD_CUM_FRAC: tuple[tuple[int, float], ...] = (
    (4 * 60, 0.00),       # 04:00 premarket open
    (9 * 60 + 30, 0.12),  # 09:30 RTH open
    (10 * 60, 0.28),      # open spike
    (12 * 60, 0.45),      # midday
    (15 * 60, 0.65),      # afternoon
    (16 * 60, 0.88),      # RTH close
    (20 * 60, 1.00),      # 20:00 AH end
)

# RVOL fallback: when on IEX free tier, Alpaca historical bars are mostly empty.
# During warmup (first N seconds after startup), skip the RVOL master gate entirely
# so the scanner can fire while yfinance data loads progressively.
HOD_MOMO_RVOL_WARMUP_GRACE_SEC = 300            # 5 min: skip RVOL gate while yfinance warms up
# Bump when master/strategy defaults change so persisted configs migrate once.
HOD_MOMO_CONFIG_SCHEMA_VERSION = 3

# Strategy names (canonical order 1–12)
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
    12: "Running Up Alert",
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
    12: "#FF6E40",
}

# Audio ON by default for all except 8 and 9
HOD_MOMO_STRATEGY_AUDIO_DEFAULT: dict[int, bool] = {
    1: True, 2: True, 3: True, 4: True, 5: True,
    6: True, 7: True, 8: False, 9: False, 10: True, 11: True, 12: True,
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
    12: {  # Running Up Alert — Warrior separate scanner; momentum without HOD
        "requires_hod": False,
        "surge_pct": 5.0,
        "surge_window_min": 5,
        "min_rvol": 2.0,
    },
}

# ── Desktop (Electron) local API ──────────────────────────────────────────────
# Sidecar binds here; Electron UI always talks to this loopback address.
NOVA_DESKTOP_API_HOST = "127.0.0.1"
NOVA_DESKTOP_API_PORT = 8000

# ── Interactive Brokers (optional trading module) ──────────────────────────────
# Set IBKR_ENABLED=true in .env to activate.
# IBKR_GATEWAY_MODE=paper|live  → which Gateway port to connect (data / L2).
# IBKR_ORDERS_ENABLED=false     → master kill switch; default OFF so live Gateway
#                                 cannot place buys/sells until you opt in.
# IBKR_LIVE_TRADING_CONFIRMED   → second key required when gateway/account is live.
IBKR_HOST = "127.0.0.1"
IBKR_PAPER_PORT = 4002       # IB Gateway paper trading port
IBKR_LIVE_PORT = 4001        # IB Gateway live trading port
IBKR_CLIENT_ID = 1
IBKR_MAX_DEPTH_SYMBOLS = 3   # IBKR plan cap: 3 simultaneous Level 2 streams
IBKR_DEPTH_NUM_ROWS = 10     # Bid/ask rows requested per side of the book
# SMART-routed depth requires isSmartDepth=True (TWS API ≥974). With False,
# IBKR rejects every SMART contract with error 10092 even when TotalView /
# OpenBook is subscribed — see PROBLEM_LOG 2026-07-13.
IBKR_DEPTH_SMART = True
# After the last DepthLadder WS viewer disconnects, keep the IBKR depth line
# alive briefly so React StrictMode remounts / fast reconnects can reattach
# without tearing down reqMktDepth (which flashes "Connecting depth…").
IBKR_DEPTH_RELEASE_GRACE_SEC = 0.75
IBKR_ACCOUNT_POLL_SEC = 5    # How often to refresh account/positions
IBKR_RECONNECT_DELAY_SEC = 10  # Delay before reconnect attempt
# TWS API error code: "Deep market data is not supported for this combination
# of security type/exchange." Arrives asynchronously via errorEvent AFTER
# reqMktDepth() already returned successfully, so it can't be caught by a
# try/except around the call — see ibkr/depth.py._on_ib_error.
IBKR_ERROR_DEPTH_NOT_SUPPORTED = 10092
# Tick-by-tick Time & Sales subscription failures (async via errorEvent).
# 10089/10189: requires additional market-data subscription; 354: not subscribed.
IBKR_ERROR_TICK_BY_TICK_CODES = frozenset({10089, 10189, 354})

# ib_async's OWN internal loggers (ib_async.wrapper / .ib / .client — not our
# app loggers) log these at ERROR even though they're expected under normal
# Gateway operation: cancelled/no-data historical or scanner queries, and
# late-cancel races. See backend/ibkr/log_filters.py, which downgrades
# matching records to WARNING so Sentry's LoggingIntegration (event_level via
# observability.py) stops opening issues for them, while local log files are
# unaffected. Confirmed against live Sentry issues PYTHON-FASTAPI-1/2/3/7/8/9/A.
IBKR_BENIGN_LOG_ERROR_CODES = frozenset({162, 365})  # e.g. "Error 162, reqId 1633: ..."
IBKR_BENIGN_LOG_MESSAGE_SUBSTRINGS = (
    "cancelmktdata: no reqid found",
    "cancelmktdepth: no reqid found",
)
IBKR_GATEWAY_MODE_DEFAULT = "paper"
IBKR_ORDERS_ENABLED_DEFAULT = False  # never spend until explicitly enabled

# ── Market-data discovery provider (gappers / gainers / losers source) ────────
# "alpaca" (default — no behavior change, free IEX feed, no cost) or
# "ibkr" (live scan through IB Gateway using the account's paid data lines).
# Alpaca code paths are never removed, so this is reversible at any time —
# switch back via Settings or NOVA_DISCOVERY_PROVIDER without redeploying.
# News (Alpaca free) and fundamentals (yfinance) stay the same either way —
# only the raw symbol/price/volume discovery source changes.
# See knowledge/obsidian/03-Nova-Decisions/Scanner-Provider-IBKR-Primary.md
DISCOVERY_PROVIDER_DEFAULT = "alpaca"
DISCOVERY_PROVIDER_OPTIONS = ("alpaca", "ibkr")

# IB market scanner — https://interactivebrokers.github.io/tws-api/market_scanners.html
# Limits enforced by IB itself: max 50 rows per scan code, max 10 active scans.
IBKR_SCAN_INSTRUMENT = "STK"
IBKR_SCAN_LOCATION = "STK.US.MAJOR"            # all major US exchanges
IBKR_SCAN_CODE_GAPPERS = "TOP_OPEN_PERC_GAIN"  # today's open vs prior close (premarket gap)
IBKR_SCAN_CODE_GAINERS = "TOP_PERC_GAIN"       # current price vs prior close, intraday
IBKR_SCAN_CODE_LOSERS = "TOP_PERC_LOSE"
# Extra seeds for HOD Momo — Warrior catches mid-day volume runners that are
# not always in the top-% gainer list (e.g. FRE / TSSI / YG style alerts).
IBKR_SCAN_CODE_HOT_VOLUME = "HOT_BY_VOLUME"
IBKR_SCAN_CODE_TOP_VOLUME_RATE = "TOP_VOLUME_RATE"
IBKR_SCAN_CODE_MOST_ACTIVE = "MOST_ACTIVE"
IBKR_SCAN_HOD_SEED_CODES = (
    IBKR_SCAN_CODE_HOT_VOLUME,
    IBKR_SCAN_CODE_TOP_VOLUME_RATE,
    IBKR_SCAN_CODE_MOST_ACTIVE,
)
IBKR_SCAN_MAX_ROWS = 50                        # IB hard cap per scan code
IBKR_SCAN_ABOVE_PRICE = SCANNER_MIN_PRICE       # mirrors the Alpaca price floor above
# 1Hz table reprice may include scanner rows (gainers/losers/AH/gappers).
IBKR_TABLE_REPRICE_MAX_SYMBOLS = 100
# Progressive batches so the UI gets a price_patch every ~1–2s instead of
# waiting on one 100-symbol reqTickersAsync (that ran 7–10s → "stale").
IBKR_TABLE_REPRICE_CHUNK_SIZE = 20
IBKR_QUOTE_BATCH_TIMEOUT_SEC = 15.0             # per-batch reqTickersAsync timeout (discovery)
IBKR_TABLE_REPRICE_CHUNK_TIMEOUT_SEC = 4.0      # tighter timeout for table chunks
IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC = 25.0        # thread->asyncio bridge wait ceiling
# Alpaca's WS trade stream gives sub-second price freshness between the 20-30s
# scan ticks (see DISCOVERY_INTERVAL_SEC comment above) — that overlay is
# intentionally disabled while DISCOVERY_PROVIDER=ibkr (see PROBLEM_LOG
# 2026-07-13), so this replaces it with a fast IBKR-native reprice tick.
IBKR_REPRICE_INTERVAL_SEC = 3.0
# Detail-panel backstop: skip the reqTickersAsync snapshot for a symbol whose
# reqMktData streaming subscription (ibkr/ticks.py) has updated within this
# window — it's already delivering live ticks, so the snapshot is redundant
# IBKR-request-queue contention with table_reprice_loop. Only symbols whose
# stream is missing/stalled longer than this fall back to the snapshot.
IBKR_DETAIL_STREAM_FRESH_SEC = 8.0
# Scanner TABLE prices: independent 1Hz reqTickersAsync snapshots (not reqMktData).
# Must not wait on the full movers scan — that starvation caused "updated 10–12s ago".
IBKR_TABLE_REPRICE_INTERVAL_SEC = 1.0
# UI / heartbeat: if no successful table price tick within this window, mark stale.
# Chunked 1Hz pushes normally reset age every ~1s; this is the honesty margin
# when a chunk times out or skip-if-busy stacks.
SCANNER_PRICE_STALE_SEC = 5.0

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
SETUPS_SCAN_INTERVAL_SEC = 15.0     # how often the background loop re-scans (Alpaca discovery)
SETUPS_SCAN_INTERVAL_IBKR_SEC = 60.0  # slower under IBKR — historical pacing is shared with charts
SETUPS_SCAN_TOP_N = 15              # only fetch bars for this many top-ranked watchlist symbols
SETUPS_SCAN_TOP_N_IBKR = 3          # fewer concurrent historical pulls when discovery=ibkr
SETUPS_IBKR_INTER_SYMBOL_DELAY_SEC = 2.0  # gap between IBKR historical pulls in one cycle
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
# P&L calendar (TraderVue-style Reports tab) — days bucketed in America/New_York
JOURNAL_CALENDAR_TIMEZONE = "America/New_York"
JOURNAL_CALENDAR_MIN_YEAR = 2000
JOURNAL_CALENDAR_MAX_YEAR = 2100

# ── Paper execution / Arm Automation (Phase D) ──────────────────────────────
# backend/strategy/executor.py places IBKR bracket orders ONLY when armed
# (always resets to disarmed on backend restart) AND risk.can_trade() AND
# risk.validate_trade_plan() both approve the signal. Every current setup
# (Gap and Go, Bull Flag, ABCD) is long-only, so the entry side is fixed.
EXECUTOR_ENTRY_SIDE_IBKR = "BUY"        # ibkr.orders.OrderSide used for every bracket entry
EXECUTOR_ENTRY_SIDE_JOURNAL = "long"    # journal.store side convention ("long"/"short")
EXECUTOR_FILL_POLL_INTERVAL_SEC = 10.0  # how often the background loop checks for bracket fills

# ── Level 2 recorder / tape features (Phase F) ──────────────────────────────
# Source: Automation-Strategy-Backbone.md section 3 — tape-reading nuance is
# explicitly NOT automated into the executor. backend/l2/ only records,
# scores, and labels; nothing here ever places, modifies, or cancels an order.
# IBKR depth has no historical API, so a recording only covers the window
# AFTER a signal fires, never before it.
L2_DB_FILENAME = "l2.db"               # lives under paths.cache_dir(), not git-tracked
L2_RECORD_WINDOW_SEC = 180.0            # how long to keep snapshotting after a signal fires
L2_SNAPSHOT_INTERVAL_SEC = 2.0          # how often to sample the book during the recording window
L2_ASK_STACKED_RATIO = 1.5              # ask size >= this many times bid size => "seller stacked on the ask"
L2_BID_HEAVY_RATIO = 1.5                # bid size >= this many times ask size => "buyers in control"
L2_PRESSURE_DRYING_LOOKBACK = 5         # snapshots compared to flag "buying pressure drying up"
L2_PRESSURE_DRYING_DROP_FRACTION = 0.30  # bid size must drop by at least this fraction to flag drying up
L2_LABEL_MATCH_TOLERANCE_SEC = 600.0    # max gap between a signal and a journal trade's opened_ts to link them
L2_SPREAD_WIDE_DOLLARS = 0.05           # spread at/above this is flagged "wide" in the UI badge
# Efficient local recorders (hot SQLite window — see Local-Market-Data-Recorders.md)
L2_CONTINUOUS_SNAPSHOT_INTERVAL_SEC = 1.0  # book sample rate while a depth session is open
L2_BATCH_SIZE = 64                         # flush L2 snapshot queue after this many pending rows
L2_BATCH_FLUSH_INTERVAL_SEC = 0.25         # or flush at least this often (whichever comes first)
TAPE_BATCH_SIZE = 256                      # flush time & sales queue after this many pending rows
TAPE_BATCH_FLUSH_INTERVAL_SEC = 0.25
L2_RETENTION_DAYS = 14                     # purge l2_snapshots / tape_trades / ended sessions older than this
L2_RETENTION_SWEEP_INTERVAL_SEC = 3600.0   # how often the background retention task runs
L2_RECALL_DEFAULT_WINDOW_SEC = 2.0         # default ±window for point-in-time recall API
TAPE_SOURCE_ALPACA = "alpaca"              # tape_trades.source for Alpaca WS prints
TAPE_SOURCE_IBKR = "ibkr"                 # tape_trades.source for IBKR tick-by-tick prints
IBKR_TAPE_TICK_TYPE = "AllLast"           # tick-by-tick type (AllLast = every print like TWS Time & Sales)
TAPE_UI_MAX_ROWS = 200                    # max rows kept in the frontend Time & Sales panel
L2_SESSION_REASON_SIGNAL = "signal"        # record_sessions.reason when setup signal fires
L2_SESSION_REASON_DEPTH = "depth"          # record_sessions.reason when DepthLadder / depth WS is open

# ── Permanent market-data archive (Nova OS P6–P10) ──────────────────────────
# Hot SQLite capture + local cold compact/restore + optional Cloudflare R2.
# Does NOT bump NOVA_OS_POLICY_VERSION — archive schema is versioned separately.
# Trim of unverified hot data stays blocked until remote verify (P8).
ARCHIVE_SCHEMA_VERSION = "archive-v1-2026-07-15"
ARCHIVE_DB_FILENAME = "archive.db"              # under paths.cache_dir(), not git-tracked
ARCHIVE_COLD_DIRNAME = "archive_cold"           # finished-day JSONL + manifests
ARCHIVE_HOT_RETENTION_DAYS = 30                 # hot window before a day is compact-eligible
ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM = True     # never timer-purge until remote verify
ARCHIVE_MAINTENANCE_ENABLED = False             # opt-in via env ARCHIVE_MAINTENANCE_ENABLED
ARCHIVE_MAINTENANCE_INTERVAL_SEC = 3600.0       # hourly stub when maintenance enabled
ARCHIVE_SOURCE_IBKR = "ibkr"
ARCHIVE_SOURCE_ALPACA = "alpaca"
ARCHIVE_STREAM_TAPE = "tape"
ARCHIVE_STREAM_L2 = "l2"
ARCHIVE_STREAM_BARS_1M = "bars_1m"
ARCHIVE_STREAM_BARS_1D = "bars_1d"
ARCHIVE_COUNTER_TAPE_RECEIVED = "tape_received"
ARCHIVE_COUNTER_TAPE_DROPPED = "tape_dropped"
ARCHIVE_COUNTER_L2_SNAPSHOTS = "l2_snapshots"
ARCHIVE_COUNTER_BARS_1M = "bars_1m"
ARCHIVE_COUNTER_BARS_1D = "bars_1d"
ARCHIVE_COUNTER_GAPS = "capture_gaps"
ARCHIVE_COUNTER_INCOMPLETE_WINDOWS = "incomplete_windows"
ARCHIVE_TABLES_COLD = (
    "bars_1m",
    "bars_1d",
    "tape_ibkr",
    "capture_gaps",
    "incomplete_windows",
)
# L2 depth snapshots + tape prints already live durably in the pre-existing
# l2/db.py hot store (l2/continuous.py samples at L2_CONTINUOUS_SNAPSHOT_INTERVAL_SEC
# whenever a depth session is open). These two tables are bridged into the same
# checksummed cold-archive + R2 pattern by archive/l2_bridge.py, but kept out of
# ARCHIVE_TABLES_COLD (a different sqlite file, no session_date column) so the
# existing bars/tape_ibkr compact+upload+restore contract is untouched.
ARCHIVE_TABLES_COLD_L2 = (
    "l2_snapshots",
    "tape_trades",
)
# Cloudflare R2 (P8) — credentials ONLY in .env (never commit). Env var names:
#   R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
#   ARCHIVE_R2_ENABLED=true to attempt uploads (still no-ops without keys)
#   R2_BUCKET (optional override of R2_BUCKET_DEFAULT)
ARCHIVE_R2_ENABLED = False
R2_BUCKET_DEFAULT = "nova-archive"
R2_PREFIX = "nova-os/archive/"                  # content-addressed keys under this prefix
R2_ENDPOINT_HOST_SUFFIX = "r2.cloudflarestorage.com"
ARCHIVE_R2_VERIFIED_INDEX = "_r2_verified.json"  # under archive_cold/
ARCHIVE_R2_VERIFIED_INDEX_L2 = "_r2_verified_l2.json"  # under archive_cold/ (l2_bridge)
# Replay / evening review (P9)
ARCHIVE_EVENING_REVIEW_HORIZON_MIN = 5         # minutes after decision for outcome heuristic
ARCHIVE_EVENING_REVIEW_VERSION = "evening-review-v1-2026-07-15"
ARCHIVE_REPLAY_MAX_SYMBOLS = 50

# ── News impact decision layer (rules-first; not a black box) ────────────────
# Explicit thresholds for whether news actually moved a ticker / Level 2.
# Every value here is surfaced in NewsImpactVerdict.factors and UI tooltips.
# "Lincoln AI" reasoning (see below) fills ai_reasoning; rules stay authoritative.
NEWS_IMPACT_RULE_VERSION = "rules-v1"
NEWS_IMPACT_FRESH_HOURS = 2.0          # age ≤ this → fresh (mirrors NEWS_FLAME_HOT_HOURS)
NEWS_IMPACT_AGING_HOURS = 6.0          # age ≤ this → aging (still attributable)
NEWS_IMPACT_STALE_HOURS = 24.0         # age ≤ this → stale; above → expired
NEWS_IMPACT_STRONG_MOVE_PCT = 10.0     # |gap%| ≥ this → strong price reaction
NEWS_IMPACT_MILD_MOVE_PCT = 3.0        # |gap%| ≥ this → mild price reaction
NEWS_IMPACT_ATTENTION_RVOL = 2.0       # RVOL ≥ this → attention spike (mirrors REL_VOLUME_HIGH)
NEWS_IMPACT_L2_IMBALANCE_MIN = 0.35    # |bid/ask imbalance| ≥ this → L2 reacting
NEWS_IMPACT_MULTI_SOURCE_CONFIRM = 2   # ≥ this many major/official sources → confirmed
# Confidence floors/ceilings applied after rule scoring (0–1).
NEWS_IMPACT_CONFIDENCE_FLOOR = 0.15
NEWS_IMPACT_CONFIDENCE_CEILING = 0.95
# Source-name substrings (case-insensitive) for credibility tiers.
NEWS_IMPACT_OFFICIAL_SOURCE_KEYWORDS = (
    "sec", "edgar", "fda", "business wire", "globe newswire", "pr newswire",
    "accesswire", "company press", "investor relations",
)
NEWS_IMPACT_OFFICIAL_URL_KEYWORDS = (
    "sec.gov", "fda.gov", "businesswire.com", "globenewswire.com",
    "prnewswire.com", "accesswire.com",
)
NEWS_IMPACT_MAJOR_SOURCE_KEYWORDS = (
    "bloomberg", "reuters", "wsj", "wall street journal", "cnbc", "marketwatch",
    "benzinga", "dow jones", "associated press", "ap news", "financial times",
    "barron", "the street", "yahoo finance",
)
NEWS_IMPACT_SECONDARY_SOURCE_KEYWORDS = (
    "motley fool", "seeking alpha", "investopedia", "zacks", "tipranks",
    "investorplace", "fool.com",
)

# ── News language understanding (FinBERT sentiment + Lincoln AI narrative) ───
# FinBERT (ProsusAI/finbert) reads the headline text itself and returns a
# positive/negative/neutral label. It runs locally (no API key, no per-call
# cost), lazily loading the model on first real headline. It is informational
# only — it never changes impact_class/confidence, so the rules stay the
# visible, authoritative decision layer per this module's own contract.
NEWS_SENTIMENT_ENABLED = True
NEWS_SENTIMENT_MODEL_NAME = "ProsusAI/finbert"
NEWS_SENTIMENT_CACHE_MAX_ENTRIES = 500

# Loughran-McDonald financial lexicon (pysentiment2) — a hand-built financial
# word list, not a fine-tuned model. Zero GPU/model-download cost, so it runs
# alongside FinBERT as a second, instant, independent read of the headline.
# Also purely informational; never changes impact_class/confidence.
NEWS_LEXICON_ENABLED = True
NEWS_LEXICON_CACHE_MAX_ENTRIES = 500

# Lincoln AI — optional LLM narrative that fills NewsImpactVerdict.ai_reasoning
# with a plain-English read of the catalyst type. Off by default: it calls an
# external API and costs money, so it mirrors the IBKR opt-in gate pattern
# (env var overrides this default; see .env.example). Requires OPENAI_API_KEY.
LINCOLN_AI_ENABLED = False
LINCOLN_AI_MODEL = "gpt-4o-mini"
LINCOLN_AI_MAX_TOKENS = 220
LINCOLN_AI_TEMPERATURE = 0.2
LINCOLN_AI_TIMEOUT_SECONDS = 8.0
LINCOLN_AI_CACHE_MAX_ENTRIES = 200

# ── Nova OS — decision brain + audit (Phases P1–P2) ──────────────────────────
# Nova OS is Nova's auditable decision + operations layer. P1 laid the audit
# foundation (event log + vocabulary). P2 adds `decide()` gate composition.
# Everything below is the single source of truth for codes and tunables so the
# event schema, read API, and decide() all speak the same language.
#
# Stability contract: these code strings are persisted in the event log and
# read back by the UI. Treat them like an API contract — add new codes, never
# silently rename or repurpose an existing one, and bump NOVA_OS_POLICY_VERSION
# when the decision semantics behind them change.
NOVA_OS_POLICY_VERSION = "nova-os-p5-2026-07-15"  # bump when decision semantics change

NOVA_OS_EVENTS_DB_FILENAME = "nova_os_events.db"  # lives under paths.cache_dir(), not git-tracked
NOVA_OS_EVENTS_DEFAULT_LIMIT = 200                # default rows returned by the read API
# Restart recovery scans this many newest events for executed_paper / closes.
NOVA_OS_RECOVERY_EVENTS_LIMIT = 500

# decide() tunables (course rules — Gap and Go first-minute volume + top ranks)
NOVA_OS_MIN_FIRST_MINUTE_VOLUME = 100_000  # ebook: ≥100k shares in the 9:30 ET minute
NOVA_OS_WATCHLIST_MAX_RANK = 4             # trade only the most-obvious top-ranked names
NOVA_OS_CATALYST_MIN_CONFIDENCE = 0.45     # soft Gate 4 floor for news-impact confidence
NOVA_OS_PRIMARY_SETUP = "gap_and_go"       # v1 strategy scope
NOVA_OS_DECIDE_DEFAULT_LIMIT = 4           # GET /api/nova-os/decide watchlist batch size
NOVA_OS_CITATIONS = (
    "SS101 Gap and Go — Five Pillars gate",
    "SS101 Gap and Go — first-minute volume ≥100k",
    "Basics — trade the most obvious gapper (top watchlist)",
    "Risk — min 2:1 R:R, max 20¢ stop, walk-away after losses",
)

# Decision verdicts — the three outcomes decide() may emit.
NOVA_OS_DECISION_BUY = "BUY"
NOVA_OS_DECISION_WAIT = "WAIT"
NOVA_OS_DECISION_NO_BUY = "NO_BUY"
NOVA_OS_DECISIONS = (NOVA_OS_DECISION_BUY, NOVA_OS_DECISION_WAIT, NOVA_OS_DECISION_NO_BUY)

# Control modes — how an approved decision is handled (see Decision-Brain Gate 6).
# Ordered least→most autonomous; auto_live always stays behind the IBKR live gate.
NOVA_OS_MODE_SIGNAL = "signal"          # display checklist + ticket only; never acts
NOVA_OS_MODE_CONFIRM = "confirm"        # stage a ticket; a human confirms before it acts
NOVA_OS_MODE_AUTO_PAPER = "auto_paper"  # auto-place paper bracket orders
NOVA_OS_MODE_AUTO_LIVE = "auto_live"    # auto-place live orders (env-gated, last resort)
NOVA_OS_MODES = (
    NOVA_OS_MODE_SIGNAL,
    NOVA_OS_MODE_CONFIRM,
    NOVA_OS_MODE_AUTO_PAPER,
    NOVA_OS_MODE_AUTO_LIVE,
)
NOVA_OS_DEFAULT_MODE = NOVA_OS_MODE_SIGNAL  # safest default; never persisted as anything else on restart

# P4/P5 — confirm + auto_paper controls (never persist mode across restart)
NOVA_OS_CONFIRM_TIMEOUT_SEC = 45           # staged ticket TTL; Gap and Go moves fast
NOVA_OS_MAX_CONCURRENT_POSITIONS = 2       # open executor positions + staged tickets combined
NOVA_OS_FLATTEN_CONFIRM_TOKEN = "FLATTEN"  # typed confirm for flatten_positions()
# NYSE full-day closures (ISO dates). Gate 0 + set_mode(auto_paper) refuse holidays.
NOVA_OS_NYSE_HOLIDAYS = frozenset({
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # Martin Luther King Jr. Day
    "2026-02-16",  # Presidents' Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-12-25",  # Christmas
})

# Action codes — what Nova OS actually did with a decision. The "no silent
# action" contract means every one of these is recorded as an event receipt.
NOVA_OS_ACTION_DISPLAYED = "displayed"          # showed a signal/ticket, took no broker action
NOVA_OS_ACTION_STAGED = "staged"                # queued a ticket awaiting human confirm
NOVA_OS_ACTION_CONFIRMED = "confirmed"          # human approved a staged ticket
NOVA_OS_ACTION_EXECUTED_PAPER = "executed_paper"  # placed a paper bracket
NOVA_OS_ACTION_EXECUTED_LIVE = "executed_live"    # placed a live bracket
NOVA_OS_ACTION_DECLINED = "declined"            # decided NO_BUY / WAIT, took no action
NOVA_OS_ACTION_HALTED = "halted"                # blocked by risk/loss policy
NOVA_OS_ACTIONS = (
    NOVA_OS_ACTION_DISPLAYED,
    NOVA_OS_ACTION_STAGED,
    NOVA_OS_ACTION_CONFIRMED,
    NOVA_OS_ACTION_EXECUTED_PAPER,
    NOVA_OS_ACTION_EXECUTED_LIVE,
    NOVA_OS_ACTION_DECLINED,
    NOVA_OS_ACTION_HALTED,
)

# Reason codes — stable identifiers for WHY a decision landed where it did.
# Grouped by the Decision-Brain gate that emits them.
NOVA_OS_REASON_CODES = (
    # Gate 0 — session / regime / risk state
    "SESSION_CLOSED",
    "SESSION_HOLIDAY",
    "RISK_HALTED",
    "LOSS_POLICY_DOWNGRADE",
    "LOSS_POLICY_HALT",
    # Gate 1 — Five Pillars
    "PILLAR_PRICE_FAIL",
    "PILLAR_CHANGE_FAIL",
    "PILLAR_RVOL_FAIL",
    "PILLAR_CATALYST_FAIL",
    "PILLAR_FLOAT_FAIL",
    "PILLARS_MISSING_DATA",
    "PILLARS_PASS",
    # Gate 2 — setup recognition (+ first-minute volume + watchlist rank)
    "NO_SETUP",
    "SETUP_MATCH",
    "FIRST_MINUTE_VOLUME_LOW",
    "FIRST_MINUTE_VOLUME_OK",
    "WATCHLIST_RANK_TOO_LOW",
    "WATCHLIST_RANK_OK",
    # Gate 3 — ticket math
    "TICKET_INVALID",
    "RR_TOO_LOW",
    "STOP_TOO_WIDE",
    "TICKET_OK",
    # Gate 4 — catalyst quality
    "CATALYST_WEAK",
    "CATALYST_STRONG",
    # Gate 5 — microstructure
    "L2_UNFAVORABLE",
    "L2_FAVORABLE",
    "MICROSTRUCTURE_NOT_EVALUATED",
    # Terminal
    "ALL_GATES_PASS",
)

# Temporary loss policy — decide() applies this via codes.loss_policy_mode().
# Graduated response to losing trades THIS SESSION (RiskState.losses_today —
# a daily count, NOT consecutive_losses; an intervening win does not reset it):
#   first loss  → downgrade control mode to `confirm` (require human per trade)
#   third loss  → halt for the day (mirrors RISK_MAX_CONSECUTIVE_LOSSES)
# These are intentionally separate from the risk-engine walk-away guardrails so
# the mode-downgrade step (which the risk engine has no concept of) is explicit.
NOVA_OS_LOSS_POLICY_DOWNGRADE_AFTER_LOSSES = 1  # first loss → force `confirm`
NOVA_OS_LOSS_POLICY_HALT_AFTER_LOSSES = 3       # third loss → halt (== RISK_MAX_CONSECUTIVE_LOSSES)
