"""The catalyst verdict on every scanner row (ADR 024 amendment, operator report 2026-09-23).

The News column showed that *an article exists* (``has_news``), and on a small-cap board the article
is usually a Benzinga movers list or a market wrap naming the ticker in passing -- the Gainers' top
three all lit up on "Dow Falls 100 Points". This module puts the classifier's verdict beside it as
``row["catalyst"]`` (``catalysts.live.compact``; ``None`` = not read yet, unknown), so the column can
say what the news is. ``has_news`` keeps its meaning for the leaderboard and the research rebuilds.

A background loop asks ``catalysts.live`` to read the current rosters (Alpaca in its own thread; the
feed is already in memory) and recomputes every board symbol's verdict off the event loop;
``stamp_row`` only reads the finished map, so serving rows never waits on a read (ADR 008, ADR 010).

Owner: this module (in-memory only). Invalidation: replaced whole on every pass
(``CATALYST_BOARD_INTERVAL_SEC``); a symbol that leaves every roster leaves the map. No disk state.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time

from catalysts import live
from constants_catalysts import CATALYST_BOARD_INTERVAL_SEC

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_verdicts: dict[str, dict | None] = {}


def stamp_row(entry: dict) -> None:
    """Put the symbol's verdict on a copied row (never a cache row). Unread symbols carry None."""
    sym = (entry.get("symbol") or "").strip().upper()
    with _lock:
        entry["catalyst"] = _verdicts.get(sym) if sym else None


def refresh(symbols: set[str], now: float | None = None) -> None:
    """Queue the symbols' Alpaca reads and recompute their verdicts from what is held now."""
    now = time.time() if now is None else now
    live.request(symbols, now)
    fresh: dict[str, dict | None] = {}
    for sym in symbols:
        try:
            fresh[sym] = live.compact(live.verdict_for(sym, now))
        except Exception:
            logger.warning("catalysts.board: verdict failed for %s", sym, exc_info=True)
            fresh[sym] = None
    with _lock:
        _verdicts.clear()
        _verdicts.update(fresh)


async def refresh_loop() -> None:
    """Keep every scanner roster's verdicts current (the same rosters the News badge reads)."""
    from scanner_news_badge import roster_symbols

    while True:
        try:
            await asyncio.to_thread(refresh, roster_symbols())
        except Exception:
            logger.exception("catalysts.board: refresh failed")
        await asyncio.sleep(CATALYST_BOARD_INTERVAL_SEC)


def reset_for_testing() -> None:
    with _lock:
        _verdicts.clear()
