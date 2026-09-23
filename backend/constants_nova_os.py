"""Nova OS, alerts, backtest. Domain constants (Phase 3)."""
from constants_archive_news import *  # noqa: F403

# read back by the UI. Treat them like an API contract — add new codes, never
# silently rename or repurpose an existing one, and bump NOVA_OS_POLICY_VERSION
# when the decision semantics behind them change.
NOVA_OS_POLICY_VERSION = "nova-os-p5-2026-07-15"  # bump when decision semantics change

NOVA_OS_EVENTS_DB_FILENAME = "nova_os_events.db"  # lives under paths.cache_dir(), not git-tracked
NOVA_OS_EVENTS_DEFAULT_LIMIT = 200                # default rows returned by the read API

# The decide() verdict, its tunables and the control-mode ladder were retired
# (ADR 025). The vocabulary below stays: historical receipts in the event log
# carry these codes and nova_os.codes validates new receipts against them.
NOVA_OS_CITATIONS = (
    "Gap and Go — Five Pillars gate",
    "Gap and Go — first-minute volume ≥100k",
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

# ── Centralized execution path (ADR 007) ────────────────────────────────────
# Single receive→validate→persist→send→ack→fill pipeline. Paper and live share
# this path; only Gateway credentials/port and safety gates differ.
EXECUTION_LEDGER_DB_FILENAME = "execution_ledger.db"
EXECUTION_ACK_SLA_P95_MS = 250.0  # receive → first real broker ack (excludes fill)
EXECUTION_ACK_WAIT_SEC = 5.0      # max wait for first non-PendingSubmit status
# After a Cancelled-without-fill ack, wait this long for PreSubmitted/Submitted
# before writing ledger failed (Error 10349 false-cancel race).
EXECUTION_CANCEL_ACK_GRACE_SEC = 0.75
# After cancel_order, re-read open_orders until absent or this timeout.
EXECUTION_CANCEL_VERIFY_TIMEOUT_SEC = 5.0
EXECUTION_CANCEL_VERIFY_POLL_SEC = 0.25
# Headroom on the IB-loop hop so on_ib does not time out before the verify does.
EXECUTION_CANCEL_VERIFY_HOP_MARGIN_SEC = 2.0
EXECUTION_FILL_WAIT_SEC = 30.0    # optional wait for complete fill (benchmark only)
EXECUTION_FILL_EVIDENCE_LIMIT = 64  # bounded callback/poll observations per execution
EXECUTION_METRICS_QUERY_LIMIT = 500
EXECUTION_ACTIVITY_DEFAULT_LIMIT = 100
# Startup sweep: ledger rows a previous process left mid-flight, oldest first.
EXECUTION_SWEEP_ROW_LIMIT = 200
EXECUTION_NON_TERMINAL_STATUSES = ("reserved", "validated", "sent", "acked")
EXECUTION_METRICS_MIN_PERCENTILE_SAMPLES = 20
IBKR_VERIFICATION_REQUIRED_REASON = "IBKR_VERIFICATION_REQUIRED"
IBKR_VERIFICATION_REQUIRED_MARKERS = (
    "LOGIN TO CLIENT PORTAL",
    "VERIFY USING THE TOKEN",
)
EXECUTION_SOURCES = (
    "manual",
    "kill",
    "cancel_working",
    "flatten",
    "benchmark",
    "bot",
)
EXECUTION_OPS = ("place", "bracket", "cancel", "replace")
# ── NYSE exchange calendar ───────────────────────────────────────────────────
# Full-day closures (ISO dates). The market clock, the Sim session clock,
# historical replay and the leaderboard recorder all read this one table, so it must answer for
# every year those consumers can be asked about — not only the current one.
#
# Policy (#386): the table is DERIVED BY RULE across a declared, closed year
# range, and callers refuse loudly outside it (sim.trading_day raises
# UnsupportedCalendarYear). Both halves are load-bearing — covering a range
# alone is silently wrong past its edge, and refusing alone is silently wrong
# inside it. We deliberately do NOT project indefinitely: a future NYSE rule
# change would reintroduce exactly the silent wrong answer this replaces. To
# extend, bump NOVA_OS_CALENDAR_LAST_YEAR after checking the published NYSE
# calendar for the added years.
#
# The derivation reproduces the previously hand-typed 2026 set exactly (all ten
# dates, zero diff), which is both its validation and a regression guard that
# production-year behaviour is unchanged. tests/test_sim_trading_day.py pins
# every derived date against a hand-entered table taken from the published NYSE
# calendars, so the rules are checked against something other than themselves.
#
# NOT modelled: early-close (13:00 ET) half-days. This table is full-day
# closures only; see sim/trading_day.py for what that costs a replayed session.
from types import MappingProxyType as _MappingProxyType

# The supported (vouchable) range. Callers refuse dates outside it.
NOVA_OS_CALENDAR_FIRST_YEAR = 2015
NOVA_OS_CALENDAR_LAST_YEAR = 2035
# The table itself carries one extra year BELOW the supported range. It is not
# a supported year — is_trading_day still refuses it — it exists so that the
# backward walk in sim.trading_day.last_trading_day can step off 2015-01-01
# onto a day the table still knows about instead of falling off its edge and
# having to guess (#386 finding 8: an in-range input must never raise).
NOVA_OS_CALENDAR_TABLE_FIRST_YEAR = NOVA_OS_CALENDAR_FIRST_YEAR - 1
NOVA_OS_NYSE_JUNETEENTH_FIRST_YEAR = 2022  # federal in 2021; the NYSE first closed in 2022
# One-off full-day closures no rule can derive (national days of mourning).
NOVA_OS_NYSE_AD_HOC_CLOSURES = frozenset({
    "2018-12-05",  # George H. W. Bush
    "2025-01-09",  # Jimmy Carter
})


# Helpers are underscore-prefixed and import datetime names inside their bodies
# so `from constants_nova_os import *` (constants.py) cannot leak them.
def _easter(year):
    """Gregorian Easter Sunday (Anonymous Gregorian computus)."""
    from datetime import date
    golden = year % 19
    century, year_in_century = divmod(year, 100)
    leap_centuries, century_rem = divmod(century, 4)
    correction = (century + 8) // 25
    lunar_shift = (century - correction + 1) // 3
    epact = (19 * golden + century - leap_centuries - lunar_shift + 15) % 30
    leap_years, weekday_rem = divmod(year_in_century, 4)
    weekday = (32 + 2 * century_rem + 2 * leap_years - epact - weekday_rem) % 7
    adjust = (golden + 11 * epact + 22 * weekday) // 451
    month, day = divmod(epact + weekday - 7 * adjust + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year, month, weekday, n):
    """The ``n``-th ``weekday`` (Mon=0) of ``month``."""
    from datetime import date, timedelta
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year, month, weekday):
    """The final ``weekday`` (Mon=0) of ``month``."""
    from datetime import date, timedelta
    following = date(year + month // 12, month % 12 + 1, 1)
    last = following - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day):
    """NYSE observance shift: Saturday -> Friday, Sunday -> Monday."""
    from datetime import timedelta
    return day + timedelta(days={5: -1, 6: 1}.get(day.weekday(), 0))


