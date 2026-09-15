"""Advise rail tunables (TradingAgents-style advisory panel).

Owner: backend/advise/. Never place or cancel orders. Never import ibkr.
"""
from __future__ import annotations

import os

# Persist
ADVISE_DB_FILENAME = "advise_book.db"
ADVISE_SCHEMA_VERSION = 1
ADVISE_GRAPH_VERSION = 1

# Product LLM -- OpenRouter alias that tracks latest Claude Sonnet.
# Cache key uses this id (not a silently resolved dated snapshot).
ADVISE_OPENROUTER_MODEL = "~anthropic/claude-sonnet-latest"
ADVISE_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ADVISE_HTTP_REFERER = "https://github.com/aaltaay/Nova"
ADVISE_HTTP_TITLE = "Nova Advise"

ADVISE_DEFAULT_DEPTH = 2
ADVISE_MIN_DEPTH = 1
ADVISE_MAX_DEPTH = 5

ADVISE_MAX_WORKERS = 3
ADVISE_STALE_SEC = 2 * 60 * 60
ADVISE_CANCEL_GRACE_SEC = 2.0
ADVISE_LLM_TIMEOUT_SEC = 120
ADVISE_LLM_MAX_TOKENS = 1800
ADVISE_LLM_TEMPERATURE = 0.3

# Rough pre-run estimate (not a bill). Sonnet-latest list prices as of 2026-09.
ADVISE_EST_PROMPT_USD_PER_MTOK = 2.0
ADVISE_EST_COMPLETION_USD_PER_MTOK = 10.0
ADVISE_EST_PROMPT_TOKENS_PER_CALL = 2200
ADVISE_EST_COMPLETION_TOKENS_PER_CALL = 900
ADVISE_EST_SEC_PER_CALL = 18.0
# 4 analysts + research manager + trader + 3 risk + judge = 10 fixed calls.
# Each debate round adds bull + bear.
ADVISE_EST_FIXED_CALLS = 10
ADVISE_EST_CALLS_PER_ROUND = 2

ADVISE_TICKET_DEFAULT_QTY = 100

ADVISE_DISCLAIMER = (
    "Advisory only -- not financial advice and not auto-trading. "
    "A human always Places in Nova. Advise never sends orders."
)

ADVISE_AGENTS = (
    "fundamentals",
    "news",
    "sentiment",
    "technical",
    "bull",
    "bear",
    "research_manager",
    "trader",
    "risk_aggressive",
    "risk_conservative",
    "risk_neutral",
    "risk_judge",
)


def advise_model_id() -> str:
    override = (os.environ.get("ADVISE_OPENROUTER_MODEL") or "").strip()
    return override or ADVISE_OPENROUTER_MODEL
