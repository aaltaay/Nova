"""The live catalyst feed (ADR 024): the primary sources, recorded as they publish.

  edgar          SEC's latest filings per form (8-K, 6-K, 424B, S-1, S-3, F-1, F-3, SC TO-T); an 8-K /
                 6-K is read for its press release (``catalysts/sec_text.py``). CIK -> ticker from
                 SEC's own ``company_tickers.json``.
  edgar_form4    SEC's latest Form 4s, kept only for an open-market purchase by an officer or a
                 director (``catalysts/feed_form4.py``); items are ``edgar`` filings, the span its own
  globenewswire  public-company releases, tickers tagged by the wire
  prnewswire     all releases; tickers from the text, else the issuer named by the wire
  newsfile       the small-cap industry feeds, polled in turn
  fda            FDA press announcements; tickers only when a listed company's full name appears

Every item goes to ``catalyst_feed.sqlite3`` (``catalysts/feed_store.py``) and to memory for the
live verdict. **Coverage is proven, not assumed:** a poll extends its source's span only when its
oldest item is no newer than the previous poll -- the feed listed everything in between. A burst
larger than the feed's page, an error or a stopped process breaks the span, and the verdict then
cannot say "none found" for a window that span does not cover.

Always on (no button); ``NOVA_CATALYST_FEED=0`` turns it off. Network runs off the event loop.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import threading
import time
import urllib.request
from urllib.parse import quote
from typing import Any, Callable

from catalysts import feed_sources, feed_store, sec_text
from catalysts.feed_form4 import Form4Reader
from constants_catalysts import (
    CATALYST_FEED_COVERAGE_SOURCES,
    CATALYST_FEED_EDGAR_ARCHIVE,
    CATALYST_FEED_EDGAR_ATOM,
    CATALYST_FEED_EDGAR_FORMS,
    CATALYST_FEED_EDGAR_POLL_SEC,
    CATALYST_FEED_ENV,
    CATALYST_FEED_FORM4_POLL_SEC,
    CATALYST_FEED_FORM4_SOURCE,
    CATALYST_FEED_HTTP_TIMEOUT_SEC,
    CATALYST_FEED_MEMORY_HOURS,
    CATALYST_FEED_NEWSFILE_INDUSTRIES,
    CATALYST_FEED_NEWSFILE_POLL_SEC,
    CATALYST_FEED_NEWSFILE_URL,
    CATALYST_FEED_RSS,
    CATALYST_FEED_SEC_MIN_GAP_SEC,
    CATALYST_FEED_SEC_TICKERS_TTL_SEC,
    CATALYST_FEED_SEC_TICKERS_URL,
    CATALYST_FEED_SEC_USER_AGENT_DEFAULT,
    CATALYST_FEED_SPAN_GAP_SEC,
    CATALYST_FEED_TICK_SEC,
    CATALYST_FEED_USER_AGENT,
)

logger = logging.getLogger(__name__)
Fetch = Callable[[str, dict], bytes]


def http_get(url: str, headers: dict) -> bytes:
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", **headers})
    with urllib.request.urlopen(req, timeout=CATALYST_FEED_HTTP_TIMEOUT_SEC) as resp:
        body = resp.read()
        return gzip.decompress(body) if resp.headers.get("Content-Encoding") == "gzip" else body


def enabled() -> bool:
    return (os.environ.get(CATALYST_FEED_ENV) or "1").strip() != "0"


class _Source:
    def __init__(self, name: str, interval: float):
        self.name, self.interval = name, interval
        self.next_due = 0.0
        self.last_poll: float | None = None
        self.last_ok: float | None = None
        self.last_error: str | None = None
        self.span: list[float] | None = None      # [start, end] of the unbroken span being extended
        self.gaps = 0
        self.items = 0


class CatalystFeed:
    def __init__(self, *, fetch: Fetch = http_get, clock: Callable[[], float] = time.time, db: Any = None):
        self._fetch, self._clock = fetch, clock
        self._db = db
        self._lock = threading.Lock()
        self.sources = {n: _Source(n, CATALYST_FEED_EDGAR_POLL_SEC if n == "edgar" else i)
                        for n, i in [("edgar", 0.0)] + [(s, i) for s, _u, i in CATALYST_FEED_RSS]}
        self.sources["newsfile"] = _Source("newsfile", CATALYST_FEED_NEWSFILE_POLL_SEC)
        self.sources[CATALYST_FEED_FORM4_SOURCE] = _Source(CATALYST_FEED_FORM4_SOURCE, CATALYST_FEED_FORM4_POLL_SEC)
        self._form4 = Form4Reader(self._sec_get)
        self._nf_next = 0                                   # next Newsfile industry in the rotation
        self._nf_cycle_ok = True
        self._nf_last: dict[str, float] = {}                # industry -> when it was last read
        self._by_ticker: dict[str, dict[str, dict]] = {}
        self._spans: dict[str, list[tuple[float, float]]] = {}
        self._seen: dict[str, float] = {}                   # item id -> published time (aged out with memory)
        self._cik: dict[str, list[str]] = {}
        self._names: dict[str, list[str]] = {}
        self._tickers_at = 0.0
        self._sec_last = 0.0
        self.error: str | None = None
        self.started: float | None = None

    # -- reads (any thread) --------------------------------------------------------------------
    def items_for(self, symbol: str, start: float, end: float) -> list[dict]:
        sym = (symbol or "").strip().upper()
        with self._lock:
            return [dict(it) for it in (self._by_ticker.get(sym) or {}).values() if start < it["published_ts"] <= end]

    def covered_sources(self, start: float, end: float) -> list[str]:
        """Sources read without a break across (start, end] -- they would have seen any release."""
        out = []
        with self._lock:
            for name in CATALYST_FEED_COVERAGE_SOURCES:
                src = self.sources[name]
                # Only the span still being extended may stand in for the poll not yet due; a span a
                # later poll proved broken covers exactly what it covered.
                live_start = src.span[0] if src.span is not None else None
                slack = 2 * src.interval + CATALYST_FEED_TICK_SEC
                if any(s <= start and (e >= end or (s == live_start and e >= end - slack))
                       for s, e in self._spans.get(name, ())):
                    out.append(name)
        return out

    def status(self) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            return {
                "enabled": enabled(), "running": self.started is not None, "since": self.started, "error": self.error,
                "store": str(feed_store.path()),
                "sources": {n: {"last_ok": s.last_ok, "last_error": s.last_error, "items": s.items, "gaps": s.gaps,
                                "covering_since": (s.span[0] if s.span and now - s.span[1] <= 2 * s.interval
                                                   + CATALYST_FEED_TICK_SEC else None)}
                            for n, s in self.sources.items()},
            }

    # -- the loop --------------------------------------------------------------------------------
    async def run(self) -> None:
        if not enabled():
            logger.info("catalyst feed: off (%s=0)", CATALYST_FEED_ENV)
            return
        await asyncio.to_thread(self.warm_start)
        while True:
            try:
                await asyncio.to_thread(self.tick)
            except Exception as exc:  # noqa: BLE001 -- the loop must outlive one bad poll
                self.error = str(exc)[:300]
                logger.exception("catalyst feed: tick failed")
            await asyncio.sleep(CATALYST_FEED_TICK_SEC)

    def warm_start(self) -> None:
        """Open the store and reload the recent items and spans, so a restart keeps the morning."""
        now = self._clock()
        try:
            if self._db is None:
                self._db = feed_store.connect()
            since = now - CATALYST_FEED_MEMORY_HOURS * 3600
            items = feed_store.items_since(self._db, since)
            spans = feed_store.spans_since(self._db, since)
        except Exception as exc:  # noqa: BLE001 -- the feed still runs in memory; the error is shown
            self.error = f"store: {exc}"[:300]
            logger.exception("catalyst feed: store unavailable, recording in memory only")
            items, spans = [], []
        with self._lock:
            for it in items:
                self._remember(it)
            for source, s, e in spans:
                self._spans.setdefault(source, []).append((s, e))
        self.started = now

    def tick(self) -> None:
        now = self._clock()
        self._refresh_tickers(now)
        for src in self.sources.values():
            if now < src.next_due:
                continue
            if src.name == "newsfile":
                src.next_due = now + src.interval / len(CATALYST_FEED_NEWSFILE_INDUSTRIES)
            else:
                src.next_due = now + src.interval
            try:
                if src.name == "newsfile" and self._nf_next == 0:
                    self._nf_cycle_ok = True
                if src.name == "edgar":
                    oldest, ok_all = self._poll_edgar(now)
                elif src.name == "newsfile":
                    oldest, ok_all = self._poll_newsfile(now)
                elif src.name == CATALYST_FEED_FORM4_SOURCE:
                    oldest, ok_all = self._poll_form4(src)
                else:
                    url = next(u for s, u, _i in CATALYST_FEED_RSS if s == src.name)
                    oldest, ok_all = self._poll_rss(src.name, url)
                src.last_ok, src.last_error = now, None
                if ok_all:
                    self._extend(src, now, oldest)
            except Exception as exc:  # noqa: BLE001 -- one source failing never stops the others
                src.last_error = str(exc)[:300]
                if src.name == "newsfile":
                    self._nf_cycle_ok = False
                    if self._nf_next == 0:
                        src.span = None           # the rotation ended on a failure: no span through it
                logger.warning("catalyst feed: %s poll failed: %s", src.name, exc)
            src.last_poll = now
        self._prune(now)

    # -- coverage --------------------------------------------------------------------------------
    def _extend(self, src: _Source, now: float, oldest: float | None) -> None:
        """A poll whose oldest item is no newer than the last poll listed everything since: extend."""
        joined = (src.span is not None and now - src.span[1] <= CATALYST_FEED_SPAN_GAP_SEC
                  and (oldest is None or oldest <= src.span[1]))
        if joined:
            src.span[1] = now
        else:
            if src.span is not None:
                src.gaps += 1
            src.span = [min(now, oldest) if oldest is not None else now, now]
        self._save_span(src)

    def _break(self, src: _Source, at: float) -> None:
        """A known miss at ``at``: the span being extended ends before it, and the next one opens after it."""
        if src.span is None:
            return
        src.gaps += 1
        if src.span[0] < at <= src.span[1]:
            src.span[1] = max(src.span[0], at - 1.0)   # SEC times are whole seconds
            self._save_span(src)
        src.span = None

    def _save_span(self, src: _Source) -> None:
        with self._lock:
            spans = [sp for sp in self._spans.get(src.name, []) if sp[0] != src.span[0]]
            spans.append((src.span[0], src.span[1]))
            self._spans[src.name] = spans
        if self._db is not None:
            try:
                feed_store.put_span(self._db, src.name, src.span[0], src.span[1])
            except Exception:  # noqa: BLE001
                logger.warning("catalyst feed: could not save the %s span", src.name, exc_info=True)

    # -- sources ---------------------------------------------------------------------------------
    def _sec_get(self, url: str) -> bytes:
        wait = CATALYST_FEED_SEC_MIN_GAP_SEC - (time.monotonic() - self._sec_last)
        if wait > 0:
            time.sleep(wait)
        self._sec_last = time.monotonic()
        ua = os.environ.get("SEC_USER_AGENT") or CATALYST_FEED_SEC_USER_AGENT_DEFAULT
        return self._fetch(url, {"User-Agent": ua})

    def _refresh_tickers(self, now: float) -> None:
        if self._cik and now - self._tickers_at < CATALYST_FEED_SEC_TICKERS_TTL_SEC:
            return
        self._tickers_at = now
        try:
            data = json.loads(self._sec_get(CATALYST_FEED_SEC_TICKERS_URL))
        except Exception as exc:  # noqa: BLE001 -- keep the previous map; say so
            self.error = f"SEC ticker map: {exc}"[:300]
            logger.warning("catalyst feed: SEC ticker map unavailable: %s", exc)
            return
        cik: dict[str, list[str]] = {}
        names: dict[str, list[str]] = {}
        for row in data.values():
            sym = str(row.get("ticker") or "").upper()
            if not sym:
                continue
            cik.setdefault(str(row.get("cik_str")), []).append(sym)
            names.setdefault(feed_sources.company_key(row.get("title")), []).append(sym)
        self._cik, self._names = cik, names

    def _poll_edgar(self, now: float) -> tuple[float | None, bool]:
        newest_oldest: float | None = None
        for form in CATALYST_FEED_EDGAR_FORMS:
            filings = feed_sources.parse_edgar_atom(self._sec_get(CATALYST_FEED_EDGAR_ATOM.format(form=quote(form))))
            if filings:
                oldest = min(f["accepted_ts"] for f in filings)
                newest_oldest = oldest if newest_oldest is None else max(newest_oldest, oldest)
            fresh = []
            for f in filings:
                item_id = f"edgar:{f['acc']}"
                if item_id in self._seen or f["role"] != "Filer" or f["form"] not in sec_text.KEEP_FORMS:
                    continue
                head, summary = None, ""
                tickers = list(self._cik.get(f["cik"], []))
                if f["form"] in sec_text.PRESS_FORMS and tickers:  # read the release only for a company that trades
                    head, summary = self._release(f)
                fresh.append({"item_id": item_id, "source": "edgar", "published_ts": f["accepted_ts"],
                              "title": sec_text.title_for(f["form"], f["items"], head), "summary": summary[:2000],
                              "url": f["url"], "publisher": "SEC EDGAR", "form": f["form"], "sec_items": f["items"],
                              "tickers": tickers, "n_tickers": 1})
            self._record("edgar", fresh)
        return newest_oldest, True

    def _release(self, filing: dict) -> tuple[str | None, str]:
        base = CATALYST_FEED_EDGAR_ARCHIVE.format(cik=filing["cik"], acc=filing["acc"].replace("-", ""))
        try:
            listing = json.loads(self._sec_get(f"{base}/index.json"))
            names = [it["name"] for it in listing.get("directory", {}).get("item", [])]
            primary = next((n for n in names if n.lower().endswith((".htm", ".html")) and "index" not in n.lower()), None)
            return sec_text.release_text(filing["form"], names, primary,
                                         lambda doc: self._sec_get(f"{base}/{doc}").decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001 -- the filing is still recorded by its form and Items
            logger.info("catalyst feed: no release text for %s: %s", filing["acc"], exc)
            return None, ""

    def _poll_form4(self, src: _Source) -> tuple[float | None, bool]:
        got = self._form4.poll(since=src.span[1] if src.span else None, tickers=self._cik,
                               seen=lambda item_id: item_id in self._seen)
        with self._lock:
            self._seen.update(got.settled)       # read and let go: never fetched again while remembered
        self._record(src.name, got.items)
        if got.missed_ts is not None:
            self._break(src, got.missed_ts)
        return got.oldest, got.complete

    def _poll_rss(self, source: str, url: str) -> tuple[float | None, bool]:
        items = feed_sources.parse_rss(self._fetch(url, {"User-Agent": CATALYST_FEED_USER_AGENT}), source)
        for it in items:
            if not it["tickers"]:
                if it.get("company"):
                    it["tickers"] = list(self._names.get(feed_sources.company_key(it["company"]), []))
                if not it["tickers"] and source == "fda":
                    it["tickers"] = feed_sources.tickers_named(f"{it['title']} {it['summary']}", self._names)
        self._record(source, [it for it in items if it["item_id"] not in self._seen])
        return (min(it["published_ts"] for it in items) if items else None), True

    def _poll_newsfile(self, now: float) -> tuple[float | None, bool]:
        """One industry per call. The span moves only when a whole rotation has been read and every
        industry's page reached back to its previous read (none published more than a page between)."""
        slug = CATALYST_FEED_NEWSFILE_INDUSTRIES[self._nf_next]
        self._nf_next = (self._nf_next + 1) % len(CATALYST_FEED_NEWSFILE_INDUSTRIES)
        prev = self._nf_last.get(slug)
        oldest, _ = self._poll_rss("newsfile", CATALYST_FEED_NEWSFILE_URL.format(slug=slug))
        self._nf_last[slug] = now
        if prev is None or (oldest is not None and oldest > prev):
            self._nf_cycle_ok = False
        if self._nf_next != 0:
            return None, False                     # mid-rotation: the span waits for the whole round
        if not self._nf_cycle_ok:
            self.sources["newsfile"].span = None   # a break: the next span opens now
        return None, True

    # -- memory ----------------------------------------------------------------------------------
    def _record(self, source: str, items: list[dict]) -> None:
        if not items:
            return
        if self._db is not None:
            try:
                feed_store.put_items(self._db, items)
            except Exception as exc:  # noqa: BLE001 -- kept in memory; the store error is shown
                self.error = f"store: {exc}"[:300]
                logger.warning("catalyst feed: could not save %d %s items", len(items), source, exc_info=True)
        with self._lock:
            for it in items:
                self._remember(it)
            self.sources[source].items += len(items)

    def _remember(self, item: dict) -> None:
        self._seen[item["item_id"]] = float(item["published_ts"])
        for sym in item.get("tickers") or ():
            self._by_ticker.setdefault(sym, {})[item["item_id"]] = item

    def _prune(self, now: float) -> None:
        cutoff = now - CATALYST_FEED_MEMORY_HOURS * 3600
        with self._lock:
            for sym in list(self._by_ticker):
                kept = {k: v for k, v in self._by_ticker[sym].items() if v["published_ts"] > cutoff}
                if kept:
                    self._by_ticker[sym] = kept
                else:
                    del self._by_ticker[sym]
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
            for name in list(self._spans):
                self._spans[name] = [sp for sp in self._spans[name] if sp[1] > cutoff]


_feed: CatalystFeed | None = None


def get_feed() -> CatalystFeed:
    global _feed
    if _feed is None:
        _feed = CatalystFeed()
    return _feed


async def run() -> None:
    """Background task entry (``app_runtime_tasks``)."""
    await get_feed().run()
