"""The Global page's reader (ADR 060): one daemon thread, one read at a time, last in line for IBKR.

``start`` runs it with the process; ``want`` marks the page wanted (it polls). Each turn takes the first due read
(``global_board.jobs``) the budget allows -- a historical read only while ``reads.history_ok()`` and at least
``GLOBAL_HISTORY_GAP_SEC`` after its last one (the Market page's own pace), a line read only while
``reads.lines_ok()`` -- runs it, and records the answer or the failure in ``global_board.state``. Nobody
looking, it keeps a slower cadence, but never from 09:30 to 16:00 ET (the desk's own hours) and never with
``NOVA_GLOBAL_BOARD_WARM=0``; ``NOVA_GLOBAL_BOARD=0`` runs nothing. The thread also keeps the answers on disk
(``global_board.keep``). ``run_once`` is one turn, for tests.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from constants_global_board import (
    GLOBAL_ENV,
    GLOBAL_HISTORY_GAP_SEC,
    GLOBAL_IDLE_WAIT_SEC,
    GLOBAL_PERIODS,
    GLOBAL_QUIET_FROM_MIN_ET,
    GLOBAL_QUIET_TO_MIN_ET,
    GLOBAL_SHED_RETRY_SEC,
    GLOBAL_TICK_SEC,
    GLOBAL_US_TZ,
    GLOBAL_WARM_ENV,
)
from global_board import jobs, keep, reads
from global_board.state import store

logger = logging.getLogger(__name__)

_thread: threading.Thread | None = None
_lock = threading.Lock()
_wake = threading.Event()
_stop = threading.Event()
_period = {"value": "1D"}
_last_history = {"at": float("-inf")}


def enabled() -> bool:
    return (os.environ.get(GLOBAL_ENV) or "1").strip() != "0"


def warm() -> bool:
    return (os.environ.get(GLOBAL_WARM_ENV) or "1").strip() != "0"


def quiet_hours(now: float) -> bool:
    """The US regular session on a weekday: nobody-looking reads wait (the desk's own hours)."""
    t = datetime.fromtimestamp(now, ZoneInfo(GLOBAL_US_TZ))
    minute = t.hour * 60 + t.minute
    return t.weekday() < 5 and GLOBAL_QUIET_FROM_MIN_ET <= minute < GLOBAL_QUIET_TO_MIN_ET


def want(period: str, now: float | None = None) -> None:
    store().want(time.time() if now is None else now)
    _period["value"] = period if period in GLOBAL_PERIODS else "1D"
    start()
    _wake.set()


def run_once(now: float | None = None) -> bool:
    """Run the first due read the budget allows; False when none ran."""
    now = time.time() if now is None else now
    st = store()
    if not reads.ready():
        st.source(False, now, "IBKR is not connected")
        st.waiting(None)
        return False
    wanted = st.wanted(now)
    if not wanted and (not warm() or quiet_hours(now)):
        st.waiting(None)
        return False
    waiting = None
    for job in jobs.due(st, now, wanted=wanted, period=_period["value"]):
        if job.budget == "history" and now - _last_history["at"] < GLOBAL_HISTORY_GAP_SEC:
            continue                                     # its own pace, not a wait on IBKR
        if job.budget == "history" and not reads.history_ok():
            waiting = waiting or "history"
            continue
        if job.budget == "lines" and not reads.lines_ok():
            waiting = waiting or "lines"
            continue
        st.waiting(None)
        if job.budget == "history":
            _last_history["at"] = now
        _run(job, now)
        return True
    st.waiting(waiting)
    return False


def _run(job: jobs.Job, now: float) -> None:
    st = store()
    started = time.monotonic()
    try:
        value = job.run()
    except reads.NoHeadroom:
        st.defer(job.key, now + GLOBAL_SHED_RETRY_SEC)   # the desk's lines come first; not a failure
        return
    except Exception as exc:  # noqa: BLE001 -- any failure is stated on the page, never raised into the loop
        at = now + (time.monotonic() - started)
        if type(exc).__name__ == "HistoricalShed":
            st.defer(job.key, at + GLOBAL_SHED_RETRY_SEC)
            return
        logger.warning("global_board: %s failed: %s", job.key, exc, exc_info=not isinstance(exc, reads.Stated))
        st.fail(job.key, f"{exc}"[:200] or type(exc).__name__, at)
        if not isinstance(exc, reads.Stated):
            st.source(False, at, f"{exc}"[:200] or type(exc).__name__)
        return
    at = now + (time.monotonic() - started)
    st.put(job.key, value, at)
    st.source(True, at)


def start() -> None:
    """Start the reader once (the process start, or the page's first ask); keeps the last process's answers first."""
    global _thread
    if not enabled():
        return
    keep.load_once(store(), time.time())
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_loop, daemon=True, name="global_board")
            _thread.start()


def _loop() -> None:
    while not _stop.is_set():
        try:
            now = time.time()
            keep.maybe_save(store(), now)
            if enabled() and run_once(now):
                continue
            if store().wanted(now):
                _stop.wait(GLOBAL_TICK_SEC)
            else:
                _wake.wait(GLOBAL_IDLE_WAIT_SEC)
                _wake.clear()
        except Exception:  # noqa: BLE001 -- the reader must outlive any one bad read
            logger.exception("global_board reader")
            _stop.wait(5.0)


def stop_for_tests(timeout: float = 5.0) -> bool:
    """End the reader a test started; True when it ended within ``timeout``."""
    global _thread
    _stop.set()
    _wake.set()
    with _lock:
        thread, _thread = _thread, None
    if thread is not None:
        thread.join(timeout)
    _stop.clear()
    return thread is None or not thread.is_alive()


def reset_for_tests() -> None:
    store().reset()
    keep.reset_for_tests()
    _period["value"] = "1D"
    _last_history["at"] = float("-inf")
