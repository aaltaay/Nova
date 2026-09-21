"""The practice day and its stamps (ADR 020).

Day P&L, ``commissions_today`` and ``fills_today`` roll at
``PRACTICE_DAY_ROLLOVER_HOUR_ET`` America/New_York -- the pre-market open Nova
already uses as session start. Timestamps are converted by arithmetic, not
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


def iso_et(ts: float) -> str:
    return at(ts).isoformat()


def iso_utc(ts: float) -> str:
    return at(ts, timezone.utc).isoformat()
