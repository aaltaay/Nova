"""Today's catalyst verdict per symbol on the live desk (ADR 024).

The same window and classifier as the backfilled history: a symbol's items published after the
prior session's 16:00 ET close, judged by ``catalysts.classify.verdict`` at the moment asked --
Alpaca articles (fetched here in the background; ``request`` queues symbols, never on the
caller's thread) plus everything the live catalyst feed recorded (``catalysts/feed.py``: SEC
filings, GlobeNewswire, PR Newswire, Newsfile, FDA). A source counts as having looked only when
its fetch or its unbroken feed span covers the window; with no source looking and nothing found
the answer is ``None`` (unknown), never "no news" (a replay playhead on another day included).
A Nasdaq T1 / T12 halt inside the window with no resumption yet adds ``news_pending``.

``panel`` answers the Trader's News panel: the verdict plus every item read, each with its label
(``GET /api/catalysts/{symbol}``); ``catalysts/board.py`` puts the verdict on every scanner row.

Owner: this module (in-memory only). Invalidation: a fetch older than
``CATALYST_LIVE_TTL_SEC`` is refreshed on the next request; the ET session rolls the window and
drops the reads of an earlier one. No disk state.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from catalysts.classify import classify_item, verdict
from constants_catalysts import (
    CATALYST_LIVE_BATCH,
    CATALYST_LIVE_TTL_SEC,
    CATALYST_NEWS_PENDING_CODES,
    CATALYST_PANEL_MAX_ITEMS,
    CATALYST_PANEL_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
_PAGE_LIMIT = 50
_MAX_PAGES = 6
# The verdict as a scanner row and the News panel carry it (the classifier's full answer minus nothing a
# reader needs: n_items stays so "none found" can say how much was read).
WIRE_KEYS = ("verdict", "category", "strength", "title", "source", "published_ts", "url", "negative_too",
             "rules_version", "sources_answered", "n_items", "news_pending", "halt_code")

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
    """The verdict at ``now``, or None when no source looked across (prior close, now] and none spoke."""
    now = time.time() if now is None else now
    sym = (symbol or "").strip().upper()
    start = window_start(now)
    items, answered = _gather(sym, start, now)
    return _verdict(sym, items, answered, start, now)


def compact(v: dict | None) -> dict | None:
    """A verdict as it goes on the wire (``WIRE_KEYS``); None stays None -- unknown, never "no news"."""
    return None if v is None else {k: v.get(k) for k in WIRE_KEYS}


def panel(symbol: str, now: float | None = None) -> dict:
    """The Trader's News panel: the verdict and every item it read since the prior close, newest first.

    Reads Alpaca for this symbol first when its read is missing or stale, on the caller's thread (a
    route's worker), so a panel opened on a name no board carries is never "not checked" for long.
    """
    now = time.time() if now is None else now
    sym = (symbol or "").strip().upper()
    start = window_start(now)
    ensure([sym], now)
    items, answered = _gather(sym, start, now)
    rows = []
    for it in items:
        ts = float(it.get("published_ts") or 0.0)
        if not start < ts <= now:
            continue
        lb = classify_item(it.get("title"), it.get("summary"), source=str(it.get("source") or ""),
                           publisher=str(it.get("publisher") or ""), n_tickers=it.get("n_tickers"),
                           form=it.get("form"), sec_items=it.get("sec_items"), url=str(it.get("url") or ""))
        rows.append({"item_id": it.get("item_id"), "source": it.get("source"), "publisher": it.get("publisher"),
                     "published_ts": ts, "title": it.get("title"), "url": it.get("url"), "kind": lb.kind,
                     "category": lb.category, "strength": lb.strength, "dilution": lb.dilution})
    rows.sort(key=lambda r: r["published_ts"], reverse=True)
    return {"schema_version": CATALYST_PANEL_SCHEMA_VERSION, "symbol": sym, "generated_at": now,
            "window_start": start, "verdict": compact(_verdict(sym, items, answered, start, now)),
            "items": rows[:CATALYST_PANEL_MAX_ITEMS], "items_total": len(rows)}


def ensure(symbols: Iterable[str], now: float | None = None) -> None:
    """Read Alpaca now, on the caller's thread, for the symbols whose read is missing or stale."""
    now = time.time() if now is None else now
    start = window_start(now)
    with _lock:
        stale = sorted({s for s in _norm(symbols) if _stale(s, start, now)})
    if not stale:
        return
    from alpaca import _alpaca_headers

    headers = _alpaca_headers()
    if not headers:
        return
    try:
        _fetch(stale, headers)
    except Exception:
        logger.warning("catalysts.live: read failed for %s", ",".join(stale), exc_info=True)


