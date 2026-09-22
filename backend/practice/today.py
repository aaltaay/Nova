"""Which practice order rows belong to "today" (QA W4, 2026-09-22).

The practice ledger keeps every closed order since its last reset, so Orders
(Today), the Working card's "Filled Today" and the drawer's "Orders . today"
listed yesterday's orders too. Today is the venue's practice day: the rollover
(``PRACTICE_DAY_ROLLOVER_HOUR_ET``) of the venue's own clock -- the wall clock
on Paper, the replay playhead on Sim -- the way IBKR's session trades only
ever hold the session's orders. A closed row's ``updated_at`` is when it
closed: the ledger stamps it at the fill, the cancel or the expiry, in venue
time (``practice.ledger``). Pure except ``day_start``, which reads the clock.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_EPS = 1e-6


def iso_ts(value: Any) -> float | None:
    """Epoch seconds of an ISO-8601 stamp, or None when absent or unparseable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def day_start(venue: str | None) -> float | None:
    """The rollover epoch the venue's clock is in (Sim: the playhead's day), or None when unreadable."""
    try:
        from practice.broker import for_venue
        from practice.clock import day_start_ts

        return day_start_ts(float(for_venue(venue or "").reference.now_ts()))
    except Exception:
        logger.exception("practice today: the %r clock is unreadable -- every closed row listed", venue)
        return None


def closed_today(rows: list[dict], start: float | None, venue: str | None) -> list[dict]:
    """``rows`` that closed at or after the practice day's start.

    ``start`` is the rollover epoch; ``None`` reads it from the venue's clock.
    A row with no parseable close stamp stays listed (it is shown, never
    hidden), and so does every row when the clock cannot be read.
    """
    if not any(iso_ts(row.get("updated_at")) is not None for row in rows):
        return rows
    boundary = start if start is not None else day_start(venue)
    if boundary is None:
        return rows
    kept: list[dict] = []
    for row in rows:
        closed = iso_ts(row.get("updated_at"))
        if closed is None or closed >= boundary - _EPS:
            kept.append(row)
    return kept
