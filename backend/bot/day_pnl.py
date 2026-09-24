"""Whole-account Day P&L meter for breakers.

Desk chip is realized + unrealized. Breakers also subtract session
CommissionReport dollars so commissions count (conservative vs the bar).

#564 (operator decision 2026-09-24): a commission read that fails is a stated
unknown, never $0. The day P&L is then ``None`` and the meter says
``commissions_unknown`` with the error; until a read succeeds again the bot
sends no new entry on Live (``commission_hold``, read by
``entry_rules.assert_entry_allowed``: ``409 BOT_COMMISSIONS_UNKNOWN``). Exits,
cancels, flatten and kill are never held. Paper and Sim read no commissions --
the practice ledger's ``DayPnL`` already paid them -- and are never held.

Owner: the commission hold -- in memory, set by every failed commission read
and cleared by the next one that succeeds.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from constants_bot import BOT_COMMISSIONS_WARN_EVERY_SEC

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_hold: dict[str, Any] | None = None     # {"error", "since"} while the last commission read failed
_last_warn_ts = 0.0
_clock: Callable[[], float] = time.time


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _read_failed(exc: Exception) -> str:
    """Hold entries and say so -- the first failure at once, then at most every ``BOT_COMMISSIONS_WARN_EVERY_SEC``."""
    global _hold, _last_warn_ts
    error = f"{type(exc).__name__}: {exc}"
    now = _clock()
    with _lock:
        first = _hold is None
        _hold = {"error": error, "since": now if first else _hold["since"]}
        warn = first or now - _last_warn_ts >= BOT_COMMISSIONS_WARN_EVERY_SEC
        if warn:
            _last_warn_ts = now
    if warn:
        logger.warning(
            "bot day P&L: the session commissions are unreadable (%s) -- day P&L unknown, "
            "new Live bot entries held until they read again", error, exc_info=first,
        )
    return error


def _read_ok() -> None:
    global _hold
    with _lock:
        released, _hold = _hold, None
    if released is not None:
        logger.info("bot day P&L: session commissions readable again after %.0fs -- Live bot entries released",
                    _clock() - float(released["since"]))


def _read_commissions() -> tuple[float | None, str | None]:
    """``(total, None)``, or ``(None, error)`` when the execution ledger cannot be read."""
    try:
        from execution.closed_blotter import session_start_ts
        from execution.store_facts import session_commission_by_symbol

        totals = session_commission_by_symbol(since_ts=session_start_ts())
        total = abs(sum(float(v) for v in totals.values()))
    except Exception as exc:
        return None, _read_failed(exc)
    _read_ok()
    return total, None


def session_commission_total() -> float | None:
    """The session's commission dollars; None (logged, entries held) when they cannot be read."""
    return _read_commissions()[0]


def commission_hold(venue: str | None = None) -> dict[str, Any] | None:
    """``{error, since}`` while new Live bot entries are held; None when they are not.

    Paper and Sim are never held. A venue that cannot be read counts as Live.
    """
    with _lock:
        hold = dict(_hold) if _hold is not None else None
    if hold is None:
        return None
    from bot.gates import current_venue
    from constants_sim import DESK_PRACTICE_VENUES

    current = venue if venue is not None else current_venue()
    return None if current in DESK_PRACTICE_VENUES else hold


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


def _before_commissions(summary: dict[str, Any]) -> float | None:
    realized = _finite(summary.get("RealizedPnL"))
    unrealized = _finite(summary.get("UnrealizedPnL"))
    if realized is None and unrealized is None:
        return None
    return (realized or 0.0) + (unrealized or 0.0)


def day_pnl_usd(
    summary: dict[str, Any] | None,
    *,
    commission_total: float | None = None,
) -> float | None:
    """Realized + unrealized less the session's commissions; None when either is unknown."""
    if not summary:
        return None
    practice = practice_day_pnl(summary)
    if practice is not None:
        return practice
    raw = _before_commissions(summary)
    if raw is None:
        return None
    cost = commission_total if commission_total is not None else session_commission_total()
    if cost is None:
        return None                     # commissions unknown (#564): so is the day
    return raw - abs(float(cost))


def read_account_day_pnl() -> tuple[float | None, dict[str, Any]]:
    try:
        from ibkr import account as _account

        summary = _account.get_account_summary() or {}
    except Exception as exc:
        return None, {"error": str(exc)}
    meter: dict[str, Any] = {
        "RealizedPnL": summary.get("RealizedPnL"),
        "UnrealizedPnL": summary.get("UnrealizedPnL"),
        "commissions_unknown": False,
        "commissions_error": None,
    }
    practice = practice_day_pnl(summary)
    if practice is not None:
        return practice, {**meter, "commissions": 0.0, "day_pnl": practice, "source": "practice_ledger_day_pnl"}
    commissions, error = _read_commissions()
    if commissions is None:
        # The day is at least this bad: the breakers still trip on it (bot.breakers).
        return None, {**meter, "commissions": None, "commissions_unknown": True, "commissions_error": error,
                      "day_pnl": None, "day_pnl_before_commissions": _before_commissions(summary),
                      "source": "account_summary"}
    pnl = day_pnl_usd(summary, commission_total=commissions)
    return pnl, {**meter, "commissions": commissions, "day_pnl": pnl, "source": "account_summary"}


def reset_for_tests(clock: Callable[[], float] | None = None) -> None:
    global _hold, _last_warn_ts, _clock
    with _lock:
        _hold = None
        _last_warn_ts = 0.0
    _clock = clock or time.time
