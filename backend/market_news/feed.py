"""The headline feed: every ``MARKET_NEWS_POLL_SEC``, Alpaca's newest all-market news goes to the store.

**Coverage is proven, not assumed** (as in ``catalysts/feed.py``): a poll extends the span only when its oldest item
is no newer than the last poll, so a burst larger than Alpaca's page, an error or a stopped process starts a new span
and a search can say what it did not read. Always on; ``NOVA_MARKET_NEWS=0`` turns it off. Network runs off the loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from constants_market_news import MARKET_NEWS_ENV, MARKET_NEWS_POLL_SEC, MARKET_NEWS_WINDOW_SEC
from market_news import store

logger = logging.getLogger(__name__)
_state: dict[str, Any] = {"at": None, "error": None, "span_start": None, "last_poll": None}


def enabled() -> bool:
    return (os.environ.get(MARKET_NEWS_ENV) or "1").strip() != "0"


def _ts(value: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def items_from(articles: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for art in articles:
        published = _ts(art.get("created_at"))
        if published is not None:
            out.append({"url": art["url"], "published_ts": published, "headline": art["headline"],
                        "summary": art.get("summary"), "source": art.get("source"), "symbols": art.get("symbols")})
    return out


def _fetch():
    from nova_news.providers import fetch_alpaca

    return fetch_alpaca()


def poll_once(now: float, db, fetch: Callable[[], Any] = _fetch) -> None:
    got = fetch()
    if not got.ok:
        _state.update(error=got.error, span_start=None)
        return
    items = items_from(got.articles)
    store.put_items(db, items)
    oldest = min((i["published_ts"] for i in items), default=now)
    last = _state["last_poll"]
    if _state["span_start"] is None or last is None or oldest > last:
        _state["span_start"] = oldest
    store.put_span(db, _state["span_start"], now)
    _state.update(at=now, error=None, last_poll=now)


def read(words: list[str], limit: int, now: float) -> dict[str, Any]:
    """The kept headlines of the last day, with what the store can vouch for."""
    since = now - MARKET_NEWS_WINDOW_SEC
    if not store.path().is_file():
        return {"items": [], "spans": [], "at": _state["at"], "error": _state["error"] or "no headlines kept yet"}
    db = store.connect()
    try:
        return {"items": store.search(db, words, since, limit), "spans": store.spans_since(db, since),
                "at": _state["at"], "error": _state["error"]}
    finally:
        db.close()


async def run() -> None:
    if not enabled():
        return
    db = await asyncio.to_thread(store.connect)
    while True:
        try:
            await asyncio.to_thread(poll_once, time.time(), db)
        except Exception as exc:  # noqa: BLE001 -- the feed outlives one bad poll; the gap breaks the span
            logger.warning("market_news: poll failed: %s", exc)
            _state.update(error=f"{exc}"[:200] or type(exc).__name__, span_start=None)
        await asyncio.sleep(MARKET_NEWS_POLL_SEC)


def reset_for_tests() -> None:
    _state.update(at=None, error=None, span_start=None, last_poll=None)
