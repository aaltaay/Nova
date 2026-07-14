"""Lincoln AI — LLM narrative that fills `NewsImpactVerdict.ai_reasoning`.

Opt-in via `LINCOLN_AI_ENABLED=true` (env override; default False in
constants.py) because it calls an external LLM API and costs money — same
gate pattern as the IBKR opt-in module. Requires `OPENAI_API_KEY`.

Never raises into the request path: any missing key, disabled flag, or API
failure degrades to `None` so the rules-first verdict in `impact.py` is
always returned regardless of this optional narrative layer.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from constants import (
    LINCOLN_AI_CACHE_MAX_ENTRIES,
    LINCOLN_AI_ENABLED,
    LINCOLN_AI_MAX_TOKENS,
    LINCOLN_AI_MODEL,
    LINCOLN_AI_TEMPERATURE,
    LINCOLN_AI_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

_client: Any = None
_client_load_attempted = False
_cache: dict[str, str] = {}


def _is_enabled() -> bool:
    override = os.environ.get("LINCOLN_AI_ENABLED")
    if override is not None:
        return override.strip().lower() in ("1", "true", "yes")
    return LINCOLN_AI_ENABLED


def _get_client() -> Any:
    global _client, _client_load_attempted
    if _client is not None or _client_load_attempted:
        return _client
    _client_load_attempted = True
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        _client = OpenAI(api_key=api_key, timeout=LINCOLN_AI_TIMEOUT_SECONDS)
    except Exception as exc:  # pragma: no cover - depends on local env
        logger.warning("Lincoln AI client unavailable: %s", exc)
        _client = None
    return _client


def generate_ai_reasoning(
    symbol: str,
    headline: str | None,
    summary: str,
    sentiment: dict[str, Any],
) -> str | None:
    """One short plain-English sentence on the catalyst, or None if unavailable."""
    if not _is_enabled():
        return None
    text = (headline or "").strip()
    if not text:
        return None

    cache_key = f"{symbol}|{text}|{summary}"
    if cache_key in _cache:
        return _cache[cache_key]

    client = _get_client()
    if client is None:
        return None

    prompt = (
        f"Symbol: {symbol}\n"
        f"Headline: {text}\n"
        f"Rules-based verdict: {summary}\n"
        f"FinBERT headline sentiment: {sentiment.get('label')} ({sentiment.get('score')})\n\n"
        "In one short sentence, explain what this headline means for a day "
        "trader watching this ticker right now. Name the catalyst type "
        "(earnings, FDA, dilution/offering, merger, guidance, etc.) if it is "
        "identifiable from the headline. Do not give investment advice."
    )
    try:
        response = client.chat.completions.create(
            model=LINCOLN_AI_MODEL,
            max_tokens=LINCOLN_AI_MAX_TOKENS,
            temperature=LINCOLN_AI_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        narrative = (response.choices[0].message.content or "").strip() or None
    except Exception as exc:  # pragma: no cover - network/API failure
        logger.warning("Lincoln AI reasoning call failed for %s: %s", symbol, exc)
        return None

    if narrative:
        if len(_cache) >= LINCOLN_AI_CACHE_MAX_ENTRIES:
            _cache.pop(next(iter(_cache)))
        _cache[cache_key] = narrative
    return narrative
