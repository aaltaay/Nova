"""Attach session CommissionReport sums onto position rows (#179).

Never invent from avg_cost - fill. Empty when no report exists.
Owner: ibkr.position_commission. Invalidation: session start (04:00 ET).
schema_version: ledger executions.commission.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def attach_session_commissions(rows: list[dict]) -> list[dict]:
    """Copy rows and set ``commission`` from this session's real reports."""
    totals: dict[str, float] = {}
    try:
        from execution.closed_blotter import session_start_ts
        from execution.store_facts import session_commission_by_symbol

        totals = session_commission_by_symbol(since_ts=session_start_ts())
    except Exception:
        logger.exception("IBKR: session commission join failed")
        totals = {}
    out: list[dict] = []
    for row in rows:
        copy = dict(row)
        symbol = str(copy.get("symbol") or "").strip().upper()
        copy["commission"] = totals.get(symbol) if symbol else None
        out.append(copy)
    return out
