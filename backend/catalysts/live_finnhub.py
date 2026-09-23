"""Finnhub company news for the live catalyst verdict (ADR 024 amendment, 2026-09-23).

Alpaca is Benzinga's newsroom, and for a small cap that is mostly movers lists. Finnhub's
``company-news`` also carries the Yahoo Finance copy of a company's own release -- GlobeNewswire,
PR Newswire, ACCESS Newswire, Business Wire -- and it answers for a window after the fact, so a
backend that was down still reads what it missed (the wire RSS feeds cannot: on 2026-09-23 a
Windows Update restart cost the feed 02:29-09:00 ET, and with it Artelo's 07:35 release and
Decoy's correction of the evening before). On the rebuilt leaderboard's movers it raised the share
with a placed catalyst from 22% to 29%.

Finnhub's Benzinga items are dropped (``CATALYST_FINNHUB_SKIP_PUBLISHERS``): Alpaca carries the same
articles, and Finnhub stamps them with Eastern wall-clock time read as UTC -- four hours early (#516).

One call per symbol (the endpoint is per symbol and date-granular); items are kept to the window by
their own timestamp. The free tier's 60 calls a minute is shared with the earnings calendar and the
logos (``finnhub_http`` cooldown), so reads are paced at ``CATALYST_FINNHUB_CALLS_PER_MIN``: a symbol
never read goes first, then the oldest read. A read counts as having looked while it is younger than
``CATALYST_FINNHUB_TTL_SEC``.

Owner: this module (in-memory only). Invalidation: a read past half its TTL is queued again on the
next request; reads of an earlier session are dropped when the window rolls. No disk state.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

import finnhub_http
from constants_catalysts import (
    CATALYST_FINNHUB_CALLS_PER_MIN,
    CATALYST_FINNHUB_HTTP_TIMEOUT_SEC,
    CATALYST_FINNHUB_KEY_ENV,
    CATALYST_FINNHUB_SKIP_PUBLISHERS,
    CATALYST_FINNHUB_TTL_SEC,
    CATALYST_FINNHUB_URL,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
SOURCE = "finnhub"

_lock = threading.Lock()
_items: dict[str, dict[str, dict]] = {}          # symbol -> item id -> item
_fetched: dict[str, tuple[float, float]] = {}    # symbol -> (window start, fetched at)
_pending: set[str] = set()
_failed: dict[str, float] = {}                   # symbol -> when its last read failed (retried after half a TTL)
_worker: threading.Thread | None = None
_status: dict[str, object] = {"last_ok": None, "last_error": None, "reads": 0}


def api_key() -> str:
    return (os.environ.get(CATALYST_FINNHUB_KEY_ENV) or "").strip().strip("'\"")


def gather(symbol: str, start: float, now: float) -> tuple[list[dict], bool]:
    """The symbol's items held, and whether a read young enough covers (start, now]."""
    with _lock:
        span = _fetched.get(symbol)
        items = list((_items.get(symbol) or {}).values())
    return items, span is not None and span[0] <= start and span[1] >= now - CATALYST_FINNHUB_TTL_SEC


def request(symbols: Iterable[str], start: float, now: float | None = None) -> None:
    """Queue the symbols whose read is missing or stale; a daemon thread drains them at the paced rate."""
    global _worker
    now = time.time() if now is None else now
    if not api_key():
        return
    with _lock:
        for sym in [s for s, span in _fetched.items() if span[1] <= start]:
            _fetched.pop(sym, None)  # an earlier session's read
            _items.pop(sym, None)
        _pending.update(s for s in symbols if _stale(s, start, now))
        if not _pending or (_worker is not None and _worker.is_alive()):
            return
        _worker = threading.Thread(target=_drain, daemon=True, name="catalysts_finnhub")
        _worker.start()


def ensure(symbol: str, start: float, now: float | None = None) -> None:
    """Read one symbol now, on the caller's thread (the News panel), when its read is missing or stale."""
    now = time.time() if now is None else now
    key = api_key()
    with _lock:
        stale = _stale(symbol, start, now)
    if not key or not stale or finnhub_http.is_blocked():
        return
    try:
        _read(symbol, key, start)
    except Exception as exc:  # noqa: BLE001 -- the panel still answers from the other sources; the error is kept
        _note_error(symbol, exc)


