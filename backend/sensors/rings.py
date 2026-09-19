"""In-process book/tape rings for sensor math.

Owner: this module.
Invalidation: process start (reset) or overflow trim.
Not persisted -- live observation only. schema_version n/a.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any

from constants_sensors import SENSOR_BOOK_RING, SENSOR_TAPE_RING

_books: dict[str, deque[dict[str, Any]]] = {}
_prints: dict[str, deque[dict[str, Any]]] = {}


def reset_for_tests() -> None:
    _books.clear()
    _prints.clear()


def observe_book(symbol: str, book: dict[str, Any], *, now: float | None = None) -> None:
    sym = (symbol or "").strip().upper()
    if not sym or not isinstance(book, dict):
        return
    row = {
        "ts": float(now if now is not None else time.time()),
        "bids": list(book.get("bids") or []),
        "asks": list(book.get("asks") or []),
        "l1_fallback": bool(book.get("l1_fallback")),
    }
    buf = _books.setdefault(sym, deque(maxlen=SENSOR_BOOK_RING))
    buf.append(row)


def observe_print(symbol: str, payload: dict[str, Any]) -> None:
    sym = (symbol or "").strip().upper()
    if not sym or not isinstance(payload, dict):
        return
    if payload.get("type") and payload.get("type") not in ("print", "trade"):
        return
    buf = _prints.setdefault(sym, deque(maxlen=SENSOR_TAPE_RING))
    buf.append(dict(payload))


def recent_books(symbol: str, limit: int | None = None) -> list[dict[str, Any]]:
    buf = _books.get((symbol or "").strip().upper())
    if not buf:
        return []
    rows = list(buf)
    if limit is not None:
        return rows[-max(1, int(limit)) :]
    return rows


def recent_prints(symbol: str, limit: int | None = None) -> list[dict[str, Any]]:
    buf = _prints.get((symbol or "").strip().upper())
    if not buf:
        return []
    rows = list(buf)
    if limit is not None:
        return rows[-max(1, int(limit)) :]
    return rows
