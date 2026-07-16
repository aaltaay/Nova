"""
Per-tag performance from closed journal trades.

Each trade may carry multiple tags; every tag is credited with the full
trade outcome (win/loss + pnl) for honest attribution, not fractional splits.
"""
from __future__ import annotations

import json
from typing import Any


def _trade_tags(trade: dict) -> list[str]:
    raw = trade.get("tags")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if str(t).strip()]
    return []


def tag_performance(trades: list[dict]) -> list[dict[str, Any]]:
    """Aggregate win rate, total pnl, and trade count per tag."""
    buckets: dict[str, dict[str, Any]] = {}

    for trade in trades:
        pnl = trade.get("pnl")
        if pnl is None:
            continue
        tags = _trade_tags(trade)
        if not tags:
            continue
        for tag in tags:
            bucket = buckets.setdefault(
                tag,
                {"tag": tag, "count": 0, "wins": 0, "losses": 0, "flat": 0, "pnl": 0.0},
            )
            bucket["count"] += 1
            bucket["pnl"] += float(pnl)
            if pnl > 0:
                bucket["wins"] += 1
            elif pnl < 0:
                bucket["losses"] += 1
            else:
                bucket["flat"] += 1

    rows: list[dict[str, Any]] = []
    for tag, bucket in sorted(buckets.items(), key=lambda item: (-item[1]["pnl"], item[0])):
        count = bucket["count"]
        wins = bucket["wins"]
        win_rate = (wins / count * 100.0) if count else None
        rows.append(
            {
                "tag": tag,
                "count": count,
                "wins": wins,
                "losses": bucket["losses"],
                "flat": bucket["flat"],
                "win_rate_pct": None if win_rate is None else round(win_rate, 1),
                "pnl": round(bucket["pnl"], 2),
            }
        )
    return rows
