"""The loss breakers on whole-account Day P&L: the bot trip and the all-stop.

Their thresholds are the operator's, per venue (``bot.breaker_limits``; -$50 and
-$200 until changed).
"""
from __future__ import annotations

import logging
from typing import Any

from bot.audit import record as audit
from bot.autonomy import drop_to_l0
from bot.breaker_limits import limits
from bot.clock import lock_until_date
from bot.day_pnl import read_account_day_pnl
from bot.flatten import alert_flatten_failed, flatten_account_with_retry
from bot.persist import load_session, save_session

logger = logging.getLogger(__name__)


async def _flatten_or_alert(tag: str) -> dict[str, Any]:
    result = await flatten_account_with_retry()
    if not result.get("ok"):
        alert_flatten_failed(result)
        audit(action=f"breaker_{tag}_flatten", outcome="failed", reason=str(result.get("error")), inputs=result)
    else:
        audit(action=f"breaker_{tag}_flatten", outcome="ok", inputs={"attempt": result.get("attempt")})
    return result


def _venue() -> str | None:
    from bot.gates import current_venue

    return current_venue()


async def trip_soft(at: float | None = None) -> dict[str, Any]:
    at = limits(load_session(), _venue())["soft_usd"] if at is None else at
    flatten = await _flatten_or_alert("soft")
    drop_to_l0(keep_soft_latch=True)
    audit(action="breaker_soft", outcome="l0", reason=f"day_pnl<={at:g}", inputs={"flatten_ok": flatten.get("ok"),
                                                                                   "threshold": at})
    return {"tripped": "soft", "flatten": flatten, "session": load_session()}


async def trip_hard(at: float | None = None) -> dict[str, Any]:
    at = limits(load_session(), _venue())["hard_usd"] if at is None else at
    flatten = await _flatten_or_alert("hard")
    row = drop_to_l0(keep_soft_latch=True)
    row["hard_lock_until_date"] = lock_until_date()
    save_session(row)
    audit(
        action="breaker_hard",
        outcome="day_lock",
        reason=f"day_pnl<={at:g}",
        inputs={"flatten_ok": flatten.get("ok"), "lock_until": row["hard_lock_until_date"], "threshold": at},
    )
    return {"tripped": "hard", "flatten": flatten, "session": row}


def _unknown_day_bound(meter: dict[str, Any] | None) -> float | None:
    """With the commissions unknown (#564) the day is at least as bad as its P&L before them."""
    if not meter or not meter.get("commissions_unknown"):
        return None
    value = meter.get("day_pnl_before_commissions")
    return float(value) if isinstance(value, (int, float)) and value == value else None


async def poll_once(pnl: float | None = None, meter: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if pnl is None:
        pnl, meter = read_account_day_pnl()
    if pnl is None:
        # The day P&L is unknown. A breaker the P&L before commissions already
        # crosses still trips -- commissions only make the day worse. Otherwise
        # nothing is compared; while the commissions are unknown, new Live bot
        # entries are held (bot.day_pnl.commission_hold).
        pnl = _unknown_day_bound(meter)
        if pnl is None:
            return None
    row = load_session()
    lim = limits(row, _venue())
    if pnl <= lim["hard_usd"] and not row.get("hard_lock_until_date"):
        return await trip_hard()
    if pnl <= lim["soft_usd"] and not row.get("soft_breaker_fired"):
        return await trip_soft()
    return None
