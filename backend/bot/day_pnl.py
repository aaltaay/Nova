"""Whole-account Day P&L meter for breakers.

Desk chip is realized + unrealized. Breakers also subtract session
CommissionReport dollars so commissions count (conservative vs the bar).
"""
from __future__ import annotations

from typing import Any


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def session_commission_total() -> float:
    try:
        from execution.closed_blotter import session_start_ts
        from execution.store_facts import session_commission_by_symbol

        totals = session_commission_by_symbol(since_ts=session_start_ts())
    except Exception:
        return 0.0
    return abs(sum(float(v) for v in totals.values()))


def practice_day_pnl(summary: dict[str, Any] | None) -> float | None:
    """The practice ledger's own day P&L, or None off the practice venues (QA W2).

    It is net liquidation less the 04:00 ET equity: today's realized plus the
    open positions' move since the boundary, every fee already paid out of
    cash -- so no commission is subtracted again. The lifetime realized that
    the summary used to carry could trip the breaker at the first poll of a
    new day on a ledger that had lost $50 since its last reset.
    """
    if not summary or not summary.get("practice"):
        return None
    return _finite(summary.get("DayPnL"))


def day_pnl_usd(
    summary: dict[str, Any] | None,
    *,
    commission_total: float | None = None,
) -> float | None:
    if not summary:
        return None
    practice = practice_day_pnl(summary)
    if practice is not None:
        return practice
    realized = _finite(summary.get("RealizedPnL"))
    unrealized = _finite(summary.get("UnrealizedPnL"))
    if realized is None and unrealized is None:
        return None
    raw = (realized or 0.0) + (unrealized or 0.0)
    cost = commission_total if commission_total is not None else session_commission_total()
    return raw - abs(float(cost or 0.0))


def read_account_day_pnl() -> tuple[float | None, dict[str, Any]]:
    try:
        from ibkr import account as _account

        summary = _account.get_account_summary() or {}
    except Exception as exc:
        return None, {"error": str(exc)}
    practice = practice_day_pnl(summary)
    commissions = 0.0 if practice is not None else session_commission_total()
    pnl = day_pnl_usd(summary, commission_total=commissions)
    return pnl, {
        "RealizedPnL": summary.get("RealizedPnL"),
        "UnrealizedPnL": summary.get("UnrealizedPnL"),
        "commissions": commissions,
        "day_pnl": pnl,
        "source": "practice_ledger_day_pnl" if practice is not None else "account_summary",
    }
