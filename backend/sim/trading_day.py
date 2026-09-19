"""Exchange calendar for the SIM session date: weekdays that are not NYSE holidays."""
from __future__ import annotations

from datetime import date, timedelta

from constants_nova_os import NOVA_OS_NYSE_HOLIDAYS


def is_trading_day(day: date) -> bool:
    return day.weekday() < 5 and day.isoformat() not in NOVA_OS_NYSE_HOLIDAYS


def last_trading_day(day: date) -> date:
    """``day`` when the exchange is open that day, else the latest earlier open day."""
    while not is_trading_day(day):
        day -= timedelta(days=1)
    return day
