"""Which ``setups.db`` row a lane's event belongs to: one row per trigger (ADR 022 amendment, 2026-10-02).

A row is named by its setup's key -- the leg, the pole, the base, the open: ``SYMBOL-DATE-KEY`` plus
``@SETUP`` and ``~TEMPLATE_ID`` (``Lane.sid``). A detector can arm the same key again after a trigger
(the pullback when a candle ties the leg's high; any detector made again mid-day), and that setup used
to land on the trade's row: AMOD 2026-10-02 rewrote its first pullback as the second, and a second
trigger replaced the first trade's score. Now an arming on a key whose row holds a trigger opens the
next attempt, ``KEY#2``, ``KEY#3`` ... The first attempt keeps the id it always had. Every later event
on the key (near, rearmed, triggered, failed, disarmed) goes to the attempt the arming opened.

The lane also learns from its host which of today's ids already hold a trigger in ``setups.db``
(``LaneHost.stored_triggers``), so a lane made after a restart never writes over a stored trade, and
a detector made mid-day starts from the day's triggers on its symbol (``TriggerDetector.restore``).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("setup_scanner.engine")
ATTEMPT_SEP = "#"


def attempt_key(key: Any, n: int) -> str:
    """The key of the ``n``-th setup on ``key``: the key itself for the first, ``KEY#N`` after."""
    return str(key) if n <= 1 else f"{key}{ATTEMPT_SEP}{n}"


def row_id(lane: Any, sym: str, key: Any, event: str) -> str:
    """The row ``event`` on ``key`` belongs to. ``armed`` skips every attempt that holds a trigger."""
    base = lane.sid(sym, key)
    if event != "armed":
        return lane.attempts.get(base, base)
    n, sid = 1, base
    while spent(lane, sym, sid):
        n += 1
        sid = lane.sid(sym, attempt_key(key, n))
    lane.attempts[base] = sid
    return sid


def spent(lane: Any, sym: str, sid: str) -> bool:
    """The row holds a trigger: in this lane's memory, else stored before this lane began."""
    row = lane.rows.get(sid)
    if row is not None:
        return bool(row.get("triggered_at"))
    return sid in stored(lane, sym)


def stored(lane: Any, sym: str) -> set[str]:
    """Today's ids on ``sym`` (this lane's template and setup) whose stored row holds a trigger, read once
    per symbol. A replay's host keeps no store and has nothing to say; a failed read is logged and read
    as none -- the lane then behaves as it did before this rule."""
    got = lane.stored_triggered.get(sym)
    if got is not None:
        return got
    got = lane.stored_triggered[sym] = set()
    read = getattr(lane.host, "stored_triggers", None)
    if read is None:
        return got
    try:
        got.update(read(sym, lane.p.template_id, lane.p.setup))
    except Exception:
        logger.warning("setup scanner: %s's stored triggers could not be read -- a setup armed again on a "
                       "stored trade's key may write over it", sym, exc_info=True)
    return got


def triggers_today(lane: Any, sym: str) -> int:
    """How many setups triggered on ``sym`` today in this lane: its own rows, and the rows stored before
    it began. A filtered setup's trigger is not one of them (``Lane._on_filtered``)."""
    mine = {sid for sid, row in lane.rows.items() if row.get("symbol") == sym and row.get("triggered_at")}
    return len(mine | stored(lane, sym))
