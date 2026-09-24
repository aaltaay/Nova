"""The replayed session's previous close: IBKR's own figure, or none (#542).

Owner of the close a Sim replay measures its change and Gap% from -- capture
replays (``capture_player``), historical downloads (``history_playback``) and
the eyes' replays (``eyes.recording``). The first answer wins:

1. IBKR's tick-9 close recorded with the Session Record: ``prev_close`` on its
   quote rows (``capture.bridge_ibkr``), the day's most common value;
2. the leaderboard's ``prev_close`` for that symbol-day -- IBKR tick 9 on the
   recorded rows, the rebuilt prior close on the reconstructed ones;
3. IBKR's regular-hours daily close of the prior session, stored with a
   historical download of that symbol-day (``history_download``);
4. ``None``: a stated absence -- the quote head shows no change and no Gap%.

Never the prior session's 15:59 one-minute close, which is the last trade
before the closing auction and not the close (WHLR 2026-09-23 read 1.97 against
IBKR's 1.87), and never a stored daily bar: those are fetched with extended
hours (``IBKR_HISTORICAL_USE_RTH``) and close on the last after-hours trade
(GRML 2026-09-21 read 4.51 against 2.85).
"""
from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from datetime import date as date_cls, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from constants_sim import SIM_HISTORY_SESSION_START_HHMM

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value > 0 else None


def recorded_close(quotes: Iterable[dict[str, Any]], day: str) -> float | None:
    """The most common tick-9 close on a recording's quote rows of ``day``'s session.

    Only rows from 04:00 ET on count -- before it a line can still carry the
    close before (the leaderboard records from 04:00 too); ties go to the later
    value. A recording made before quote rows carried ``prev_close`` answers ``None``.
    """
    since = datetime.combine(date_cls.fromisoformat(day), time(*SIM_HISTORY_SESSION_START_HHMM), ET).timestamp()
    counts: dict[float, int] = {}
    latest: dict[float, int] = {}
    for index, row in enumerate(quotes):
        ts = _positive(row.get("ts"))
        value = _positive(row.get("prev_close"))
        if value is not None and ts is not None and ts >= since:
            counts[value] = counts.get(value, 0) + 1
            latest[value] = index
    if not counts:
        return None
    return max(counts, key=lambda value: (counts[value], latest[value]))


def prior_session_close(closes: Iterable[tuple[str, float]], day: str) -> tuple[str, float] | None:
    """``(date, close)`` of the exchange session before ``day`` among daily closes, else ``None``.

    Only that session answers: a series missing it (a halt, a new listing) gives
    no close rather than an older one. ``last_open_day`` walks holidays and
    degrades to weekdays outside the exchange calendar.
    """
    from sim.trading_day import last_open_day

    prior = last_open_day(date_cls.fromisoformat(day) - timedelta(days=1)).isoformat()
    for when, close in closes:
        value = _positive(close)
        if when == prior and value is not None:
            return prior, value
    return None


def previous_close(symbol: str, day: str, *, recorded: float | None = None) -> float | None:
    """The replayed session's previous close by the order above; never raises."""
    value = _positive(recorded)
    if value is not None:
        return value
    sym = symbol.strip().upper()
    try:
        from leaderboard import store as leaderboard_store
        from sim import history_store

        value = leaderboard_store.day_prev_close(day, sym)
        return value if value is not None else history_store.prior_close(sym, day)
    except Exception:
        # The replay still loads; its quote head states no change rather than guessing one.
        logger.warning("REPLAY: prior close unread for %s %s; none shown", sym, day, exc_info=True)
        return None
