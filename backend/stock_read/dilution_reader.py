"""The read of SEC EDGAR behind "Dilution on file" (ADR 036): in the background, never on the stock read.

``view(symbol)`` answers from memory at once -- the last read kept for the symbol, or that one is under
way, failed, or cannot be made (SEC's ticker list does not hold the symbol) -- and queues a read when the
kept one is missing or no longer fresh. One daemon thread drains the queue: SEC's ticker -> CIK list
(``company_tickers.json``, the list the catalyst feed reads), the registrant's submissions file, and the
older pages ``dilution.pages_wanted`` names. Every request carries the desk's SEC user agent
(``SEC_USER_AGENT`` in ``.env``, else the catalyst feed's default) and is at least
``STOCK_READ_DILUTION_SEC_MIN_GAP_SEC`` after the one before.

A read is fresh for its session day: until the next 04:00 ET, and never longer than
``STOCK_READ_DILUTION_TTL_SEC``. A failed read is tried again after ``STOCK_READ_DILUTION_RETRY_SEC``, the
next time the symbol is asked about. Reads are kept on disk (``stock_read/dilution_store.py``), so a restart
keeps the day's. Always on; ``NOVA_DILUTION_READER=0`` turns it off. Read-only: nothing places, stages or
gates on it.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from constants_catalysts import CATALYST_FEED_SEC_TICKERS_URL, CATALYST_FEED_SEC_USER_AGENT_DEFAULT
from constants_stock_read import (
    STOCK_READ_DILUTION_DAY_START_HOUR_ET,
    STOCK_READ_DILUTION_ENV,
    STOCK_READ_DILUTION_KEEP_DAYS,
    STOCK_READ_DILUTION_PAGE_URL,
    STOCK_READ_DILUTION_RETRY_SEC,
    STOCK_READ_DILUTION_SEC_MIN_GAP_SEC,
    STOCK_READ_DILUTION_SUBMISSIONS_URL,
    STOCK_READ_DILUTION_TICKERS_TTL_SEC,
    STOCK_READ_DILUTION_TTL_SEC,
)
from stock_read import dilution, dilution_store

logger = logging.getLogger(__name__)
Fetch = Callable[[str, dict], bytes]
SEC_USER_AGENT_ENV = "SEC_USER_AGENT"       # the catalyst feed's setting: one user agent for every SEC read


def _http_get(url: str, headers: dict) -> bytes:
    from catalysts.feed import http_get     # the desk's transport for SEC (gzip, the feed's timeout)

    return http_get(url, headers)


def enabled() -> bool:
    return (os.environ.get(STOCK_READ_DILUTION_ENV) or "1").strip() != "0"


def session_start(now: float) -> float:
    """The last 04:00 ET at or before ``now``: what was read before it is read again."""
    at = datetime.fromtimestamp(float(now), dilution.ET)
    start = at.replace(hour=STOCK_READ_DILUTION_DAY_START_HOUR_ET, minute=0, second=0, microsecond=0)
    if at < start:
        start -= timedelta(days=1)
    return start.timestamp()


def fresh(fetched_at: float, now: float, ttl: float = STOCK_READ_DILUTION_TTL_SEC) -> bool:
    return now - fetched_at < ttl and fetched_at >= session_start(now)


def ticker_key(symbol: str) -> str:
    """A symbol as SEC's ticker list writes it: upper case, a share class after a hyphen (``BRK-B``)."""
    return re.sub(r"[ ./]+", "-", (symbol or "").strip().upper())


def parse_tickers(data: Any) -> dict[str, int]:
    """SEC's ``company_tickers.json`` as ticker -> CIK; a ticker listed twice keeps its first row."""
    rows = list(data.values()) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("not SEC's ticker list")
    out: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ticker = ticker_key(str(row.get("ticker") or ""))
        try:
            cik = int(row.get("cik_str"))
        except (TypeError, ValueError):
            continue
        if ticker:
            out.setdefault(ticker, cik)
    if not out:
        raise ValueError("SEC's ticker list holds no ticker")
    return out


