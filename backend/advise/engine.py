"""Full Advise debate graph in-process (worker only).

Inspired by TauricResearch/TradingAgents (Apache-2.0). Original prompts.
Never imports ibkr. Never sends orders.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from advise.events import make_event
from advise import llm
from advise.market_data import gather, render_brief
from advise.usage import add_usage, empty_usage, stub_call_usage
from advise.prompts import (
    analyst_system,
    bear_system,
    bull_system,
    judge_system,
    research_manager_system,
    risk_system,
    trader_system,
    user_block,
)
from advise.result_parse import parse_judge
from constants_advise import ADVISE_DEFAULT_DEPTH, ADVISE_MAX_DEPTH, ADVISE_MIN_DEPTH

Emit = Callable[[dict[str, Any]], None]


def _clamp_depth(depth: int) -> int:
    return max(ADVISE_MIN_DEPTH, min(ADVISE_MAX_DEPTH, int(depth or ADVISE_DEFAULT_DEPTH)))


def _stub_enabled() -> bool:
    return (os.environ.get("ADVISE_STUB") or "").strip().lower() in ("1", "true", "yes")


def _chat(system: str, user: str, stub_text: str) -> tuple[str, dict[str, Any]]:
    if _stub_enabled():
        return stub_text, stub_call_usage()
    result = llm.chat(system, user)
    return result.content, result.usage


def _emit_message(emit: Emit, agent: str, content: str) -> None:
    emit(make_event("message", agent=agent, content=content))


def run_debate(
    symbol: str,
    depth: int,
    emit: Emit,
    usage_out: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    rounds = _clamp_depth(depth)
    acc = usage_out if usage_out is not None else empty_usage()
    calls = 0
    fail_after = int(os.environ.get("ADVISE_STUB_FAIL_AFTER") or "0")
    emit(make_event("status", message=f"Gathering Yahoo snapshot for {symbol}"))
    if _stub_enabled():
        snapshot = {
            "symbol": symbol,
            "source": "stub",
            "headlines": [],
            "vendor_notes": ["ADVISE_STUB"],
        }
    else:
        snapshot = gather(symbol)
    brief = render_brief(snapshot)
    emit(make_event("status", message="Snapshot ready -- starting full agent set"))
    hang = float(os.environ.get("ADVISE_STUB_HANG_SEC") or "0")
    if _stub_enabled() and hang > 0:
        emit(make_event("status", message="stub hang (cancel test)"))
        time.sleep(hang)

    prior_parts: list[str] = []

    def ask(agent: str, system: str, stub: str) -> str:
        nonlocal calls
        calls += 1
        if _stub_enabled() and fail_after > 0 and calls > fail_after:
            raise RuntimeError("ADVISE_STUB_FAIL_AFTER")
        emit(make_event("status", message=f"{agent} speaking"))
        delay = float(os.environ.get("ADVISE_STUB_SLEEP_SEC") or "0")
        if _stub_enabled() and delay > 0:
            time.sleep(delay)
        user = user_block(symbol, brief, "\n\n".join(prior_parts[-8:]))
        text, piece = _chat(system, user, stub)
        add_usage(acc, piece)
        prior_parts.append(f"{agent}: {text}")
        _emit_message(emit, agent, text)
        return text

    ask("fundamentals", analyst_system("fundamentals"), _STUB["fundamentals"])
    ask("news", analyst_system("news"), _STUB["news"])
    ask("sentiment", analyst_system("sentiment"), _STUB["sentiment"])
    ask("technical", analyst_system("technical"), _STUB["technical"])

    for round_i in range(1, rounds + 1):
        emit(make_event("status", message=f"Debate round {round_i}/{rounds}"))
        ask("bull", bull_system(), _STUB["bull"].format(round=round_i))
        ask("bear", bear_system(), _STUB["bear"].format(round=round_i))

    ask("research_manager", research_manager_system(), _STUB["research_manager"])
    ask("trader", trader_system(), _STUB["trader"])
    ask("risk_aggressive", risk_system("risk_aggressive"), _STUB["risk_aggressive"])
    ask("risk_conservative", risk_system("risk_conservative"), _STUB["risk_conservative"])
    ask("risk_neutral", risk_system("risk_neutral"), _STUB["risk_neutral"])
    judge_text = ask("risk_judge", judge_system(), _STUB["risk_judge"])
    result = parse_judge(symbol, judge_text)
    emit(make_event("result", **result))
    return result


_STUB = {
    "fundamentals": "Float and earnings look ordinary. Valuation is not extreme.",
    "news": "Headlines are mixed; no hard catalyst in the snapshot.",
    "sentiment": "Headline tone is cautious. Social vendors were not configured.",
    "technical": "Price is near the recent mean. RSI is mid-range.",
    "bull": "Round {round}: upside if the name reclaims the short average.",
    "bear": "Round {round}: downside if the recent range fails.",
    "research_manager": "Debate is unresolved; wait for a cleaner level.",
    "trader": "HOLD. No ticket until a level breaks. Size hint 0.",
    "risk_aggressive": "A small probe is acceptable only after a break.",
    "risk_conservative": "Pass. News and tape do not pay for the risk.",
    "risk_neutral": "Hold is the honest call.",
    "risk_judge": (
        '{"stance":"HOLD","reasons":["No clean catalyst","Range-bound tape",'
        '"Debate unresolved"],"risks":["Whipsaw","Headline gap","Thin liquidity"],'
        '"qty_hint":null}'
    ),
}
