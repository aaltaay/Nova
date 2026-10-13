"""The Market page's refreshers (ADR 053): every read on its own cadence, warm while nobody looks.

Three daemon threads start with the process: ``ibkr``, ``history`` -- both on the IB loop through ``run_coro`` --
and ``files``; what each reads, and how often, is ``market_board.jobs``. Each takes the first due read,
runs it, records the answer or the failure in ``market_board.state`` and its time in the perf record
(``market_board.<read>``; ``market_board.first.<read>`` from the page opening to its first answer).

Warm (ADR 053 amendment 2026-10-13 evening): every read runs whenever IBKR is connected -- at its page cadence
while the page asked within ``MARKET_WANTED_SEC``, else at its slower background cadence (``Job.idle``) -- so the
page opens on a board that is already there. ``NOVA_MARKET_BOARD_WARM=0`` runs reads only while the page is wanted
(the NYSE breadth sample still runs once a minute in the regular session); ``NOVA_MARKET_BOARD=0`` runs nothing.
The ``files`` thread also keeps the IBKR answers on disk (``market_board.keep``), read back at the first start.
``run_once`` is the whole step for tests.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from functools import partial

from constants_market_board import (
    MARKET_BREADTH_SAMPLE_SEC,
    MARKET_ENV,
    MARKET_IDLE_WAIT_SEC,
    MARKET_SHED_RETRY_SEC,
    MARKET_TICK_SEC,
    MARKET_WARM_ENV,
)
from constants_scanner import SESSION_RTH_OPEN_MIN_ET
from market_board import breadth, clock, contracts, ibkr_reads, jobs, keep
from market_board.jobs import FOREVER, Job
from market_board.state import Stated, store

logger = logging.getLogger(__name__)


_group_last: dict[str, float] = {}
_threads: dict[str, threading.Thread] = {}
_threads_lock = threading.Lock()
LANES = ("ibkr", "history", "files")
IBKR_LANES = ("ibkr", "history")
_wake = {lane: threading.Event() for lane in LANES}


def enabled() -> bool:
    return (os.environ.get(MARKET_ENV) or "1").strip() != "0"


def warm() -> bool:
    """Reads keep a background cadence while nobody looks (``NOVA_MARKET_BOARD_WARM=0`` turns that off)."""
    return (os.environ.get(MARKET_WARM_ENV) or "1").strip() != "0"


def want(now: float | None = None) -> None:
    store().want(time.time() if now is None else now)
    _start()


def _breadth_sample(day_iso: str) -> dict | None:
    from datetime import date

    quotes = ibkr_reads.reference_quotes(contracts.breadth_specs(), day_iso)
    sample = breadth.sample_from(quotes)
    if sample is None:
        why = next((q.get("error") for q in quotes.values() if q.get("error")), None)
        raise ibkr_reads.SourceError(why or "IBKR gave no NYSE advancing / declining counts")
    breadth.record(sample, date.fromisoformat(day_iso), time.time())
    return sample


def breadth_due(now: float) -> bool:
    day = clock.trading_date(now)
    if clock.phase(now) != "regular" or now < clock.at(day, SESSION_RTH_OPEN_MIN_ET):
        return False
    return store().due("breadth_latest", now, MARKET_BREADTH_SAMPLE_SEC)


def run_once(lane: str, now: float | None = None) -> bool:
    """Run the first due read of ``lane`` (``ibkr`` | ``history`` | ``files``); False when none was due."""
    now = time.time() if now is None else now
    st = store()
    if lane in IBKR_LANES:
        if not ibkr_reads.ready():
            st.source_down(ibkr_reads.SOURCE, "IBKR is not connected")
            return False
        st.source_down(ibkr_reads.SOURCE, None)
        if lane == "ibkr" and breadth_due(now):
            _run(Job("breadth_latest", ibkr_reads.SOURCE, MARKET_BREADTH_SAMPLE_SEC,
                     partial(_breadth_sample, clock.trading_date(now).isoformat())), now, error_key="breadth")
            return True
    wanted = st.wanted(now)
    if not wanted and not warm():
        return False
    for job in jobs.for_lane(lane, now):
        if _due(job, now, wanted):
            _run(job, now)
            return True
    return False


def _due(job: Job, now: float, wanted: bool = True) -> bool:
    st = store()
    if job.gap_group and now - _group_last.get(job.gap_group, -FOREVER) < job.gap:
        return False
    if job.fresh is None:
        return st.due(job.key, now, job.ttl_now(wanted))
    if not st.due(job.key, now, 0.0):
        return False
    value = st.get(job.key, now, FOREVER)
    return value is None or not job.fresh(value)


def _measure(job: Job, started_ns: int, ok: bool, answered: float | None, first: bool) -> None:
    """The read's wall time and, on its first answer since the page opened, how long the page waited for it."""
    from metrics.op_metrics import mark_wall, record, record_since

    kind = job.key.split(":", 1)[0]
    record_since(f"market_board.{kind}", started_ns, ok, wall=True)
    since = store().wanted_since()
    if first and answered is not None and since is not None:
        mark_wall(f"market_board.first.{kind}")
        record(f"market_board.first.{kind}", max(0, int((answered - since) * 1e9)))


