"""Bot localhost API tunables (ADR 016 / epic #205).

Owner: backend/bot/. Re-exported from the constants barrel.
"""
from __future__ import annotations

# 4 (ADR 027): the pack fields (active_pack, pack_settings, llm) are gone; a v1-3
# file loads with them stripped.
BOT_SCHEMA_VERSION = 4
BOT_SCHEMA_VERSIONS = (1, 2, 3, 4)
BOT_RETIRED_SESSION_KEYS = ("active_pack", "pack_settings", "llm")
BOT_SESSION_FILENAME = "bot-session.json"
BOT_PROPOSALS_FILENAME = "bot-proposals.json"
BOT_AUDIT_FILENAME = "bot-audit.jsonl"
BOT_STATE_OWNER = "bot.persist"

BOT_LEVEL_OFF = 0
BOT_LEVEL_EYES = 1
BOT_LEVEL_STRATEGY = 2
BOT_LEVEL_UNRESTRICTED = 3  # parked -- refuse

BOT_STRATEGY_SMALL_CAP = "small-cap"
BOT_STRATEGIES = (BOT_STRATEGY_SMALL_CAP,)

# -- The playbook (ADR 027): the operator's setups from their trading material.
# One plays at a time; only a setup with a live scanner can be chosen. ADR 031:
# the bull flag joins, and it, the flat-top breakout and red to green get scanners.
BOT_SETUP_FIRST_PULLBACK = "first_pullback"
BOT_SETUP_BULL_FLAG = "bull_flag"
BOT_SETUP_GAP_AND_GO = "gap_and_go"
BOT_SETUP_FLAT_TOP = "flat_top_breakout"
BOT_SETUP_RED_TO_GREEN = "red_to_green"
BOT_SETUP_MICRO_PULLBACK = "micro_pullback"
BOT_SETUPS = (
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUP_BULL_FLAG,
    BOT_SETUP_FLAT_TOP,
    BOT_SETUP_RED_TO_GREEN,
    BOT_SETUP_GAP_AND_GO,
    BOT_SETUP_MICRO_PULLBACK,
)
# The setups whose scanners run, in the order the engine builds their lanes.
BOT_SCANNER_SETUPS = (
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUP_BULL_FLAG,
    BOT_SETUP_FLAT_TOP,
    BOT_SETUP_RED_TO_GREEN,
)
BOT_SETUPS_WITH_SCANNER = frozenset(BOT_SCANNER_SETUPS)
BOT_SETUP_DEFAULT = BOT_SETUP_FIRST_PULLBACK
# The material's trading window and one trade a day: entries (buy_* kinds) at
# Strategy only. Venue clock (the replay playhead on Sim).
BOT_ENTRY_WINDOW_START_ET = "07:00"
BOT_ENTRY_WINDOW_END_ET = "10:00"
BOT_ENTRIES_PER_DAY = 1
BOT_SYMBOL_ALLOWLIST_CAP = 50
# Default brain id for the SDK client (bot/client.py); any brain may send its own.
BOT_BRAIN_SESSION_ID = "nova-brain"

BOT_ACTION_KINDS = (
    "buy_market",
    "buy_limit_ask_offset",
    "sell_limit_bid_offset",
    "sell_limit_ask_offset",
    "exit_pos",
    "cancel_symbol",
    "exit_pos_pct",
    "sell_pos_pct_ask",
    "sell_pos_pct_bid_offset",
)

BOT_LATER_KINDS = (
    "cancel_and_exit",
    "cancel_all_orders",
)

# ADR 030: Nova's own first-pullback bot enters with a limit at the entry the
# scanner scored. A buy kind (the day's cap counts it), never on a brain's
# allowlist: it carries the scanner's price, not a session preset.
BOT_KIND_SETUP_ENTRY = "buy_setup_limit"

BOT_BUY_KINDS = frozenset({
    "buy_market",
    "buy_limit_ask_offset",
    BOT_KIND_SETUP_ENTRY,
})

BOT_DEFAULT_MAX_SHARES = 1
BOT_MAX_SHARES_CAP = 10
BOT_DEFAULT_BP_BUDGET_USD = 50.0
BOT_BP_BUDGET_HARD_MAX_USD = 50.0
BOT_DEFAULT_WORKING_TTL_SEC = 3
BOT_WORKING_TTL_MIN_SEC = 1
BOT_WORKING_TTL_MAX_SEC = 10
BOT_DEFAULT_EXIT_PCT = 50
BOT_EXIT_PCTS = (25, 50)
BOT_DEFAULT_ASK_OFFSET_USD = 0.05
BOT_DEFAULT_BID_EXIT_OFFSET_USD = 0.03

BOT_ADVISE_DEFAULT_USD_CAP = 2.0
BOT_ADVISE_DEFAULT_CALL_CAP = 10

# Loss breakers on the whole account's day P&L (operator ask 2026-09-24): the
# operator's settings per venue (``bot.breaker_limits``), these the defaults.
BOT_SOFT_BREAKER_USD = -50.0            # the bot trip: flatten, the bot to L0
BOT_HARD_BREAKER_USD = -200.0           # the all-stop: flatten, bot and manual buys locked to ET midnight
BOT_SOFT_BREAKER_LOOSEST_USD = -1000.0
BOT_SOFT_BREAKER_TIGHTEST_USD = -5.0
BOT_HARD_BREAKER_LOOSEST_USD = -5000.0
BOT_HARD_BREAKER_TIGHTEST_USD = -10.0
BOT_BREAKER_STEP_USD = 5.0
BOT_BREAKER_VENUES = ("live", "paper", "sim")
BOT_REASON_BREAKER_INVALID = "BOT_BREAKER_INVALID"
BOT_FLATTEN_RETRIES = 1
BOT_BREAKER_POLL_SEC = 1.0
BOT_TTL_POLL_SEC = 0.5
BOT_EYES_PUSH_SEC = 0.25

