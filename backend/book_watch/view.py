"""The book watcher's readings (ADR 031), shaped for ``/sensors/book-pulls`` and its event feed.

Plain dicts: the sensors adapter wraps them in the sensor envelope, so this
package never imports the sensors package.
"""
from __future__ import annotations

import time
from typing import Any

from book_watch import live
from book_watch.constants_book_watch import (
    BOOK_WATCH_CAVEATS,
    BOOK_WATCH_NOTE,
    BOOK_WATCH_READ_LIMIT,
    BOOK_WATCH_SCHEMA_VERSION,
)


def _base() -> dict[str, Any]:
    return {"schema_version": BOOK_WATCH_SCHEMA_VERSION, "source": "ibkr_depth",
            "caveats": list(BOOK_WATCH_CAVEATS), "note": BOOK_WATCH_NOTE}


def book_pulls(symbol: str) -> tuple[dict[str, Any], str | None]:
    """One symbol's reading and, when there is none, the reason."""
    if not live.enabled():
        return {**_base(), "watching": False}, "The book watcher is off (NOVA_BOOK_WATCH=0)."
    snap = live.snapshot(symbol)
    if snap is None:
        return {**_base(), "watching": False}, (
            f"No Level 2 line for {symbol} has reached the book watcher: it follows only the symbols "
            "Nova holds depth for (at most 3). Open its Level 2 or record it.")
    flags = snap.pop("flags")[:BOOK_WATCH_READ_LIMIT]
    pulls = snap.pop("pulls")[:BOOK_WATCH_READ_LIMIT]
    return {**_base(), **snap, "flags": flags, "pulls_recent": pulls}, None


def book_pull_events(since: float | None, symbol: str | None) -> dict[str, Any]:
    """Flags newer than ``since`` across the watched lines, oldest first -- a poller's feed."""
    return {
        "schema_version": BOOK_WATCH_SCHEMA_VERSION,
        "now": time.time(),
        "since": since,
        "flags": live.flags_since(since if since is not None else 0.0, symbol),
        "watcher": live.status(),
        "note": BOOK_WATCH_NOTE,
    }


def spoof_hints(symbol: str, limit: int) -> list[dict[str, Any]]:
    """The L2 sensor's hints: the watcher's newest large pulls (unfilled size), newest first."""
    snap = live.snapshot(symbol)
    if snap is None:
        return []
    return [
        {"side": p["side"], "price": p["price"], "from_size": p["level_before"], "pulled": p["pulled"],
         "filled": p["filled"], "ts": p["ts"]}
        for p in snap["pulls"][:limit]
    ]
