"""Read one stock-day from the Massive flat files into the Massive store (ADR 046).

``run`` is the import itself, wherever it runs (the worker process in the desk, a
thread in tests): it reads the day's trades, 1-minute bars and NBBO quotes for one
ticker (``massive_files``) once, and writes what it keeps in one transaction
(``massive_store.replace_window``) -- whole or absent. ``massive_import`` owns the
job around it: starting, pausing, listing.

What it keeps (amendment 2026-10-09): the job's whole span -- a stock-day's session --
while every reader holds no more rows than a selection can (``_Kept``). As soon as one
reader passes its cap, every reader keeps only the job's focus window and goes on
counting, so a day over a cap is found out in the same read, never a second one. The
day's 1-minute bars are always kept whole.

The three files are read side by side (zlib inflates without the GIL), and the
job's ``scan_pct`` is the share of their bytes read, rewritten at least every
``SIM_MASSIVE_PROGRESS_EVERY_SEC`` -- the import's heartbeat. A day whose quotes
file is not on disk yet imports trades and bars and says so (``quote_status:
"not_downloaded"``).

A focus window with more prints (or quotes) than a selection can hold is refused
with the count as soon as a reader passes the cap, before anything is written.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from constants_sim import (
    SIM_HISTORY_MAX_SELECTION_PRINTS, SIM_MASSIVE_MAX_SELECTION_QUOTES, SIM_MASSIVE_MINUTES,
    SIM_MASSIVE_MINUTES_SCOPE_DAY as MINUTES_SCOPE_DAY, SIM_MASSIVE_PROGRESS_EVERY_SEC, SIM_MASSIVE_QUOTES,
    SIM_MASSIVE_TRADES,
)
from sim import massive_files as files, massive_store as store

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


class TooLarge(ValueError):
    """The window holds more rows than a replay selection can."""


class _Kept:
    """One reader's rows in the job's span: all of them while no reader is over its cap, else the focus window's.

    ``over`` is shared by the readers. The first to pass its cap sets it (``passed``), and each reader trims
    what it holds to the focus the next time it adds a row, and once more when the reading ends. ``count``
    is every row of the span read, kept or not: the day's size, for the job to state.
    """

    def __init__(self, what: str, limit: int, span: tuple[float, float], focus: tuple[float, float],
                 over: threading.Event, ts):
        self.what, self.limit, self.span, self.focus, self.over, self.ts = what, limit, span, focus, over, ts
        self.rows: list = []
        self.count = 0
        self.passed = self.trimmed = False

    def add(self, item, symbol: str) -> None:
        at = self.ts(item)
        if not self.span[0] <= at < self.span[1]:
            return
        self.count += 1
        if self.over.is_set():
            self.trim()
            if not self.focus[0] <= at < self.focus[1]:
                return
        self.rows.append(item)
        if len(self.rows) <= self.limit:
            return
        if not self.trimmed:                            # the day is over this cap: keep only the focus from now on
            self.passed = True
            self.over.set()
            self.trim()
        if len(self.rows) > self.limit:                 # the focus alone: refused as soon as it is, not after the file
            raise TooLarge(f"{symbol} {self.what} {self.limit:,} in this window, more than a replay holds; narrow the window")

    def trim(self) -> None:
        if not self.trimmed:
            self.trimmed = True
            self.rows = [row for row in self.rows if self.focus[0] <= self.ts(row) < self.focus[1]]


def _hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M")


class _Progress:
    """Throttled job rewrites from the readers running side by side: the desk's progress, and the import's heartbeat.

    ``stop`` (the operator's pause) and a reader's failure both raise ``halt``, which
    every reader checks between chunks, so one failing reader ends the others too.
    """

    def __init__(self, job_id: str, sizes: dict[str, int], stop: threading.Event | None):
        total = max(sum(sizes.values()), 1)
        self.job_id, self.stop = job_id, stop
        self.shares = {name: size / total for name, size in sizes.items()}   # by bytes to inflate
        self.fractions = dict.fromkeys(sizes, 0.0)
        self.halt = threading.Event()
        self.lock = threading.Lock()
        self.last = 0.0

    def reporter(self, name: str):
        def report(fraction: float) -> None:
            if self.stop is not None and self.stop.is_set():
                self.halt.set()
            with self.lock:
                self.fractions[name] = min(max(fraction, 0.0), 1.0)
                now = time.monotonic()
                if now - self.last < SIM_MASSIVE_PROGRESS_EVERY_SEC:
                    return
                self.last = now
                pct = round(100 * sum(self.shares[k] * f for k, f in self.fractions.items()), 2)
                stages = {k: round(100 * f, 1) for k, f in self.fractions.items()}
            store.update(self.job_id, stage="reading", scan_pct=min(pct, 98.0), stages=stages)
        return report


def _read_side_by_side(readers: dict, meter: _Progress) -> dict[str, list]:
    """Run each ``name -> callable(progress, halt)`` on its own thread (zlib inflates without the GIL)."""
    results: dict[str, list] = {}
    errors: list[BaseException] = []

    def work(name, read):
        try:
            results[name] = read(meter.reporter(name), meter.halt)
        except BaseException as exc:  # recorded and re-raised on the calling thread
            errors.append(exc)
            meter.halt.set()
    threads = [threading.Thread(target=work, args=item, daemon=True, name=f"massive-{item[0]}") for item in readers.items()]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    real = [exc for exc in errors if not isinstance(exc, files.Cancelled)]
    if real:
        raise real[0]
    if errors or (meter.stop is not None and meter.stop.is_set()):
        raise files.Cancelled()
    return results


def run(job_id: str, stop: threading.Event | None = None) -> dict:
    """Read the stock-day once, keep the whole span (or the focus, over a cap) and store it; returns the completed job."""
    job = store.get(job_id)
    if job is None:
        raise ValueError("Import not found")
    symbol, day, start, end = job["symbol"], job["date"], job["start_ts"], job["end_ts"]
    # The window asked for, inside the span: kept instead of the span when the day is over a cap.
    focus = (max(job.get("focus_start_ts") or start, start), min(job.get("focus_end_ts") or end, end))
    trades_file = files.day_file(SIM_MASSIVE_TRADES, day)
    if trades_file is None:
        raise ValueError(f"The Massive trades file for {day} is not on disk (yet)")
    quotes_file = files.day_file(SIM_MASSIVE_QUOTES, day)
    minutes_file = files.day_file(SIM_MASSIVE_MINUTES, day)
    paths = {name: path for name, path in ((SIM_MASSIVE_TRADES, trades_file), (SIM_MASSIVE_MINUTES, minutes_file),
                                           (SIM_MASSIVE_QUOTES, quotes_file)) if path is not None}
    meter = _Progress(job_id, {name: path.stat().st_size for name, path in paths.items()}, stop)
    store.update(job_id, stage="reading", scan_pct=0.0, stages=dict.fromkeys(paths, 0.0))
    began = time.time()
    over = threading.Event()
    trades = _Kept("printed over", SIM_HISTORY_MAX_SELECTION_PRINTS, (start, end), focus, over, lambda p: p["ts"])
    quoted = _Kept("quoted over", SIM_MASSIVE_MAX_SELECTION_QUOTES, (start, end), focus, over, lambda q: q[0])
    # The NBBO standing when the span opens, and when the focus opens: whichever is kept starts with it.
    opening: dict[str, tuple | None] = dict(span=None, focus=None)

    def quote(row):
        item = files.quote(row)
        for name, edge in (("span", start), ("focus", focus[0])):
            if item[0] < edge and (opening[name] is None or item[0] >= opening[name][0]):
                opening[name] = item
        return item

    def keeping(path, convert, kept):
        def read(progress, halt):
            for item in files.rows(path, symbol, convert, progress=progress, stop=halt):
                kept.add(item, symbol)
            return kept
        return read
    readers = {SIM_MASSIVE_TRADES: keeping(trades_file, lambda row: files.trade(row, symbol), trades)}
    if minutes_file is not None:
        readers[SIM_MASSIVE_MINUTES] = lambda progress, halt: list(files.rows(minutes_file, symbol, files.minute,
                                                                               progress=progress, stop=halt))
    if quotes_file is not None:
        readers[SIM_MASSIVE_QUOTES] = keeping(quotes_file, quote, quoted)
    results = _read_side_by_side(readers, meter)
    capped = over.is_set()
    if capped:
        trades.trim()                                   # a reader that saw no row after another passed its cap
        quoted.trim()
    lo, hi = focus if capped else (start, end)
    prints = sorted(trades.rows, key=lambda p: (p["ns"], p["sequence"]))
    # The ticker's whole day of 1-minute bars, not only the window's: the charts draw the day before the
    # window from them (premarket, the open, the run that led in), never past the playhead (operator, 2026-10-09).
    bars = sorted(results.get(SIM_MASSIVE_MINUTES, []), key=files.minute_start)
    quotes: list[tuple] = []
    if quotes_file is not None:
        # The first prints kept are judged against the quote standing when they open, never a later one.
        first = opening["focus" if capped else "span"]
        quotes = ([first] if first is not None else []) + sorted(quoted.rows, key=lambda q: q[0])
    quote_status = "not_downloaded" if quotes_file is None else ("complete" if quotes else "none")
    over_cap = next((kept for kept in (trades, quoted) if kept.passed), None)
    cap = None if over_cap is None else dict(what="prints" if over_cap is trades else "quotes", count=over_cap.count,
                                             limit=over_cap.limit)
    store.update(job_id, stage="saving", scan_pct=99.0)
    dropped = store.replace_window(job_id, prints, bars, quotes, drop_held=(symbol, day, lo, hi))
    volume = sum(p["size"] for p in prints if p["sets_price"])
    logger.info("Massive import %s %s kept %s-%s%s: %d prints, %d bars, %d quotes (%s) in %.0f s; %d older imports "
                "dropped", symbol, day, _hhmm(lo), _hhmm(hi), f" ({cap['what']} over {cap['limit']:,})" if cap else "",
                len(prints), len(bars), len(quotes), quote_status, time.time() - began, len(dropped))
    return store.update(job_id, status="complete", stage=None, stages=None, scan_pct=100.0, ranges=[[lo, hi]],
                        cursor=hi, count=len(prints), volume=volume, bar_count=len(bars), quote_count=len(quotes),
                        quote_status=quote_status, error=None, kept_start=_hhmm(lo), kept_end=_hhmm(hi), capped=cap,
                        minutes_scope=MINUTES_SCOPE_DAY if minutes_file is not None else None,
                        elapsed_sec=round(time.time() - began, 1),
                        files=dict(trades=True, quotes=quotes_file is not None, minute_aggs=minutes_file is not None))
