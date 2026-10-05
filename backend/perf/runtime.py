"""Start and stop the performance recorder from the lifespan (ADR 026).

``NOVA_PERF=0`` turns the whole recorder off (no watcher thread, no writer,
no samples); ``/api/perf/live`` then reports ``running: false``.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Callable

from constants_perf import PERF_ENV_SWITCH, PERF_HEAP_EVERY_SEC, PERF_HEAP_FIRST_AFTER_SEC
from perf import freeze_watch, gc_watch, heap, loop_cpu, recorder, stall_watch
from perf.store import PerfStore, default_dir

logger = logging.getLogger(__name__)

_store: PerfStore | None = None


def enabled() -> bool:
    return os.environ.get(PERF_ENV_SWITCH, "1").strip().lower() not in ("0", "false", "off", "no")


def start(spawn_ib: Callable[[str, Callable[[], Any]], None] | None = None) -> list[asyncio.Task]:
    """Start on the running (HTTP) loop; watch the IB loop when it is up.

    Returns the HTTP-loop tasks so the lifespan cancels them with the rest.
    """
    global _store
    if not enabled():
        logger.info("perf recorder: off (%s=0)", PERF_ENV_SWITCH)
        return []
    http_loop = asyncio.get_running_loop()
    _store = PerfStore(default_dir())
    _store.start()
    recorder.configure(_store)
    gc_watch.install()
    stall_watch.watch("http", http_loop)
    tasks = [
        asyncio.create_task(loop_cpu.sample_loop("http"), name="perf.http_cpu"),
        asyncio.create_task(recorder.run(), name="perf.recorder"),
        asyncio.create_task(_heap_loop(), name="perf.heap"),
    ]
    if spawn_ib is not None:
        from ibkr.loop_supervisor import get_loop

        ib_loop = get_loop()
        if ib_loop is not None:
            stall_watch.watch("ib", ib_loop)
            spawn_ib("perf.ib_cpu", lambda: loop_cpu.sample_loop("ib"))
    stall_watch.start()
    try:
        freeze_watch.start(_store.root)  # ADR 045: a whole-process freeze writes every thread's stack
    except Exception:
        logger.exception("perf: the freeze watch did not start")
    logger.info("perf recorder: on (%s)", _store.root)
    return tasks


async def _heap_loop() -> None:
    """A heap census some minutes after start, then hourly, never in the opening minutes (#619)."""
    await asyncio.sleep(PERF_HEAP_FIRST_AFTER_SEC)
    while True:
        wait = heap.seconds_until_allowed(time.time())
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            await asyncio.to_thread(heap.latest, 0.0, recorder.persist)
        except Exception:
            logger.exception("perf: heap census failed")
        await asyncio.sleep(PERF_HEAP_EVERY_SEC)


def stop() -> None:
    global _store
    stall_watch.stop()
    if freeze_watch._watch is not None:
        freeze_watch._watch.stop()
    gc_watch.uninstall()
    if _store is not None:
        _store.stop()
    _store = None
