"""
IBKR account summary and positions.

Reads from ib_async caches. Sync helpers that wait on the IB event loop
must not run under FastAPI — use Async variants for refresh.
"""
from __future__ import annotations

import logging

from ibkr import client as _client

logger = logging.getLogger(__name__)

_SUMMARY_TAGS = (
    "NetLiquidation",
    "TotalCashValue",
    "BuyingPower",
    "UnrealizedPnL",
    "RealizedPnL",
    "GrossPositionValue",
)


def get_positions() -> list[dict]:
    ib = _client.get_ib()
    if ib is None:
        return []
    try:
        return [
            {
                "symbol": p.contract.symbol,
                "qty": p.position,
                "avg_cost": p.avgCost,
                "market_value": None,
            }
            for p in ib.positions()
        ]
    except Exception as exc:
        logger.error("IBKR: get_positions error: %s", exc)
        return []


def _summary_from_items(items: list) -> dict:
    summary: dict = {"connected": True, "mode": _client.account_mode()}
    for item in items:
        tag = getattr(item, "tag", None)
        if tag not in _SUMMARY_TAGS:
            continue
        currency = getattr(item, "currency", "") or ""
        if currency and currency not in ("USD", "BASE", ""):
            continue
        raw = getattr(item, "value", None)
        try:
            summary[tag] = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            summary[tag] = None
    return summary


def get_account_summary() -> dict:
    """Snapshot from Gateway cache (no nested event-loop wait)."""
    ib = _client.get_ib()
    if ib is None:
        return {"connected": False, "mode": "disconnected"}

    try:
        values = list(ib.accountValues())
        summary = _summary_from_items(values)
        if "NetLiquidation" not in summary:
            summary["pending"] = True
        return summary
    except Exception as exc:
        logger.error("IBKR: get_account_summary error: %s", exc)
        return {"connected": False, "mode": _client.account_mode(), "error": str(exc)}


async def refresh_account_summary() -> dict:
    """Async refresh via accountSummaryAsync, then return snapshot."""
    ib = _client.get_ib()
    if ib is None:
        return {"connected": False, "mode": "disconnected"}
    try:
        items = await ib.accountSummaryAsync()
        if items:
            return _summary_from_items(list(items))
        return get_account_summary()
    except Exception as exc:
        logger.error("IBKR: refresh_account_summary error: %s", exc)
        # Fall back to whatever is already cached.
        snap = get_account_summary()
        if "error" not in snap:
            snap["error"] = str(exc)
        return snap


def get_portfolio() -> list[dict]:
    ib = _client.get_ib()
    if ib is None:
        return []
    try:
        return [
            {
                "symbol": item.contract.symbol,
                "qty": item.position,
                "market_price": item.marketPrice,
                "market_value": item.marketValue,
                "avg_cost": item.averageCost,
                "unrealized_pnl": item.unrealizedPNL,
                "realized_pnl": item.realizedPNL,
            }
            for item in ib.portfolio()
        ]
    except Exception as exc:
        logger.error("IBKR: get_portfolio error: %s", exc)
        return []
