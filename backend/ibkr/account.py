"""
IBKR account summary and positions polling.

Polls on demand (called by the /api/ibkr/account and /api/ibkr/positions
routes). No background loop — data is fetched per-request to keep it fresh.
"""
from __future__ import annotations

import logging

from ibkr import client as _client

logger = logging.getLogger(__name__)


def get_positions() -> list[dict]:
    """Return a list of current positions as plain dicts."""
    ib = _client.get_ib()
    if ib is None:
        return []
    try:
        positions = ib.positions()
        return [
            {
                "symbol": p.contract.symbol,
                "qty": p.position,
                "avg_cost": p.avgCost,
                "market_value": None,  # populated separately via portfolio()
            }
            for p in positions
        ]
    except Exception as exc:
        logger.error("IBKR: get_positions error: %s", exc)
        return []


def get_account_summary() -> dict:
    """Return key account metrics as a plain dict."""
    ib = _client.get_ib()
    if ib is None:
        return {"connected": False, "mode": "disconnected"}

    try:
        summary_items = ib.accountSummary()
        summary: dict = {"connected": True, "mode": _client.account_mode()}
        for item in summary_items:
            tag = item.tag
            if tag in ("NetLiquidation", "TotalCashValue", "BuyingPower",
                       "UnrealizedPnL", "RealizedPnL", "GrossPositionValue"):
                summary[tag] = float(item.value) if item.value else None
        return summary
    except Exception as exc:
        logger.error("IBKR: get_account_summary error: %s", exc)
        return {"connected": False, "mode": _client.account_mode(), "error": str(exc)}


def get_portfolio() -> list[dict]:
    """Return portfolio items (positions with market value)."""
    ib = _client.get_ib()
    if ib is None:
        return []
    try:
        portfolio = ib.portfolio()
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
            for item in portfolio
        ]
    except Exception as exc:
        logger.error("IBKR: get_portfolio error: %s", exc)
        return []
