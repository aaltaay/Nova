"""The book watcher's readings (ADR 033), shaped for ``/sensors/book-pulls`` and its event feed.

Plain dicts: the sensors adapter wraps them in the sensor envelope, so this
package never imports the sensors package.
"""
from __future__ import annotations

import time
from typing import Any

from book_watch import live
from book_watch.constants_book_watch import (
    BOOK_WATCH_CAVEATS,
    BOOK_WATCH_HIDDEN_NOTE,
    BOOK_WATCH_NOTE,
    BOOK_WATCH_OFF_REASON,
    BOOK_WATCH_READ_LIMIT,
    BOOK_WATCH_SCHEMA_VERSION,
)


def _base() -> dict[str, Any]:
    return {"schema_version": BOOK_WATCH_SCHEMA_VERSION, "source": "ibkr_depth",
            "caveats": list(BOOK_WATCH_CAVEATS), "note": BOOK_WATCH_NOTE}


def book_pulls(symbol: str) -> tuple[dict[str, Any], str | None]:
    """One symbol's reading and, when there is none, the reason."""
    if not live.enabled():
        return {**_base(), "watching": False}, BOOK_WATCH_OFF_REASON
    snap = live.snapshot(symbol)
    if snap is None:
        return {**_base(), "watching": False}, (
            f"No Level 2 line for {symbol} has reached the book watcher: it follows only the symbols "
            "Nova holds depth for (at most 3). Open its Level 2 or record it.")
    flags = snap.pop("flags")[:BOOK_WATCH_READ_LIMIT]
    pulls = snap.pop("pulls_recent")[:BOOK_WATCH_READ_LIMIT]
    hidden = snap.pop("hidden_recent")[:BOOK_WATCH_READ_LIMIT]
    return {**_base(), **snap, "flags": flags, "pulls_recent": pulls, "hidden_recent": hidden,
            "hidden_note": BOOK_WATCH_HIDDEN_NOTE}, None


def book_pull_events(since: float | None, symbol: str | None) -> dict[str, Any]:
    """Flags newer than ``since`` across the watched lines, oldest first -- a poller's feed."""
    return {
        "schema_version": BOOK_WATCH_SCHEMA_VERSION,
        "now": time.time(),
        "since": since,
        "flags": live.flags_since(since if since is not None else 0.0, symbol),
        "hidden": live.hidden_since(since if since is not None else 0.0, symbol),
        "watcher": live.status(),
        "note": BOOK_WATCH_NOTE,
    }


def hidden_now(symbol: str, window_sec: float, now: float | None = None) -> dict[str, Any] | None:
    """The hidden sellers and buyers holding, or heard from in the last ``window_sec``, newest first;
    None while the watcher follows no fresh depth line for the symbol (unknown, never "none")."""
    now = time.time() if now is None else now
    snap = live.snapshot(symbol, now)
    if snap is None or not snap["watching"]:
        return None
    # A stretch whose book later showed as much as traded there hides nothing any more.
    rows = [h for h in snap["hidden_recent"]
            if h["hidden"] > 0 and (h["state"] == "holding" or h["ts"] >= now - window_sec)]
    return {"stretches": rows, "window_sec": window_sec, "note": BOOK_WATCH_HIDDEN_NOTE}


def spoof_hints(symbol: str, limit: int) -> list[dict[str, Any]]:
    """The L2 sensor's hints: the watcher's newest large pulls (unfilled size), newest first."""
    snap = live.snapshot(symbol)
    if snap is None:
        return []
    return [
        {"side": p["side"], "price": p["price"], "from_size": p["level_before"], "pulled": p["pulled"],
         "filled": p["filled"], "ts": p["ts"]}
        for p in snap["pulls_recent"][:limit]
    ]
