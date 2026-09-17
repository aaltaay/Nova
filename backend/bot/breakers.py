"""-$50 / -$200 loss breakers on whole-account Day P&L."""
from __future__ import annotations

import logging
from typing import Any

from bot.audit import record as audit
from bot.autonomy import drop_to_l0
from bot.clock import lock_until_date
from bot.day_pnl import read_account_day_pnl
from bot.flatten import alert_flatten_failed, flatten_account_with_retry
from bot.persist import load_session, save_session
from constants_bot import BOT_HARD_BREAKER_USD, BOT_SOFT_BREAKER_USD

logger = logging.getLogger(__name__)


async def _flatten_or_alert(tag: str) -> dict[str, Any]:
    result = await flatten_account_with_retry()
    if not result.get("ok"):
        alert_flatten_failed(result)
        audit(action=f"breaker_{tag}_flatten", outcome="failed", reason=str(result.get("error")), inputs=result)
    else:
        audit(action=f"breaker_{tag}_flatten", outcome="ok", inputs={"attempt": result.get("attempt")})
    return result


async def trip_soft() -> dict[str, Any]:
    flatten = await _flatten_or_alert("soft")
    drop_to_l0(keep_soft_latch=True)
    audit(action="breaker_soft", outcome="l0", reason="day_pnl<=-50", inputs={"flatten_ok": flatten.get("ok")})
    return {"tripped": "soft", "flatten": flatten, "session": load_session()}


async def trip_hard() -> dict[str, Any]:
    flatten = await _flatten_or_alert("hard")
    row = drop_to_l0(keep_soft_latch=True)
    row["hard_lock_until_date"] = lock_until_date()
    save_session(row)
    audit(
        action="breaker_hard",
        outcome="day_lock",
        reason="day_pnl<=-200",
        inputs={"flatten_ok": flatten.get("ok"), "lock_until": row["hard_lock_until_date"]},
    )
    return {"tripped": "hard", "flatten": flatten, "session": row}


async def poll_once(pnl: float | None = None, meter: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if pnl is None:
        pnl, meter = read_account_day_pnl()
    if pnl is None:
        return None
    row = load_session()
    if pnl <= BOT_HARD_BREAKER_USD and not row.get("hard_lock_until_date"):
        return await trip_hard()
    if pnl <= BOT_SOFT_BREAKER_USD and not row.get("soft_breaker_fired"):
        return await trip_soft()
    return None
