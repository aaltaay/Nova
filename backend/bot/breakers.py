"""The loss breakers on whole-account Day P&L: the bot trip and the all-stop.

Their thresholds are the operator's, per venue (``bot.breaker_limits``; -$50 and -$200 until
changed), and they compare the desk venue's own day P&L (``bot.day_pnl``: IBKR's on Live, the
practice ledger's on Paper and at the Sim live edge). On a Sim replay they compare nothing.

- **The bot trip** flattens, turns the bot off -- the master at Eyes, so Eyes keep proposing (ADR
  043) -- and latches until the next 04:00 ET (``bot.autonomy.drop_to_eyes``); the trip's record --
  ``soft_breaker_at`` / ``soft_breaker_pnl``
  / ``soft_breaker_usd`` -- is written here.
- **The all-stop** does the same and locks new buys on its venue until the next 04:00 ET
  (``bot.buy_lock``): ``hard_lock_until_date`` / ``hard_lock_at`` / ``hard_lock_pnl`` /
  ``hard_lock_usd``.

Each trip's flatten is stamped with its origin (``bot_trip`` / ``all_stop``), so the Orders table
says the breaker sold, and its audit line (``breaker_soft`` / ``breaker_hard``) lists what it sold
(``inputs.closes``): the desk's breaker notice reads it (operator report 2026-10-01: "I don't
remember selling it").

Both write to the dial of the venue whose P&L crossed (``bot.buy_lock.dial_of``), so a lock
belongs to that venue even if the desk moved while it flattened. One day boundary, 04:00 ET:
the locks lift as the practice day rolls, so yesterday's practice P&L never trips them again
after midnight (``bot.clock``).
"""
from __future__ import annotations

import logging
from typing import Any

from bot.audit import record as audit
from bot.autonomy import drop_to_eyes
from bot.breaker_limits import limits, replay_desk, venue_key
from bot.buy_lock import desk_venue, dial_of, lock_for
from bot.clock import lock_until, now_ts, soft_latched, until_text
from bot.day_pnl import read_account_day_pnl
from bot.flatten import alert_flatten_failed, closes_sold, flatten_account_with_retry
from bot.persist import load_session, save_session

logger = logging.getLogger(__name__)


async def _flatten_or_alert(tag: str, origin: str) -> dict[str, Any]:
    result = await flatten_account_with_retry(origin=origin)
    if not result.get("ok"):
        alert_flatten_failed(result)
        audit(action=f"breaker_{tag}_flatten", outcome="failed", reason=str(result.get("error")), inputs=result)
    else:
        audit(action=f"breaker_{tag}_flatten", outcome="ok", inputs={"attempt": result.get("attempt")})
    return result


def _venue() -> str | None:
    return desk_venue()


def _stamp(row: dict[str, Any], venue: str | None, fields: dict[str, Any]) -> None:
    """Write a trip's record on ``venue``'s dial: the row for the desk's own venue, else the
    stored dial (started if that venue has none yet -- the desk moved while it flattened)."""
    dial = dial_of(row, venue)
    if dial is not row and not dial:
        stored = row.get("venue_levels")
        if not isinstance(stored, dict):
            stored = row["venue_levels"] = {}
        dial = stored.setdefault(venue_key(venue), {})
    dial.update(fields)


def _money(value: float | None) -> str:
    return "unknown" if value is None else f"{value:+,.2f}"


async def trip_soft(at: float | None = None, *, pnl: float | None = None, venue: str | None = None) -> dict[str, Any]:
    """The bot trip: flatten, the bot off at Eyes, the latch until the next 04:00 ET, and its record."""
    venue = _venue() if venue is None else venue
    at = limits(load_session(), venue)["soft_usd"] if at is None else at
    flatten = await _flatten_or_alert("soft", "bot_trip")
    row = drop_to_eyes(keep_soft_latch=True, reason="bot_trip")
    _stamp(row, venue, {"soft_breaker_at": now_ts(), "soft_breaker_pnl": pnl, "soft_breaker_usd": at})
    row = save_session(row)
    audit(action="breaker_soft", outcome="eyes",
          reason=(f"{venue or 'live'}: the day P&L {_money(pnl)} reached the bot trip ({at:g}) -- "
                  f"flattened, the bot is off (Eyes keep watching) until you re-enable it (or 04:00 ET)"),
          inputs={"flatten_ok": flatten.get("ok"), "threshold": at, "pnl": pnl, "venue": venue,
                  "until": row.get("soft_breaker_until"), "closes": closes_sold(flatten),
                  "flatten_error": flatten.get("error")})
    return {"tripped": "soft", "flatten": flatten, "session": row}


async def trip_hard(at: float | None = None, *, pnl: float | None = None, venue: str | None = None) -> dict[str, Any]:
    """The all-stop: flatten, the bot off at Eyes, buys on ``venue`` locked until the next 04:00 ET."""
    venue = _venue() if venue is None else venue
    at = limits(load_session(), venue)["hard_usd"] if at is None else at
    flatten = await _flatten_or_alert("hard", "all_stop")
    row = drop_to_eyes(keep_soft_latch=True, reason="all_stop")
    until = lock_until()
    _stamp(row, venue, {"hard_lock_until_date": until, "hard_lock_at": now_ts(),
                        "hard_lock_pnl": pnl, "hard_lock_usd": at})
    row = save_session(row)
    audit(
        action="breaker_hard",
        outcome="day_lock",
        reason=(f"{venue or 'live'}: the day P&L {_money(pnl)} reached the all-stop ({at:g}) -- "
                f"flattened, buys on {venue or 'live'} locked until {until_text(until)}"),
        inputs={"flatten_ok": flatten.get("ok"), "lock_until": until, "threshold": at, "pnl": pnl,
                "venue": venue, "closes": closes_sold(flatten), "flatten_error": flatten.get("error")},
    )
    return {"tripped": "hard", "flatten": flatten, "session": row}


async def poll_once(pnl: float | None = None, meter: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Compare the desk venue's day P&L with its breakers once; trip the first one it crosses.

    Nothing is compared on a Sim replay (a replay's P&L is not today's) or while the day P&L is
    unknown -- the meter (``GET /api/bot/pnl``) says which.
    """
    venue = _venue()
    if venue == "sim" and replay_desk():
        return None
    if pnl is None:
        pnl, meter = read_account_day_pnl()
    if pnl is None:
        return None
    row = load_session()
    lim = limits(row, venue)
    # A lock from an earlier day has lifted: the all-stop trips again (it read the stale
    # date as "already locked" and never tripped a second time).
    if pnl <= lim["hard_usd"] and not lock_for(row, venue)["active"]:
        return await trip_hard(pnl=pnl, venue=venue)
    if pnl <= lim["soft_usd"] and not soft_latched(row):
        return await trip_soft(pnl=pnl, venue=venue)
    return None
