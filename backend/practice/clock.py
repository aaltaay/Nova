"""The practice day and its stamps (ADR 020).

Day P&L, ``commissions_today`` and ``fills_today`` roll at
``PRACTICE_DAY_ROLLOVER_HOUR_ET`` America/New_York -- the pre-market open Nova
already uses as session start -- and, like the boards and Orders (Today), they walk
back over a weekend or holiday to the last exchange day (``session_day_start_ts``):
Saturday 04:00 is no rollover, so Friday's Day P&L stays Friday's until Monday 04:00.
``day_start_ts`` is the plain calendar clock, which turns every day at 04:00; the
loss limit keeps it on purpose (ADR 056, an operator decision). Timestamps are converted by arithmetic, not
``datetime.fromtimestamp``: Windows refuses negative epochs and the Sim tests
run replay clocks that start near zero.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from constants_practice import PRACTICE_DAY_ROLLOVER_HOUR_ET

ET = ZoneInfo("America/New_York")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def at(ts: float, tz: Any = ET) -> datetime:
    """The aware datetime for an epoch second, safe for any sign of ``ts``."""
    return (_EPOCH + timedelta(seconds=float(ts))).astimezone(tz)


def day_start_ts(ts: float) -> float:
    """Epoch of the practice day ``ts`` belongs to: the last rollover hour ET at or before it."""
    now = at(ts)
    start = now.replace(hour=PRACTICE_DAY_ROLLOVER_HOUR_ET, minute=0, second=0, microsecond=0)
    if now < start:
        start -= timedelta(days=1)
    return start.timestamp()


def session_day_start_ts(ts: float) -> float:
    """Epoch of 04:00 ET on the trading session ``ts`` belongs to (``market.session_key_et``).

    ``day_start_ts``, except that a weekend or holiday belongs to the last exchange day before
    it: the day's figures and "today" lists stay that session's until the next one opens.
    """
    from market import session_key_et

    key = datetime.fromisoformat(session_key_et(at(ts)))
    return key.replace(tzinfo=ET, hour=PRACTICE_DAY_ROLLOVER_HOUR_ET).timestamp()


def iso_et(ts: float) -> str:
    return at(ts).isoformat()


def iso_utc(ts: float) -> str:
    return at(ts, timezone.utc).isoformat()
