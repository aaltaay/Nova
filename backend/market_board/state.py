"""The Market page's memory (ADR 053): each read's last good answer, each source's health, and who is looking.

Owner: this module; ``market_board.keep`` writes the IBKR answers to disk and restores them at start, each with its
own answer time. A read is a key ("quotes", "closes:XLK", "holdings:XLK") answered by one source. A failed read
keeps its last good answer for ``MARKET_STALE_MAX_SEC`` (or twice its refresh time, whichever is longer); after that
it reads ``None`` -- unknown, never another source's number.
"""
from __future__ import annotations

import threading
from typing import Any

from constants_market_board import MARKET_RETRY_SEC, MARKET_STALE_MAX_SEC, MARKET_WANTED_SEC

SOURCES: tuple[tuple[str, str], ...] = (
    ("ibkr", "IBKR"),
    ("ssga", "State Street holdings"),
    ("bea", "BEA calendar"),
    ("finnhub", "Finnhub earnings"),
    ("leaderboard", "Nova's scanner history"),
)
_RESULT_RECENT_SEC = 3600.0


class Stated(Exception):
    """A read failed for a known reason; its message is what the page shows (logged without a traceback)."""


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, tuple[Any, float]] = {}
        self._result: dict[str, tuple[str, bool, float, str | None]] = {}
        self._next: dict[str, float] = {}
        self._down: dict[str, str] = {}
        self._wanted_until = 0.0
        self._wanted_since: float | None = None
        self._version = 0

    # -- who is looking ----------------------------------------------------------------------------------------
    def want(self, now: float) -> None:
        with self._lock:
            if now >= self._wanted_until:
                self._wanted_since = now
            self._wanted_until = now + MARKET_WANTED_SEC

    def wanted(self, now: float) -> bool:
        with self._lock:
            return now < self._wanted_until

    def wanted_since(self) -> float | None:
        with self._lock:
            return self._wanted_since

    # -- answers -----------------------------------------------------------------------------------------------
    def put(self, key: str, source: str, value: Any, now: float) -> None:
        with self._lock:
            self._data[key] = (value, now)
            self._result[key] = (source, True, now, None)
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

    def version(self) -> int:
        """Bumped by every answer, so a writer can tell whether anything changed since it last looked."""
        with self._lock:
            return self._version

    def entries(self, keep: Any) -> dict[str, tuple[Any, float]]:
        """``{key: (value, at)}`` for every key ``keep(key)`` accepts."""
        with self._lock:
            return {k: v for k, v in self._data.items() if keep(k)}

    def fail(self, key: str, source: str, error: str, now: float, retry: float = MARKET_RETRY_SEC) -> None:
        with self._lock:
            self._result[key] = (source, False, now, error)
            self._next[key] = now + retry

    def defer(self, key: str, until: float) -> None:
        with self._lock:
            self._next[key] = until

    def source_down(self, source: str, why: str | None) -> None:
        with self._lock:
            if why:
                self._down[source] = why
            else:
                self._down.pop(source, None)

    def get(self, key: str, now: float, ttl: float = 0.0) -> Any | None:
        with self._lock:
            got = self._data.get(key)
        if got is None:
            return None
        value, at = got
        return value if now - at <= max(MARKET_STALE_MAX_SEC, 2 * ttl) else None

    def merged(self, prefix: str, now: float, ttl: float = 0.0) -> dict[str, Any]:
        """Every ``prefix<n>`` answer (a read done in chunks) merged into one dict, each by its own age rule."""
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
        out: dict[str, Any] = {}
        for key in sorted(keys):
            value = self.get(key, now, ttl)
            if isinstance(value, dict):
                out.update(value)
        return out

    def answered_at(self, key: str) -> float | None:
        with self._lock:
            got = self._data.get(key)
            return got[1] if got else None

    def error(self, key: str) -> str | None:
        with self._lock:
            res = self._result.get(key)
        return res[3] if res and not res[1] else None

    def tried(self, key: str) -> bool:
        """The read answered or failed at least once in this process."""
        with self._lock:
            return key in self._result

    def tried_since(self, key: str, since: float | None) -> bool:
        with self._lock:
            res = self._result.get(key)
        return res is not None and since is not None and res[2] >= since

    def due(self, key: str, now: float, ttl: float) -> bool:
        with self._lock:
            if now < self._next.get(key, 0.0):
                return False
            got = self._data.get(key)
            return got is None or now - got[1] >= ttl

    def statuses(self, now: float) -> list[dict]:
        """``[{id, label, ok, at, error}]`` in ``SOURCES`` order; ``ok: None`` until a read of it was tried."""
        with self._lock:
            results = list(self._result.items())
            down = dict(self._down)
        out = []
        for sid, label in SOURCES:
            mine = [(k, r) for k, r in results if r[0] == sid and now - r[2] <= _RESULT_RECENT_SEC]
            last_ok = max((r[2] for _, r in mine if r[1]), default=None)
            failing = sorted(((k, r) for k, r in mine if not r[1]), key=lambda kr: kr[1][2], reverse=True)
            if sid in down:
                ok, error = False, down[sid]
            elif failing:
                ok, error = False, f"{failing[0][0].replace(':', ' ')}: {failing[0][1][3] or 'failed'}"
            else:
                ok, error = (True if mine else None), None
            out.append({"id": sid, "label": label, "ok": ok, "at": last_ok, "error": error})
        return out

    def reset(self) -> None:
        with self._lock:
            self._data.clear()
            self._result.clear()
            self._next.clear()
            self._down.clear()
            self._wanted_until = 0.0
            self._wanted_since = None
            self._version = 0


_store = Store()


def store() -> Store:
    return _store
