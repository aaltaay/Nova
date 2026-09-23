"""Start and stop the performance recorder from the lifespan (ADR 026).

``NOVA_PERF=0`` turns the whole recorder off (no watcher thread, no writer,
no samples); ``/api/perf/live`` then reports ``running: false``.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable

from constants_perf import PERF_ENV_SWITCH
from perf import gc_watch, loop_cpu, recorder, stall_watch
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
    ]
    if spawn_ib is not None:
        from ibkr.loop_supervisor import get_loop

        ib_loop = get_loop()
        if ib_loop is not None:
            stall_watch.watch("ib", ib_loop)
            spawn_ib("perf.ib_cpu", lambda: loop_cpu.sample_loop("ib"))
    stall_watch.start()
    logger.info("perf recorder: on (%s)", _store.root)
    return tasks


def stop() -> None:
    global _store
    stall_watch.stop()
    gc_watch.uninstall()
    if _store is not None:
        _store.stop()
    _store = None
