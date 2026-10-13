"""Win / loss for a followed trade, and a trader's record (operator decisions, 2026-10-13). Pure.

Nothing more than this: a closed trade with one exit price is a win when its P/L is above zero, a loss below, a
scratch at exactly zero (left out of the win rate); a trade whose exit is not one known price -- a window, not
read yet, not read at all, a close the feed never saw -- is unscored. An open trade has no result.
"""
from __future__ import annotations

from typing import Any

RESULTS = ("win", "loss", "scratch", "unscored")


def result(row: dict[str, Any]) -> str | None:
    """``win | loss | scratch | unscored`` for a trade row of the answer (``view.trade_row``), None while open."""
    if row["status"] == "open":
        return None
    exit_ = row.get("exit") or {}
    pl = row.get("pl")
    if exit_.get("state") != "at" or not pl or "per_share" not in pl:
        return "unscored"
    if pl["per_share"] > 0:
        return "win"
    if pl["per_share"] < 0:
        return "loss"
    return "scratch"


def record(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """``{wins, losses, scratches, unscored, open, win_rate}``; ``win_rate`` is wins over wins plus losses, in
    percent points, None when there is neither."""
    counts = {"win": 0, "loss": 0, "scratch": 0, "unscored": 0, None: 0}
    for row in rows:
        counts[row.get("result") if "result" in row else result(row)] += 1
    decided = counts["win"] + counts["loss"]
    return {"wins": counts["win"], "losses": counts["loss"], "scratches": counts["scratch"],
            "unscored": counts["unscored"], "open": counts[None],
            "win_rate": round(counts["win"] / decided * 100.0, 1) if decided else None}
