"""
R-multiple analytics: R = pnl / planned risk where risk = |entry - stop| * qty.

Trades without a stop are skipped honestly — never imputed.
"""
from __future__ import annotations

from typing import Any


def _risk_dollars(trade: dict) -> float | None:
    stop = trade.get("stop_price")
    entry = trade.get("entry_price")
    qty = trade.get("qty")
    if stop is None or entry is None or qty is None:
        return None
    risk = abs(float(entry) - float(stop)) * int(qty)
    return risk if risk > 0 else None


def compute_r_multiples(trades: list[dict]) -> dict[str, Any]:
    """Per-trade R values plus aggregate expectancy over trades with stops."""
    per_trade: list[dict[str, Any]] = []
    r_values: list[float] = []

    for trade in trades:
        pnl = trade.get("pnl")
        if pnl is None:
            continue
        risk = _risk_dollars(trade)
        row: dict[str, Any] = {
            "trade_id": trade.get("id"),
            "symbol": trade.get("symbol"),
            "pnl": round(float(pnl), 2),
            "risk_dollars": None if risk is None else round(risk, 2),
            "r_multiple": None,
        }
        if risk is not None:
            r = float(pnl) / risk
            row["r_multiple"] = round(r, 3)
            r_values.append(r)
        per_trade.append(row)

    skipped = sum(1 for row in per_trade if row["r_multiple"] is None)
    expectancy = (sum(r_values) / len(r_values)) if r_values else None
    avg_win_r = None
    avg_loss_r = None
    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r < 0]
    if wins:
        avg_win_r = round(sum(wins) / len(wins), 3)
    if losses:
        avg_loss_r = round(sum(losses) / len(losses), 3)

    return {
        "trade_count": len(per_trade),
        "scored_count": len(r_values),
        "skipped_no_stop": skipped,
        "expectancy_r": None if expectancy is None else round(expectancy, 3),
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "trades": per_trade,
    }
