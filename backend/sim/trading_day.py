"""Exchange calendar for the SIM session date: weekdays that are not NYSE holidays.

The holiday table in ``constants_nova_os`` is derived by rule across the declared
range ``[NOVA_OS_CALENDAR_FIRST_YEAR, NOVA_OS_CALENDAR_LAST_YEAR]``. Outside that
range we do not pretend to know: a year the table could not vouch for used to
come back "open", which silently selected exchange holidays as trading days
(#386).

Two answers are possible outside the range, and which one is correct depends on
who is asking, so this module offers both rather than forcing one:

* ``is_trading_day`` / ``last_trading_day`` REFUSE with ``UnsupportedCalendarYear``.
  Use them where a human typed the date (historical selection): telling the
  operator the calendar stops at 2035 beats answering from a rule we did not
  check. ``UnsupportedCalendarYear`` subclasses ``ValueError`` so
  ``sim.history_routes.checked`` renders it as an actionable 422, never a 500.
* ``last_open_day`` DEGRADES to the weekday-only rule and logs a warning. Use it
  where Nova derived the date itself — the wall clock, or the day before an
  already-stored selection. Those callers sit under routes with no ValueError
  mapping, so refusing there is an HTTP 500 and a dead Sim desk, and the
  degraded answer is exactly what shipped before the calendar existed.

An input INSIDE the range never raises from either one, including the first
supported day: the table carries one margin year below
``NOVA_OS_CALENDAR_FIRST_YEAR`` (``NOVA_OS_CALENDAR_TABLE_FIRST_YEAR``) purely so
the backward walk has somewhere to land.

NOT MODELLED — early-close (13:00 ET) half-days. The table holds full-day
closures only, so the day after Thanksgiving, and Dec 24 / Jul 3 when they fall
next to a weekday-observed holiday, are reported as ordinary open days. Session
bounds ignore half-days entirely: ``sim.session_clock.session_bounds_on`` opens
the full 04:00–20:00 window on them, so a replayed half-day shows a live-looking
but empty tape after 13:00 instead of a closed session. That was already true
for 2026 before #386 and is now reachable across the whole supported range
(~2 days a year). Modelling it means an early-close table plus a session-bounds
change in every consumer, which is deliberately out of scope here.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from constants_nova_os import (
    NOVA_OS_CALENDAR_FIRST_YEAR,
    NOVA_OS_CALENDAR_LAST_YEAR,
    NOVA_OS_NYSE_HOLIDAYS,
)

logger = logging.getLogger(__name__)


class UnsupportedCalendarYear(ValueError):
    """A date outside the exchange calendar Nova can vouch for."""


def is_supported(day: date) -> bool:
    """True when the derived holiday table vouches for ``day``'s year."""
    return NOVA_OS_CALENDAR_FIRST_YEAR <= day.year <= NOVA_OS_CALENDAR_LAST_YEAR


def require_supported(day: date) -> date:
    """Return ``day``, or refuse loudly when the calendar cannot vouch for it.

    The message names the supported range and nothing else — the operator gets
    this text over HTTP, so it must not describe Nova's own source layout.
    Extending the range is one constant: ``NOVA_OS_CALENDAR_LAST_YEAR``.
    """
    if not is_supported(day):
        raise UnsupportedCalendarYear(
            f"{day.isoformat()} is outside the supported exchange calendar "
            f"{NOVA_OS_CALENDAR_FIRST_YEAR}-{NOVA_OS_CALENDAR_LAST_YEAR}")
    return day


def _is_open(day: date) -> bool:
    """Weekday that is not a listed full-day closure. No range check.

    Outside the table this is the weekday-only rule Nova used before #386, which
    is why every walk below terminates: at most two consecutive days can fail it
    off-table, and three on it (holiday plus weekend).
    """
    return day.weekday() < 5 and day.isoformat() not in NOVA_OS_NYSE_HOLIDAYS


def is_trading_day(day: date) -> bool:
    """True when the exchange is open on ``day``; refuses an unsupported year."""
    return _is_open(require_supported(day))


def last_open_day(day: date) -> date:
    """Same walk, but never refuses a year — for dates Nova derived itself.

    Inside the supported range this is exactly ``last_trading_day``. Outside it
    the answer comes from the weekday-only rule and is logged as unvouched: a
    wall clock that has slipped (a container booting at the epoch) or a date
    past 2035 must degrade the Sim session date, not take the clock down.
    """
    if not is_supported(day):
        logger.warning(
            "%s is outside the supported exchange calendar %d-%d; falling back to "
            "the weekday rule, so holidays in that year are treated as open",
            day.isoformat(), NOVA_OS_CALENDAR_FIRST_YEAR, NOVA_OS_CALENDAR_LAST_YEAR)
    while not _is_open(day):
        day -= timedelta(days=1)
    return day


def last_trading_day(day: date) -> date:
    """``day`` when the exchange is open that day, else the latest earlier open day.

    Refuses an unsupported ``day``, and a supported ``day`` always answers — the
    walk itself is unchecked, and the table's margin year covers the few days
    below the first supported January, so 2015-01-01 resolves to 2014-12-31
    instead of raising at the edge it sits inside.
    """
    return last_open_day(require_supported(day))
