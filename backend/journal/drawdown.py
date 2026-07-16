"""
Equity curve and max drawdown from closed trades sorted by closed_ts.

Uses cumulative closed-trade P&L — not account balance — so the curve is
honest even when the journal has partial history.
"""
from __future__ import annotations

from typing import Any


def compute_drawdown(trades: list[dict]) -> dict[str, Any]:
    """Build equity curve and peak-to-trough max drawdown."""
    closed = [t for t in trades if t.get("pnl") is not None and t.get("closed_ts") is not None]
    closed.sort(key=lambda t: float(t["closed_ts"]))

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    max_dd_pct: float | None = None
    curve: list[dict[str, Any]] = []

    for trade in closed:
        pnl = float(trade["pnl"])
        equity += pnl
        peak = max(peak, equity)
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = (dd / peak * 100.0) if peak > 0 else None
        curve.append(
            {
                "trade_id": trade.get("id"),
                "symbol": trade.get("symbol"),
                "closed_ts": trade.get("closed_ts"),
                "pnl": round(pnl, 2),
                "equity": round(equity, 2),
                "drawdown": round(dd, 2),
            }
        )

    return {
        "trade_count": len(closed),
        "final_equity": round(equity, 2) if closed else 0.0,
        "peak_equity": round(peak, 2) if closed else 0.0,
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": None if max_dd_pct is None else round(max_dd_pct, 2),
        "curve": curve,
    }
