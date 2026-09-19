"""LLM decide spend + config. Activate is the go -- no hidden fire flag."""
from __future__ import annotations

import os
from typing import Any

from bot.audit import record as audit
from bot.errors import BotError
from bot.persist import load_session, save_session
from constants_bot import (
    BOT_LEVEL_STRATEGY,
    BOT_LLM_DEFAULT_CALL_CAP,
    BOT_LLM_DEFAULT_MODEL,
    BOT_LLM_DEFAULT_USD_CAP,
    BOT_LLM_OPENROUTER_BASE_URL,
    BOT_LLM_USD_PER_CALL_EST,
    BOT_REASON_LLM_CAP,
    BOT_REASON_LLM_IDLE,
)


def llm_api_key() -> str:
    return (
        (os.environ.get("NOVA_LLM_API_KEY") or "").strip()
        or (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    )


def llm_base_url() -> str:
    return (os.environ.get("NOVA_LLM_BASE_URL") or "").strip() or BOT_LLM_OPENROUTER_BASE_URL


def llm_model_id() -> str:
    return (
        (os.environ.get("NOVA_LLM_MODEL") or "").strip()
        or (os.environ.get("NOVA_BRAIN_MODEL") or "").strip()
        or BOT_LLM_DEFAULT_MODEL
    )


def llm_configured() -> bool:
    return bool(llm_api_key())


def default_llm() -> dict[str, Any]:
    return {
        "call_cap": BOT_LLM_DEFAULT_CALL_CAP,
        "usd_cap": BOT_LLM_DEFAULT_USD_CAP,
        "usd_spent": 0.0,
        "calls_used": 0,
    }


def estimate_usd(usage: dict[str, Any] | None) -> float:
    if usage:
        try:
            prompt = float(usage.get("prompt_tokens") or 0)
            completion = float(usage.get("completion_tokens") or 0)
        except (TypeError, ValueError):
            prompt = 0.0
            completion = 0.0
        if prompt or completion:
            return max(0.0001, (prompt * 0.0000015) + (completion * 0.000006))
    return float(BOT_LLM_USD_PER_CALL_EST)


def _armed(row: dict[str, Any]) -> bool:
    token_on = bool((row.get("desk_arm_token") or "").strip())
    return bool(row.get("armed")) and token_on


def public_llm(row: dict[str, Any] | None = None) -> dict[str, Any]:
    sess = row if row is not None else load_session()
    current = dict(sess.get("llm") or {})
    merged = {**default_llm(), **current}
    level = int(sess.get("level") or 0)
    return {
        "configured": llm_configured(),
        "live_fire": level >= BOT_LEVEL_STRATEGY and _armed(sess),
        "call_cap": max(0, int(merged.get("call_cap") or BOT_LLM_DEFAULT_CALL_CAP)),
        "usd_cap": max(0.0, float(merged.get("usd_cap") or BOT_LLM_DEFAULT_USD_CAP)),
        "usd_spent": max(0.0, float(merged.get("usd_spent") or 0)),
        "calls_used": max(0, int(merged.get("calls_used") or 0)),
    }


def assert_and_charge(usd: float) -> dict[str, Any]:
    if not llm_configured():
        raise BotError(
            "LLM pack is idle -- set OPENROUTER_API_KEY (same key as Advise) "
            "or NOVA_LLM_API_KEY",
            409,
            BOT_REASON_LLM_IDLE,
        )
    row = load_session()
    state = {**default_llm(), **dict(row.get("llm") or {})}
    used = int(state.get("calls_used") or 0)
    spent = float(state.get("usd_spent") or 0)
    call_cap = max(0, int(state.get("call_cap") or 0))
    usd_cap = max(0.0, float(state.get("usd_cap") or 0))
    cost = max(0.0, float(usd))
    if used + 1 > call_cap:
        raise BotError(f"LLM call cap {call_cap} reached", 409, BOT_REASON_LLM_CAP)
    if spent + cost > usd_cap + 1e-9:
        raise BotError(
            f"LLM session cap ${usd_cap:.2f} would be exceeded (spent ${spent:.2f} + ${cost:.2f})",
            409,
            BOT_REASON_LLM_CAP,
        )
    state["calls_used"] = used + 1
    state["usd_spent"] = spent + cost
    row["llm"] = state
    save_session(row)
    view = public_llm(row)
    audit(action="llm_call", outcome="charged", advise_spend=cost, inputs={"usd": cost})
    return view
