"""OpenRouter usage parse + Sonnet rate fallback. No live HTTP."""
from __future__ import annotations

import pytest

from advise.usage import (
    add_usage,
    empty_usage,
    parse_usage,
    stub_call_usage,
    usd_from_sonnet_rates,
)
from constants_advise import (
    ADVISE_EST_COMPLETION_TOKENS_PER_CALL,
    ADVISE_EST_PROMPT_TOKENS_PER_CALL,
)


def test_parse_usage_prefers_body_cost():
    usage = parse_usage(
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "cost": 0.31,
            }
        },
        {"x-openrouter-cost": "9.99"},
    )
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 20
    assert usage["actual_usd"] == 0.31


def test_parse_usage_uses_cost_header():
    usage = parse_usage(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 5}},
        {"X-OpenRouter-Cost": "0.12"},
    )
    assert usage["actual_usd"] == 0.12


def test_parse_usage_sonnet_rate_fallback():
    usage = parse_usage({"usage": {"prompt_tokens": 1000, "completion_tokens": 1000}})
    assert usage["actual_usd"] == usd_from_sonnet_rates(1000, 1000)
    assert usage["actual_usd"] == 0.012


def test_parse_usage_empty_is_unknown():
    usage = parse_usage({})
    assert usage["prompt_tokens"] == 0
    assert usage["completion_tokens"] == 0
    assert usage["actual_usd"] is None


def test_add_usage_sums_partial():
    total = empty_usage()
    add_usage(total, parse_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.1}}))
    add_usage(total, parse_usage({"usage": {"prompt_tokens": 5, "completion_tokens": 3, "cost": 0.05}}))
    assert total["prompt_tokens"] == 15
    assert total["completion_tokens"] == 5
    assert total["actual_usd"] == pytest.approx(0.15)


def test_stub_call_usage_matches_estimate_rates():
    piece = stub_call_usage()
    assert piece["prompt_tokens"] == ADVISE_EST_PROMPT_TOKENS_PER_CALL
    assert piece["completion_tokens"] == ADVISE_EST_COMPLETION_TOKENS_PER_CALL
    assert piece["actual_usd"] == usd_from_sonnet_rates(
        ADVISE_EST_PROMPT_TOKENS_PER_CALL,
        ADVISE_EST_COMPLETION_TOKENS_PER_CALL,
    )
