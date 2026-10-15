"""The account's day P&L meter (``GET /api/bot/pnl``) and the #564 commission hold.

Nothing compares this figure any more: the loss breakers it fed are gone (ADR 056), and the daily
loss limit counts only trades opened today (``loss_limit``). The meter stays read-only, and its Live
read refreshes the commission hold every ``BOT_COMMISSION_POLL_SEC`` (``bot.loops.commission_loop``).

- **Live**: IBKR's ``reqPnL.dailyPnL`` for the READY session/account (#664); a stated
  ``RealizedPnL`` + ``UnrealizedPnL`` summary fallback while daily P&L is unavailable.
  The fallback includes lifetime unrealized P&L on overnight positions. IBKR already
  counts every commission in both: realized P&L is "the difference between your entry execution
  cost (execution price + commissions to open the position) and exit execution cost (execution
  price + commissions to close the position)", and the average cost behind unrealized P&L is
  "cost (execution price + commission) / quantity" (TWS Users' Guide, Profit and Loss). Until
  2026-09-30 the breakers subtracted the session's commission reports again, so every commission
  counted twice (spec D). The commissions are still read -- for the meter and for the hold below --
  and never subtracted.
- **Paper, and Sim at the live edge**: the practice ledger's ``DayPnL`` -- net liquidation less
  the 04:00 ET equity, every fee already paid out of cash (QA W2).
- **Sim off the live edge** (a replay): nothing. A replay's P&L is not today's, and the meter says
  so (``REPLAY_NOTE``).

#564 (operator decision 2026-09-24): a commission read that fails is a stated unknown, never $0.
While it fails, the bot sends no new entry on Live (``commission_hold``, read by
``entry_rules.assert_entry_allowed``: ``409 BOT_COMMISSIONS_UNKNOWN``) -- the unreadable file is the
same execution ledger every order is written to before it is sent. Exits, cancels, flatten and kill
are never held; Paper and Sim read no commissions and are never held. Since the commissions are no
longer part of the figure, a failed read no longer makes the day P&L unknown.

Owner: the commission hold -- in memory, set by every failed commission read and cleared by the
next one that succeeds.
"""
from __future__ import annotations

import logging
import math
import sys
import threading
import time
from typing import Any, Callable

from constants_bot import BOT_COMMISSIONS_WARN_EVERY_SEC

logger = logging.getLogger(__name__)

LIVE_COMPARES = "IBKR's daily P&L for the account; commissions are already included."
LIVE_FALLBACK_COMPARES = ("Fallback: IBKR's realized + unrealized P&L for the account. "
                         "It includes an overnight position's lifetime unrealized P&L; "
                         "commissions are already inside both, so none is subtracted again.")
LIVE_RESET = "IBKR owns the daily reset, configured in TWS; the API does not report its time."
FALLBACK_RESET = "The account-summary fallback has no daily-reset guarantee."
PRACTICE_COMPARES = ("{venue}'s day P&L since 04:00 ET: net liquidation less the 04:00 equity, "
                     "every commission and fee already paid.")
REPLAY_NOTE = "Sim replay: a replay's P&L is not today's, so the meter reads nothing here."

_lock = threading.Lock()
_hold: dict[str, Any] | None = None     # {"error", "since"} while the last commission read failed
_last_warn_ts = 0.0
_clock: Callable[[], float] = time.time


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or abs(number) == sys.float_info.max:
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
            "bot day P&L: the session commissions are unreadable (%s) -- "
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
    from constants_sim import DESK_PRACTICE_VENUES

    current = venue if venue is not None else _desk_venue()
    return None if current in DESK_PRACTICE_VENUES else hold


def practice_day_pnl(summary: dict[str, Any] | None) -> float | None:
    """The practice ledger's own day P&L, or None off the practice venues (QA W2).

    It is net liquidation less the 04:00 ET equity: today's realized plus the
    open positions' move since the boundary, every fee already paid out of
    cash -- so no commission is subtracted again.
    """
    if not summary or not summary.get("practice"):
        return None
    return _finite(summary.get("DayPnL"))


def _ibkr_day(summary: dict[str, Any]) -> float | None:
    realized = _finite(summary.get("RealizedPnL"))
    unrealized = _finite(summary.get("UnrealizedPnL"))
    if realized is None and unrealized is None:
        return None
    return _finite((realized or 0.0) + (unrealized or 0.0))


