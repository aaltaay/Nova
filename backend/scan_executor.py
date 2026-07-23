"""
Dedicated thread pool for scanner / IBKR-bridge work.

Starlette runs sync FastAPI routes (including /api/health) on the default
``asyncio`` executor. If scan_loop also uses that pool for 25s IBKR
``run_coro`` waits, health probes cannot get a worker → API_WEDGED.

Keep heavy scan work on this pool so liveness stays responsive.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from constants import SCAN_EXECUTOR_WORKERS

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None


def get_scan_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=SCAN_EXECUTOR_WORKERS,
            thread_name_prefix="nova-scan",
        )
        logger.info(
            "scan executor started (max_workers=%s)",
            SCAN_EXECUTOR_WORKERS,
        )
    return _executor


def shutdown_scan_executor() -> None:
    global _executor
    if _executor is None:
        return
    _executor.shutdown(wait=False, cancel_futures=True)
    _executor = None
    logger.info("scan executor shut down")
