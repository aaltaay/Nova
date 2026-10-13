"""The reads behind the daily charts' earnings and split marks: in the background, never on a request.

``view(symbol)`` answers from memory at once -- the read kept for the symbol, or that one is under way or
failed -- and queues a read when none is kept, the kept one is no longer fresh, or part of it failed and its
retry wait is over. One daemon thread drains the queue, the symbol asked last first (the chart on screen):

  earnings   SEC's ticker -> CIK list, the registrant's submissions file, its older pages back to
             ``CHART_EVENTS_HISTORY_DAYS`` (every 8-K's items), its financial facts, then the words of each
             6-K and Item 2.02 8-K of the last ``CHART_EVENTS_6K_SCAN_DAYS`` not read before
             (``release_text.py``) -- and the Exhibit 99.1 of one whose cover only says a press release is
             attached; the answer is kept before they are read and every ``CHART_EVENTS_6K_KEEP_EVERY``
             after, so ``scan.pending`` counts down
  splits     Massive's reference list, the SEC-confirmed splits and Yahoo's split history
             (``split_sources.py``, merged by ``splits.py``)

Every SEC request carries the desk's SEC user agent (``SEC_USER_AGENT`` in ``.env``, else the catalyst feed's
default) and is at least ``CHART_EVENTS_SEC_MIN_GAP_SEC`` after the one before; a Yahoo read gives up after
``CHART_EVENTS_YAHOO_TIMEOUT_SEC``. A source that fails is said in the answer, never read as "none".

A read is fresh for its session day (until the next 04:00 ET, never longer than ``CHART_EVENTS_TTL_SEC``).
Reads live in memory only -- a restart reads again on the first ask -- and so do the 6-K readings, by
accession (a filing never changes). Always on; ``NOVA_CHART_EVENTS=0`` turns it off. Read-only: nothing
places, stages or gates on it.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable

from chart_events import earnings, release_text
from chart_events.split_sources import ListPaths, SplitSources, YahooSplits, list_paths, yahoo_splits
from chart_events.constants_chart_events import (
    CHART_EVENTS_6K_CACHE_MAX,
    CHART_EVENTS_6K_DOC_URL,
    CHART_EVENTS_6K_KEEP_EVERY,
    CHART_EVENTS_6K_SCAN_DAYS,
    CHART_EVENTS_COMPANYFACTS_URL,
    CHART_EVENTS_ENV,
    CHART_EVENTS_EXHIBIT_RE,
    CHART_EVENTS_FILING_INDEX_URL,
    CHART_EVENTS_HISTORY_DAYS,
    CHART_EVENTS_INTERIM_FORMS,
    CHART_EVENTS_KEEP_SYMBOLS,
    CHART_EVENTS_PENDING_MAX,
    CHART_EVENTS_RETRY_SEC,
    CHART_EVENTS_SEC_MIN_GAP_SEC,
    CHART_EVENTS_SOURCE_SEC,
    CHART_EVENTS_TICKERS_TTL_SEC,
    CHART_EVENTS_TTL_SEC,
)
from constants_catalysts import CATALYST_FEED_SEC_TICKERS_URL, CATALYST_FEED_SEC_USER_AGENT_DEFAULT
from constants_stock_read import (
    STOCK_READ_DILUTION_PAGE_NAME_RE,
    STOCK_READ_DILUTION_PAGE_URL,
    STOCK_READ_DILUTION_SUBMISSIONS_URL,
)
from stock_read.dilution_reader import SEC_USER_AGENT_ENV, fresh, parse_tickers, ticker_key

logger = logging.getLogger(__name__)
Fetch = Callable[[str, dict], bytes]

_PAGE_NAME = re.compile(STOCK_READ_DILUTION_PAGE_NAME_RE)
_EXHIBIT = re.compile(CHART_EVENTS_EXHIBIT_RE, re.I)


def _http_get(url: str, headers: dict) -> bytes:
    from catalysts.feed import http_get     # the desk's transport for SEC (gzip, the feed's timeout)

    return http_get(url, headers)


def enabled() -> bool:
    return (os.environ.get(CHART_EVENTS_ENV) or "1").strip() != "0"


def _why(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:200]


class ChartEventsReader:
    def __init__(self, *, fetch: Fetch = _http_get, yahoo: YahooSplits = yahoo_splits,
                 list_paths: ListPaths = list_paths, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic,
                 run_inline: bool = False):
        self._fetch = fetch
        self._splits = SplitSources(yahoo=yahoo, paths=list_paths)
        self._clock, self._sleep, self._monotonic = clock, sleep, monotonic
        self._run_inline = run_inline           # tests: read on the asking thread instead of the worker
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}
        self._fails: dict[str, dict[str, Any]] = {}      # symbol -> {count, error, retry_at}
        self._pending: list[str] = []                    # newest ask first
        self._reading: str | None = None
        self._worker: threading.Thread | None = None
        # The worker's own: SEC's ticker list, the release readings and the pacing clock.
        self._tickers: dict[str, int] | None = None
        self._tickers_at = 0.0
        self._readings: dict[str, dict | None] = {}
        self._last_request: float | None = None

    # -- the answer (any thread; memory only) ------------------------------------------------------
    def view(self, symbol: str, now: float | None = None) -> dict[str, Any]:
        """The symbol's answer now. Asking is what starts a read; the answer never waits for it."""
        sym = (symbol or "").strip().upper()
        if not enabled():
            return {"status": "off", "symbol": sym}
        now = self._clock() if now is None else now
        with self._lock:
            record, fail = self._records.get(sym), self._fails.get(sym)
            is_fresh = record is not None and fresh(record["fetched_at"], now, CHART_EVENTS_TTL_SEC)
            waiting = fail is not None and now < fail["retry_at"]
            alive = self._worker is not None and self._worker.is_alive()
            if (not is_fresh or fail is not None) and not waiting and not (alive and sym == self._reading):
                if sym in self._pending:
                    self._pending.remove(sym)
                self._pending.insert(0, sym)
                del self._pending[CHART_EVENTS_PENDING_MAX:]
            start = bool(self._pending) and not alive
            if start and not self._run_inline:
                self._worker = threading.Thread(target=self._drain, daemon=True, name="chart_events")
                self._worker.start()
        if start and self._run_inline:
            self._drain()
            with self._lock:
                record, fail = self._records.get(sym), self._fails.get(sym)
                is_fresh = record is not None and fresh(record["fetched_at"], now, CHART_EVENTS_TTL_SEC)
        if record is None:
            if fail is not None:
                return {"status": "error", "symbol": sym, "error": fail["error"], "retry_at": fail["retry_at"]}
            return {"status": "reading", "symbol": sym}
        return {**record, "status": "read", "symbol": sym, "stale": not is_fresh,
                "error": fail["error"] if fail else None, "retry_at": fail["retry_at"] if fail else None}

    # -- the reads (the worker's thread) -----------------------------------------------------------
    def _drain(self) -> None:
        while True:
            with self._lock:
                if not self._pending:
                    self._reading = None
                    if not self._run_inline:
                        self._worker = None
                    return
                sym = self._reading = self._pending.pop(0)
            self.read(sym)

    def read(self, symbol: str) -> None:
        """Read every source for one symbol on this thread and keep the answer. A part that fails keeps its
        reason (and the last good events) and the symbol is read again after the retry wait."""
        sym = (symbol or "").strip().upper()
        today = datetime.fromtimestamp(self._clock()).date()
        since = today - timedelta(days=CHART_EVENTS_HISTORY_DAYS)
        with self._lock:
            held = self._records.get(sym) or {}
        record: dict[str, Any] = {"fetched_at": self._clock(), "splits": self._splits.read(sym, since, held)}
        try:
            cik, name, submissions, pages, facts = self._read_sec(sym, since)
        except Exception as exc:  # noqa: BLE001 -- one source failing never hides the other; the answer says why
            logger.warning("chart events: SEC read failed for %s: %s", sym, exc)
            record["earnings"] = {**(held.get("earnings") or {"events": []}), "status": "error",
                                  "error": _why(exc), "source": CHART_EVENTS_SOURCE_SEC}
            self._keep(sym, record)
            return
        if cik is None:
            record["earnings"] = {"status": "no_cik", "source": CHART_EVENTS_SOURCE_SEC, "cik": None, "name": None,
                                  "events": [], "error": None, "scan": None, "foreign_6k": False}
            self._keep(sym, record)
            return
        rows = earnings.filings(submissions, pages)
        # Every release is known from the oldest filing read (all of them within the window, unless a page
        # failed); a registrant that files 6-Ks only from the first day its 6-Ks are read.
        unread = [to for name_, to in earnings.older_pages(submissions, since) if name_ not in pages]
        known = max(since, max(unread) + timedelta(days=1)) if unread else since
        scan_since = today - timedelta(days=CHART_EVENTS_6K_SCAN_DAYS)
        listed = earnings.release_filings(rows, scan_since)
        files_6k = any(r.get("form") in CHART_EVENTS_INTERIM_FORMS for r in rows)
        todo = [r for r in listed if r["accessionNumber"] not in self._readings]
        failed: list[str] = []

        def answer() -> dict[str, Any]:
            cut = max(known, scan_since) if files_6k else known
            return {"status": "read", "source": CHART_EVENTS_SOURCE_SEC, "cik": cik, "name": name,
                    "error": f"{len(failed)} filing(s) could not be read" if failed else None,
                    "releases_known_since": cut.isoformat(), "foreign_6k": files_6k,
                    "events": earnings.events(submissions, facts, pages=pages, readings=self._readings,
                                              since=since, releases_known_since=cut),
                    "scan": {"since": scan_since.isoformat(), "listed": len(listed),
                             "pending": sum(1 for r in listed if r["accessionNumber"] not in self._readings)
                             - len(failed),
                             "failed": len(failed)}}

        record["earnings"] = answer()
        self._keep(sym, record, partial=bool(todo))
        if not todo:
            return
        for i, row in enumerate(todo, start=1):
            accn = row["accessionNumber"]
            try:
                self._readings[accn] = self._read_release(cik, row)
            except Exception as exc:  # noqa: BLE001 -- an unread filing is counted in scan.failed and read again later
                failed.append(accn)
                logger.warning("chart events: %s %s of %s unread: %s", row.get("form"), accn, sym, exc)
            if i < len(todo) and i % CHART_EVENTS_6K_KEEP_EVERY == 0:
                record["earnings"] = answer()
                self._keep(sym, record, partial=True)
        for accn in list(self._readings)[: max(0, len(self._readings) - CHART_EVENTS_6K_CACHE_MAX)]:
            self._readings.pop(accn, None)
        record["earnings"] = answer()
        self._keep(sym, record)

    def _read_release(self, cik: int, row: dict[str, Any]) -> dict[str, Any] | None:
        """What a 6-K or Item 2.02 8-K says (``release_text``): its cover, and its Exhibit 99.1 when the cover
        only says a press release is attached."""
        folder = row["accessionNumber"].replace("-", "")
        cover = self._get(CHART_EVENTS_6K_DOC_URL.format(cik=cik, accession=folder, document=row["primaryDocument"]))
        if earnings.is_release_8k(row):
            reading = release_text.read_8k(cover, str(row.get("items") or ""))
        else:
            reading = release_text.read_6k(cover)
        if reading is None or reading["kind"] != "unknown":
            return reading
        listing = json.loads(self._get(CHART_EVENTS_FILING_INDEX_URL.format(cik=cik, accession=folder)))
        names = [str(item.get("name") or "") for item in ((listing.get("directory") or {}).get("item") or [])]
        exhibits = sorted((n for n in names if _EXHIBIT.search(n) and n.lower().endswith((".htm", ".html", ".txt"))),
                          key=lambda n: (not re.search(r"99[-_.]?0?1(?!\d)", n), n))
        if not exhibits:
            return reading
        exhibit = self._get(CHART_EVENTS_6K_DOC_URL.format(cik=cik, accession=folder, document=exhibits[0]))
        return release_text.merge(reading, release_text.read_exhibit(exhibit))

    def _keep(self, sym: str, record: dict[str, Any], *, partial: bool = False) -> None:
        failed = [f"{name}: {part['error']}" for name, part in (("earnings", record["earnings"]),
                                                                ("splits", record["splits"]))
                  if part.get("error")]
        with self._lock:
            self._records[sym] = dict(record)
            if len(self._records) > CHART_EVENTS_KEEP_SYMBOLS:
                oldest = sorted(self._records, key=lambda s: self._records[s]["fetched_at"])
                for s in oldest[: len(self._records) - CHART_EVENTS_KEEP_SYMBOLS]:
                    self._records.pop(s, None)
                    self._fails.pop(s, None)
            if partial:
                return
            if not failed:
                self._fails.pop(sym, None)
                return
            count = int((self._fails.get(sym) or {}).get("count", 0)) + 1
            wait = CHART_EVENTS_RETRY_SEC[min(count, len(CHART_EVENTS_RETRY_SEC)) - 1]
            self._fails[sym] = {"count": count, "error": "; ".join(failed), "retry_at": self._clock() + wait}

    def _read_sec(self, sym: str, since: date) -> tuple[int | None, str | None, dict, dict, dict]:
        """The registrant's CIK and name, its submissions file, the older pages that reach ``since`` (a page
        that fails is left unread, and the answer's ``releases_known_since`` stops short of it), and its
        financial facts."""
        cik = self._ticker_list().get(ticker_key(sym))
        if cik is None:
            return None, None, {}, {}, {}
        submissions = json.loads(self._get(STOCK_READ_DILUTION_SUBMISSIONS_URL.format(cik=cik)))
        pages: dict[str, dict] = {}
        for page, _to in earnings.older_pages(submissions, since):
            if not _PAGE_NAME.match(page):
                break
            try:
                pages[page] = json.loads(self._get(STOCK_READ_DILUTION_PAGE_URL.format(name=page)))
            except Exception as exc:  # noqa: BLE001 -- releases are then known only back to this page's end
                logger.warning("chart events: SEC page %s of %s unread: %s", page, sym, exc)
                break
        facts = json.loads(self._get(CHART_EVENTS_COMPANYFACTS_URL.format(cik=cik)))
        return cik, submissions.get("name"), submissions, pages, facts

    def _ticker_list(self) -> dict[str, int]:
        """SEC's ticker -> CIK list, read again once a day. A list that cannot be read again is still used
        (a listed ticker's registrant seldom changes); with none ever read, the read fails."""
        now = self._clock()
        if self._tickers is not None and fresh(self._tickers_at, now, CHART_EVENTS_TICKERS_TTL_SEC):
            return self._tickers
        try:
            self._tickers = parse_tickers(json.loads(self._get(CATALYST_FEED_SEC_TICKERS_URL)))
            self._tickers_at = self._clock()
        except Exception:
            if self._tickers is None:
                raise
            logger.warning("chart events: SEC's ticker list could not be read again; using the list held",
                           exc_info=True)
        return self._tickers

    def _get(self, url: str) -> bytes:
        if self._last_request is not None:
            wait = CHART_EVENTS_SEC_MIN_GAP_SEC - (self._monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._monotonic()
        agent = os.environ.get(SEC_USER_AGENT_ENV) or CATALYST_FEED_SEC_USER_AGENT_DEFAULT
        return self._fetch(url, {"User-Agent": agent})


_reader: ChartEventsReader | None = None
_reader_lock = threading.Lock()


def get_reader() -> ChartEventsReader:
    global _reader
    with _reader_lock:
        if _reader is None:
            _reader = ChartEventsReader()
        return _reader


def view(symbol: str, now: float | None = None) -> dict[str, Any]:
    return get_reader().view(symbol, now)


def reset_for_tests(reader: ChartEventsReader | None = None) -> None:
    global _reader
    with _reader_lock:
        _reader = reader
