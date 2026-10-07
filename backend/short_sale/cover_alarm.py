"""The day cover's alarm (ADR 048 decision 5, step 6): a short whose cover could not go out, on any venue.

In memory only. ``short_sale.closes`` (Paper and Sim) and ``short_sale.live_closes`` (Live) raise one per
venue and symbol when a cover due cannot go out -- the venue refused it or a cancel before it, IBKR is not
connected, or Live stands outside the regular session -- and clear it when a cover goes out or the short is
gone. The bot session carries ``view()`` (``shorts.day_cover``), which every desk window polls, and each
window shows a red banner while one holds.

An alarm is ``{id, venue, symbol, qty, kind: "refused" | "disconnected" | "outside_session", since,
updated, error, reason_code, text, last_seen}`` -- ``last_seen`` (epoch seconds) when the short is the one
IBKR last reported before it went quiet, else null.
"""
from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_alarms: dict[tuple[str, str], dict[str, Any]] = {}
VENUE_WORDS = {"live": "Live", "paper": "Paper", "sim": "Sim"}


def raise_(venue: str, symbol: str, qty: float, *, kind: str, text: str, error: str | None = None,
           reason_code: str | None = None, last_seen: float | None = None, now: float | None = None) -> None:
    """Raise (or refresh) the alarm for ``symbol`` short on ``venue``."""
    at = time.time() if now is None else float(now)
    key = (venue, symbol.upper())
    with _lock:
        prior = _alarms.get(key)
        _alarms[key] = {"id": f"{venue}:{symbol.upper()}", "venue": venue, "symbol": symbol.upper(),
                        "qty": abs(float(qty)), "kind": kind, "since": prior["since"] if prior else at,
                        "updated": at, "error": error, "reason_code": reason_code, "text": text,
                        "last_seen": last_seen}


def clear(venue: str, symbol: str) -> None:
    with _lock:
        _alarms.pop((venue, symbol.upper()), None)


def keep_only(venue: str, symbols: set[str]) -> None:
    """Clear ``venue``'s alarms for every symbol no longer short there."""
    keep = {s.upper() for s in symbols}
    with _lock:
        for key in [k for k in _alarms if k[0] == venue and k[1] not in keep]:
            _alarms.pop(key, None)


def view() -> dict[str, Any]:
    """``{alarms: [...]}``, the oldest first."""
    with _lock:
        alarms = sorted((dict(a) for a in _alarms.values()), key=lambda a: (a["since"], a["id"]))
    return {"alarms": alarms}


def reset_for_tests() -> None:
    with _lock:
        _alarms.clear()
