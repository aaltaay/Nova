"""Exchange calendar for the SIM session date: weekdays that are not NYSE holidays.

The holiday table in ``constants_nova_os`` is derived by rule across the declared
range ``[NOVA_OS_CALENDAR_FIRST_YEAR, NOVA_OS_CALENDAR_LAST_YEAR]``. Outside that
range we refuse loudly rather than answer: a year the table could not vouch for
used to come back "open", which silently selected exchange holidays as trading
days (#386). ``UnsupportedCalendarYear`` subclasses ``ValueError`` so
``sim.history_routes.checked`` renders it as an actionable 422, never a 500.
"""
from __future__ import annotations

from datetime import date, timedelta

from constants_nova_os import (
    NOVA_OS_CALENDAR_FIRST_YEAR,
    NOVA_OS_CALENDAR_LAST_YEAR,
    NOVA_OS_NYSE_HOLIDAYS,
)


class UnsupportedCalendarYear(ValueError):
    """A date outside the exchange calendar Nova can vouch for."""


def is_trading_day(day: date) -> bool:
    if not NOVA_OS_CALENDAR_FIRST_YEAR <= day.year <= NOVA_OS_CALENDAR_LAST_YEAR:
        raise UnsupportedCalendarYear(
            f"{day.isoformat()} is outside the supported exchange calendar "
            f"{NOVA_OS_CALENDAR_FIRST_YEAR}-{NOVA_OS_CALENDAR_LAST_YEAR}; "
            "extend NOVA_OS_CALENDAR_LAST_YEAR in backend/constants_nova_os.py")
    return day.weekday() < 5 and day.isoformat() not in NOVA_OS_NYSE_HOLIDAYS


def last_trading_day(day: date) -> date:
    """``day`` when the exchange is open that day, else the latest earlier open day.

    The range check inside ``is_trading_day`` terminates the backward walk at the
    lower calendar boundary, so no separate iteration bound is needed.
    """
    while not is_trading_day(day):
        day -= timedelta(days=1)
    return day
