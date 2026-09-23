"""The stall catcher (ADR 026): what a loop was running while it was stuck.

A daemon thread posts a no-op callback onto each watched loop every
``PERF_WATCH_PING_SEC`` and times how long it waits. A callback that has
waited past ``PERF_STALL_MS`` means the loop is stalled -- one long callback,
blocking I/O, or a backlog of short ones -- and the watcher samples that
thread's stack every ``PERF_STALL_SAMPLE_SEC`` until the callback runs. The
loop's own callback only stamps two numbers; folding the samples happens here,
off both loops. Completed stalls go to ``completed`` for the recorder.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import sys
import threading
import time

from constants_perf import (
    PERF_STALL_MAX_FRAMES,
    PERF_STALL_MAX_SAMPLES,
    PERF_STALL_MS,
    PERF_STALL_SAMPLE_SEC,
    PERF_STALL_TOP_STACKS,
    PERF_WATCH_PING_SEC,
)
from perf import stacks

logger = logging.getLogger(__name__)

_NS_PER_MS = 1_000_000


class _Watched:
    def __init__(self, name: str, loop: asyncio.AbstractEventLoop) -> None:
        self.name = name
        self.loop = loop
        self.ident: int | None = None
        self.posted_ns: int | None = None
        self.acked_ns: int | None = None
        self.last_post_ns = 0
        self.delay_max_ns: int | None = None
        self.stalled_in_interval = False
        self.stall_started_ns: int | None = None
        self.stall_started_ts: float | None = None
        self.samples: list[tuple[stacks.Frame, ...]] = []
        self.truncated = False


_lock = threading.Lock()
_watched: dict[str, _Watched] = {}
_thread: threading.Thread | None = None
_stop = threading.Event()
# Finished stall reports (without before/after context) for the recorder.
completed: "queue.SimpleQueue[dict]" = queue.SimpleQueue()


def watch(name: str, loop: asyncio.AbstractEventLoop) -> None:
    """Watch ``loop`` under ``name`` (``ib`` / ``http``). Replaces a previous loop."""
    with _lock:
        _watched[name] = _Watched(name, loop)


def _ack(w: _Watched) -> None:
    """Runs on the watched loop: stamp who and when, nothing else."""
    now = time.perf_counter_ns()
    with _lock:
        w.ident = threading.get_ident()
        w.acked_ns = now


def take_delay(name: str) -> tuple[float | None, bool]:
    """``(delay_max_ms, stalled)`` since the previous call, counting a wait in progress."""
    now = time.perf_counter_ns()
    with _lock:
        w = _watched.get(name)
        if w is None:
            return None, False
        worst = w.delay_max_ns
        if w.posted_ns is not None and (w.acked_ns is None or w.acked_ns < w.posted_ns):
            worst = max(worst or 0, now - w.posted_ns)
        stalled = w.stalled_in_interval or w.stall_started_ns is not None
        w.delay_max_ns = None
        w.stalled_in_interval = False
    return (round(worst / _NS_PER_MS, 1) if worst is not None else None), stalled


def _finish(w: _Watched, ended_ns: int) -> dict:
    duration_ms = (ended_ns - (w.stall_started_ns or ended_ns)) / _NS_PER_MS
    started_ts = w.stall_started_ts or time.time()
    folded, top_frame = stacks.fold(w.samples, PERF_STALL_TOP_STACKS)
    report = {
        "id": f"{int(started_ts * 1000)}-{w.name}",
        "loop": w.name,
        "started_ts": round(started_ts, 3),
        "ended_ts": round(started_ts + duration_ms / 1000.0, 3),
        "duration_ms": round(duration_ms, 1),
        "samples": len(w.samples),
        "truncated": w.truncated,
        "top_frame": top_frame,
        "stacks": folded,
    }
    w.stall_started_ns = None
    w.stall_started_ts = None
    w.samples = []
    w.truncated = False
    return report


def _step(w: _Watched, now: int) -> bool:
    """Advance one watched loop; True while it is stalled."""
    finished: dict | None = None
    with _lock:
        if w.posted_ns is not None and w.acked_ns is not None and w.acked_ns >= w.posted_ns:
            delay = w.acked_ns - w.posted_ns
            w.delay_max_ns = max(w.delay_max_ns or 0, delay)
            if w.stall_started_ns is not None:
                finished = _finish(w, w.acked_ns)
            w.posted_ns = None
        posted, ident = w.posted_ns, w.ident
    if finished is not None:
        completed.put(finished)
    if not w.loop.is_running() or w.loop.is_closed():
        with _lock:
            w.posted_ns = None
        return False
    if posted is None:
        if now - w.last_post_ns >= PERF_WATCH_PING_SEC * 1e9:
            with _lock:
                w.posted_ns = now
                w.last_post_ns = now
            try:
                w.loop.call_soon_threadsafe(_ack, w)
            except RuntimeError:
                with _lock:
                    w.posted_ns = None
        return False
    if now - posted < PERF_STALL_MS * _NS_PER_MS:
        return False
    with _lock:
        if w.stall_started_ns is None:
            w.stall_started_ns = posted
            w.stall_started_ts = time.time() - (now - posted) / 1e9
            w.stalled_in_interval = True
    if ident is not None:
        if len(w.samples) < PERF_STALL_MAX_SAMPLES:
            frame = sys._current_frames().get(ident)
            if frame is not None:
                w.samples.append(stacks.capture(frame, PERF_STALL_MAX_FRAMES))
        else:
            w.truncated = True
    return True


def _run() -> None:
    while not _stop.is_set():
        now = time.perf_counter_ns()
        stalled = False
        for w in list(_watched.values()):
            try:
                stalled = _step(w, now) or stalled
            except Exception:
                logger.exception("perf stall watch: step failed for %s", w.name)
        _stop.wait(PERF_STALL_SAMPLE_SEC if stalled else PERF_WATCH_PING_SEC / 2)


def start() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="nova-perf-watch", daemon=True)
    _thread.start()


def stop(timeout: float = 2.0) -> None:
    global _thread
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=timeout)
    _thread = None


def reset_for_tests() -> None:
    stop()
    with _lock:
        _watched.clear()
    while not completed.empty():
        completed.get_nowait()
