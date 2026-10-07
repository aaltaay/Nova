"""Bot localhost API tunables (ADR 016 / epic #205).

Owner: backend/bot/. Re-exported from the constants barrel.
"""
from __future__ import annotations

# 4 (ADR 027): the pack fields (active_pack, pack_settings, llm) are gone; a v1-3
# file loads with them stripped.
# 5 (ADR 042): one owner for Nova's buys. The chosen setup is retired -- ``level`` is
# the master ceiling and every setup with a scanner keeps its own level (0..2); each
# venue's dial carries its sleeve (``caps``), its bot list (``symbol_allowlist``) and
# its day lock; ``setup``, ``strategy`` and the ``advise`` budget are gone. A v1-4 file
# migrates on load (``bot.persist``); an unknown version refuses loudly.
BOT_SCHEMA_VERSION = 5
BOT_SCHEMA_VERSIONS = (1, 2, 3, 4, 5)
BOT_RETIRED_SESSION_KEYS = ("active_pack", "pack_settings", "llm")
BOT_RETIRED_V5_KEYS = ("setup", "strategy", "advise")
BOT_SESSION_FILENAME = "bot-session.json"
BOT_PROPOSALS_FILENAME = "bot-proposals.json"
BOT_AUDIT_FILENAME = "bot-audit.jsonl"
BOT_STATE_OWNER = "bot.persist"

BOT_LEVEL_OFF = 0
BOT_LEVEL_EYES = 1
BOT_LEVEL_STRATEGY = 2
BOT_LEVEL_UNRESTRICTED = 3  # parked -- refuse

# -- The playbook (ADR 027): the operator's setups from their trading material.
# ADR 031: the bull flag joins, and it, the flat-top breakout and red to green get
# scanners. ADR 042: no setup is "chosen" -- each setup with a scanner has its own
# level, under the master ``level``. ADR 031 amendment 2026-10-06: the 5-minute flat top -- the flat top
# read on 5-minute candles, bought on the 1-minute candle that holds it -- is a strategy of its own.
BOT_SETUP_FIRST_PULLBACK = "first_pullback"
BOT_SETUP_BULL_FLAG = "bull_flag"
BOT_SETUP_GAP_AND_GO = "gap_and_go"
BOT_SETUP_FLAT_TOP = "flat_top_breakout"
BOT_SETUP_FLAT_TOP_5M = "flat_top_5m"
BOT_SETUP_RED_TO_GREEN = "red_to_green"
BOT_SETUP_MICRO_PULLBACK = "micro_pullback"
BOT_SETUPS = (
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUP_BULL_FLAG,
    BOT_SETUP_FLAT_TOP,
    BOT_SETUP_FLAT_TOP_5M,
    BOT_SETUP_RED_TO_GREEN,
    BOT_SETUP_GAP_AND_GO,
    BOT_SETUP_MICRO_PULLBACK,
)
# The setups whose scanners run, in the order the engine builds their lanes.
BOT_SCANNER_SETUPS = (
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUP_BULL_FLAG,
    BOT_SETUP_FLAT_TOP,
    BOT_SETUP_FLAT_TOP_5M,
    BOT_SETUP_RED_TO_GREEN,
    BOT_SETUP_GAP_AND_GO,
)
BOT_SETUPS_WITH_SCANNER = frozenset(BOT_SCANNER_SETUPS)
# The setup a schema 4 session called "chosen" when it named none (the v5 migration).
BOT_SETUP_DEFAULT = BOT_SETUP_FIRST_PULLBACK
# The material's trading window: entries (buy_* kinds) at Strategy only, the venue's
# clock (the replay playhead on Sim). Each setup's template in play sets its own.
BOT_ENTRY_WINDOW_START_ET = "07:00"
BOT_ENTRY_WINDOW_END_ET = "10:00"
# The sleeve's default daily cap: Nova's automatic entries (the bot and Auto-entry) per venue day.
BOT_ENTRIES_PER_DAY = 1
BOT_ENTRIES_PER_DAY_MIN = 1
BOT_ENTRIES_PER_DAY_MAX = 3
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

