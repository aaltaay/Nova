"""OpenRouter token/cost accounting for Advise runs.

Owner: advise.usage
Never treats the pre-run estimate as a bill.
"""
from __future__ import annotations

from typing import Any, Mapping

from constants_advise import (
    ADVISE_EST_COMPLETION_TOKENS_PER_CALL,
    ADVISE_EST_COMPLETION_USD_PER_MTOK,
    ADVISE_EST_PROMPT_TOKENS_PER_CALL,
    ADVISE_EST_PROMPT_USD_PER_MTOK,
)


def empty_usage() -> dict[str, Any]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "actual_usd": None}


def usd_from_sonnet_rates(prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens / 1_000_000 * ADVISE_EST_PROMPT_USD_PER_MTOK
        + completion_tokens / 1_000_000 * ADVISE_EST_COMPLETION_USD_PER_MTOK
    )


def stub_call_usage() -> dict[str, Any]:
    prompt = ADVISE_EST_PROMPT_TOKENS_PER_CALL
    completion = ADVISE_EST_COMPLETION_TOKENS_PER_CALL
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "actual_usd": usd_from_sonnet_rates(prompt, completion),
    }


def add_usage(total: dict[str, Any], piece: Mapping[str, Any]) -> None:
    total["prompt_tokens"] = int(total.get("prompt_tokens") or 0) + int(
        piece.get("prompt_tokens") or 0
    )
    total["completion_tokens"] = int(total.get("completion_tokens") or 0) + int(
        piece.get("completion_tokens") or 0
    )
    piece_usd = piece.get("actual_usd")
    if piece_usd is not None:
        total["actual_usd"] = float(total.get("actual_usd") or 0.0) + float(piece_usd)


def should_persist(usage: Mapping[str, Any]) -> bool:
    return bool(
        usage.get("prompt_tokens")
        or usage.get("completion_tokens")
        or usage.get("actual_usd") is not None
    )


def _as_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _int_field(raw: Any) -> int:
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _header_map(headers: Mapping[str, Any] | None) -> dict[str, str]:
    if headers is None:
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def parse_usage(
    body: Mapping[str, Any] | None,
    headers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = body or {}
    raw_usage = payload.get("usage")
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    prompt = _int_field(usage.get("prompt_tokens"))
    completion = _int_field(usage.get("completion_tokens"))
    details = usage.get("cost_details")
    cost_details = details if isinstance(details, dict) else {}
    body_cost = _as_float(usage.get("cost"))
    if body_cost is None:
        body_cost = _as_float(usage.get("total_cost"))
    if body_cost is None:
        body_cost = _as_float(cost_details.get("upstream_inference_cost"))
    header = _header_map(headers)
    header_cost = _as_float(header.get("x-openrouter-cost"))
    if header_cost is None:
        header_cost = _as_float(header.get("x-openrouter-total-cost"))
    if body_cost is not None:
        actual = body_cost
    elif header_cost is not None:
        actual = header_cost
    elif prompt or completion:
        actual = usd_from_sonnet_rates(prompt, completion)
    else:
        actual = None
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "actual_usd": actual,
    }
