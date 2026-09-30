"""The Cryptos page's memory (ADR 040): each read's last good answer, each source's health, and who is looking.

Owner: this module; nothing is written to disk. A read is a key ("markets", "candles:BTC:15m", "closes:MSTR")
answered by one source. A failed read keeps its last good answer until it is older than the key's max age
(``CRYPTO_STALE_MAX_SEC`` or twice its refresh time, whichever is longer); after that it reads ``None`` --
unknown, never another source's number. A source is healthy when every read of it tried lately answered.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from constants_crypto import CRYPTO_RETRY_SEC, CRYPTO_STALE_MAX_SEC, CRYPTO_WANTED_SEC

SOURCES: tuple[tuple[str, str], ...] = (
    ("coingecko", "CoinGecko"),
    ("coinbase", "Coinbase"),
    ("fear_greed", "alternative.me"),
    ("hyperliquid", "Hyperliquid"),
    ("defillama", "DefiLlama"),
    ("deribit", "Deribit"),
    ("alpaca", "Alpaca news"),
    ("ibkr", "IBKR"),
)
_LABELS = dict(SOURCES)
_RESULT_RECENT_SEC = 3600.0  # a read's result counts toward its source's health this long


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, tuple[Any, float]] = {}            # key -> (value, answered at)
        self._result: dict[str, tuple[str, bool, float, str | None]] = {}  # key -> (source, ok, at, error)
        self._next: dict[str, float] = {}                        # key -> earliest next try
        self._blocked: dict[str, float] = {}                     # source -> no try before (a 429)
        self._down: dict[str, str] = {}                          # source -> why none of its reads can run
        self._wanted_until = 0.0
        self._wanted_since: float | None = None
        self._candles: dict[tuple[str, str], float] = {}         # (symbol, tf) -> wanted until

    # -- who is looking ------------------------------------------------------------------------------
    def want(self, now: float) -> bool:
        """Mark the board wanted; True when this starts a new look (nobody was looking)."""
        with self._lock:
            fresh = now >= self._wanted_until
            if fresh:
                self._wanted_since = now
            self._wanted_until = now + CRYPTO_WANTED_SEC
            return fresh

    def wanted(self, now: float) -> bool:
        with self._lock:
            return now < self._wanted_until

    def wanted_since(self) -> float | None:
        with self._lock:
            return self._wanted_since

    def want_candles(self, symbol: str, tf: str, now: float) -> None:
        with self._lock:
            self._candles[(symbol, tf)] = now + CRYPTO_WANTED_SEC
            self.want(now)

    def wanted_candles(self, now: float) -> list[tuple[str, str]]:
        with self._lock:
            for key in [k for k, until in self._candles.items() if until <= now]:
                del self._candles[key]
            return sorted(self._candles)

    # -- answers -------------------------------------------------------------------------------------
    def put(self, key: str, source: str, value: Any, now: float) -> None:
        with self._lock:
            self._data[key] = (value, now)
            self._result[key] = (source, True, now, None)
            self._next.pop(key, None)
            self._down.pop(source, None)

    def fail(self, key: str, source: str, error: str, now: float, retry: float = CRYPTO_RETRY_SEC) -> None:
        with self._lock:
            self._result[key] = (source, False, now, error)
            self._next[key] = now + retry
            if error.startswith("HTTP 429"):
                self._blocked[source] = now + retry

    def defer(self, key: str, until: float) -> None:
        """Try ``key`` again no sooner than ``until`` without calling it a failure (IBKR's budget said later)."""
        with self._lock:
            self._next[key] = until

    def source_down(self, source: str, why: str | None) -> None:
        """Record that none of ``source``'s reads can run now (IBKR not connected), or clear it."""
        with self._lock:
            if why:
                self._down[source] = why
            else:
                self._down.pop(source, None)

    def get(self, key: str, now: float, ttl: float = 0.0) -> Any | None:
        """The last good answer, or ``None`` when there is none or it is too old to show."""
        with self._lock:
            got = self._data.get(key)
        if got is None:
            return None
        value, at = got
        return value if now - at <= max(CRYPTO_STALE_MAX_SEC, 2 * ttl) else None

    def answered_at(self, key: str) -> float | None:
        with self._lock:
            got = self._data.get(key)
            return got[1] if got else None

    def result(self, key: str) -> tuple[str, bool, float, str | None] | None:
        with self._lock:
            return self._result.get(key)

    def tried_since(self, key: str, since: float | None) -> bool:
        with self._lock:
            res = self._result.get(key)
        return res is not None and since is not None and res[2] >= since

    # -- scheduling ----------------------------------------------------------------------------------
    def due(self, key: str, source: str, now: float, ttl: float) -> bool:
        """Never answered, or answered longer than ``ttl`` ago -- and not waiting out a retry or a 429."""
        with self._lock:
            if now < self._next.get(key, 0.0) or now < self._blocked.get(source, 0.0):
                return False
            got = self._data.get(key)
            return got is None or now - got[1] >= ttl

    # -- health --------------------------------------------------------------------------------------
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
                ok, error = False, _what(failing[0][0], failing[0][1][3])
            else:
                ok, error = (True if mine else None), None
            out.append({"id": sid, "label": label, "ok": ok, "at": last_ok, "error": error})
        return out

    def reset(self) -> None:
        with self._lock:
            self._data.clear()
            self._result.clear()
            self._next.clear()
            self._blocked.clear()
            self._down.clear()
            self._wanted_until = 0.0
            self._wanted_since = None
            self._candles.clear()


def label(source: str) -> str:
    return _LABELS.get(source, source)


def _what(key: str, error: str | None) -> str:
    """"candles BTC 15m: HTTP 404" -- which read failed, then why."""
    return f"{key.replace(':', ' ')}: {error or 'failed'}"


_store = Store()


def store() -> Store:
    return _store


def now() -> float:
    return time.time()