BOT_TZ = "America/New_York"
BOT_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost", "testclient")
BOT_HEARTBEAT_STALE_SEC = 15
BOT_DESK_ARM_HEADER = "X-Nova-Desk-Arm"

BOT_REASON_L0_DARK = "BOT_L0_DARK"
BOT_REASON_L1_NO_FIRE = "BOT_L1_NO_FIRE"
BOT_REASON_NOT_ACTIVE = "BOT_NOT_ACTIVE"
BOT_REASON_L3_PARKED = "BOT_L3_PARKED"
BOT_REASON_ARM_REQUIRED = "BOT_ARM_REQUIRED"
BOT_REASON_ARM_DESK_ONLY = "BOT_ARM_DESK_ONLY"
BOT_REASON_HEARTBEAT_STALE = "BOT_HEARTBEAT_STALE"
BOT_REASON_KIND_BLOCKED = "BOT_KIND_BLOCKED"
BOT_REASON_FREE_FORM_QTY = "BOT_FREE_FORM_QTY"
BOT_REASON_SHARES_CAP = "BOT_SHARES_CAP"
BOT_REASON_BP_BUDGET = "BOT_BP_BUDGET"
BOT_REASON_WORKING_BLOCK = "BOT_WORKING_BLOCK"
BOT_REASON_DAY_LOCK = "BOT_DAY_LOCK"
BOT_REASON_BRAIN_EXCLUSIVE = "BOT_BRAIN_EXCLUSIVE"
BOT_REASON_ADVISE_OFF = "BOT_ADVISE_OFF"
BOT_REASON_ADVISE_CAP = "BOT_ADVISE_CAP"
BOT_REASON_NEEDS_DEPTH = "BOT_NEEDS_DEPTH"
# ADR 020 second pass (2026-09-21): a bot fires only on an allowlisted symbol
# whose depth line the backend itself holds -- an open Trader Level 2 or a
# Session Record line (ibkr.depth.state.is_subscribed / is_live). The backend
# cannot see UI tabs, so the held line is the server-side fact. No line budget.
BOT_REASON_NO_DEPTH_LINE = "BOT_NO_DEPTH_LINE"
BOT_NO_DEPTH_LINE_HINT = "open its Level 2 or record it"
# Sim time travel (ADR 020 decision 3): the audit action a bot receives when
# the scratch account unwound behind the playhead.
BOT_AUDIT_ACTION_PRACTICE_REWIND = "practice_rewind"
BOT_REASON_NOT_LOOPBACK = "BOT_NOT_LOOPBACK"
BOT_REASON_TTL_EXPIRED = "working_ttl_expired"
BOT_REASON_SYMBOL_BLOCKED = "BOT_SYMBOL_BLOCKED"
BOT_REASON_TRADING_LOCKED = "BOT_TRADING_LOCKED"
# ADR 027: Strategy waits on the setup's pre-registered read-out; entries keep
# the material's window and one trade a day.
BOT_REASON_READOUT_NOT_PASSED = "BOT_READOUT_NOT_PASSED"
BOT_REASON_OUTSIDE_WINDOW = "BOT_OUTSIDE_WINDOW"
BOT_REASON_DAY_TRADE_CAP = "BOT_DAY_TRADE_CAP"
BOT_REASON_SETUP_NO_SCANNER = "BOT_SETUP_NO_SCANNER"
# ADR 031: a level per setup -- only a setup with a scanner other than the chosen one
# takes one through ``setup_levels`` (Off or Eyes); the chosen setup's is ``level``.
BOT_REASON_SETUP_LEVEL = "BOT_SETUP_LEVEL"
# #564 (operator decision 2026-09-24): on Live the breakers' day P&L subtracts
# the session's commissions; while that read fails the day P&L is unknown and
# no new bot entry is sent. Exits, cancels, flatten and kill are never held.
BOT_REASON_COMMISSIONS_UNKNOWN = "BOT_COMMISSIONS_UNKNOWN"
# The breaker polls every second: a failing read is logged once, then at most this often.
BOT_COMMISSIONS_WARN_EVERY_SEC = 60.0

# -- ADR 030: the first-pullback bot on Paper and Sim (backend/bot/first_pullback/).
# The read-out gates Live only; Nova's own bot places on the practice venues only.
BOT_RUNNER_BRAIN_ID = "nova-first-pullback"
BOT_AUDIT_ACTION_TRADE = "bot_trade"
BOT_FP_POLL_SEC = 0.5               # CHOSEN: the bot's loop
BOT_FP_HEARTBEAT_SEC = 5.0          # CHOSEN: well inside BOT_HEARTBEAT_STALE_SEC
BOT_FP_TRIGGER_MAX_AGE_SEC = 5.0    # CHOSEN: an older trigger (a restart, a warm-up) is not traded
BOT_FP_TIME_STOP_MIN = 15           # CHOSEN: the scoreboard's window (SETUPS_SCORE_WINDOW_MIN)
BOT_FP_CLOSE_ATTEMPTS = 2           # limit-at-the-bid tries before the protective flatten
BOT_FP_CANCEL_WAIT_SEC = 5.0        # how long a cancel may stay unconfirmed before the bot says so
BOT_REASON_LIVE_NOT_PLAYED = "BOT_LIVE_NOT_PLAYED"
