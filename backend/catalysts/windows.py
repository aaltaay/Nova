"""The catalyst verdict's windows on the exchange calendar (ADR 024). Pure apart from the calendar table.

  window_start(now)        the prior session's 16:00 ET close: today's verdict reads only what came after it
  prior_session_open(now)  that session's 04:00 ET open: the prior-session pointer reads from here to the
                           close (v8)
  memory_cutoff(now)       what the live catalyst feed keeps in memory: never less than back to that open
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from constants_catalysts import CATALYST_FEED_MEMORY_HOURS, CATALYST_PRIOR_SESSION_OPEN_HOUR_ET

ET = ZoneInfo("America/New_York")
_CLOSE = dtime(16, 0)


def _prior_session(now: float) -> date:
    from sim.trading_day import last_open_day

    return last_open_day(datetime.fromtimestamp(now, ET).date() - timedelta(days=1))


def window_start(now: float) -> float:
    """The prior session's 16:00 ET close, the same opening the history's windows use."""
    return datetime.combine(_prior_session(now), _CLOSE, ET).timestamp()


def prior_session_open(now: float) -> float:
    """The prior session's 04:00 ET open (a Monday's is Friday's)."""
    return datetime.combine(_prior_session(now), dtime(CATALYST_PRIOR_SESSION_OPEN_HOUR_ET, 0), ET).timestamp()


def memory_cutoff(now: float) -> float:
    """Feed items published before this leave memory: ``CATALYST_FEED_MEMORY_HOURS`` back, or the prior
    session's 04:00 ET open when that is earlier (a Monday's reaches back to Friday's)."""
    return min(now - CATALYST_FEED_MEMORY_HOURS * 3600, prior_session_open(now))
