"""Bounded, ordered session I/O off the HTTP loop (ADR 001, #314).

Only the short ingress lock is shared with producers. Disk operations and the
recorder lock belong to the daemon writer. Lifecycle callers wait in FastAPI's
threadpool; they never hold ingress while waiting for I/O.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from concurrent.futures import Future
from copy import deepcopy
from typing import Any, Callable

from capture.constants_capture import CAPTURE_PENDING_BATCHES

logger = logging.getLogger(__name__)
_condition = threading.Condition()
_lifecycle = threading.Lock()
_jobs: deque[tuple[Callable[[], Any], Future | None, bool]] = deque()
_thread: threading.Thread | None = None
_pending = 0
_accepting = False
_error: str | None = None
_generation = 0


def _ensure_thread_locked() -> None:
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_run, name="capture-writer", daemon=True)
        _thread.start()


def _run() -> None:
    global _pending, _accepting, _error
    while True:
        with _condition:
            while not _jobs:
                _condition.wait()
            operation, future, data = _jobs.popleft()
        try:
            if data:
                from capture.recorder import is_recording

                if not is_recording():
                    continue  # An earlier failed batch already finalized this session.
            result = operation()
        except Exception as exc:
            logger.exception("CAPTURE: worker operation failed")
            if future is not None:
                future.set_exception(exc)
            else:
                with _condition:
                    _accepting = False
                    _error = f"Capture worker failed: {exc}"
                _fail_recording(_error)
        else:
            if future is not None:
                future.set_result(result)
        finally:
            if data:
                with _condition:
                    _pending -= 1


def _fail_recording(error: str) -> None:
    from capture.recorder import fail_recorder

    try:
        fail_recorder(error)
    except Exception:
        logger.exception("CAPTURE: failed to finalize worker failure")


def session_token(symbol: str) -> int | None:
    """Fence a producer to the current run, even across same-symbol restarts."""
    from capture.mode import capture_symbols

    with _condition:
        return _generation if _accepting and symbol in capture_symbols() else None


def submit(operation: Callable[..., None], *args: Any, token: int | None) -> bool:
    """Accept a copied batch, or visibly fail on overload; never wait for I/O."""
    global _pending, _accepting, _error
    with _condition:
        if not _accepting or token != _generation:
            return False
        if _pending >= CAPTURE_PENDING_BATCHES:
            _accepting = False
            _error = "Capture writer backlog full; recording stopped to prevent silent data loss"
            logger.error("CAPTURE: %s", _error)
            error = _error
            # One reserved control entry, after all accepted data, even at capacity.
            _jobs.append((lambda: _fail_recording(error), None, False))
            _condition.notify()
            return False
        copied = deepcopy(args)
        _pending += 1
        _jobs.append((lambda: operation(*copied), None, True))
        _condition.notify()
        return True


def transition(operation: Callable[[], Any]) -> Any:
    """Close ingress, drain accepted data, then change session on the writer."""
    global _accepting, _error, _generation
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("Capture lifecycle must be awaited with asyncio.to_thread")
    with _lifecycle:
        future: Future = Future()
        with _condition:
            _accepting = False
            _generation += 1
            _ensure_thread_locked()
            _jobs.append((operation, future, False))
            _condition.notify()
        result = future.result()
        from capture.recorder import is_recording

        with _condition:
            _accepting = is_recording()
            if _accepting:
                _error = None
        return result


def status() -> dict[str, Any]:
    with _condition:
        return {"pending_batches": _pending, "accepting": _accepting, "error": _error}
