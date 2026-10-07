"""Every position says its side and the price at which IBKR would liquidate it (ADR 048 decision 4).

``GET /api/ibkr/positions`` rows add ``position_side`` (``long`` | ``short``), ``liquidation_price``
(``number | null``) and ``liquidation_source``. The liquidation price is where the account's equity --
this position marked at that price, every other position held still -- falls to the maintenance
requirement (``short_sale.margin``), on all three venues:

- Paper and Sim: the practice ledger's equity and maintenance, each stock's maintenance its
  published requirement times IBKR's what-if ratio for it (``practice.margin``);
- Live: IBKR's own equity and maintenance (net liquidation less excess liquidity), less this
  position's own requirement by the same rule.

``null`` when Nova cannot read the account, when the position can never be liquidated by its own
price alone (a long the account fully pays for), or for a row it cannot mark.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from short_sale import margin, whatif

logger = logging.getLogger(__name__)


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _account(venue: str, rows: list[dict[str, Any]]) -> tuple[float | None, float | None, Any]:
    """``(equity, total maintenance, ratio fn)`` for ``venue``; Nones when it cannot be read."""
    if venue in ("paper", "sim"):
        from practice.broker import for_venue

        ledger = for_venue(venue).ledger
        return ledger.net_liquidation(), ledger.maintenance(), ledger.margin_ratio
    from ibkr import account as _acct

    summary = _acct.get_account_summary() or {}
    equity, excess = _num(summary.get("NetLiquidation")), _num(summary.get("ExcessLiquidity"))
    ratio_fn = whatif.ratio
    if equity is None:
        return None, None, ratio_fn
    if excess is not None:
        return equity, max(0.0, equity - excess), ratio_fn
    total = 0.0
    for row in rows:
        qty, mark = _num(row.get("qty")), _num(row.get("market_price") or row.get("avg_cost"))
        if qty is None or mark is None:
            return equity, None, ratio_fn
        factor, _ = ratio_fn(str(row.get("symbol") or ""), "short" if qty < 0 else "long")
        total += margin.requirement("short" if qty < 0 else "long", mark, abs(qty), factor)
    return equity, total, ratio_fn


def decorate(rows: list[dict[str, Any]], venue: str) -> list[dict[str, Any]]:
    """``rows`` with each position's side and liquidation price added."""
    out = [dict(row) for row in rows]
    try:
        equity, total, ratio_fn = _account(venue, out)
    except Exception:  # an unreadable account: the side still shows, the price reads unknown
        logger.warning("positions: the %s account is unreadable -- no liquidation prices", venue, exc_info=True)
        equity, total, ratio_fn = None, None, whatif.ratio
    for row in out:
        qty = _num(row.get("qty")) or 0.0
        side = "short" if qty < 0 else "long"
        row["position_side"] = side if qty else None
        row["liquidation_price"] = None
        row["liquidation_source"] = None
        mark = _num(row.get("market_price") or row.get("avg_cost"))
        if not qty or mark is None or mark <= 0 or equity is None or total is None:
            continue
        factor, source = ratio_fn(str(row.get("symbol") or ""), side)
        own = margin.requirement(side, mark, abs(qty), factor)
        other = max(0.0, total - own)
        solve = margin.short_liquidation_price if side == "short" else margin.long_liquidation_price
        price = solve(equity=equity, other_maint=other, qty=abs(qty), mark=mark, ratio=factor)
        row["liquidation_price"] = round(price, 4) if price is not None else None
        row["liquidation_source"] = (source if venue in ("paper", "sim")
                                     else f"IBKR's account maintenance; this stock's own: {source}")
    return out
