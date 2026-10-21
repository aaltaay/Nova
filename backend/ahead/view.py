"""The wire answers of ``/api/ahead/*`` (ADR 061, ``architecture/schema/ahead.md``). Pure composition.

``answer`` is ``AheadAnswer`` and ``status`` is ``AheadStatus`` in ``frontend/src/ahead/aheadTypes.ts``; the
fixtures in ``frontend/src/ahead/__fixtures__/`` hold one of each state and ``tests/test_ahead_wire.py`` checks this
module builds the same key tree. The real facts (candles, price, prior close, the last 15 minutes' volume) are
Nova's; everything under ``ai`` is the forecaster's view, and a non-ready answer carries none of its numbers.
Prices are rounded to 4 decimals (6 below $1), volumes to whole shares.
"""
from __future__ import annotations

import math
from typing import Any

from ahead.inputs import contiguous_tail
from constants_ahead import (
    AHEAD_HORIZON_MIN,
    AHEAD_LAST15_SEC,
    AHEAD_NEVER,
    AHEAD_PRICE_DP,
    AHEAD_PRICE_DP_SUB_DOLLAR,
    AHEAD_RATIO_DP,
    AHEAD_READY,
    AHEAD_SCHEMA_VERSION,
    AHEAD_STEP_SEC,
)


def price(x: float) -> float:
    return round(float(x), AHEAD_PRICE_DP_SUB_DOLLAR if abs(x) < 1 else AHEAD_PRICE_DP)


def whole(x: float) -> int:
    return int(round(float(x)))


def _epoch(x: float) -> float:
    return round(float(x), 3)


def _ready_part(forecast: dict[str, Any] | None, issued_at: float | None) -> dict[str, Any]:
    """The ready-only fields: the forecaster's numbers, or every one of them null."""
    if forecast is None:
        return {"levels": None, "close": None, "volume": None, "paths": None, "volume_15": None, "range_15": None,
                "compute_ms": None, "issued_at": None}
    paths = forecast["paths"]
    return {
        "levels": list(forecast["levels"]),
        "close": [[price(x) for x in row] for row in forecast["close"]],
        "volume": [[whole(x) for x in row] for row in forecast["volume"]],
        "paths": {"n": int(paths["n"]), "close": [[price(x) for x in row] for row in paths["close"]],
                  "joined_by": paths["joined_by"]},
        "volume_15": [whole(x) for x in forecast["volume_15"]],
        "range_15": [round(float(x), AHEAD_RATIO_DP) for x in forecast["range_15"]],
        "compute_ms": round(float(forecast["compute_ms"]), 1),
        "issued_at": _epoch(issued_at) if issued_at is not None else None,
    }


def ai_block(state: str, *, reason: str | None = None, need: int | None = None, have: int | None = None,
             retry_ms: int | None = None, retry_at: float | None = None, health: dict[str, Any] | None = None,
             forecast: dict[str, Any] | None = None, issued_at: float | None = None) -> dict[str, Any]:
    """``AheadAi``. ``health`` is the forecaster's last parsed health (its model and exam), ``forecast`` the parsed
    answer -- given only with ``state == "ready"``."""
    ready = state == AHEAD_READY
    if ready != (forecast is not None):
        raise ValueError("a forecast goes with the ready state only")
    model = forecast["model"] if forecast is not None else (health or {}).get("model")
    return {
        "state": state,
        "reason": None if ready else reason,
        "need": need,
        "have": have,
        "retry_ms": retry_ms,
        "retry_at": _epoch(retry_at) if retry_at is not None else None,
        "model": dict(model) if model else None,
        "exam_passed": bool(forecast["exam_passed"]) if forecast is not None else None,
        "exam": (health or {}).get("exam"),
        "horizon_min": AHEAD_HORIZON_MIN,
        "step_sec": AHEAD_STEP_SEC,
        **_ready_part(forecast, issued_at),
    }


def tail_gap(now: float, as_of: float) -> int:
    """The desk minute minus ``as_of``, seconds (never below zero)."""
    return max(0, whole(math.floor(now / AHEAD_STEP_SEC) * AHEAD_STEP_SEC - as_of))


def answer(*, sym: str, now: float, replay: bool, venue: str, bars: list[dict[str, float]],
           prior_close: float | None, ai: dict[str, Any]) -> dict[str, Any]:
    """``AheadAnswer``: Nova's facts about the candles sent, and the forecaster's view in ``ai``."""
    bar_t = bars[-1]["t"] if bars else None
    as_of = bar_t + AHEAD_STEP_SEC if bar_t is not None else None
    last15 = (whole(sum(b["v"] for b in bars if b["t"] >= as_of - AHEAD_LAST15_SEC)) if as_of is not None else None)
    return {
        "schema_version": AHEAD_SCHEMA_VERSION,
        "symbol": sym,
        "generated_at": _epoch(now),
        "replay": bool(replay),
        "venue": venue,
        "bar_t": bar_t,
        "as_of": as_of,
        "bars": {"n": len(bars), "contiguous_tail": contiguous_tail(bars),
                 "tail_gap_sec": tail_gap(now, as_of) if as_of is not None else None},
        "price": price(bars[-1]["c"]) if bars else None,
        "prior_close": price(prior_close) if prior_close is not None else None,
        "volume_last15": last15,
        "ai": ai,
        "never": AHEAD_NEVER,
    }


def status(*, configured: bool, reason: str | None, health: dict[str, Any] | None,
           checked_at: float) -> dict[str, Any]:
    """``AheadStatus``: is a forecaster set up, and what its health said (null when unknown)."""
    return {
        "schema_version": AHEAD_SCHEMA_VERSION,
        "configured": bool(configured),
        "reason": reason,
        "checked_at": _epoch(checked_at),
        "health": None if health is None else {
            "state": health["state"],
            "detail": health["detail"],
            "contract_ok": True,        # an answer in another contract is refused before it gets here
            "model": health["model"],
            "exam": health["exam"],
            "live": health["live"],
        },
    }