def day_pnl_usd(summary: dict[str, Any] | None) -> float | None:
    """The practice ``DayPnL`` or Live summary fallback; the meter uses ``read_account_day_pnl``."""
    if not summary:
        return None
    practice = practice_day_pnl(summary)
    if practice is not None:
        return practice
    return _ibkr_day(summary)


def _desk_venue() -> str | None:
    """The desk venue, or None when it cannot be read (logged; the hold then counts it as Live)."""
    try:
        from sim.mode import venue

        return venue()
    except Exception:
        logger.warning("bot day P&L: the desk venue is unreadable -- read as Live", exc_info=True)
        return None


def _replay_desk() -> bool:
    """Sim off the live edge; a live edge Nova cannot read counts as a replay (logged)."""
    try:
        from sim.mode import is_replay_desk

        return bool(is_replay_desk())
    except Exception:
        logger.warning("bot day P&L: the Sim live edge is unreadable -- read as a replay", exc_info=True)
        return True


def _desk() -> tuple[str | None, bool]:
    venue = _desk_venue()
    return venue, venue == "sim" and _replay_desk()


def read_account_day_pnl() -> tuple[float | None, dict[str, Any]]:
    """``(day_pnl, meter)``: the account's day P&L now, and what it is in plain words.

    The meter always says ``compares`` (the words), ``source`` and ``venue``; ``day_pnl`` is None
    when there is nothing to compare (a Sim replay, or neither broker figure known -- ``error``).
    """
    venue, replay = _desk()
    meter: dict[str, Any] = {"venue": venue, "compared": True, "note": None, "error": None,
                             "commissions": None, "commissions_in_figure": True,
                             "commissions_unknown": False, "commissions_error": None,
                             "fallback": False, "fallback_reason": None, "reset_time": None,
                             "reset_semantics": None, "daily_pnl_updated_at": None}
    if replay:
        return None, {**meter, "compared": False, "source": "replay", "day_pnl": None,
                      "compares": REPLAY_NOTE, "note": REPLAY_NOTE}
    summary_error = None
    try:
        from ibkr import account as _account

        summary = _account.get_account_summary() or {}
    except Exception as exc:  # the account module logs the failure itself
        summary, summary_error = {}, f"{type(exc).__name__}: {exc}"
        if venue in ("paper", "sim"):
            return None, {**meter, "source": "error", "day_pnl": None, "error": summary_error,
                          "compares": f"Nothing: the account summary cannot be read ({summary_error})."}
    meter.update(RealizedPnL=_finite(summary.get("RealizedPnL")),
                 UnrealizedPnL=_finite(summary.get("UnrealizedPnL")))
    if venue in ("paper", "sim") or summary.get("practice"):
        name = str(venue or "the practice account").capitalize()
        practice = practice_day_pnl(summary)
        return practice, {**meter, "source": "practice_ledger_day_pnl", "day_pnl": practice,
                          "compares": PRACTICE_COMPARES.format(venue=name),
                          "error": None if practice is not None else "the practice ledger reported no day P&L"}
    from ibkr import day_pnl as broker_day_pnl

    daily = broker_day_pnl.read()
    pnl = _finite(daily.get("daily_pnl"))
    fallback = pnl is None
    if fallback:
        pnl = _ibkr_day(summary)
    commissions, error = _read_commissions()    # the #564 hold reads them; they are never subtracted
    out = {**meter, "source": "account_summary" if fallback else "ibkr_daily_pnl",
           "day_pnl": pnl, "compares": LIVE_FALLBACK_COMPARES if fallback else LIVE_COMPARES,
           "fallback": fallback, "fallback_reason": daily.get("error") or (
               "IBKR has no valid daily P&L update yet" if fallback else None),
           "reset_semantics": FALLBACK_RESET if fallback else LIVE_RESET,
           "daily_pnl_updated_at": None if fallback else daily.get("updated_at"),
           "summary_error": summary_error,
           "commissions": commissions, "commissions_unknown": commissions is None,
           "commissions_error": error}
    if pnl is None:
        out["source"] = "error" if summary_error else "account_summary"
        out["error"] = summary_error or ("IBKR's account summary has no realized or unrealized P&L yet"
                        + (" (Gateway disconnected)" if summary.get("connected") is False else ""))
        out["compares"] = f"Nothing: daily P&L and its account-summary fallback are unavailable ({out['error']})."
    return pnl, out


def reset_for_tests(clock: Callable[[], float] | None = None) -> None:
    global _hold, _last_warn_ts, _clock
    with _lock:
        _hold = None
        _last_warn_ts = 0.0
    _clock = clock or time.time
