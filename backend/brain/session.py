"""The brain's session: which program holds the door, its heartbeat, its note, what it reads, and today's events.

One program on this PC is the brain. The first session id to claim holds the door until its heartbeat is
``BRAIN_HEARTBEAT_STALE_SEC`` old; another id is refused until then (``Held``). Memory only: a backend restart ends
the claim and the brain claims again. Events are today's (the desk day, 04:00 ET), newest first.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from brain.constants_brain import (
    BRAIN_EVENT_KINDS,
    BRAIN_EVENTS_MAX,
    BRAIN_HEARTBEAT_STALE_SEC,
    BRAIN_NOTE_MAX,
    BRAIN_READING_MAX,
)

_lock = threading.Lock()
_holder: str | None = None
_beat_at: float | None = None
_note: dict[str, Any] | None = None
_reading: list[dict[str, str]] = []
_events: deque[dict[str, Any]] = deque(maxlen=BRAIN_EVENTS_MAX)
_events_day: str | None = None
_silent_said = False


class Held(Exception):
    """Another program's heartbeat is fresh: the door is its."""


class NotClaimed(Exception):
    """A write from a session that has not claimed the door (or lost it)."""


def _now(now: float | None) -> float:
    return time.time() if now is None else float(now)


def _fresh(t: float) -> bool:
    return _beat_at is not None and t - _beat_at <= BRAIN_HEARTBEAT_STALE_SEC


def connected(now: float | None = None) -> bool:
    """The brain's program answered within ``BRAIN_HEARTBEAT_STALE_SEC``."""
    with _lock:
        return _holder is not None and _fresh(_now(now))


def claim(session_id: str, now: float | None = None) -> bool:
    """``session_id`` takes the door, or keeps it; True when it is newly its. ``Held`` while another's is fresh."""
    global _holder, _beat_at, _silent_said
    sid = (session_id or "").strip()
    if not sid:
        raise NotClaimed("the brain's session id is missing")
    t = _now(now)
    with _lock:
        if _holder not in (None, sid) and _fresh(t):
            raise Held("another program holds the brain's door: its heartbeat is fresh")
        new = _holder != sid or not _fresh(t)
        _holder, _beat_at, _silent_said = sid, t, False
        return new


def beat(session_id: str, now: float | None = None) -> None:
    """The holder says it is alive. ``NotClaimed`` for any other session."""
    global _beat_at, _silent_said
    sid = (session_id or "").strip()
    with _lock:
        if not sid or sid != _holder:
            raise NotClaimed("this program has not claimed the brain's door (POST /api/brain/claim)")
        _beat_at, _silent_said = _now(now), False


def went_silent(now: float | None = None) -> bool:
    """True once, the first time the holder's heartbeat is found stale: the caller says so on the stream."""
    global _silent_said
    with _lock:
        if _holder is None or _fresh(_now(now)) or _silent_said:
            return False
        _silent_said = True
        return True


def view(session_id: str | None = None, now: float | None = None) -> dict[str, Any]:
    with _lock:
        return {"held": _holder is not None and _fresh(_now(now)), "mine": bool(session_id) and session_id == _holder,
                "heartbeat_at": _beat_at}


def set_note(text: str | None, reading: list[dict[str, Any]] | None = None, now: float | None = None) -> None:
    """The brain's words for its pill and panel, and what it is reading now (``None`` keeps the list)."""
    global _note, _reading
    words = (text or "").strip()[:BRAIN_NOTE_MAX]
    with _lock:
        if words:
            _note = {"text": words, "at": _now(now)}
        if reading is not None:
            rows = []
            for row in reading[:BRAIN_READING_MAX]:
                sym = str(row.get("symbol") or "").strip().upper()
                if sym:
                    rows.append({"symbol": sym, "text": str(row.get("text") or "").strip()[:BRAIN_NOTE_MAX]})
            _reading = rows


def note() -> dict[str, Any] | None:
    with _lock:
        return dict(_note) if _note else None


def reading() -> list[dict[str, str]]:
    with _lock:
        return [dict(r) for r in _reading]


def _day(t: float) -> str:
    from traders.switches import desk_day

    return desk_day(t)


def event(kind: str, text: str, symbol: str | None = None, now: float | None = None) -> dict[str, Any]:
    """One line on the brain's stream (and the log). Yesterday's lines are dropped at the desk day's rollover."""
    global _events_day
    assert kind in BRAIN_EVENT_KINDS, kind
    import logging

    t = switch_clock() if now is None else float(now)
    row = {"at": t, "kind": kind, "symbol": (symbol or "").upper() or None, "text": text}
    day = _day(t)
    with _lock:
        if _events_day != day:
            _events.clear()
            _events_day = day
        _events.appendleft(row)
    logging.getLogger(__name__).info("BRAIN %s: %s", kind, text)
    return row


def switch_clock() -> float:
    from traders.switches import now_ts

    return now_ts()


def events(now: float | None = None) -> list[dict[str, Any]]:
    day = _day(switch_clock() if now is None else float(now))
    with _lock:
        return [dict(e) for e in _events] if _events_day == day else []


def reset_for_tests() -> None:
    global _holder, _beat_at, _note, _reading, _events_day, _silent_said
    with _lock:
        _holder = _beat_at = _note = _events_day = None
        _reading = []
        _events.clear()
        _silent_said = False
