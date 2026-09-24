"""Scanner leaderboard tunables: the per-minute board, its gaps, halts and auto-record.

Owner: backend/leaderboard/ (ADR 023). The store keeps one row per symbol per
minute for the boards the desk showed ("recorded") and for boards rebuilt from
minute flat files ("reconstructed"). Nothing here places an order.
"""
from __future__ import annotations

# ── Store ───────────────────────────────────────────────────────────────────
LEADERBOARD_DIR_ENV = "NOVA_LEADERBOARD_DIR"
# Durable archive on the operator's F: drive; beside, never inside, the capture
# root (F:\Nova\sim_capture) and the historical downloads (F:\Nova\sim\_capture\historical).
LEADERBOARD_DEFAULT_ROOT_WIN = r"F:\Nova\leaderboard"
LEADERBOARD_DB_FILENAME = "leaderboard.sqlite3"
# 2 (#498): adds catalyst_checks / catalyst_items; a version-1 store migrates in place (new tables only).
# 3 (#532): rows add float_contradicted / shares_outstanding, so playback judges LEADERS_RULES' float as
# auto-record did; a version-1 or -2 store migrates in place (two nullable columns, no row rewritten).
LEADERBOARD_SCHEMA_VERSION = 3
LEADERBOARD_SQLITE_TIMEOUT_SEC = 10.0
# Retention (operator decision on #485, 2026-09-24): keep everything -- nothing
# deletes leaderboard rows automatically. Recorded days cannot be replaced, a
# rebuild takes ~53 s a day, and SQLite gives no space back without a VACUUM
# of the whole file. The store grows about 6-9 GB a year; the diagnostics row
# ``leaderboard_recorder`` guards the drive instead. GB as Windows Explorer
# counts them (GiB).
LEADERBOARD_FREE_WARN_BYTES = 50 * 1024**3
LEADERBOARD_FREE_FAIL_BYTES = 10 * 1024**3
LEADERBOARD_GROWTH_PER_YEAR = "about 6-9 GB a year"

# ── Row vocabulary ──────────────────────────────────────────────────────────
LEADERBOARD_SOURCE_RECORDED = "recorded"
LEADERBOARD_SOURCE_RECONSTRUCTED = "reconstructed"
LEADERBOARD_SOURCES = (LEADERBOARD_SOURCE_RECORDED, LEADERBOARD_SOURCE_RECONSTRUCTED)

# Recorded boards are the desk's lists; a reconstructed day has one whole-market board.
LEADERBOARD_BOARD_GAPPERS = "gappers"
LEADERBOARD_BOARD_GAINERS = "gainers"
LEADERBOARD_BOARD_LOSERS = "losers"
LEADERBOARD_BOARD_AFTERHOURS = "afterhours"
LEADERBOARD_BOARD_LARGE_CAP = "large_cap"
LEADERBOARD_BOARD_MARKET = "market"
LEADERBOARD_RECORDED_BOARDS = (
    LEADERBOARD_BOARD_GAPPERS,
    LEADERBOARD_BOARD_GAINERS,
    LEADERBOARD_BOARD_LOSERS,
    LEADERBOARD_BOARD_AFTERHOURS,
    LEADERBOARD_BOARD_LARGE_CAP,
)
LEADERBOARD_BOARDS = LEADERBOARD_RECORDED_BOARDS + (LEADERBOARD_BOARD_MARKET,)

# Per-minute coverage state of one board. A minute with no coverage row was not recorded.
LEADERBOARD_STATE_LIVE = "live"
LEADERBOARD_STATE_FROZEN = "frozen"
LEADERBOARD_STATE_UNAVAILABLE = "unavailable"
LEADERBOARD_STATE_FEED_DOWN = "feed_down"
LEADERBOARD_STATE_REBUILT = "rebuilt"
LEADERBOARD_STATES = (
    LEADERBOARD_STATE_LIVE,
    LEADERBOARD_STATE_FROZEN,
    LEADERBOARD_STATE_UNAVAILABLE,
    LEADERBOARD_STATE_FEED_DOWN,
    LEADERBOARD_STATE_REBUILT,
)

