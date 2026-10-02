"""Shares issued, per the filings (ADR 024 amendment 2026-10-02; operator decision on #700: warn, don't block).

Per symbol, the newest SEC 8-K of the last ``CATALYST_ISSUANCE_LOOKBACK_DAYS`` that says new shares were issued
(``classify.shares_issued``: Item 3.02, or Item 2.01 the rules label a raise), from the live catalyst feed's
store. Yahoo's float and share count lag such a filing by weeks (AMOD read 630,935 and 4,966,818 after issuing
51,621,560 shares), so the desk shows the float as "631K?" with the filing named -- scanner rows and the
Trader's fundamentals (``stamp``) -- and ``/api/why`` reads the float as unknown. A warning only: no max-float
gate reads it, and the float shown is still Yahoo's.

Owner: this module (in memory). A background pass re-reads the store every ``CATALYST_ISSUANCE_REFRESH_SEC``
(one filtered query, off the loop); readers only look the symbol up, so serving a row never waits on disk.
Invalidation: the map is replaced whole on every pass, and a filing older than the look-back leaves it. No
disk state of its own; with no store on disk the map stays empty (nothing on file, never "no issuance").
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from catalysts import feed_store
from catalysts.classify import shares_issued
from constants_catalysts import CATALYST_ISSUANCE_LOOKBACK_DAYS, CATALYST_ISSUANCE_REFRESH_SEC

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

_lock = threading.Lock()
_by_symbol: dict[str, dict] = {}


def refresh(now: float | None = None, db: sqlite3.Connection | None = None) -> int:
    """Rebuild the map from the feed's store; returns the symbols with a filing on file."""
    now = time.time() if now is None else now
    since = now - CATALYST_ISSUANCE_LOOKBACK_DAYS * 86400
    if db is None and not feed_store.path().exists():
        rows: list[dict[str, Any]] = []
    else:
        con = db if db is not None else feed_store.connect()
        try:
            rows = feed_store.issuance_candidates(con, since)
        finally:
            if db is None:
                con.close()
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for item in rows:
        for ticker in item["tickers"]:
            by_ticker[ticker.strip().upper()].append(item)
    fresh = {sym: hit for sym, items in by_ticker.items() if (hit := shares_issued(items, start=since, end=now))}
    with _lock:
        _by_symbol.clear()
        _by_symbol.update(fresh)
    return len(fresh)


def for_symbol(symbol: str | None) -> dict | None:
    """The newest share-issuing 8-K on file for ``symbol``: ``{published_ts, source, form, items, title, url}``."""
    sym = (symbol or "").strip().upper()
    with _lock:
        hit = _by_symbol.get(sym)
    return dict(hit) if hit else None


def reason(hit: dict | None) -> str | None:
    """The warning's words: "Shares were issued per the SEC 8-K of Oct 1 11:30 ET (Items 2.01, 8.01) ..."."""
    if not hit:
        return None
    when = datetime.fromtimestamp(float(hit["published_ts"]), ET)
    items = ", ".join(i for i in str(hit.get("items") or "").split(",") if i)
    return (f"Shares were issued per the SEC {hit.get('form') or '8-K'} of {when:%b} {when.day} {when:%H:%M} ET"
            + (f" (Items {items})" if items else "")
            + ": Yahoo's float and share count predate it. A warning only: no gate reads it")


def stamp(entry: dict, symbol: str | None = None) -> dict:
    """Put ``shares_issued`` / ``shares_issued_reason`` on a copied row or fundamentals dict (never a cache's)."""
    hit = for_symbol(symbol if symbol is not None else entry.get("symbol"))
    entry["shares_issued"] = hit
    entry["shares_issued_reason"] = reason(hit)
    return entry


async def refresh_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(refresh)
        except Exception:
            logger.exception("catalysts.issuance: refresh failed; the last map stands")
        await asyncio.sleep(CATALYST_ISSUANCE_REFRESH_SEC)


def reset_for_testing() -> None:
    with _lock:
        _by_symbol.clear()
