"""Versions of each symbol's Level 2 book and quote (ADR 045).

A version is ``(seq, at)``: ``seq`` goes up by one on every change and is never reset while the
process runs; ``at`` is when Nova applied the change (epoch seconds). The last
``MARKET_VIEW_HISTORY_KEEP`` versions are kept, so the gate can answer "when was the version the
operator saw replaced?". Bumped from the IB thread and read from the socket loop: every access
takes the one lock, and nothing under it waits.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

from constants_market_view import MARKET_VIEW_HISTORY_KEEP

BOOK = "book"
QUOTE = "quote"


@dataclass(frozen=True)
class Version:
    seq: int
    at: float


@dataclass(frozen=True)
class Replaced:
    """How a version the desk showed stands now.

    ``current``: it is the newest. Otherwise ``at`` is when the next one replaced it, or, for a
    version older than the kept history, ``at`` is the oldest kept (it was replaced before that)
    with ``before_history`` set. ``unknown`` is a ``seq`` past the newest (another process's).
    """

    current: bool
    at: float | None = None
    before_history: bool = False
    unknown: bool = False


class _Track:
    __slots__ = ("seq", "times", "pending")

    def __init__(self) -> None:
        self.seq = 0
        # times[i] is when version (seq - len(times) + 1 + i) was applied.
        self.times: deque[float] = deque(maxlen=MARKET_VIEW_HISTORY_KEEP)
        self.pending: set[int] = set()


_lock = threading.Lock()
_tracks: dict[tuple[str, str], _Track] = {}


def bump(stream: str, symbol: str, at: float | None = None, *, pending: bool = False) -> Version:
    """A new version of ``symbol``'s ``stream``: the next ``seq``, applied at ``at`` (now by default)."""
    when = time.time() if at is None else float(at)
    key = (stream, symbol.upper())
    with _lock:
        track = _tracks.get(key)
        if track is None:
            track = _tracks[key] = _Track()
        track.seq += 1
        track.times.append(when)
        if pending:
            track.pending.add(track.seq)
        return Version(track.seq, when)


def commit(stream: str, symbol: str, seq: int) -> None:
    """Mark a pre-bumped ``seq`` as delivered so a later replay transition cannot unbump it."""
    with _lock:
        track = _tracks.get((stream, symbol.upper()))
        if track is not None:
            track.pending.discard(seq)


def unbump(stream: str, symbol: str, seq: int, at: float | None = None) -> bool:
    """Roll back an undelivered ``pending`` version when its frame is suppressed on replay (#867)."""
    key = (stream, symbol.upper())
    with _lock:
        track = _tracks.get(key)
        if track is None or not track.times or seq not in track.pending:
            return False
        oldest = track.seq - len(track.times) + 1
        if seq < oldest or seq > track.seq:
            track.pending.discard(seq)
            return False
        idx = seq - oldest
        if at is not None and track.times[idx] != float(at):
            return False
        while len(track.times) > idx:
            track.pending.discard(track.seq)
            track.times.pop()
            track.seq -= 1
        if track.seq <= 0 or not track.times:
            _tracks.pop(key, None)
        return True



def latest(stream: str, symbol: str) -> Version | None:
    """The newest version, or None before the first."""
    with _lock:
        track = _tracks.get((stream, symbol.upper()))
        if track is None or not track.seq:
            return None
        return Version(track.seq, track.times[-1])


def replaced(stream: str, symbol: str, seq: int) -> Replaced:
    """When the version ``seq`` was replaced by the next one (see ``Replaced``)."""
    with _lock:
        track = _tracks.get((stream, symbol.upper()))
        newest = track.seq if track is not None else 0
        if seq > newest or seq < 1:
            return Replaced(current=False, unknown=True)
        if seq == newest:
            return Replaced(current=True)
        assert track is not None
        oldest = newest - len(track.times) + 1
        nxt = seq + 1
        if nxt < oldest:
            return Replaced(current=False, at=track.times[0], before_history=True)
        return Replaced(current=False, at=track.times[nxt - oldest])


def reset_for_tests() -> None:
    with _lock:
        _tracks.clear()
