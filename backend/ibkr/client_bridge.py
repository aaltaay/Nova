"""Thread-safe bridge: run ib_async coroutines on the IB event loop.

``run_coro`` is used by ThreadPoolExecutor workers (scan loop, discovery)
that cannot await the IB-bound loop directly. Lives outside ``client.py``
to keep the connection manager under the file-size limit.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import TimeoutError as _FuturesTimeoutError
from typing import Any

from constants import (
    IBKR_RUN_CORO_MAX_INFLIGHT,
    IBKR_RUN_CORO_MAX_INFLIGHT_WHEN_WEDGED,
)
from ibkr import session_state as _session
from ibkr.errors import StaleIbkrSessionError

logger = logging.getLogger(__name__)

_run_coro_inflight = 0


def run_coro(coro, timeout: float, *, label: str = "") -> Any:
    """
    Bridge: run an ib_async coroutine on the loop IB is connected to, blocking
    the calling thread until done. ib_async's IB instance is bound to whichever
    event loop called connectAsync(), so scan-loop code running in a
    ThreadPoolExecutor worker (see main.py's run_in_executor calls) cannot
    await IBKR coroutines directly -- this bridges that gap safely.

    On timeout, cancels the submitted future instead of abandoning it -- an
    uncancelled ``run_coroutine_threadsafe`` future keeps running against the
    IBKR session after the caller gives up, so a reconnect can race a still-
    live old-generation request (see PROBLEM_LOG 2026-07-23). Cancellation
    propagates into the coroutine as ``CancelledError`` at its next await.

    Raises ``StaleIbkrSessionError`` if the IBKR session disconnected and
    reconnected (generation changed) while this call was in flight -- the
    result reflects a session the caller no longer owns and must not be
    applied.
    """
    from ibkr import client as _client
    from ibkr.loop_supervisor import get_loop as _supervisor_loop

    global _run_coro_inflight
    loop = _supervisor_loop() or _client._loop
    if loop is None or not loop.is_running():
        raise RuntimeError("IBKR event loop not running (client not started)")
    tag = f" [{label}]" if label else ""

    # Circuit breaker keys off IB-loop lag (ADR 010), not uvicorn.
    try:
        import loop_lag as _loop_lag
        wedged = _loop_lag.is_wedged()
    except Exception:
        wedged = False
    cap = (
        IBKR_RUN_CORO_MAX_INFLIGHT_WHEN_WEDGED
        if wedged
        else IBKR_RUN_CORO_MAX_INFLIGHT
    )
    if _run_coro_inflight >= cap:
        raise TimeoutError(
            f"IBKR run_coro circuit open{tag}: inflight={_run_coro_inflight} "
            f"cap={cap} wedged={wedged}"
        )

    generation_before = _session.generation()
    _run_coro_inflight += 1
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        result = future.result(timeout=timeout)
    except _FuturesTimeoutError:
        cancelled = future.cancel()
        logger.warning(
            "IBKR: run_coro timed out after %.1fs%s (cancel %s)",
            timeout, tag, "accepted" if cancelled else "too late -- already running/done",
        )
        raise
    finally:
        _run_coro_inflight = max(0, _run_coro_inflight - 1)
    if _session.generation() != generation_before:
        logger.warning(
            "IBKR: run_coro%s result from stale generation (%s -> %s) -- discarding",
            tag, generation_before, _session.generation(),
        )
        raise StaleIbkrSessionError(
            f"session reconnected during call{tag} "
            f"(generation {generation_before} -> {_session.generation()})"
        )
    return result