class TickerListUnread(Exception):
    """SEC's ticker list could not be read and none is held: no symbol can be looked up."""


def _why(exc: BaseException) -> str:
    if isinstance(exc, TickerListUnread):
        return str(exc)[:200]
    return f"{type(exc).__name__}: {exc}"[:200]


class DilutionReader:
    def __init__(self, *, fetch: Fetch = _http_get, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic,
                 db: Any = None):
        self._fetch, self._clock, self._sleep, self._monotonic, self._db = fetch, clock, sleep, monotonic, db
        self._lock = threading.Lock()
        self._warmed = False
        self._records: dict[str, dict[str, Any]] = {}
        self._fails: dict[str, dict[str, Any]] = {}      # symbol -> {count, error, retry_at}
        self._pending: list[str] = []                    # symbols waiting for a read, in the order asked
        self._reading: str | None = None
        self._worker: threading.Thread | None = None
        # The worker's own (one thread reads EDGAR): SEC's ticker list and the pacing clock.
        self._tickers: dict[str, int] | None = None
        self._tickers_at = 0.0
        self._tickers_retry_at = 0.0
        self._tickers_error: str | None = None
        self._last_request: float | None = None
        self.store_error: str | None = None

    # -- the answer (any thread; memory only) ------------------------------------------------------
    def view(self, symbol: str, now: float | None = None) -> dict[str, Any]:
        """The symbol's answer now. Asking is what starts a read when none is kept or the kept one is no
        longer fresh; the answer never waits for it."""
        sym = (symbol or "").strip().upper()
        if not enabled():
            return {"status": "off", "symbol": sym}
        now = self._clock() if now is None else now
        self._warm()
        with self._lock:
            record, fail = self._records.get(sym), self._fails.get(sym)
            is_fresh = record is not None and fresh(record["fetched_at"], now)
            waiting = fail is not None and now < fail["retry_at"]
            working = self._worker is not None and self._worker.is_alive()
            if not is_fresh and not waiting and sym not in self._pending and not (working and sym == self._reading):
                self._pending.append(sym)
            if self._pending and not working:
                self._worker = threading.Thread(target=self._drain, daemon=True, name="stock_read_dilution")
                self._worker.start()
            if record is None:
                if waiting:
                    return {"status": "error", "symbol": sym, "error": fail["error"], "retry_at": fail["retry_at"]}
                return {"status": "reading", "symbol": sym}
            return {**record, "symbol": sym, "stale": not is_fresh, "error": fail["error"] if fail else None,
                    "retry_at": fail["retry_at"] if fail else None}

    # -- the reads (the worker's thread) -----------------------------------------------------------
    def _drain(self) -> None:
        while True:
            with self._lock:
                if not self._pending:
                    self._reading = self._worker = None
                    return
                sym = self._reading = self._pending.pop(0)
            self.read(sym)

    def read(self, symbol: str) -> None:
        """Read EDGAR for one symbol on this thread and keep the answer; a failure is kept as the reason."""
        sym = (symbol or "").strip().upper()
        self._warm()
        try:
            self._keep(sym, self._read(sym))
        except Exception as exc:  # noqa: BLE001 -- one symbol's failure never stops the queue; its row says why
            now = self._clock()
            with self._lock:
                count = int((self._fails.get(sym) or {}).get("count", 0)) + 1
                wait = STOCK_READ_DILUTION_RETRY_SEC[min(count, len(STOCK_READ_DILUTION_RETRY_SEC)) - 1]
                self._fails[sym] = {"count": count, "error": _why(exc), "retry_at": now + wait}
            logger.warning("stock read dilution: EDGAR read failed for %s (try %d): %s", sym, count, exc)

    def _keep(self, sym: str, record: dict[str, Any]) -> None:
        cutoff = record["fetched_at"] - STOCK_READ_DILUTION_KEEP_DAYS * 86400
        with self._lock:
            self._records = {s: r for s, r in self._records.items() if r["fetched_at"] >= cutoff}
            self._records[sym] = record
            self._fails.pop(sym, None)
            if self._db is None:
                return
            try:
                dilution_store.put(self._db, sym, record)
                dilution_store.prune(self._db, cutoff)
            except Exception as exc:  # noqa: BLE001 -- the read still answers from memory until a restart
                self.store_error = _why(exc)
                logger.warning("stock read dilution: could not keep the read of %s", sym, exc_info=True)

    def _read(self, sym: str) -> dict[str, Any]:
        tickers, listed_at = self._ticker_list()
        cik = tickers.get(ticker_key(sym))
        if cik is None:
            return {"status": "no_cik", "cik": None, "name": None, "filings": [], "more": [], "unread_to": None,
                    "listed_at": listed_at, "fetched_at": self._clock()}
        payload = json.loads(self._get(STOCK_READ_DILUTION_SUBMISSIONS_URL.format(cik=cik)))
        fetched = self._clock()
        today = dilution.today_et(fetched)
        pages = {name: json.loads(self._get(STOCK_READ_DILUTION_PAGE_URL.format(name=name)))
                 for name in dilution.pages_wanted(payload, today)}
        return {"status": "read", "cik": cik, "fetched_at": fetched, **dilution.digest(payload, pages, today)}

    def _ticker_list(self) -> tuple[dict[str, int], float]:
        """SEC's ticker -> CIK list and when it was read. One that cannot be read again is still used
        (a listed ticker's registrant seldom changes); with none ever read, the read fails. After a
        failure the list is not asked for again before the first retry wait is over."""
        now = self._clock()
        held = self._tickers
        if held is not None and fresh(self._tickers_at, now, STOCK_READ_DILUTION_TICKERS_TTL_SEC):
            return held, self._tickers_at
        if now >= self._tickers_retry_at:
            try:
                tickers = parse_tickers(json.loads(self._get(CATALYST_FEED_SEC_TICKERS_URL)))
            except Exception as exc:  # noqa: BLE001 -- said in the row (no list held), or an older list stands in
                self._tickers_retry_at = now + STOCK_READ_DILUTION_RETRY_SEC[0]
                self._tickers_error = f"SEC's ticker list could not be read ({_why(exc)})"
                logger.warning("stock read dilution: %s%s", self._tickers_error,
                               "; using the list held" if held is not None else "")
            else:
                self._tickers, self._tickers_at, self._tickers_error = tickers, self._clock(), None
                return tickers, self._tickers_at
        if held is None:
            raise TickerListUnread(self._tickers_error or "SEC's ticker list could not be read")
        return held, self._tickers_at

    def _get(self, url: str) -> bytes:
        if self._last_request is not None:
            wait = STOCK_READ_DILUTION_SEC_MIN_GAP_SEC - (self._monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._monotonic()
        agent = os.environ.get(SEC_USER_AGENT_ENV) or CATALYST_FEED_SEC_USER_AGENT_DEFAULT
        return self._fetch(url, {"User-Agent": agent})

    # -- the kept reads ----------------------------------------------------------------------------
    def _warm(self) -> None:
        """Open the store and take what it kept, once; a store that will not open leaves memory only."""
        if self._warmed:
            return
        with self._lock:
            if self._warmed:
                return
            self._warmed = True
            try:
                if self._db is None:
                    self._db = dilution_store.connect()
                cutoff = self._clock() - STOCK_READ_DILUTION_KEEP_DAYS * 86400
                self._records = {s: r for s, r in dilution_store.load(self._db).items() if r["fetched_at"] >= cutoff}
            except Exception as exc:  # noqa: BLE001 -- the reader still answers, from memory
                self.store_error = _why(exc)
                logger.exception("stock read dilution: the kept reads are unavailable; keeping reads in memory")

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None


_reader: DilutionReader | None = None
_reader_lock = threading.Lock()


def get_reader() -> DilutionReader:
    global _reader
    with _reader_lock:
        if _reader is None:
            _reader = DilutionReader()
        return _reader


def view(symbol: str, now: float | None = None) -> dict[str, Any]:
    return get_reader().view(symbol, now)


def reset_for_tests() -> None:
    global _reader
    with _reader_lock:
        if _reader is not None:
            _reader.close()
        _reader = None
