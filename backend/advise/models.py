"""Advise run / result shapes (plain dicts at the API boundary)."""
from __future__ import annotations

from typing import Any, Literal

AdviseStatus = Literal["queued", "running", "complete", "failed", "cancelled"]
AdviseStance = Literal["LONG", "SHORT", "HOLD"]


def cache_key(symbol: str, session_date: str, model: str, graph_version: int, depth: int) -> str:
    return f"{symbol}|{session_date}|{model}|{graph_version}|{depth}"


def empty_result() -> dict[str, Any]:
    return {
        "stance": None,
        "reasons": [],
        "risks": [],
        "ticket": None,
    }
