"""One build of a rebuilt day's Gappers by the second, wherever it runs (the worker process, a thread in tests).

Stages, each written to the job file (``store.write_job``) so the desk can say where it is:
``inputs`` (the stored day, the minute file, prior closes), ``index`` (the trades file's seek index), ``trades``
(each candidate's prints, ``done`` of ``total`` stocks, read in file order so the disk reads forward) and
``writing``. Nothing is visible before the data file is renamed into place, whole.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any

from constants_leaderboard import (
    LEADERBOARD_SECONDS_BOARD,
    LEADERBOARD_SECONDS_BUILDING,
    LEADERBOARD_SECONDS_PROGRESS_EVERY_SEC,
    LEADERBOARD_SECONDS_READY,
    LEADERBOARD_SECONDS_SCHEMA_VERSION,
    LEADERBOARD_SECONDS_STAGE_INDEX,
    LEADERBOARD_SECONDS_STAGE_INPUTS,
    LEADERBOARD_SECONDS_STAGE_TRADES,
    LEADERBOARD_SECONDS_STAGE_WRITING,
)
from leaderboard.seconds import build, inputs, store

logger = logging.getLogger(__name__)
BOARD = LEADERBOARD_SECONDS_BOARD


class _Progress:
    """The job file, rewritten when the stage changes and at most every ``PROGRESS_EVERY_SEC`` otherwise."""

    def __init__(self, day: str):
        self.day, self.last, self.stage = day, 0.0, None

    def __call__(self, stage: str, done: int | None = None, total: int | None = None, *, force: bool = False) -> None:
        now = time.monotonic()
        if stage == self.stage and not force and now - self.last < LEADERBOARD_SECONDS_PROGRESS_EVERY_SEC:
            return
        self.stage, self.last = stage, now
        store.write_job(self.day, BOARD, status=LEADERBOARD_SECONDS_BUILDING, stage=stage, done=done, total=total)


def candidates_for(day: str, stored: inputs.StoredDay) -> tuple[list[build.Candidate], int]:
    """Every minute's candidates, and how many premarket stocks came from outside the store's prior closes."""
    universe = inputs.universe()
    known = stored.prev_close

    def keep(ticker: str) -> bool:
        return ticker in known or ticker in universe

    bars = inputs.minute_bars(day, keep)
    freeze = inputs.freeze_ts(day)
    outside = inputs.outside_prior_closes(day, sorted(t for t in bars if t not in known))
    prev_close = {**outside, **known}
    premarket = list(inputs.premarket_minutes(day))
    out: list[build.Candidate] = []
    from_outside: set[str] = set()
    for symbol, series in bars.items():
        found = build.premarket_candidates(symbol, [b for b in series if b[0] < freeze], prev_close.get(symbol),
                                           premarket)
        if found and symbol not in known:
            from_outside.add(symbol)
        out.extend(found)
    out.extend(build.frozen_candidates(stored.frozen, bars, prev_close, list(inputs.frozen_minutes(day))))
    return out, len(from_outside)


def run(day: str, stop: threading.Event | None = None) -> dict[str, Any]:
    """Build the day's file and mark the job ready; returns the summary. Raises (the job says why) on failure."""
    started = time.monotonic()
    progress = _Progress(day)
    progress(LEADERBOARD_SECONDS_STAGE_INPUTS, force=True)
    stored = inputs.stored_day(day)
    if stored is None:
        raise LookupError(f"The leaderboard store holds no rebuilt Gappers for {day}")
    candidates, from_outside = candidates_for(day, stored)
    by_minute: dict[int, list[build.Candidate]] = defaultdict(list)
    minutes_of: dict[str, set[int]] = defaultdict(set)
    for candidate in candidates:
        by_minute[candidate.minute].append(candidate)
        minutes_of[candidate.symbol].add(candidate.minute)
    check = build.check_minutes(stored.gappers, by_minute, inputs.premarket_minutes(day))

    progress(LEADERBOARD_SECONDS_STAGE_INDEX, force=True)
    index = inputs.ensure_index(day, stop, lambda: progress(LEADERBOARD_SECONDS_STAGE_INDEX, force=True))

    symbols = sorted(minutes_of)
    writer = store.DataWriter(day, BOARD)
    try:
        writer.candidates(candidates)
        rows = indexed = 0
        for done, symbol in enumerate(symbols):
            if stop is not None and stop.is_set():
                raise inputs.Cancelled()
            progress(LEADERBOARD_SECONDS_STAGE_TRADES, done, len(symbols))
            minutes = minutes_of[symbol]
            read = inputs.TradeRead(day, symbol, max(minutes) + 60, stop)
            seconds = build.tally_seconds(read, minutes)
            writer.seconds(symbol, seconds)
            rows += len(seconds)
            indexed += bool(read.indexed)
        progress(LEADERBOARD_SECONDS_STAGE_WRITING, len(symbols), len(symbols), force=True)
        summary = {
            "candidates": len(symbols), "from_outside_store": from_outside, "stocks_read": len(symbols),
            "seconds_rows": rows, "read_indexed": indexed, "index": index, **check,
            "build_sec": round(time.monotonic() - started, 1),
        }
        writer.finish({"schema_version": LEADERBOARD_SECONDS_SCHEMA_VERSION, "built_ts": time.time(),
                       "fingerprint": stored.fingerprint, "summary": summary})
    except BaseException:
        writer.abort()
        raise
    store.write_job(day, BOARD, status=LEADERBOARD_SECONDS_READY, stage=None, done=len(symbols), total=len(symbols),
                    finished_ts=time.time(), error=None, fingerprint=stored.fingerprint, summary=summary)
    logger.info("Gappers by the second for %s: %s", day, summary)
    return summary
