"""Ahead (ADR 065): the forecast zone on the Trader's 1-minute chart.

Owner: ``backend/ahead/``. Schema: ``architecture/schema/ahead.md``. Mirrors: ``frontend/src/ahead/aheadConstants.ts``
(``AHEAD_HORIZON_MIN``, ``AHEAD_LEVELS``, the states and ``AHEAD_NEVER``): the desk draws what the backend answers.
"""
from __future__ import annotations

AHEAD_SCHEMA_VERSION = 1
# The private forecaster's wire (architecture/schema/ahead.md, "The forecaster's contract").
AHEAD_CONTRACT = "ahead-forecaster/1"
AHEAD_URL_ENV = "NOVA_AHEAD_URL"
AHEAD_TOKEN_ENV = "NOVA_AHEAD_TOKEN"
# The forecaster runs on this PC only: any other host is refused before the token is ever sent.
AHEAD_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
AHEAD_POOL = "ahead"                       # http_pool session name

# Deadlines (the contract's): one health ask, one forecast ask; the status route waits a little longer.
AHEAD_HEALTH_TIMEOUT_SEC = 1.0
AHEAD_FORECAST_TIMEOUT_SEC = 3.0
AHEAD_STATUS_WAIT_SEC = 1.5
# A ready health is trusted this long; a not-ready or unreachable one is asked again after the shorter wait.
AHEAD_HEALTH_TTL_SEC = 15.0
AHEAD_HEALTH_RETRY_SEC = 5.0
# A failed ask (offline, warming, error) is answered from memory this long, then asked again.
AHEAD_NEGATIVE_TTL_SEC = 5.0
AHEAD_MAX_BODY_BYTES = 512 * 1024
AHEAD_READ_CHUNK_BYTES = 64 * 1024

# The forecast: 15 one-minute steps from the end of the newest completed candle.
AHEAD_HORIZON_MIN = 15
AHEAD_STEP_SEC = 60
AHEAD_LEVELS = (0.1, 0.25, 0.5, 0.75, 0.9)
AHEAD_LEVEL_TOLERANCE = 1e-9
AHEAD_MIN_PATHS = 16                       # the desk draws 16 paths: fewer is an answer it cannot draw
AHEAD_MIN_BARS = 30                        # the contract: the forecaster refuses fewer
AHEAD_BARS_LIMIT = 1000                    # one 04:00-20:00 session of 1-minute rows
AHEAD_MAX_TAIL_GAP_SEC = 120               # newest candle older than this vs the desk minute -> "quiet"
AHEAD_LAST15_SEC = 900                     # the real volume of the last 15 minutes, beside the forecast's

# Asking: its own threads (never the FastAPI pool, never the reads' threads), a memory, a breaker.
AHEAD_ASK_WORKERS = 2
AHEAD_READ_WORKERS = 2
AHEAD_CACHE_MAX = 64
AHEAD_BREAKER_FAILS = 3
AHEAD_BREAKER_SEC = 30.0
AHEAD_PENDING_RETRY_MS = 1000

# Rounding on the wire: prices to 4 decimals (6 below $1), shares of a range to 6.
AHEAD_PRICE_DP = 4
AHEAD_PRICE_DP_SUB_DOLLAR = 6
AHEAD_RATIO_DP = 6

AHEAD_NEVER = "A forecast only: nothing here places, blocks, sizes or delays an order."

# The wire's ai.state.
AHEAD_READY = "ready"
AHEAD_PENDING = "pending"
AHEAD_NOT_SET_UP = "not_set_up"
AHEAD_OFFLINE = "offline"
AHEAD_WARMING = "warming"
AHEAD_NOT_ENOUGH_BARS = "not_enough_bars"
AHEAD_QUIET = "quiet"
AHEAD_ERROR = "error"
# The forecaster's own health states.
AHEAD_HEALTH_STATES = frozenset({"ready", "warming", "error"})

AHEAD_ERR_BAD_SYMBOL = "AHEAD_BAD_SYMBOL"

# Nova's own words for each state (the desk shows them as they are).
AHEAD_WORDS_URL_UNSET = "NOVA_AHEAD_URL is not set"
AHEAD_WORDS_URL_BAD = "NOVA_AHEAD_URL must name this PC (127.0.0.1)"
AHEAD_WORDS_TOKEN_UNSET = "NOVA_AHEAD_TOKEN is not set"
AHEAD_WORDS_PENDING = "Reading the minute that just closed."
AHEAD_WORDS_WARMING = "The forecaster is starting up."
AHEAD_WORDS_NO_CONNECT = "could not connect to the forecaster"
AHEAD_WORDS_TOKEN_REFUSED = "the forecaster refused Nova's token"
AHEAD_WORDS_UNREADABLE = "an answer Nova cannot read"
AHEAD_WORDS_FUTURE_BAR = "a candle ends after the forecast time, so nothing was asked"
AHEAD_WORDS_ASK_FAILED = "Nova could not ask the forecaster"
