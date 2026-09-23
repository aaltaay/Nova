"""The Watchlist's News column: today's catalyst verdict per row (ADR 024).

Read-only. The same verdict the setup scanner grades on (``catalysts/live.py``):
items published after the prior session's 16:00 ET close, classified by the one
pure classifier. ``catalyst`` is ``None`` when no source has looked yet -- the
table then falls back to the scanner's ``has_news`` flag and says so, never "no
news". Asking queues a background Alpaca fetch for the symbols; nothing here
waits on the network.

Owner: this module (no state of its own; the verdicts live in ``catalysts.live``).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# The verdict fields the table and the side panel read; the rest stay on the
# setup board's grade tooltip.
CATALYST_KEYS = ("verdict", "category", "strength", "title", "source", "published_ts", "news_pending")


def compact(verdict: dict | None) -> dict | None:
    if not isinstance(verdict, dict):
        return None
    return {key: verdict.get(key) for key in CATALYST_KEYS}


def attach(rows: list[dict]) -> list[dict]:
    """Add ``catalyst`` to each watchlist row dict in place; returns ``rows``."""
    symbols = [r["symbol"] for r in rows if isinstance(r.get("symbol"), str)]
    try:
        from catalysts import live as catalyst_live

        catalyst_live.request(symbols)
    except Exception:
        logger.warning("watchlist: catalyst fetch request failed", exc_info=True)
        for row in rows:
            row["catalyst"] = None
        return rows
    for row in rows:
        try:
            row["catalyst"] = compact(catalyst_live.verdict_for(row.get("symbol") or ""))
        except Exception:
            logger.warning("watchlist: catalyst verdict failed for %s", row.get("symbol"), exc_info=True)
            row["catalyst"] = None
    return rows