def status() -> dict:
    with _lock:
        return {"enabled": bool(api_key()), "pending": len(_pending), "symbols": len(_fetched), **_status}


def _stale(symbol: str, start: float, now: float) -> bool:
    """Caller holds ``_lock``. A read that misses the window's opening or is past half its TTL -- unless the
    last read failed recently (a symbol Finnhub refuses must not spend the shared budget every pass)."""
    if _failed.get(symbol, 0.0) > now - CATALYST_FINNHUB_TTL_SEC / 2:
        return False
    span = _fetched.get(symbol)
    return span is None or span[0] > start or span[1] < now - CATALYST_FINNHUB_TTL_SEC / 2


def _next_symbol() -> str | None:
    """Caller holds ``_lock``. A symbol never read first, then the oldest read."""
    if not _pending:
        return None
    sym = min(_pending, key=lambda s: (_fetched.get(s, (0.0, 0.0))[1], s))
    _pending.discard(sym)
    return sym


def _drain() -> None:
    global _worker
    from catalysts.live import window_start

    gap = 60.0 / CATALYST_FINNHUB_CALLS_PER_MIN
    while True:
        key = api_key()
        with _lock:
            sym = _next_symbol() if key else None
            if sym is None:
                _pending.clear()
                _worker = None
                return
        wait = finnhub_http.remaining_sec()
        if wait > 0:
            time.sleep(wait)
        try:
            _read(sym, key, window_start(time.time()))
        except Exception as exc:  # noqa: BLE001 -- one symbol failing never stops the queue
            _note_error(sym, exc)
        time.sleep(gap)


def _note_error(symbol: str, exc: Exception) -> None:
    with _lock:
        _failed[symbol] = time.time()
        _status["last_error"] = f"{symbol}: {exc}"[:300]
    logger.warning("catalysts.live_finnhub: read failed for %s: %s", symbol, exc)


def _read(symbol: str, key: str, start: float) -> None:
    import requests

    now = time.time()
    frm = datetime.fromtimestamp(start, ET).date().isoformat()
    to = (datetime.fromtimestamp(now, ET).date() + timedelta(days=1)).isoformat()
    resp = requests.get(CATALYST_FINNHUB_URL, params={"symbol": symbol, "from": frm, "to": to, "token": key},
                        timeout=CATALYST_FINNHUB_HTTP_TIMEOUT_SEC)
    if resp.status_code == 429:
        finnhub_http.note_rate_limit(resp)
        with _lock:
            _pending.add(symbol)  # read again once the cooldown ends
        return
    resp.raise_for_status()
    rows = resp.json()
    record(symbol, rows if isinstance(rows, list) else [], start=start, through=now)


def record(symbol: str, rows: list[dict], *, start: float, through: float) -> None:
    """Store one read's company news for ``symbol`` (none found is recorded as looked)."""
    items: dict[str, dict] = {}
    for r in rows:
        publisher = str(r.get("source") or "")
        try:
            ts = float(r.get("datetime") or 0)
        except (TypeError, ValueError):
            continue
        if not ts or publisher.strip().lower() in CATALYST_FINNHUB_SKIP_PUBLISHERS:
            continue
        item_id = f"{SOURCE}:{r.get('id')}"
        items[item_id] = {"item_id": item_id, "source": SOURCE, "published_ts": ts, "title": r.get("headline"),
                          "summary": (r.get("summary") or "")[:2000], "url": r.get("url"), "publisher": publisher,
                          "n_tickers": None}
    with _lock:
        _items[symbol] = items
        _fetched[symbol] = (start, through)
        _status["last_ok"] = through
        _status["reads"] = int(_status["reads"] or 0) + 1


def reset_for_testing() -> None:
    global _worker
    with _lock:
        _items.clear()
        _fetched.clear()
        _pending.clear()
        _failed.clear()
        _status.update({"last_ok": None, "last_error": None, "reads": 0})
        _worker = None
