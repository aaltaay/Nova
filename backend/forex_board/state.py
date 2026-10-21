"""The Forex page's memory (ADR 061): each read's last good answer, each failure, and who is looking.

Owner: this module; ``forex_board.keep`` writes the answers to disk and restores them at start, each with its own
answer time. A read is a key (``quotes``, ``hourly:JPY``, ``daily:JPY``, ``flow:JPY``, ``flow_daily:JPY``,
``refused:future:JPY:CME``). A failed read keeps its last good answer for ``FOREX_STALE_MAX_SEC`` (a weekend: Friday's
FX day is still shown on Sunday); after that it reads ``None`` -- unknown.
"""
from __future__ import annotations

import threading
from typing import Any

from constants_forex_board import FOREX_RETRY_SEC, FOREX_STALE_MAX_SEC, FOREX_WANTED_SEC


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, tuple[Any, float]] = {}
        self._failed: dict[str, tuple[str, float]] = {}
        self._next: dict[str, float] = {}
        self._wanted_until = 0.0
        self._waiting: str | None = None
        self._source: tuple[bool | None, float | None, str | None] = (None, None, None)
        self._version = 0

    # -- who is looking ----------------------------------------------------------------------------------------
    def want(self, now: float) -> None:
        with self._lock:
            self._wanted_until = now + FOREX_WANTED_SEC

    def wanted(self, now: float) -> bool:
        with self._lock:
            return now < self._wanted_until

    # -- answers -----------------------------------------------------------------------------------------------
    def put(self, key: str, value: Any, now: float) -> None:
        with self._lock:
            self._data[key] = (value, now)
            self._failed.pop(key, None)
            self._next.pop(key, None)
            self._version += 1

    def restore(self, key: str, value: Any, at: float) -> bool:
        """A kept answer from an earlier process, at its own answer time; never over a newer one in memory."""
        with self._lock:
            got = self._data.get(key)
            if got is not None and got[1] >= at:
                return False
            self._data[key] = (value, at)
            return True

    def get(self, key: str, now: float) -> Any | None:
        with self._lock:
            got = self._data.get(key)
        if got is None or now - got[1] > FOREX_STALE_MAX_SEC:
            return None
        return got[0]

    def answered_at(self, key: str) -> float | None:
        with self._lock:
            got = self._data.get(key)
            return got[1] if got else None

    def fail(self, key: str, error: str, now: float, retry: float = FOREX_RETRY_SEC) -> None:
        with self._lock:
            self._failed[key] = (error, now)
            self._next[key] = now + retry

    def failure(self, key: str) -> tuple[str, float] | None:
        with self._lock:
            return self._failed.get(key)

    def defer(self, key: str, until: float) -> None:
        with self._lock:
            self._next[key] = until

    def held(self, key: str, now: float) -> bool:
        """A failed or deferred read waits until its retry time."""
        with self._lock:
            return now < self._next.get(key, 0.0)

    def version(self) -> int:
        with self._lock:
            return self._version

    def entries(self) -> dict[str, tuple[Any, float]]:
        with self._lock:
            return dict(self._data)

    # -- the source's health and why reads wait ----------------------------------------------------------------
    def source(self, ok: bool | None, now: float, error: str | None = None) -> None:
        with self._lock:
            self._source = (ok, now, error)

    def source_view(self) -> tuple[bool | None, float | None, str | None]:
        with self._lock:
            return self._source

    def waiting(self, why: str | None) -> None:
        with self._lock:
            self._waiting = why

    def waiting_for(self) -> str | None:
        with self._lock:
            return self._waiting

    def reset(self) -> None:
        with self._lock:
            self._data.clear()
            self._failed.clear()
            self._next.clear()
            self._wanted_until = 0.0
            self._waiting = None
            self._source = (None, None, None)
            self._version = 0


_store = Store()


def store() -> Store:
    return _store
