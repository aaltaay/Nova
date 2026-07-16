"""IBKR live, discovery, setups, risk, L2. Domain constants (Phase 3)."""
from constants_scanner import *  # noqa: F403
from constants_scanner import SCANNER_MIN_PRICE

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
# Legacy / cold-path snapshot tunables (NOT the active-table freshness SLA).
# IB completes snapshots on tickSnapshotEnd ~11s later — never use a 4s timeout
# for live table freshness. Active tab + HOD use reqMktData L1 streams instead.
IBKR_TABLE_REPRICE_MAX_SYMBOLS = 100
IBKR_TABLE_REPRICE_CHUNK_SIZE = 20
IBKR_QUOTE_BATCH_TIMEOUT_SEC = 15.0             # cold/discovery reqTickersAsync (≥12s)
IBKR_TABLE_REPRICE_CHUNK_TIMEOUT_SEC = 12.0     # honest snapshot budget (was 4s — impossible)
IBKR_DISCOVERY_BRIDGE_TIMEOUT_SEC = 25.0        # thread->asyncio bridge wait ceiling
IBKR_REPRICE_INTERVAL_SEC = 3.0                 # detail-panel cold backstop cadence
# Detail-panel backstop: skip the reqTickersAsync snapshot for a symbol whose
# reqMktData streaming subscription (ibkr/ticks.py) has updated within this
# window — it's already delivering live ticks.
IBKR_DETAIL_STREAM_FRESH_SEC = 8.0
# Kept for UI/docs mirrors; table freshness is now L1-stream driven.
IBKR_TABLE_REPRICE_INTERVAL_SEC = 1.0
# UI / heartbeat: if no successful table price_patch within this window, mark stale.
SCANNER_PRICE_STALE_SEC = 5.0

# ── Active-tab + reserved HOD Level-1 streaming (reqMktData) ──────────────────
# Budget ≈ active tab (≤50) + HOD active set (40) + open ticker reserve, with
# overlap dedupe. Do not stream the whole discovery universe.
IBKR_L1_STREAM_BUDGET = 100                     # hard cap concurrent L1 lines
IBKR_L1_STREAM_RESERVE = 5                      # headroom for open ticker / depth peers
IBKR_L1_ACTIVE_TAB_MAX = 50                     # IBKR scanner row cap per tab
IBKR_L1_BATCH_FLUSH_SEC = 0.35                  # coalesce ticks → /ws/scanner patches
IBKR_L1_RECONCILE_SEC = 1.0                     # desired-set reconcile cadence
IBKR_L1_SUBSCRIBE_PACE_SEC = 0.05               # pace subscribe churn (Gateway)
IBKR_L1_TAB_SWITCH_GRACE_SEC = 0.75             # keep prior tab streams briefly on switch
# Per-row honesty: tint when last IB tick older than this (liquid symbols).
IBKR_L1_ROW_STALE_SEC = 3.0

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
# Reports v2 (Phase F) — tag analytics, R-multiples, drawdown
JOURNAL_TAGS_DEFAULT_JSON = "[]"
JOURNAL_TAGS_MAX_PER_TRADE = 20
JOURNAL_IBKR_IMPORT_MAX_ROWS = 500

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
