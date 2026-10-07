"""When a short may open, and when Nova covers it (ADR 048 1.9 and 5).

New shorts are taken from 09:35 ET until ten minutes before the close (15:50, or 12:50 on an
NYSE early close), never premarket or after hours. Five minutes before the close (15:55 / 12:55)
Nova covers every short still open. Every time here is the venue's own clock: the wall clock on
Live and Paper, the playhead on a Sim replay (``venue_now``).

A short is due its cover whenever the clock stands outside its trading day's short hours -- from
the cover time on, overnight, at the weekend -- so a short that survived the session (Nova was
closed at 15:55) is covered the moment Nova sees it.

Pure over a timestamp, except ``venue_now``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from constants_nova_os import (
    NOVA_OS_NYSE_EARLY_CLOSE_MIN_ET,
    NOVA_OS_NYSE_EARLY_CLOSES,
    NOVA_OS_NYSE_HOLIDAYS,
)
from constants_scanner import SESSION_RTH_CLOSE_MIN_ET
from constants_shorts import SHORT_COVER_LEAD_MIN, SHORT_LAST_ENTRY_LEAD_MIN, SHORT_OPEN_MIN_ET

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Hours:
    """One trading day's short hours, as epoch seconds."""

    date: str
    half_day: bool
    open_ts: float          # 09:35 ET: the first new short
    last_short_ts: float    # 15:50 (12:50): no new short from here
    cover_ts: float         # 15:55 (12:55): Nova covers what is left
    close_ts: float         # 16:00 (13:00)


def _at(day: datetime, minutes: int) -> float:
    return (day + timedelta(minutes=minutes)).timestamp()


def hours_on(ts: float) -> Hours | None:
    """The short hours of ``ts``'s Eastern date; None on a weekend or an NYSE holiday."""
    when = datetime.fromtimestamp(float(ts), ET)
    day = when.date()
    iso = day.isoformat()
    if day.weekday() >= 5 or iso in NOVA_OS_NYSE_HOLIDAYS:
        return None
    midnight = datetime(day.year, day.month, day.day, tzinfo=ET)
    half = iso in NOVA_OS_NYSE_EARLY_CLOSES
    close_min = NOVA_OS_NYSE_EARLY_CLOSE_MIN_ET if half else SESSION_RTH_CLOSE_MIN_ET
    return Hours(
        date=iso, half_day=half, open_ts=_at(midnight, SHORT_OPEN_MIN_ET),
        last_short_ts=_at(midnight, close_min - SHORT_LAST_ENTRY_LEAD_MIN),
        cover_ts=_at(midnight, close_min - SHORT_COVER_LEAD_MIN), close_ts=_at(midnight, close_min),
    )


def clock(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), ET).strftime("%H:%M")


def entry_refusal(ts: float) -> str | None:
    """Why no new short may open at ``ts``, or None inside the short hours."""
    hours = hours_on(ts)
    now = clock(ts)
    if hours is None:
        return ("No session today (a weekend or a market holiday): new shorts open on trading days, "
                "09:35 to 15:50 ET.")
    if ts < hours.open_ts:
        return (f"New shorts open at 09:35 ET, never premarket: it is {now} ET. The short check opens "
                f"at {clock(hours.open_ts)}.")
    if ts >= hours.last_short_ts:
        day = "an early close: the market closes at 13:00, so " if hours.half_day else ""
        return (f"New shorts stop at {clock(hours.last_short_ts)} ET ({day}Nova covers what is left at "
                f"{clock(hours.cover_ts)}): it is {now} ET.")
    return None


def entry_lapsed(entered_ts: float, ts: float) -> str | None:
    """Why a short entry placed at ``entered_ts`` may no longer rest or fill at ``ts``, or None.

    A short entry lives inside the short hours of the trading day it was placed on: the door checked
    its borrow, SSR, halt and margin that day. It lapses at that day's last short time, and a GTC one
    never carries into the next session -- even when Nova was closed over the cutoff and the clock
    stands inside the next day's hours again (PR #787 review).
    """
    closed = entry_refusal(ts)
    if closed is not None:
        return closed
    placed, now = hours_on(entered_ts), hours_on(ts)
    if placed is not None and now is not None and placed.date == now.date:
        return None
    day = datetime.fromtimestamp(float(entered_ts), ET).date().isoformat()
    return (f"This short entry was placed on {day}, and a short entry never carries into the next session, "
            "GTC or not: its borrow, SSR, halt and margin checks were that day's. Place it again.")


def cover_due(ts: float) -> bool:
    """A short held at ``ts`` is due its cover: the clock stands outside its day's short hours."""
    hours = hours_on(ts)
    return hours is None or not (hours.open_ts <= ts < hours.cover_ts)


def venue_now(venue: str) -> float:
    """The venue's clock: the playhead on a Sim replay, the wall clock otherwise."""
    if venue in ("paper", "sim"):
        from practice.broker import for_venue

        return float(for_venue(venue).reference.now_ts())
    return time.time()
