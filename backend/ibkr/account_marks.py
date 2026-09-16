"""Position MTM overlay: prefer an already-streamed L1 last over portfolio.

Does not open ``reqMktData``. Qty stays ``ib.positions()`` SSOT.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any


def finite_last(value: Any) -> float | None:
    """Positive finite last, else None (0 / NaN / junk are not marks)."""
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(val) or val <= 0:
        return None
    return val


def live_l1_last(symbol: str) -> float | None:
    """Last price from an existing Nova L1 stream, or None."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    from ibkr import ticks as _ticks

    row = _ticks.last_quotes([sym]).get(sym)
    if not row:
        return None
    return finite_last(row.get("price"))


def apply_l1_position_mark(row: dict, l1_last: float | None) -> dict:
    """Replace market_price / market_value / unrealized when L1 last is live."""
    last = finite_last(l1_last)
    if last is None:
        return row
    out = dict(row)
    try:
        qty = float(out.get("qty") or 0)
    except (TypeError, ValueError):
        return row
    out["market_price"] = last
    out["market_value"] = last * qty
    avg = out.get("avg_cost")
    if avg is not None:
        try:
            out["unrealized_pnl"] = (last - float(avg)) * qty
        except (TypeError, ValueError):
            pass
    return out


def apply_l1_marks(
    rows: list[dict],
    last_for: Callable[[str], float | None],
) -> list[dict]:
    """Overlay L1 last per row; symbols without a stream keep the portfolio mark."""
    out: list[dict] = []
    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        out.append(apply_l1_position_mark(row, last_for(sym)))
    return out


def _sum_finite(values: list[Any]) -> float | None:
    total = 0.0
    any_val = False
    for raw in values:
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isnan(val):
            continue
        total += val
        any_val = True
    return total if any_val else None


def overlay_account_summary(summary: dict, positions: list[dict]) -> dict:
    """Day P&L / Net Liq follow L1-marked unrealized; BP stays the IB cache."""
    if not summary or not summary.get("connected"):
        return summary
    u_sum = _sum_finite([p.get("unrealized_pnl") for p in positions])
    if u_sum is None:
        return summary
    out = dict(summary)
    ib_u = out.get("UnrealizedPnL")
    out["UnrealizedPnL"] = u_sum
    try:
        ib_nl = out.get("NetLiquidation")
        if ib_nl is not None and ib_u is not None:
            out["NetLiquidation"] = float(ib_nl) + (u_sum - float(ib_u))
    except (TypeError, ValueError):
        pass
    return out
