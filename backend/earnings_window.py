"""Yahoo earnings-day window for scanner dots (ET calendar).

``earningsTimestamp`` is the event of record (today / yesterday / tomorrow).
``earningsTimestampStart`` is the next scheduled date -- Large Cap countdown
reads that field via ``fundamentals.earnings_next_date``, not this module.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from constants import EARNINGS_DOT_WINDOW_DAYS, SESSION_RTH_CLOSE_MIN_ET, SESSION_RTH_OPEN_MIN_ET
from market import ET


def _as_epoch(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_date(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def earnings_date_et(earnings_ts: Any) -> str | None:
    """ET calendar date of a Yahoo earnings epoch."""
    epoch = _as_epoch(earnings_ts)
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=ET).strftime("%Y-%m-%d")


def earnings_day_offset(
    earnings_ts: Any,
    *,
    earnings_date: str | None = None,
    now_et: datetime | None = None,
) -> int | None:
    """Calendar days from today (ET) to the earnings date.

    +1 tomorrow, 0 today, -1 yesterday. None outside
    ``EARNINGS_DOT_WINDOW_DAYS`` or when the date is unknown.
    """
    if now_et is None:
        from market import now_et as live_now_et

        now_et = live_now_et()
    today = now_et.date()
    epoch = _as_epoch(earnings_ts)
    if epoch is not None:
        event = datetime.fromtimestamp(epoch, tz=ET).date()
    else:
        event = _parse_date(earnings_date)
    if event is None:
        return None
    offset = (event - today).days
    if abs(offset) > EARNINGS_DOT_WINDOW_DAYS:
        return None
    return offset


def earnings_session(earnings_ts: Any) -> str | None:
    """'bmo' before the open, 'amc' at/after the close, else 'intraday'."""
    epoch = _as_epoch(earnings_ts)
    if epoch is None:
        return None
    event = datetime.fromtimestamp(epoch, tz=ET)
    mins = event.hour * 60 + event.minute
    if mins < SESSION_RTH_OPEN_MIN_ET:
        return "bmo"
    if mins >= SESSION_RTH_CLOSE_MIN_ET:
        return "amc"
    return "intraday"