def _gather(sym: str, start: float, now: float) -> tuple[list[dict], list[str]]:
    """Every item held for ``sym`` (Alpaca + the feed) and the sources whose reading covers (start, now]."""
    with _lock:
        span = _fetched.get(sym)
        items = list((_items.get(sym) or {}).values())
    answered = []
    if span is not None and span[0] <= start and span[1] >= now - CATALYST_LIVE_TTL_SEC:
        answered.append("alpaca")
    feed_items, feed_answered = _feed_view(sym, start, now)
    return items + feed_items, answered + feed_answered


def _verdict(sym: str, items: list[dict], answered: list[str], start: float, now: float) -> dict | None:
    if not answered and not any(start < float(it.get("published_ts") or 0) <= now for it in items):
        return None
    out = verdict(items, window_start=start, cutoff=now, sources_answered=answered)
    out.update(_halt_view(sym, start, now))
    return out


def _norm(symbols: Iterable[str]) -> set[str]:
    return {s for s in ((x or "").strip().upper() for x in symbols) if s}


def _stale(sym: str, start: float, now: float) -> bool:
    """Caller holds ``_lock``. A read that misses the window's opening or is past half its TTL."""
    span = _fetched.get(sym)
    return span is None or span[0] > start or span[1] < now - CATALYST_LIVE_TTL_SEC / 2


def _feed_view(symbol: str, start: float, now: float) -> tuple[list[dict], list[str]]:
    try:
        from catalysts import feed

        if not feed.enabled():
            return [], []
        f = feed.get_feed()
        return f.items_for(symbol, start, now), f.covered_sources(start, now)
    except Exception:
        logger.warning("catalysts.live: feed read failed for %s", symbol, exc_info=True)
        return [], []


def _halt_view(symbol: str, start: float, now: float) -> dict:
    """A news-pending halt (T1 / T12) that started inside the window and has not resumed."""
    try:
        from ibkr import nasdaq_halt_feed

        ov = nasdaq_halt_feed.overlay_for(symbol)
    except Exception:
        logger.debug("catalysts.live: no halt overlay for %s", symbol, exc_info=True)
        return {"news_pending": False, "halt_code": None}
    code = (ov.get("reason_code") or "").strip().upper() or None
    halted = ov.get("official_halt_start")
    resumed = ov.get("trade_resume")
    in_window = isinstance(halted, (int, float)) and start < float(halted) <= now
    open_halt = resumed is None or float(resumed) > now
    return {"news_pending": bool(in_window and open_halt and code in CATALYST_NEWS_PENDING_CODES),
            "halt_code": code if in_window else None}


def request(symbols: Iterable[str]) -> None:
    """Queue symbols whose fetch is missing or stale; a daemon thread drains them."""
    global _worker
    now = time.time()
    start = window_start(now)
    with _lock:
        for sym in [s for s, span in _fetched.items() if span[1] <= start]:  # an earlier session's reads
            _fetched.pop(sym, None)
            _items.pop(sym, None)
        _pending.update(s for s in _norm(symbols) if _stale(s, start, now))
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
