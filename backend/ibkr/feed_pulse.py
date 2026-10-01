"""Is IBKR data arriving? The feed's heartbeat and its gaps (#672, #673).

Every IBKR market-data handler -- L1 (``ticks_handler.on_ticker_update``),
tick-by-tick (``tape_events.on_tape_update``) and depth
(``depth.handlers.on_update_book``) -- calls ``note()`` on the IB loop. That costs
a clock read and a comparison per event; the whole seconds with data are kept
once a second.

A **gap** is a stretch with no market-data message on any line for at least
``FEED_GAP_SEC``, after a busy stretch (data in at least ``FEED_GAP_BUSY_FRACTION``
of the ``FEED_GAP_BUSY_WINDOW_SEC`` whole seconds before it, seconds inside an
earlier gap not counted), inside the 04:00-20:00 ET session of an exchange day.
An open gap is reported only while the Gateway session is ready (a disconnect is
the header's own state). A thin feed that is quiet for seconds, or the market
closing at 20:00, is never a gap.

Why (2026-10-01 09:31-09:32 ET): the desk's Wi-Fi re-authenticated five times and
no IBKR data reached Nova for 4, 4, 8, 16 and 4 s while both loops stayed under
15 ms. The charts and Time & Sales froze and nothing said why; the held data then
arrived in one burst, stamped on arrival (#563). ``view()`` answers
``GET /api/ibkr/feed`` (the desk's NO DATA chip), ``gaps_for_tape()`` the setup
scanner's tape hold (``setup_scanner/tape_gap.py``).

In memory only: a restart forgets the gaps.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_feed import (
    FEED_GAP_BUSY_FRACTION,
    FEED_GAP_BUSY_MIN_SEC,
    FEED_GAP_BUSY_WINDOW_SEC,
    FEED_GAP_KEEP,
    FEED_GAP_SEC,
    FEED_GAP_SECONDS_KEEP,
    FEED_GAP_SETTLE_SEC,
    FEED_PULSE_SCHEMA_VERSION,
    FEED_SESSION_END_ET,
    FEED_SESSION_START_ET,
)
from ibkr import wifi_drops

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
TAPE_HORIZON_SEC = 900.0  # closed gaps a tape read can still reach (the longest flow history, with room)

_lock = threading.Lock()
_last: float | None = None
_first: float | None = None
_seconds: deque[int] = deque(maxlen=FEED_GAP_SECONDS_KEEP)
_gaps: deque[dict[str, float]] = deque(maxlen=FEED_GAP_KEEP)
_logged_open: float | None = None


def note(now: float | None = None) -> None:
    """A market-data message arrived. Closes a gap when the silence before it was one."""
    global _last, _first
    t = time.time() if now is None else now
    last = _last
    if last is not None and t - last >= FEED_GAP_SEC:
        _close(last, t)
    _last = t
    if _first is None:
        _first = t
    sec = int(t)
    if not _seconds or _seconds[-1] != sec:
        with _lock:
            _seconds.append(sec)


def _close(start: float, end: float) -> None:
    if not (_in_session(start) and _in_session(end) and _et(start).date() == _et(end).date()
            and _busy_before(start)):
        return
    with _lock:
        _gaps.append({"start": start, "end": end})
    logger.warning("IBKR feed: no market data on any line for %.1f s (%s-%s ET); what IBKR held arrived at once",
                   end - start, _clock(start), _clock(end))
    wifi_drops.lookup(start, end, now=end)


def _busy_before(ts: float) -> bool:
    """Data arrived in most of the known whole seconds just before ``ts``."""
    end_sec = int(ts)
    with _lock:
        have = set(_seconds)
        gaps = list(_gaps)
    first_sec = int(_first) if _first is not None else end_sec
    known = [s for s in range(end_sec - FEED_GAP_BUSY_WINDOW_SEC + 1, end_sec + 1)
             if s >= first_sec and not _inside(s, gaps)]
    if len(known) < FEED_GAP_BUSY_MIN_SEC:
        return False
    return sum(1 for s in known if s in have) >= FEED_GAP_BUSY_FRACTION * len(known)


def _inside(sec: int, gaps: list[dict[str, float]]) -> bool:
    """The whole second ``[sec, sec + 1)`` fell inside a gap's silence."""
    return any(g["start"] < sec and sec + 1 <= g["end"] for g in gaps)


def _et(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, ET)


def _clock(ts: float) -> str:
    return _et(ts).strftime("%H:%M:%S")


