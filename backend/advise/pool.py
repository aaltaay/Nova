"""Advise worker pool: max 3, one active per symbol, queue extras.

Workers are OS subprocesses so Cancel can kill them. Not the IBKR loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any

from advise import book
from advise.events import decode_event
from constants_advise import ADVISE_CANCEL_GRACE_SEC, ADVISE_MAX_WORKERS

_BACKEND_DIR = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)

_subscribers: dict[int, list[asyncio.Queue]] = {}
_active_by_symbol: dict[str, int] = {}
_procs: dict[int, asyncio.subprocess.Process] = {}
_reserved: set[int] = set()
_queue: list[int] = []
_lock = asyncio.Lock()


def subscribe(run_id: int) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.setdefault(int(run_id), []).append(queue)
    return queue


def unsubscribe(run_id: int, queue: asyncio.Queue) -> None:
    holders = _subscribers.get(int(run_id))
    if not holders:
        return
    if queue in holders:
        holders.remove(queue)
    if not holders:
        _subscribers.pop(int(run_id), None)


def publish(run_id: int, event: dict[str, Any]) -> None:
    for queue in list(_subscribers.get(int(run_id), [])):
        try:
            queue.put_nowait(event)
        except Exception:
            logger.debug("advise publish drop run=%s", run_id, exc_info=True)


def active_run_for(symbol: str) -> int | None:
    return _active_by_symbol.get(symbol.strip().upper())


def queued_run_ids() -> list[int]:
    return list(_queue)


def worker_command(run_id: int) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--advise-worker", "--run-id", str(run_id)]
    return [sys.executable, "-m", "advise.worker_main", "--run-id", str(run_id)]


def _worker_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8:backslashreplace")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(_BACKEND_DIR) + (os.pathsep + existing if existing else "")
    )
    return env


async def enqueue(run_id: int) -> None:
    async with _lock:
        if run_id not in _queue and run_id not in _procs:
            _queue.append(run_id)
    await pump()


async def pump() -> None:
    async with _lock:
        blocked: list[int] = []
        while (len(_procs) + len(_reserved)) < ADVISE_MAX_WORKERS and _queue:
            run_id = _queue.pop(0)
            run = book.get_run(run_id)
            if run is None:
                continue
            symbol = run["symbol"]
            if symbol in _active_by_symbol and _active_by_symbol[symbol] != run_id:
                blocked.append(run_id)
                continue
            _active_by_symbol[symbol] = run_id
            _reserved.add(run_id)
            asyncio.create_task(_spawn(run_id), name=f"advise-worker-{run_id}")
        if blocked:
            _queue[:] = blocked + _queue


def _already_stopped(run_id: int) -> bool:
    run = book.get_run(run_id)
    return run is None or run["status"] in ("cancelled", "complete", "failed")


async def _spawn(run_id: int) -> None:
    cmd = worker_command(run_id)
    kwargs: dict[str, Any] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "env": _worker_env(),
        "cwd": str(_BACKEND_DIR),
    }
    if os.name != "nt":
        kwargs["start_new_session"] = True
    try:
        if _already_stopped(run_id):
            return
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, **kwargs)
        except Exception as exc:
            if not _already_stopped(run_id):
                book.update_status(
                    run_id,
                    "failed",
                    fail_reason=f"worker spawn failed: {exc}",
                    finished=True,
                )
            return
        if _already_stopped(run_id):
            _kill(proc, force=True)
            try:
                await proc.wait()
            except Exception:
                logger.debug("advise spawn wait after cancel run=%s", run_id, exc_info=True)
            return
        async with _lock:
            _procs[run_id] = proc
        assert proc.stdout is not None

        async def _pump_stdout() -> None:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    return
                event = decode_event(line.decode("utf-8", errors="replace"))
                if event:
                    publish(run_id, event)

        reader = asyncio.create_task(_pump_stdout(), name=f"advise-stdout-{run_id}")
        try:
            code = await proc.wait()
        finally:
            if not reader.done():
                reader.cancel()
                try:
                    await reader
                except asyncio.CancelledError:
                    pass
        run = book.get_run(run_id)
        if run is None or run["status"] in ("cancelled", "complete", "failed"):
            return
        if code == 0:
            book.update_status(run_id, "complete", finished=True)
            publish(run_id, {"type": "done", "status": "complete"})
            return
        reason = f"worker exited {code}"
        if proc.stderr is not None:
            err = await proc.stderr.read()
            extra = err.decode("utf-8", errors="replace").strip()[:400]
            if extra:
                reason = f"{reason}: {extra}"
        book.update_status(run_id, "failed", fail_reason=reason, finished=True)
        publish(run_id, {"type": "error", "message": reason})
    finally:
        await _clear(run_id)
        await pump()


async def _clear(run_id: int) -> None:
    async with _lock:
        _procs.pop(run_id, None)
        _reserved.discard(run_id)
        dead_syms = [sym for sym, rid in _active_by_symbol.items() if rid == run_id]
        for sym in dead_syms:
            _active_by_symbol.pop(sym, None)


async def cancel(run_id: int) -> bool:
    async with _lock:
        if run_id in _queue:
            _queue.remove(run_id)
        proc = _procs.get(run_id)
    book.update_status(run_id, "cancelled", fail_reason="cancelled", finished=True)
    publish(run_id, {"type": "error", "message": "cancelled"})
    if proc is not None and proc.returncode is None:
        _kill(proc)
        try:
            await asyncio.wait_for(proc.wait(), timeout=ADVISE_CANCEL_GRACE_SEC)
        except TimeoutError:
            _kill(proc, force=True)
            try:
                await asyncio.wait_for(proc.wait(), timeout=ADVISE_CANCEL_GRACE_SEC)
            except TimeoutError:
                logger.warning("advise worker %s did not die after kill", run_id)
        _close_pipes(proc)
    await _clear(run_id)
    await pump()
    return True


def _close_pipes(proc: asyncio.subprocess.Process) -> None:
    for pipe in (proc.stdout, proc.stderr, proc.stdin):
        if pipe is None:
            continue
        try:
            pipe.close()
        except Exception:
            logger.debug("advise pipe close", exc_info=True)


def _kill(proc: asyncio.subprocess.Process, force: bool = False) -> None:
    pid = proc.pid
    if os.name != "nt" and pid:
        try:
            os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
        except (ProcessLookupError, OSError):
            logger.debug("advise killpg missed pid=%s", pid, exc_info=True)
    try:
        if force:
            proc.kill()
        else:
            proc.terminate()
    except (ProcessLookupError, OSError):
        return


def reset_for_tests() -> None:
    _subscribers.clear()
    _active_by_symbol.clear()
    _procs.clear()
    _reserved.clear()
    _queue.clear()
