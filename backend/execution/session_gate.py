"""Market orders need regular hours (operator decision, 2026-09-21).

No US exchange accepts an unpriced order outside 09:30-16:00 ET -- Nasdaq does
not offer them in its extended sessions -- and IBKR holds an RTH-only MKT until
the next open (Warning 399) while ignoring ``outsideRth`` on it (Warning 2109).
A market order sent after hours is therefore a blind market-on-open, never a
fill now. The practice venues used to fill it instantly at the far quote (the
GRML buy at 8.86 on 2026-09-21, a 3.6% spread after the close), teaching a
habit Live refuses. Nova now refuses it on every venue: ``MKT_OUTSIDE_RTH``,
"use a limit at the ask". Protective sources are exempt (ADR 018): flatten
already plans an extended-hours limit (``execution/flatten_exit.py``) and a
practice position can always close at its last mark.

The clock is the venue's: wall time America/New_York on Live and Paper, the
replay playhead on Sim -- a replayed 10:00 is regular hours whatever the wall
clock says. The predicate itself is ``market.regular_hours_at``; the practice
broker repeats the check for callers that bypass the door
(``practice.order_rules.mkt_outside_rth``).
"""
from __future__ import annotations

import logging
from datetime import datetime

from constants_practice import MKT_OUTSIDE_RTH_CODE, MKT_OUTSIDE_RTH_REASON
from ibkr.safety import PROTECTIVE_SOURCES
from market import now_et, regular_hours_at

logger = logging.getLogger(__name__)


def venue_now_et() -> datetime:
    """The venue's clock as an aware America/New_York datetime.

    A practice venue whose reference cannot name its time (nothing loaded on
    Sim) falls back to the wall clock -- admission refuses that order anyway,
    and the fallback is logged rather than hidden.
    """
    from sim.mode import is_practice_venue

    if is_practice_venue():
        try:
            from execution.practice_checks import venue_broker
            from practice.clock import at

            return at(venue_broker().reference.now_ts())
        except Exception as exc:  # noqa: BLE001 -- any venue fault reads as wall time, loudly
            logger.warning("session_gate: venue clock unavailable (%s); using wall clock", exc)
    return now_et()


def regular_hours_now() -> bool:
    """Whether the venue's clock is inside regular hours right now."""
    return regular_hours_at(venue_now_et())


# The conftest pins regular_hours_now to True so after-hours and weekend CI
# does not flip every MKT test; tests about this gate restore the real clock.
regular_hours_now_unpatched = regular_hours_now


def mkt_outside_rth_refusal(order_type: str | None, source: str | None) -> tuple[str, str] | None:
    """``(detail, reason_code)`` for a non-protective MKT outside regular hours; ``None`` to admit."""
    if (order_type or "").strip().upper() != "MKT":
        return None
    if source in PROTECTIVE_SOURCES:
        return None
    if regular_hours_now():
        return None
    return MKT_OUTSIDE_RTH_REASON, MKT_OUTSIDE_RTH_CODE