def _in_session(ts: float) -> bool:
    from sim.trading_day import last_open_day

    t = _et(ts)
    if last_open_day(t.date()) != t.date():
        return False
    return FEED_SESSION_START_ET <= (t.hour, t.minute) < FEED_SESSION_END_ET


def _connected() -> bool:
    try:
        from ibkr import client
        return bool(client.is_ready())
    except Exception:
        logger.debug("feed_pulse: IBKR readiness unknown", exc_info=True)
        return False


def open_gap(now: float | None = None) -> dict[str, Any] | None:
    """The gap still open at ``now`` -- ``{start, end: None}`` -- or ``None``."""
    t = time.time() if now is None else now
    last = _last
    if last is None or t - last < FEED_GAP_SEC:
        return None
    if not (_in_session(t) and _in_session(last) and _busy_before(last) and _connected()):
        return None
    return {"start": last, "end": None}


def gaps_for_tape(now: float | None = None) -> list[dict[str, Any]]:
    """Every gap a tape read at ``now`` could reach: the open one and the closed ones of the last
    ``TAPE_HORIZON_SEC``, as ``{start, end}`` (``end`` ``None`` while open)."""
    t = time.time() if now is None else now
    with _lock:
        out: list[dict[str, Any]] = [dict(g) for g in _gaps if g["end"] >= t - TAPE_HORIZON_SEC]
    live = open_gap(t)
    if live is not None:
        out.append(live)
    return out


def _gap_view(gap: dict[str, Any], now: float) -> dict[str, Any]:
    start, end = gap["start"], gap.get("end")
    stop = end if end is not None else now
    wifi = wifi_drops.lookup(start, end, now=now)
    hits = wifi_drops.overlapping(wifi["drops"], start, stop)
    view = {
        "start": start,
        "end": end,
        "silent_sec": round(stop - start, 1),
        "ongoing": end is None,
        "cause": "wifi" if hits else None,
        "wifi": {"state": wifi["state"], "drops": hits},
    }
    view["text"] = gap_text(view)
    return view


def gap_text(gap: dict[str, Any]) -> str:
    """One gap in plain words, for the desk's hover and the checklist."""
    start, end = gap["start"], gap.get("end")
    secs = f"{gap['silent_sec']:.0f} s"
    drops = (gap.get("wifi") or {}).get("drops") or []
    downs = [d["stopped"] for d in drops if d.get("stopped") is not None]
    wifi = (f" Windows logged the Wi-Fi reconnecting at {', '.join(_clock(t) for t in downs)} ET."
            if downs else " Windows logged the Wi-Fi coming back." if drops else "")
    if end is None:
        return (f"No IBKR data on any line for {secs} (since {_clock(start)} ET) while IB Gateway is connected."
                f"{wifi} Nova is running; nothing is arriving from the Gateway"
                f"{'' if drops else ' (the network or the Gateway)'}.")
    return (f"No IBKR data for {secs} ({_clock(start)}-{_clock(end)} ET).{wifi} What IBKR held arrived at "
            f"{_clock(end)} in one burst, stamped when it arrived; Nova did not read the tape across it.")


def view(now: float | None = None) -> dict[str, Any]:
    """``GET /api/ibkr/feed``: is data arriving, the open gap, and the recent closed ones (newest first)."""
    global _logged_open
    t = time.time() if now is None else now
    last = _last
    live = open_gap(t)
    if live is not None and _logged_open != live["start"]:
        _logged_open = live["start"]
        logger.warning("IBKR feed: no market data on any line since %s ET while the Gateway is connected",
                       _clock(live["start"]))
    with _lock:
        closed = [dict(g) for g in _gaps]
    return {
        "schema_version": FEED_PULSE_SCHEMA_VERSION,
        "now": t,
        "connected": _connected(),
        "in_session": _in_session(t),
        "last_data_ts": last,
        "silent_sec": round(t - last, 1) if last is not None else None,
        "gap": _gap_view(live, t) if live is not None else None,
        "recent": [_gap_view(g, t) for g in reversed(closed)],
        "rule": {
            "gap_sec": FEED_GAP_SEC,
            "settle_sec": FEED_GAP_SETTLE_SEC,
            "busy_window_sec": FEED_GAP_BUSY_WINDOW_SEC,
            "busy_fraction": FEED_GAP_BUSY_FRACTION,
        },
    }


def _reset_for_tests() -> None:
    global _last, _first, _logged_open
    with _lock:
        _last = _first = _logged_open = None
        _seconds.clear()
        _gaps.clear()
