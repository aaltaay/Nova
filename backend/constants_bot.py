"""Bot localhost API tunables (ADR 016 / epic #205).

Owner: backend/bot/. Re-exported from the constants barrel.
"""
from __future__ import annotations

BOT_SCHEMA_VERSION = 3
BOT_SCHEMA_VERSIONS = (1, 2, 3)
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

BOT_PACK_HALT_LULD = "halt-luld"
BOT_PACK_QUOTE_SPIKE = "quote-spike"
BOT_PACK_VOLUME = "volume"
BOT_PACK_LLM_DECIDE = "llm-decide"
BOT_PACK_DEFAULT = BOT_PACK_HALT_LULD
BOT_PACKS = (
    BOT_PACK_HALT_LULD,
    BOT_PACK_QUOTE_SPIKE,
    BOT_PACK_VOLUME,
    BOT_PACK_LLM_DECIDE,
)
BOT_PACK_STUBS = frozenset({BOT_PACK_QUOTE_SPIKE, BOT_PACK_VOLUME})
BOT_PACK_LABELS = {
    BOT_PACK_HALT_LULD: "Halt / LULD resume",
    BOT_PACK_QUOTE_SPIKE: "Quote spike (stub)",
    BOT_PACK_VOLUME: "Volume boost (stub)",
    BOT_PACK_LLM_DECIDE: "LLM decide",
}
BOT_PACK_DESCRIPTIONS = {
    BOT_PACK_HALT_LULD: (
        "When an allowlisted live-focus symbol resumes from halt or LULD, "
        "Eyes proposes and L2 plus Activate fires buy_market (or the configured "
        "kind) once, then waits the cooldown."
    ),
    BOT_PACK_QUOTE_SPIKE: (
        "Stub: quote-spike is not implemented yet -- the brain heartbeats "
        "only and fire returns 409 BOT_PACK_STUB."
    ),
    BOT_PACK_VOLUME: (
        "Stub: Scanner tab Volume boost is the detection SSOT. This pack "
        "does not fire -- heartbeats only and fire returns 409 BOT_PACK_STUB."
    ),
    BOT_PACK_LLM_DECIDE: (
        "A configured LLM posts fixed-schema proposals for allowlisted "
        "live-focus names and live-fires those kinds only when L2 + Activate "
        "are on. Idle if the key, base URL, or model is missing."
    ),
}
BOT_LLM_MIN_INTERVAL_SEC = 15
BOT_LLM_USD_PER_CALL_EST = 0.02
BOT_LLM_HTTP_TIMEOUT_SEC = 20
BOT_SYMBOL_ALLOWLIST_CAP = 50
BOT_HALT_RESUME_COOLDOWN_SEC = 30
BOT_BRAIN_SESSION_ID = "nova-brain"
BOT_BRAIN_POLL_SEC = 1.0

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

BOT_BUY_KINDS = frozenset({
    "buy_market",
    "buy_limit_ask_offset",
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
BOT_LLM_DEFAULT_USD_CAP = BOT_ADVISE_DEFAULT_USD_CAP
BOT_LLM_DEFAULT_CALL_CAP = BOT_ADVISE_DEFAULT_CALL_CAP

BOT_SOFT_BREAKER_USD = -50.0
BOT_HARD_BREAKER_USD = -200.0
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
BOT_REASON_NOT_LOOPBACK = "BOT_NOT_LOOPBACK"
BOT_REASON_TTL_EXPIRED = "working_ttl_expired"
BOT_REASON_SYMBOL_BLOCKED = "BOT_SYMBOL_BLOCKED"
BOT_REASON_PACK_STUB = "BOT_PACK_STUB"
BOT_REASON_LLM_CAP = "BOT_LLM_CAP"
BOT_REASON_LLM_IDLE = "BOT_LLM_IDLE"
