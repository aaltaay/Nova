"""IBKR's open tick (type 14), taken as today's open only once today's session has opened.

IBKR documents tick 14 as "current session's opening price. Before open will
refer to previous day." Read before 09:30 ET it is yesterday's open, and a gap
computed from it against the prior close (tick 9) is yesterday's open-to-close
move: GCTK on 2026-09-24 read "+9.9%" all premarket while it traded +103% on
the prior close, and VRME / NCPL sat on the Gappers list with negative "gaps".
Every reader of the tick goes through ``todays_open``, so no row, gap or quote
head is given another day's open.
"""
from __future__ import annotations

from datetime import datetime

from market import now_et, regular_session_opened_at


def todays_open(open_price: float | None, now: datetime | None = None) -> float | None:
    """``open_price`` when it can be today's open, else ``None`` (unknown, never 0).

    ``now`` is the wall clock (IBKR's session, not a Sim playhead); a missing
    or non-positive tick is unknown too.
    """
    if open_price is None or not open_price > 0:
        return None
    return open_price if regular_session_opened_at(now or now_et()) else None
