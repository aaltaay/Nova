"""One build of a rebuilt day's HOD Momo alerts, wherever it runs (the worker process, a thread in tests).

Stages, each written to the job file so the desk can say where it is: ``inputs`` (the rebuilt boards, the active
set minute by minute, day-bar facts and Yahoo floats), ``index`` (the trades file's seek index), ``trades`` (each
watched stock's trades into L1 ticks, ``done`` of ``total`` stocks), ``engine`` (the ticks through HOD Momo,
``done`` of ``total`` ticks) and ``writing``. Nothing is visible before the alerts file is written whole.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from constants_hod_momo import (
    HOD_MOMO_REBUILD_FLOAT_BASIS,
    HOD_MOMO_REBUILD_LOGIC_VERSION,
    HOD_MOMO_REBUILD_PROGRESS_EVERY_SEC,
)
from constants_leaderboard import (
    LEADERBOARD_SECONDS_BUILDING,
    LEADERBOARD_SECONDS_READY,
    LEADERBOARD_SECONDS_STAGE_INDEX,
    LEADERBOARD_SECONDS_STAGE_INPUTS,
    LEADERBOARD_SECONDS_STAGE_TRADES,
    LEADERBOARD_SECONDS_STAGE_WRITING,
)
from hod_momo_rebuild import daily, engine, store, ticks, watch
from leaderboard.seconds import inputs

logger = logging.getLogger(__name__)
STAGE_ENGINE = "engine"


def fingerprint(boards: str, config: str) -> str:
    """What a build depends on: the rebuild's logic, the day's rebuilt boards and the operator's HOD settings."""
    return f"{HOD_MOMO_REBUILD_LOGIC_VERSION}:{boards}:{config}"


class _Progress:
    """The job file, rewritten when the stage changes and at most every ``PROGRESS_EVERY_SEC`` otherwise."""

    def __init__(self, day: str):
        self.day, self.last, self.stage = day, 0.0, None

    def __call__(self, stage: str, done: int | None = None, total: int | None = None, *, force: bool = False) -> None:
        now = time.monotonic()
        if stage == self.stage and not force and now - self.last < HOD_MOMO_REBUILD_PROGRESS_EVERY_SEC:
            return
        self.stage, self.last = stage, now
        store.write_job(self.day, status=LEADERBOARD_SECONDS_BUILDING, stage=stage, done=done, total=total)


def run(day: str, stop: threading.Event | None = None) -> dict[str, Any]:
    """Build the day's alerts file and mark the job ready; returns the summary. Raises (the job says why)."""
    started = time.monotonic()
    progress = _Progress(day)
    progress(LEADERBOARD_SECONDS_STAGE_INPUTS, force=True)
    plan = watch.plan(day)
    if plan is None:
        raise LookupError(f"The leaderboard store holds no rebuilt boards for {day}")
    minutes = plan.active_minutes()
    symbols = sorted(minutes)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="hod-rebuild-floats") as pool:
        floats_later = pool.submit(daily.floats, symbols)       # Yahoo answers while the files are read
        facts = daily.history(day, symbols)

        progress(LEADERBOARD_SECONDS_STAGE_INDEX, force=True)
        index = inputs.ensure_index(day, stop, lambda: progress(LEADERBOARD_SECONDS_STAGE_INDEX, force=True))
        days: dict[str, ticks.SymbolDay] = {}
        for done, symbol in enumerate(symbols):
            if stop is not None and stop.is_set():
                raise inputs.Cancelled()
            progress(LEADERBOARD_SECONDS_STAGE_TRADES, done, len(symbols))
            days[symbol] = ticks.build(symbol, inputs.TradeRead(day, symbol, max(minutes[symbol]) + 60, stop),
                                       minutes[symbol])
        floats = floats_later.result()
    for symbol, fund in floats.items():
        fact = facts[symbol]
        fact.float_shares = fund.get("float_shares")
        fact.float_contradicted = fund.get("float_contradicted")
        fact.shares_outstanding = fund.get("shares_outstanding")

    progress(STAGE_ENGINE, 0, sum(len(d) for d in days.values()), force=True)
    result = engine.run(day, days, plan.prev_close, facts, stop=stop,
                        progress=lambda done, total: progress(STAGE_ENGINE, done, total))
    if stop is not None and stop.is_set():
        raise inputs.Cancelled()

    progress(LEADERBOARD_SECONDS_STAGE_WRITING, force=True)
    mark = fingerprint(plan.fingerprint, result.config)
    summary = {
        "watched": len(symbols),
        "watched_minutes": sum(len(m) for m in minutes.values()),
        "prints": sum(d.prints for d in days.values()),
        "ticks": result.ticks,
        "alerts": len(result.alerts),
        "pending_unflushed": result.pending_unflushed,
        "with_float": sum(1 for f in facts.values() if f.float_shares),
        "with_avg_volume": sum(1 for f in facts.values() if f.avg_volume),
        "with_52wk_high": sum(1 for f in facts.values() if f.fifty_two_week_high),
        "index": index,
        "build_sec": round(time.monotonic() - started, 1),
    }
    store.write_data(day, fingerprint=mark, float_basis=HOD_MOMO_REBUILD_FLOAT_BASIS, summary=summary,
                     alerts=result.alerts)
    store.write_job(day, status=LEADERBOARD_SECONDS_READY, stage=None, done=None, total=None,
                    finished_ts=time.time(), error=None, fingerprint=mark, summary=summary)
    logger.info("HOD rebuild for %s: %s", day, summary)
    return summary
