"""Read one replay window from the Massive flat files into the Massive store (ADR 046).

``run`` is the import itself, wherever it runs (the worker process in the desk, a
thread in tests): it reads the day's trades, 1-minute bars and NBBO quotes for one
ticker (``massive_files``), keeps the window's prints and quotes and the day's
1-minute bars, and writes them in one transaction (``massive_store.replace_window``) -- the window is whole or absent.
``massive_import`` owns the job around it: starting, pausing, listing.

The three files are read side by side (zlib inflates without the GIL), and the
job's ``scan_pct`` is the share of their bytes read, rewritten at least every
``SIM_MASSIVE_PROGRESS_EVERY_SEC`` -- the import's heartbeat. A day whose quotes
file is not on disk yet imports trades and bars and says so (``quote_status:
"not_downloaded"``).

A window with more prints (or quotes) than a selection can hold is refused with
the count as soon as a reader passes the cap, before anything is written.
"""
from __future__ import annotations

import logging
import threading
import time

from constants_sim import (
    SIM_HISTORY_MAX_SELECTION_PRINTS, SIM_MASSIVE_MAX_SELECTION_QUOTES, SIM_MASSIVE_MINUTES,
    SIM_MASSIVE_MINUTES_SCOPE_DAY as MINUTES_SCOPE_DAY, SIM_MASSIVE_PROGRESS_EVERY_SEC, SIM_MASSIVE_QUOTES,
    SIM_MASSIVE_TRADES,
)
from sim import massive_files as files, massive_store as store

logger = logging.getLogger(__name__)


class TooLarge(ValueError):
    """The window holds more rows than a replay selection can."""


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
    """Read, filter and store one window; returns the completed job."""
    job = store.get(job_id)
    if job is None:
        raise ValueError("Import not found")
    symbol, day, start, end = job["symbol"], job["date"], job["start_ts"], job["end_ts"]
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
    opening: list[tuple] = []

    def kept_trade(row):
        item = files.trade(row, symbol)
        return item if item is not None and start <= item["ts"] < end else None

    def kept_quote(row):
        item = files.quote(row)
        if item[0] < start:
            opening[:] = [item]                         # the NBBO in force when the window opens
            return None
        return item if item[0] < end else None

    def capped(path, convert, limit, what):
        def read(progress, halt):
            out = []
            for item in files.rows(path, symbol, convert, progress=progress, stop=halt):
                out.append(item)
                if len(out) > limit:                    # refused as soon as it is too large, not after the whole file
                    raise TooLarge(f"{symbol} {what} {limit:,} in this window, more than a replay holds; narrow the window")
            return out
        return read
    readers = {SIM_MASSIVE_TRADES: capped(trades_file, kept_trade, SIM_HISTORY_MAX_SELECTION_PRINTS, "printed over")}
    if minutes_file is not None:
        readers[SIM_MASSIVE_MINUTES] = lambda progress, halt: list(files.rows(minutes_file, symbol, files.minute,
                                                                               progress=progress, stop=halt))
    if quotes_file is not None:
        readers[SIM_MASSIVE_QUOTES] = capped(quotes_file, kept_quote, SIM_MASSIVE_MAX_SELECTION_QUOTES, "quoted over")
    results = _read_side_by_side(readers, meter)
    prints = sorted(results[SIM_MASSIVE_TRADES], key=lambda p: (p["ns"], p["sequence"]))
    # The ticker's whole day of 1-minute bars, not only the window's: the charts draw the day before the
    # window from them (premarket, the open, the run that led in), never past the playhead (operator, 2026-10-09).
    bars = sorted(results.get(SIM_MASSIVE_MINUTES, []), key=files.minute_start)
    quotes: list[tuple] = []
    if quotes_file is not None:
        # The window's first prints are judged against the quote standing at its open, never a later one.
        quotes = opening + sorted(results[SIM_MASSIVE_QUOTES], key=lambda q: q[0])
    quote_status = "not_downloaded" if quotes_file is None else ("complete" if quotes else "none")
    store.update(job_id, stage="saving", scan_pct=99.0)
    store.replace_window(job_id, prints, bars, quotes)
    volume = sum(p["size"] for p in prints if p["sets_price"])
    logger.info("Massive import %s %s %s-%s: %d prints, %d bars, %d quotes (%s) in %.0f s", symbol, day, job["start"],
                job["end"], len(prints), len(bars), len(quotes), quote_status, time.time() - began)
    return store.update(job_id, status="complete", stage=None, stages=None, scan_pct=100.0, ranges=[[start, end]],
                        cursor=end, count=len(prints), volume=volume, bar_count=len(bars), quote_count=len(quotes),
                        quote_status=quote_status, error=None,
                        minutes_scope=MINUTES_SCOPE_DAY if minutes_file is not None else None,
                        elapsed_sec=round(time.time() - began, 1),
                        files=dict(trades=True, quotes=quotes_file is not None, minute_aggs=minutes_file is not None))
