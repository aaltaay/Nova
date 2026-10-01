"""The tape hold: a live tape read never reads across an IBKR feed gap (#673).

Prints and books are stamped when they reach Nova (#563). After a feed gap
(``ibkr/feed_pulse.py``) everything IBKR held arrives in one burst: 16 s of
trading landed in about one second at 09:32:22 on 2026-10-01. Read as tape, that
burst is "green on the tape", a pace burst or a flush that never happened at that
speed. So a tape read whose window touches a gap -- from its last message to
``FEED_GAP_SETTLE_SEC`` after the first one back -- reads ``blind`` with the gap as
its reason, and a flow baseline starts again after the gap.

Pure. A gap is ``{start, end}`` (epoch seconds; ``end`` ``None`` while it is open);
the live host hands them in, a replay hands in none.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from constants_feed import FEED_GAP_SETTLE_SEC
from constants_setups import TAPE_FLOW_BLIND, TAPE_VERDICT_BLIND

ET = ZoneInfo("America/New_York")


def _stop(gap: dict[str, Any], settle: float) -> float:
    end = gap.get("end")
    return math.inf if end is None else float(end) + settle


def touching(gaps: Iterable[dict[str, Any]] | None, start: float, end: float,
             settle: float = FEED_GAP_SETTLE_SEC) -> dict[str, Any] | None:
    """The newest gap whose stretch overlaps the read window ``[start, end]``, else ``None``."""
    hit = None
    for gap in gaps or ():
        if float(gap["start"]) <= end and _stop(gap, settle) >= start:
            if hit is None or gap["start"] > hit["start"]:
                hit = gap
    return hit


def history_from(gaps: Iterable[dict[str, Any]] | None, since: float | None, now: float,
                 settle: float = FEED_GAP_SETTLE_SEC) -> float | None:
    """The earliest moment a flow baseline may count from: never before the newest gap had settled."""
    after = [_stop(g, settle) for g in gaps or () if _stop(g, settle) <= now]
    if not after:
        return since
    newest = max(after)
    return newest if since is None else max(since, newest)


def brief(gap: dict[str, Any], now: float) -> dict[str, Any]:
    end = gap.get("end")
    return {"start": gap["start"], "end": end, "silent_sec": round((end if end is not None else now) - gap["start"], 1)}


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S")


def words(gap: dict[str, Any], now: float) -> str:
    end = gap.get("end")
    if end is None:
        return (f"IBKR data has stopped on every line for {now - gap['start']:.0f} s (since {_clock(gap['start'])} ET)"
                " -- Nova cannot see the tape")
    return (f"IBKR data stopped for {end - gap['start']:.0f} s at {_clock(gap['start'])} ET; what IBKR held arrived "
            f"in one burst at {_clock(end)}, so Nova does not read the tape across it")


def blind_gate(gap: dict[str, Any], now: float, window_sec: float) -> dict[str, Any]:
    """The tape gate's answer while its window touches a gap."""
    return {"verdict": TAPE_VERDICT_BLIND, "reasons": [words(gap, now)],
            "metrics": {"window_sec": window_sec, "feed_gap": brief(gap, now)}}


def hold_flow(reading: dict[str, Any], gaps: Iterable[dict[str, Any]] | None, now: float,
              window_sec: float) -> dict[str, Any]:
    """A flow reading, or ``blind`` with the gap when its window touches one (no burst, no flush)."""
    gap = touching(gaps, now - window_sec, now)
    if gap is None:
        return reading
    return {
        **reading,
        "score": None,
        "label": TAPE_FLOW_BLIND,
        "readings": {k: None for k in (reading.get("readings") or {})},
        "gap": {**brief(gap, now), "text": words(gap, now)},
        "metrics": {**(reading.get("metrics") or {}), "feed_gap": brief(gap, now)},
    }
