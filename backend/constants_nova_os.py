"""Nova OS, alerts, backtest. Domain constants (Phase 3)."""
from constants_archive_news import *  # noqa: F403

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

# ── Centralized execution path (ADR 007) ────────────────────────────────────
# Single receive→validate→persist→send→ack→fill pipeline. Paper and live share
# this path; only Gateway credentials/port and safety gates differ.
EXECUTION_LEDGER_DB_FILENAME = "execution_ledger.db"
EXECUTION_ACK_SLA_P95_MS = 250.0  # receive → first real broker ack (excludes fill)
EXECUTION_ACK_WAIT_SEC = 5.0      # max wait for first non-PendingSubmit status
EXECUTION_FILL_WAIT_SEC = 30.0    # optional wait for complete fill (benchmark only)
EXECUTION_FILL_EVIDENCE_LIMIT = 64  # bounded callback/poll observations per execution
EXECUTION_METRICS_QUERY_LIMIT = 500
EXECUTION_METRICS_MIN_PERCENTILE_SAMPLES = 20
EXECUTION_SOURCES = (
    "manual",
    "approve",
    "auto_paper",
    "kill",
    "cancel_working",
    "flatten",
    "benchmark",
)
EXECUTION_OPS = ("place", "bracket", "cancel", "replace")
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

# ── Local API auth (SEC-002 / SEC-004) ──────────────────────────────────────────
# Mutating /api/* routes require this header when NOVA_API_KEY is set, or when
# the bind host is not loopback (see backend/auth.py).
NOVA_API_KEY_HEADER = "X-Nova-Api-Key"
NOVA_API_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

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
