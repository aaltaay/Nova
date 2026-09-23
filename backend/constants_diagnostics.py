"""Desk diagnostics + bounded Gateway attach retry (ADR 021). Domain constants.

The checklist is a list of facts, never a verdict: every row carries a
state, a plain-words cause and fix, and the raw evidence it was judged from.
"""
from __future__ import annotations

DIAG_SCHEMA_VERSION = 1

# Row states. ``unknown`` always says why Nova cannot tell.
DIAG_STATE_OK = "ok"
DIAG_STATE_WARN = "warn"
DIAG_STATE_FAIL = "fail"
DIAG_STATE_OFF = "off"
DIAG_STATE_UNKNOWN = "unknown"
DIAG_STATES = (DIAG_STATE_OK, DIAG_STATE_WARN, DIAG_STATE_FAIL, DIAG_STATE_OFF, DIAG_STATE_UNKNOWN)

# Group order on the checklist and in the bundle. Mirror: constantGroups/diagnostics.ts.
DIAG_GROUP_PROCESS = "process"
DIAG_GROUP_INTEGRATIONS = "integrations"
DIAG_GROUP_GATEWAY = "gateway"
DIAG_GROUP_MARKET_DATA = "market_data"
DIAG_GROUP_RECORDER = "recorder"
DIAG_GROUP_PRACTICE = "practice"
DIAG_GROUP_FRONTEND = "frontend"
DIAG_GROUP_PERFORMANCE = "performance"  # ADR 026
DIAG_GROUPS: tuple[tuple[str, str], ...] = (
    (DIAG_GROUP_PROCESS, "Process"),
    (DIAG_GROUP_INTEGRATIONS, "Integrations"),
    (DIAG_GROUP_GATEWAY, "Gateway"),
    (DIAG_GROUP_MARKET_DATA, "Market data"),
    (DIAG_GROUP_RECORDER, "Recorder"),
    (DIAG_GROUP_PRACTICE, "Practice"),
    (DIAG_GROUP_FRONTEND, "Frontend"),
    (DIAG_GROUP_PERFORMANCE, "Performance"),
)

# Actions the UI may attach to a row. Only actions that exist today.
DIAG_ACTION_RECONNECT_IBKR = "reconnect_ibkr"
DIAG_ACTION_LAUNCH_GATEWAY = "launch_gateway"
DIAG_ACTION_RELOAD_BACKEND = "reload_backend"
DIAG_ACTION_REFRESH = "refresh"
DIAG_ACTIONS = (
    DIAG_ACTION_RECONNECT_IBKR,
    DIAG_ACTION_LAUNCH_GATEWAY,
    DIAG_ACTION_RELOAD_BACKEND,
    DIAG_ACTION_REFRESH,
)
DIAG_ACTION_LABELS: dict[str, str] = {
    DIAG_ACTION_RECONNECT_IBKR: "Reconnect Nova to Gateway",
    DIAG_ACTION_LAUNCH_GATEWAY: "Launch Gateway",
    DIAG_ACTION_RELOAD_BACKEND: "Reload backend",
    DIAG_ACTION_REFRESH: "Refresh",
}

# Where the value of an env key came from. Never the value of a secret.
DIAG_ENV_SOURCE_FILE = "env_file"
DIAG_ENV_SOURCE_PROCESS = "process_env"
DIAG_ENV_SOURCE_UNSET = "unset"

# Integration keys the checklist reports (presence only, never the value).
DIAG_INTEGRATION_KEYS: tuple[tuple[str, str, str], ...] = (
    # (row id, title, env key)
    ("ibkr_enabled", "IBKR enabled", "IBKR_ENABLED"),
    ("alpaca_key", "Alpaca key (news / listing aux)", "APCA_API_KEY_ID"),
    ("alpaca_secret", "Alpaca secret (news / listing aux)", "APCA_API_SECRET_KEY"),
    ("openai_key", "OpenAI key (Lincoln AI)", "OPENAI_API_KEY"),
)
DIAG_TRUE_VALUES = frozenset({"1", "true", "yes"})

# TCP probe for the Gateway ports on the diagnostics read (never an IB attach).
DIAG_PORT_PROBE_TIMEOUT_SEC = 0.35
# ``git rev-parse`` at import; a hung git must not stall the API start.
DIAG_GIT_TIMEOUT_SEC = 3.0

DIAG_BUNDLE_HEADER = "Nova desk diagnostics"
# Query parameter the UI sends so the frontend row can compare revisions.
DIAG_UI_TAG_PARAM = "ui"

# Plain-words copy for the env-file rows (also on /api/health.env_file and the
# integration chips when the file is missing -- ADR 021 decision 3).
DIAG_ENV_MISSING_CAUSE = (
    "This API process reads its .env from the repo root of the running code "
    "(or NOVA_ENV_PATH). That file does not exist, so every key reads as unset."
)
DIAG_ENV_MISSING_FIX = (
    "Start the API from the repository that holds .env (Run Nova.bat / Start API "
    "in the desk), or set NOVA_ENV_PATH to that file and restart the API."
)
DIAG_ENV_MISSING_PREFIX = "no .env at"

# ── Bounded Gateway attach retry (ADR 021 decision 2) ─────────────────────────
# Port open, session not READY, connect timed out: retry on this schedule and
# record every attempt for the diagnostics row.
IBKR_ATTACH_BACKOFF_SEC: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0)
# After this many attempts inside the window the stall is a human step, not a
# retry problem -- poll politely and say so.
IBKR_ATTACH_MAX_ATTEMPTS_PER_WINDOW = 5
IBKR_ATTACH_WINDOW_SEC = 600.0
# Polite poll while a human step (IBC login / 2FA / stop the other API) is pending.
IBKR_ATTACH_HUMAN_STEP_POLL_SEC = 30.0
# Attempt reasons that are a human step on their own, before any cap.
IBKR_ATTACH_HUMAN_STEP_REASONS = frozenset({
    "second_factor_pending",
    "client_id_in_use",
    "account_kind_mismatch",
})
# Reason stamped when the window cap turned a retryable reason into a human step.
IBKR_ATTACH_CAP_REASON = "attach_cap"
# Attempts kept for /api/ibkr/status.attach.recent (newest last).
IBKR_ATTACH_LEDGER_MAX = 20
# IB farm-status notices: errorEvent codes that report a data farm connecting or
# connected. They are the Gateway saying "OK", never an error to warn about.
IBKR_INFORMATIONAL_NOTICE_CODES = frozenset({2104, 2106, 2107, 2108, 2119, 2158})