def _nyse_holidays(year):
    """``{date: name}`` of NYSE full-day closures in ``year``."""
    from datetime import date, timedelta
    days = {}
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:  # A Saturday Jan 1 is not observed; the NYSE trades Dec 31
        days[_observed(new_year)] = "New Year's Day"
    days[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    days[_nth_weekday(year, 2, 0, 3)] = "Presidents' Day"
    days[_easter(year) - timedelta(days=2)] = "Good Friday"
    days[_last_weekday(year, 5, 0)] = "Memorial Day"
    if year >= NOVA_OS_NYSE_JUNETEENTH_FIRST_YEAR:
        days[_observed(date(year, 6, 19))] = "Juneteenth"
    days[_observed(date(year, 7, 4))] = "Independence Day"
    days[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    days[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving Day"
    days[_observed(date(year, 12, 25))] = "Christmas Day"
    for iso in NOVA_OS_NYSE_AD_HOC_CLOSURES:
        closure = date.fromisoformat(iso)
        if closure.year == year:
            days[closure] = "National day of mourning"
    return days


# ISO date -> holiday name, for auditable and loud diagnostics.
NOVA_OS_NYSE_HOLIDAY_NAMES = _MappingProxyType({
    day.isoformat(): name
    for year in range(NOVA_OS_CALENDAR_TABLE_FIRST_YEAR, NOVA_OS_CALENDAR_LAST_YEAR + 1)
    for day, name in sorted(_nyse_holidays(year).items())
})
# Same name and same frozenset-of-ISO-strings contract as the 2026-only literal
# it replaces, so its readers became year-correct with no edit of their own.
NOVA_OS_NYSE_HOLIDAYS = frozenset(NOVA_OS_NYSE_HOLIDAY_NAMES)

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

# ── Local API auth (SEC-002 / SEC-004 / D-040) ────────────────────────────────
# Mutating /api/* routes require this header when NOVA_API_KEY is set, or when
# the bind host is not loopback (see backend/auth.py).
# POST /api/config always requires a configured key, including loopback -- any
# local process can otherwise rewrite Alpaca keys into .env.
NOVA_API_KEY_HEADER = "X-Nova-Api-Key"
NOVA_API_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
NOVA_CONFIG_MUTATE_PATH = "/api/config"

# ── Kill switch latch (D-037) ───────────────────────────────────────────────────
# Persisted so an API restart cannot silently re-arm spending. Owner +
# invalidation trigger are documented in kill_switch/state.py.
KILL_SWITCH_STATE_FILENAME = "kill_switch_state.json"
KILL_SWITCH_STATE_SCHEMA_VERSION = 1

# ── Outbound alerts (Phase D) ───────────────────────────────────────────────────
ALERTS_CHANNELS_FILENAME = "alerts_channels.json"
# Optional comma-separated host allowlist for outbound webhooks (SEC-008).
# Empty = any public https host (private/link-local/metadata still blocked).
ALERTS_WEBHOOK_HOST_ALLOWLIST_DEFAULT: tuple[str, ...] = ()
ALERTS_WEBHOOK_ALLOWED_SCHEMES = ("https",)
ALERTS_HTTP_TIMEOUT_SEC = 10.0
ALERTS_MAX_CHANNELS = 20
ALERTS_STATUS_RING_SIZE = 50
ALERTS_DISCORD_USERNAME = "Nova"
ALERTS_SECRET_MASK_VISIBLE_CHARS = 4
ALERTS_CHANNEL_TYPE_DISCORD = "discord"
ALERTS_CHANNEL_TYPE_TELEGRAM = "telegram"
ALERTS_CHANNEL_TYPE_WEBHOOK = "webhook"
ALERTS_CHANNEL_TYPES = (
    ALERTS_CHANNEL_TYPE_DISCORD,
    ALERTS_CHANNEL_TYPE_TELEGRAM,
    ALERTS_CHANNEL_TYPE_WEBHOOK,
)
ALERTS_EVENT_TYPE_HOD_MOMO = "hod_momo"
ALERTS_EVENT_TYPE_NOVA_OS = "nova_os"
ALERTS_EVENT_TYPE_TEST = "test"
ALERTS_EVENT_TYPE_SYSTEM = "system"
# Nova OS receipts worth outbound notify (kind/action filter in hooks.py).
ALERTS_NOVA_OS_NOTIFY_KINDS = ("action",)
ALERTS_NOVA_OS_NOTIFY_ACTIONS = (
    NOVA_OS_ACTION_STAGED,
    NOVA_OS_ACTION_CONFIRMED,
    NOVA_OS_ACTION_EXECUTED_PAPER,
    NOVA_OS_ACTION_EXECUTED_LIVE,
    NOVA_OS_ACTION_HALTED,
)

# ── Backtest (Phase E) — Nova-native scorer on archived 1m bars ───────────────
BACKTEST_MAX_SYMBOLS = 50
BACKTEST_MAX_TRADES_PER_DAY = 10
BACKTEST_DEFAULT_RISK_DOLLARS = 20.0          # 1R sizing anchor for qty + pnl_r
BACKTEST_MIN_QTY = 1
BACKTEST_SETUP_NAMES = ("gap_and_go", "bull_flag", "abcd", "all")
BACKTEST_DEFAULT_SETUP = "all"
# Synthesized candidate fields when archive has bars only (no scanner row).
BACKTEST_CANDIDATE_REL_VOLUME = 5.0
BACKTEST_CANDIDATE_HAS_NEWS = True
BACKTEST_CANDIDATE_FLOAT = 5_000_000
BACKTEST_MARKET_CLOSE_HOUR_ET = 16
BACKTEST_MARKET_CLOSE_MINUTE_ET = 0
BACKTEST_JOB_TTL_SEC = 3600