def _run(job: Job, now: float, error_key: str | None = None) -> None:
    st = store()
    if job.gap_group:
        _group_last[job.gap_group] = now
    started = time.monotonic()
    started_ns = time.perf_counter_ns()
    since = st.wanted_since()
    before = st.answered_at(job.key)
    try:
        value = job.fetch()
    except ibkr_reads.NoHeadroom as exc:
        st.defer(job.key, now + MARKET_SHED_RETRY_SEC)   # the desk's lines come first; not a failure
        if error_key:
            st.fail(error_key, job.source, f"waiting for spare market-data lines: {exc}", now, MARKET_SHED_RETRY_SEC)
        return
    except Exception as exc:  # noqa: BLE001 -- any failure is stated on the page, never raised into the loop
        at = now + (time.monotonic() - started)
        if type(exc).__name__ == "HistoricalShed":
            st.defer(job.key, at + MARKET_SHED_RETRY_SEC)
            return
        logger.warning("market_board: %s failed: %s", job.key, exc, exc_info=not isinstance(exc, Stated))
        _measure(job, started_ns, False, None, False)
        message = f"{exc}"[:200] or type(exc).__name__
        st.fail(job.key, job.source, message, at, job.retry)
        if error_key:
            st.fail(error_key, job.source, message, at, job.retry)
        return
    at = now + (time.monotonic() - started)
    st.put(job.key, job.source, value, at)
    _measure(job, started_ns, True, at, since is not None and (before is None or before < since))
    if error_key:
        st.put(error_key, job.source, None, at)
    if job.fresh is not None and not job.fresh(value):
        st.defer(job.key, at + job.retry)


def _start() -> None:
    if not enabled():
        return
    keep.load_once(store(), time.time())   # the last process's answers, before any read runs
    with _threads_lock:
        for lane in LANES:
            thread = _threads.get(lane)
            if thread is None or not thread.is_alive():
                thread = threading.Thread(target=_loop, args=(lane,), daemon=True, name=f"market_board_{lane}")
                _threads[lane] = thread
                thread.start()
    for event in _wake.values():
        event.set()


def start_breadth_sampler() -> None:
    """Start the IBKR lane at process start, so the breadth line exists before anyone opens the page."""
    _start()


def _loop(lane: str) -> None:
    while True:
        try:
            now = time.time()
            if not enabled():
                _wake[lane].wait(30.0)
                _wake[lane].clear()
                continue
            if lane == "files":
                keep.maybe_save(store(), now)
            if not run_once(lane, now):
                if store().wanted(now):
                    time.sleep(MARKET_TICK_SEC)
                else:
                    _wake[lane].wait(MARKET_IDLE_WAIT_SEC)
                    _wake[lane].clear()
        except Exception:  # noqa: BLE001 -- the refresher must outlive any one bad read
            logger.exception("market_board refresher %s", lane)
            time.sleep(5.0)


def reset_for_tests() -> None:
    _group_last.clear()
    store().reset()
    keep.reset_for_tests()