# What a row's rvol divides by. Never compared across bases.
LEADERBOARD_RVOL_BASIS_DAILY = "daily_avg"      # today's volume / average daily volume (the desk's RVOL)
LEADERBOARD_RVOL_BASIS_TOD = "time_of_day_20"   # volume so far / same-minute average of the prior 20 sessions
LEADERBOARD_RVOL_BASES = (LEADERBOARD_RVOL_BASIS_DAILY, LEADERBOARD_RVOL_BASIS_TOD)

# Why a stretch has no board (the gap policy).
LEADERBOARD_GAP_NOT_RUNNING = "not_running"       # no recorder run covered it (server down / restarting)
LEADERBOARD_GAP_FEED_DOWN = "feed_down"           # recorder up, IBKR feed not live
LEADERBOARD_GAP_NOT_RECORDED = "not_recorded"     # the day has no recorder run at all
LEADERBOARD_GAP_OUTSIDE_SESSION = "outside_session"

# ── Live recorder ───────────────────────────────────────────────────────────
# One snapshot per board per minute, 04:00-20:00 ET on exchange days.
LEADERBOARD_RECORD_START_MIN_ET = 4 * 60
LEADERBOARD_RECORD_END_MIN_ET = 20 * 60
LEADERBOARD_RECORD_INTERVAL_SEC = 60
# Seconds after the minute boundary before the snapshot is taken (lets that
# second's roster push land; the snapshot is still stamped at the boundary).
LEADERBOARD_RECORD_SETTLE_SEC = 1.0
LEADERBOARD_ROWS_PER_BOARD_MAX = 100
LEADERBOARD_QUEUE_MAX = 20_000
LEADERBOARD_WRITE_FLUSH_SEC = 2.0
LEADERBOARD_WRITE_BATCH_MAX = 5_000
# A run whose last heartbeat is older than this and has no stop stamp ended unexpectedly.
LEADERBOARD_RUN_STALE_SEC = 180.0
LEADERBOARD_RUN_STOP_SHUTDOWN = "shutdown"

# ── Halt / LULD log ─────────────────────────────────────────────────────────
LEADERBOARD_HALT_EVENT_START = "start"
LEADERBOARD_HALT_EVENT_END = "end"
LEADERBOARD_HALT_SOURCE_IBKR = "ibkr_ticker_halted"
LEADERBOARD_HALT_SOURCE_NASDAQ = "nasdaq_trade_halt_rss"

# ── Ranking presets (leaderboard/ranking.py) ────────────────────────────────
# The leaders playback shows and auto-record records: the first pullback's
# universe (Bot-Trading-Plan.md section 2f) -- the leading % gainer, $3-10,
# float under 10M (an unknown float is admitted: recording a name that turns
# out larger costs a line, missing the leader costs the day), with enough
# shares traded to be tradeable.
LEADERBOARD_LEADERS_MIN_PRICE = 3.0
LEADERBOARD_LEADERS_MAX_PRICE = 10.0
LEADERBOARD_LEADERS_MAX_FLOAT = 10_000_000
LEADERBOARD_LEADERS_MIN_VOLUME = 100_000
LEADERBOARD_LEADERS_TOP_N = 3
# S5 (offline rolling universe): top-3 % gainer with >= 5x time-of-day RVOL.
LEADERBOARD_S5_MIN_RVOL = 5.0
LEADERBOARD_S5_TOP_N = 3

# ── Auto-record (07:00-10:00 ET) ────────────────────────────────────────────
LEADERBOARD_AUTO_RECORD_START_MIN_ET = 7 * 60
LEADERBOARD_AUTO_RECORD_END_MIN_ET = 10 * 60
LEADERBOARD_AUTO_RECORD_TOP_N = LEADERBOARD_LEADERS_TOP_N
LEADERBOARD_AUTO_RECORD_BOARD = LEADERBOARD_BOARD_GAINERS
# A leader must hold its place this long before auto-record rotates to it, so a
# name flickering in and out of the top 3 does not churn the Level 2 lines.
LEADERBOARD_AUTO_RECORD_MIN_HOLD_SEC = 120.0
LEADERBOARD_AUTO_RECORD_TICK_SEC = 15.0

# ── Playback API ────────────────────────────────────────────────────────────
# Every day on file: five years of rebuilt sessions plus recorded ones (~330 ms at 1,255 days).
LEADERBOARD_DAYS_LIMIT = 2_500
