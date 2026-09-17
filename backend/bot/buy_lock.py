"""-$200 day lock -- blocks bot and manual BUY places.

Read by execution.service (lazy import). Protective sources still spend.
"""
from __future__ import annotations

from bot.clock import lock_is_active
from bot.persist import load_session
from constants_bot import BOT_REASON_DAY_LOCK


def day_lock_active() -> bool:
    try:
        row = load_session()
    except Exception:
        return False
    return lock_is_active(row.get("hard_lock_until_date"))


def buy_blocked(side: str | None, source: str | None) -> tuple[bool, str | None]:
    if (side or "").upper() != "BUY":
        return False, None
    if source in ("flatten", "kill", "cancel_working"):
        return False, None
    if not day_lock_active():
        return False, None
    return True, BOT_REASON_DAY_LOCK