# The sleeve (ADR 042): one per venue, for every Nova automatic buy (the bot and Auto-entry).
BOT_DEFAULT_MAX_SHARES = 1
BOT_MAX_SHARES_MIN = 1
BOT_MAX_SHARES_CAP = 10
BOT_DEFAULT_BP_BUDGET_USD = 50.0
BOT_BP_BUDGET_MIN_USD = 0.01
BOT_BP_BUDGET_HARD_MAX_USD = 50.0
BOT_DEFAULT_WORKING_TTL_SEC = 3
BOT_WORKING_TTL_MIN_SEC = 1
BOT_WORKING_TTL_MAX_SEC = 10
# Risk per trade: a Nova automatic buy is sized by it (bounds mirror STOCK_MODE_RISK_*_USD).
BOT_DEFAULT_RISK_USD = 20.0
BOT_RISK_MIN_USD = 1.0
BOT_RISK_MAX_USD = 10_000.0
BOT_DEFAULT_EXIT_PCT = 50
BOT_EXIT_PCTS = (25, 50)
BOT_DEFAULT_ASK_OFFSET_USD = 0.05
BOT_DEFAULT_BID_EXIT_OFFSET_USD = 0.03

# Loss breakers on the whole account's day P&L (operator ask 2026-09-24): the
# operator's settings per venue (``bot.breaker_limits``), these the defaults.
BOT_SOFT_BREAKER_USD = -50.0            # the bot trip: flatten, the bot to L0
BOT_HARD_BREAKER_USD = -200.0           # the all-stop: flatten, bot and manual buys on its venue locked to 04:00 ET
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
# ADR 031 / 042: a level per setup with a scanner, 0 (Off) to 2 (Strategy), under the master.
BOT_REASON_SETUP_LEVEL = "BOT_SETUP_LEVEL"
# ADR 042: there is no chosen setup any more (``PATCH {setup}``).
BOT_REASON_SETUP_RETIRED = "BOT_SETUP_RETIRED"
BOT_SETUP_RETIRED_TEXT = "There is no chosen setup any more: set each setup's own level (ADR 042)"
# Activate's refusals (ADR 042 B): each says what to do in plain words.
BOT_REASON_LIVE_NOT_BUILT = "BOT_LIVE_NOT_BUILT"
BOT_REASON_REPLAY_DESK = "BOT_REPLAY_DESK"
BOT_REASON_VENUE_UNKNOWN = "BOT_VENUE_UNKNOWN"
BOT_REASON_LEVEL_NOT_STRATEGY = "BOT_LEVEL_NOT_STRATEGY"
BOT_REASON_NO_SETUP_AT_STRATEGY = "BOT_NO_SETUP_AT_STRATEGY"
BOT_REASON_PADLOCK_LOCKED = "BOT_PADLOCK_LOCKED"
BOT_REASON_TRIP_LATCHED = "BOT_TRIP_LATCHED"
BOT_LIVE_NOT_BUILT_TEXT = ("Nova's bot trades Paper and Sim only. Live trading by a bot is not built; "
                           "it waits on its own operator decision (ADR 042).")
# The bot list is full (``bot.eligibility``): a refusal, never a change that did not happen.
BOT_REASON_ALLOWLIST_FULL = "BOT_ALLOWLIST_FULL"
# A sleeve value outside its bounds is refused with them, never clamped in silence.
BOT_REASON_CAPS_INVALID = "BOT_CAPS_INVALID"
# Why Activate was cleared (``deactivated.reason``).
BOT_DEACTIVATED_REASONS = ("restart", "padlock", "venue", "level", "no_setup", "bot_trip", "all_stop", "operator")
# #564 (operator decision 2026-09-24): on Live the breakers' day P&L subtracts
# the session's commissions; while that read fails the day P&L is unknown and
# no new bot entry is sent. Exits, cancels, flatten and kill are never held.
BOT_REASON_COMMISSIONS_UNKNOWN = "BOT_COMMISSIONS_UNKNOWN"
# The breaker polls every second: a failing read is logged once, then at most this often.
BOT_COMMISSIONS_WARN_EVERY_SEC = 60.0

