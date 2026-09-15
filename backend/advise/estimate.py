"""Pre-run rough cost / time estimate. Not a bill and not a live quote."""
from __future__ import annotations

from constants_advise import (
    ADVISE_DEFAULT_DEPTH,
    ADVISE_DISCLAIMER,
    ADVISE_EST_CALLS_PER_ROUND,
    ADVISE_EST_COMPLETION_TOKENS_PER_CALL,
    ADVISE_EST_COMPLETION_USD_PER_MTOK,
    ADVISE_EST_FIXED_CALLS,
    ADVISE_EST_PROMPT_TOKENS_PER_CALL,
    ADVISE_EST_PROMPT_USD_PER_MTOK,
    ADVISE_EST_SEC_PER_CALL,
    ADVISE_MAX_DEPTH,
    ADVISE_MIN_DEPTH,
    ADVISE_OPENROUTER_MODEL,
    advise_model_id,
)


def clamp_depth(depth: int | None) -> int:
    value = ADVISE_DEFAULT_DEPTH if depth is None else int(depth)
    return max(ADVISE_MIN_DEPTH, min(ADVISE_MAX_DEPTH, value))


def call_count(depth: int) -> int:
    return ADVISE_EST_FIXED_CALLS + ADVISE_EST_CALLS_PER_ROUND * clamp_depth(depth)


def estimate(symbol: str, depth: int | None = None) -> dict:
    rounds = clamp_depth(depth)
    calls = call_count(rounds)
    prompt_tok = calls * ADVISE_EST_PROMPT_TOKENS_PER_CALL
    completion_tok = calls * ADVISE_EST_COMPLETION_TOKENS_PER_CALL
    usd = (
        prompt_tok / 1_000_000 * ADVISE_EST_PROMPT_USD_PER_MTOK
        + completion_tok / 1_000_000 * ADVISE_EST_COMPLETION_USD_PER_MTOK
    )
    seconds = calls * ADVISE_EST_SEC_PER_CALL
    minutes = max(1, round(seconds / 60))
    return {
        "symbol": (symbol or "").strip().upper(),
        "depth": rounds,
        "model": advise_model_id(),
        "model_label": "Claude Sonnet (latest via OpenRouter)",
        "catalog_model": ADVISE_OPENROUTER_MODEL,
        "llm_calls": calls,
        "est_prompt_tokens": prompt_tok,
        "est_completion_tokens": completion_tok,
        "est_usd": round(usd, 2),
        "est_minutes": minutes,
        "summary": f"~${usd:.2f} and ~{minutes} min for {rounds} debate round(s)",
        "disclaimer": ADVISE_DISCLAIMER,
        "note": "Rough only. Reopening a saved book entry spends nothing.",
    }
