"""Dedicated IB connect-loop (ADR 010).

HTTP/WS stay on uvicorn. All ``ib.*`` runs on this thread's loop -- the same
loop that called ``connectAsync``. Wrong-loop use is a hard error once started.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_thread: threading.Thread | None = None
_loop: asyncio.AbstractEventLoop | None = None
_http_loop: asyncio.AbstractEventLoop | None = None
_ready = threading.Event()
_stop = threading.Event()


def is_started() -> bool:
    return _loop is not None and _loop.is_running()


def get_loop() -> asyncio.AbstractEventLoop | None:
    return _loop


def set_http_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _http_loop
    _http_loop = loop


def get_http_loop() -> asyncio.AbstractEventLoop | None:
    return _http_loop


def is_ib_loop() -> bool:
    if _loop is None:
        return False
    try:
        return asyncio.get_running_loop() is _loop
    except RuntimeError:
        return False


def is_ib_thread() -> bool:
    return _thread is not None and threading.current_thread() is _thread


def assert_ib_loop() -> None:
    """Hard error when ``ib.*`` runs off the connect-loop (no-op before start)."""
    if not is_started():
        return
    if is_ib_loop():
        return
    raise RuntimeError(
        "ib.* must run on the IB connect-loop (ADR 010). "
        "Use on_ib() / call_on_ib() / run_coro()."
    )


def _thread_main() -> None:
    global _loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _loop = loop
    _ready.set()
    logger.info("IB loop supervisor started (tid=%s)", threading.get_ident())
    try:
        loop.run_forever()
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            logger.exception("IB loop supervisor: drain failed")
        loop.close()
        logger.info("IB loop supervisor stopped")


def start() -> asyncio.AbstractEventLoop:
    """Start the IB thread if needed. Safe to call from uvicorn lifespan."""
    global _thread
    if is_started() and _loop is not None:
        return _loop
    _ready.clear()
    _stop.clear()
    _thread = threading.Thread(
        target=_thread_main, name="nova-ib-loop", daemon=True,
    )
    _thread.start()
    if not _ready.wait(timeout=5.0) or _loop is None:
        raise RuntimeError("IB loop supervisor failed to start")
    return _loop


def stop(timeout: float = 5.0) -> None:
    global _thread, _loop
    loop = _loop
    if loop is not None and loop.is_running():
        loop.call_soon_threadsafe(loop.stop)
    if _thread is not None:
        _thread.join(timeout=timeout)
    _thread = None
    _loop = None
    _ready.clear()


async def on_ib(
    coro: Coroutine[Any, Any, T],
    timeout: float,
    *,
    label: str = "",
) -> T:
    """Await ``coro`` on the IB loop. Yields the caller loop while IB works."""
    if not is_started() or is_ib_loop():
        return await asyncio.wait_for(coro, timeout=timeout)
    assert _loop is not None
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    try:
        return await asyncio.wait_for(asyncio.wrap_future(future), timeout=timeout)
    except (asyncio.TimeoutError, FuturesTimeout):
        future.cancel()
        tag = f" [{label}]" if label else ""
        logger.warning("IB on_ib timed out after %.1fs%s", timeout, tag)
        raise


def call_on_ib(fn: Callable[[], T], timeout: float, *, label: str = "") -> T:
    """Run a sync callable on the IB loop (placeOrder / cancelOrder / cache reads)."""
    if not is_started() or is_ib_loop() or is_ib_thread():
        if is_started():
            assert_ib_loop()
        return fn()

    async def _wrap() -> T:
        assert_ib_loop()
        return fn()

    from ibkr.client_bridge import run_coro

    return run_coro(_wrap(), timeout, label=label)


def publish_to_http(cb: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Marshal a callback onto the uvicorn loop. Never touch Starlette from IB."""
    loop = _http_loop
    if loop is None or not loop.is_running():
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("publish_to_http: no HTTP loop for %s", getattr(cb, "__name__", cb))
            return
    try:
        loop.call_soon_threadsafe(lambda: cb(*args, **kwargs))
    except Exception:
        logger.exception("publish_to_http failed")


def spawn_ib(name: str, factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
    """Create a task on the IB loop (scanner/reconnect/lag)."""
    if not is_started() or _loop is None:
        raise RuntimeError("IB loop supervisor not started")

    def _create() -> None:
        asyncio.create_task(factory(), name=name)

    _loop.call_soon_threadsafe(_create)