# -- ADR 030: Nova's own bot on Paper and Sim (backend/bot/first_pullback/). ADR 042: it
# plays every setup at Strategy; it never trades Live. The brain id is kept from ADR 030
# so a running session keeps its claim.
BOT_RUNNER_BRAIN_ID = "nova-first-pullback"
BOT_AUDIT_ACTION_TRADE = "bot_trade"
BOT_FP_POLL_SEC = 0.5               # CHOSEN: the bot's loop
BOT_FP_HEARTBEAT_SEC = 5.0          # CHOSEN: well inside BOT_HEARTBEAT_STALE_SEC
BOT_FP_TRIGGER_MAX_AGE_SEC = 5.0    # CHOSEN: an older trigger (a restart, a warm-up) is not traded
BOT_FP_TIME_STOP_MIN = 15           # CHOSEN: the scoreboard's window (SETUPS_SCORE_WINDOW_MIN)
BOT_FP_CLOSE_ATTEMPTS = 2           # limit-at-the-bid tries before the protective flatten
BOT_FP_CANCEL_WAIT_SEC = 5.0        # how long a cancel may stay unconfirmed before the bot says so
# A trigger the bot or Auto-entry did not take (``bot.first_pullback.admit``): the skip codes.
BOT_SKIP_NOT_ACTIVE = "BOT_NOT_ACTIVE"
BOT_SKIP_SETUP_NOT_STRATEGY = "BOT_SETUP_NOT_STRATEGY"
BOT_SKIP_NOT_FIRST = "BOT_NOT_FIRST_OF_DAY"
BOT_SKIP_TAPE = "BOT_TAPE_NOT_GO"
BOT_SKIP_NOT_A_TRADE = "BOT_NOT_A_TRADE"
BOT_SKIP_STALE = "BOT_TRIGGER_STALE"
BOT_SKIP_ONE_TRADE = "BOT_ONE_TRADE"
BOT_SKIP_EXTENDED_HOURS = "BOT_EXTENDED_HOURS"
BOT_SKIP_SIZE = "BOT_SIZE_ZERO"
BOT_SKIP_VENUE_CHANGING = "BOT_VENUE_CHANGING"   # the desk is leaving the venue (ADR 042 F)

# -- ADR 044: one Bots page. --------------------------------------------------------------
# Each strategy's bot rules, on its template in play (the template's bot group: changing them never
# starts a read-out over). Grades Nova buys -- C stays NOT A TRADE -- and setups a stock a day.
BOT_GRADES_AB = "AB"
BOT_GRADES_A = "A"
BOT_GRADES_CHOICES = ((BOT_GRADES_AB, "A and B"), (BOT_GRADES_A, "A only"))
BOT_GRADES_DEFAULT = BOT_GRADES_AB
BOT_SETUPS_A_DAY_DEFAULT = 1
BOT_SETUPS_A_DAY_MAX = 2
BOT_SKIP_GRADE = "BOT_SKIP_GRADE"            # a grade the strategy does not buy
# Today's 04:00 ET reset of yesterday's bot buys has not run, or failed (``hot_list.day_reset_block``). Until
# 2026-10-06 this slot was BOT_SKIP_NOT_LISTED (the bot bought only starred stocks); old audit lines keep that code.
BOT_SKIP_DAY_NOT_RESET = "BOT_SKIP_DAY_NOT_RESET"
# The Bot switch: ON is the master at Strategy and Activate in one step; OFF is the master at Eyes.
BOT_AUDIT_ACTION_SWITCH = "bot_switch"
# The squares, by ticker (``GET /api/bot/triggers``): the gates in the order Nova runs them.
BOT_TRIGGERS_SCHEMA_VERSION = 1
BOT_TRIGGER_GATES = (
    ("bot_on", "Bot on"),
    ("strategy_on", "Strategy on"),
    ("grade", "Grade"),
    ("setups_a_day", "Setups a day"),
    ("bot_window", "Bot window"),
    ("nova_buys", "Bot buys"),
    ("level2_line", "Level 2 line"),
    ("tape_go", "Tape GO"),
    ("trades_today", "Trades today"),
)
# Nothing records the template's bot rules at a trigger: these gates read today's.
BOT_TRIGGER_JUDGED_NOW = ("grade", "setups_a_day", "bot_window")
