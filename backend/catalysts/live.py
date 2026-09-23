"""Today's catalyst verdict per symbol on the live desk (ADR 024).

The same window and classifier as the backfilled history: a symbol's Alpaca articles published
after the prior session's 16:00 ET close, judged by ``catalysts.classify.verdict`` at the moment
asked. ``request`` queues symbols for a background fetch (never on the caller's thread);
``verdict_for`` answers only from a fetch that covers the asked window -- otherwise ``None``
(unknown), never "no news" for a window nobody looked at (a replay playhead on another day
included).

Owner: this module (in-memory only). Invalidation: a fetch older than
``CATALYST_LIVE_TTL_SEC`` is refreshed on the next request; the ET session rolls the window.
No disk state.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from catalysts.classify import verdict
from constants_catalysts import CATALYST_LIVE_BATCH, CATALYST_LIVE_TTL_SEC

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
_PAGE_LIMIT = 50
_MAX_PAGES = 6

_lock = threading.Lock()
_items: dict[str, dict[str, dict]] = {}          # symbol -> item id -> item
_fetched: dict[str, tuple[float, float]] = {}    # symbol -> (window start, fetched through)
_pending: set[str] = set()
_worker: threading.Thread | None = None


def window_start(now: float) -> float:
    """The prior session's 16:00 ET close, the same opening the history's windows use."""
    from sim.trading_day import last_open_day

    day = datetime.fromtimestamp(now, ET).date()
    prior = last_open_day(day - timedelta(days=1))
    return datetime.combine(prior, dtime(16, 0), ET).timestamp()


def verdict_for(symbol: str, now: float | None = None) -> dict | None:
    """The verdict at ``now``, or None when no fetch covers (prior close, now]."""
    now = time.time() if now is None else now
    sym = (symbol or "").strip().upper()
    start = window_start(now)
    with _lock:
        span = _fetched.get(sym)
        items = list((_items.get(sym) or {}).values())
    if span is None or span[0] > start or span[1] < now - CATALYST_LIVE_TTL_SEC:
        return None
    return verdict(items, window_start=start, cutoff=now, sources_answered=["alpaca"])


def request(symbols: Iterable[str]) -> None:
    """Queue symbols whose fetch is missing or stale; a daemon thread drains them."""
    global _worker
    now = time.time()
    start = window_start(now)
    with _lock:
        for s in symbols:
            sym = (s or "").strip().upper()
            span = _fetched.get(sym)
            if sym and (span is None or span[0] > start or span[1] < now - CATALYST_LIVE_TTL_SEC / 2):
                _pending.add(sym)
        if not _pending or (_worker is not None and _worker.is_alive()):
            return
        _worker = threading.Thread(target=_drain, daemon=True, name="catalysts_live")
        _worker.start()


def _drain() -> None:
    global _worker
    from alpaca import _alpaca_headers

    headers = _alpaca_headers()
    while True:
        with _lock:
            batch = sorted(_pending)[:CATALYST_LIVE_BATCH]
            _pending.difference_update(batch)
            if not batch or not headers:
                _pending.clear()
                _worker = None
                if not headers:
                    logger.warning("catalysts.live: no Alpaca keys -- catalyst verdicts stay unknown")
                return
        try:
            _fetch(batch, headers)
        except Exception:
            logger.warning("catalysts.live: fetch failed for %d symbol(s)", len(batch), exc_info=True)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch(symbols: list[str], headers: dict) -> None:
    import requests

    from alpaca import ALPACA_DATA_URL

    now = time.time()
    start = window_start(now)
    news, token = [], None
    for _ in range(_MAX_PAGES):
        params = {"symbols": ",".join(symbols), "start": _iso(start), "end": _iso(now), "limit": _PAGE_LIMIT,
                  "sort": "desc", "include_content": "false"}
        if token:
            params["page_token"] = token
        resp = requests.get(f"{ALPACA_DATA_URL}/v1beta1/news", headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        body = resp.json()
        news.extend(body.get("news") or [])
        token = body.get("next_page_token")
        if not token:
            break
    if token and news:
        # More pages than read: only the stretch back to the oldest article read is covered, so a
        # verdict for the whole window stays unknown rather than missing what was not read.
        start = min(datetime.fromisoformat(str(n["created_at"]).replace("Z", "+00:00")).timestamp()
                    for n in news if n.get("created_at"))
    record(symbols, news, start=start, through=now)


def record(symbols: list[str], news: list[dict], *, start: float, through: float) -> None:
    """Store one fetch's Alpaca articles for ``symbols`` (a symbol with none is recorded as looked)."""
    wanted = {s.upper() for s in symbols}
    fresh: dict[str, dict[str, dict]] = {s: {} for s in wanted}
    for n in news:
        try:
            ts = datetime.fromisoformat(str(n["created_at"]).replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            continue
        tickers = [str(t).upper() for t in n.get("symbols") or []]
        item = {"item_id": f"alpaca:{n.get('id')}", "source": "alpaca", "published_ts": ts,
                "title": n.get("headline"), "summary": n.get("summary"), "url": n.get("url"),
                "publisher": n.get("source") or n.get("author"), "n_tickers": len(tickers)}
        for t in wanted.intersection(tickers):
            fresh[t][item["item_id"]] = item
    with _lock:
        for sym, items in fresh.items():
            _items[sym] = items
            _fetched[sym] = (start, through)


def reset_for_testing() -> None:
    global _worker
    with _lock:
        _items.clear()
        _fetched.clear()
        _pending.clear()
        _worker = None
