"""Parent-loss and dark-port self-exit for the Nova API process.

Owner: this module (started from api_instance_lock.acquire_or_exit).
A live PID that is not listening on the API port is a D-005 orphan --
it must exit so the instance lock can be reclaimed without starting a
second clientId 17 session.

Only a probe that says "nobody listens" counts (2026-10-14). That day the PC ran out of
network ports: every test connection failed at once (WinError 52 / 10048), the probe read
that as a dark port, and this guard stopped a serving API about every two minutes -- 19
restarts, no Time & Sales or Level 2, and every recording cut short. A probe that cannot
run says ``None`` (unknown), and unknown never stops the API.

A stop it does make writes out what the process still holds first: the eyes' journal batch
and the log queue (``_flush_before_exit``).
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8000
STARTUP_GRACE_SEC = 10.0
POLL_SEC = 2.0
JOURNAL_FLUSH_SEC = 5.0          # the eyes' journal's own flush budget (``eyes.journal.flush``)

_started = False
_lock = threading.Lock()


def parent_lost(initial_ppid: int, current_ppid: int, parent_alive: bool) -> bool:
    """True when the process that launched us is gone."""
    if initial_ppid <= 1:
        return False
    if not parent_alive:
        return True
    return current_ppid == 1 and initial_ppid != 1


def should_exit_for_dark_port(
    age_sec: float,
    listening: bool | None,
    grace_sec: float = STARTUP_GRACE_SEC,
) -> bool:
    """True after startup grace if our API port has no listener. ``None`` -- the probe could not
    run -- is never a reason to exit."""
    if listening is not False:
        return False
    return age_sec >= grace_sec


def _flush_before_exit() -> None:
    """What ``os._exit`` would drop: the eyes' journal lines still queued, then the log queue. Only
    modules already loaded are touched; each step is bounded. Lines the journal cannot write within
    ``JOURNAL_FLUSH_SEC`` (a blocked disk) are lost with the exit -- the log says how many, never
    silence."""
    journal = sys.modules.get("eyes.journal")
    if journal is not None:
        try:
            if not journal.flush(JOURNAL_FLUSH_SEC):
                # pending(), not status()["queued"]: a batch the writer took and is stuck writing is no longer
                # in the queue, and is lost all the same.
                logger.error("api_process_guard: the eyes' journal still had %s line(s) not on disk after %.0fs -- "
                             "they are lost with this exit", journal.pending(), JOURNAL_FLUSH_SEC)
        except Exception:
            logger.warning("api_process_guard: the eyes' journal did not flush before exit", exc_info=True)
    setup = sys.modules.get("logging_setup")
    if setup is not None:
        try:
            setup.shutdown_logging()
        except Exception:  # maintainer: allow-swallow the log queue is what failed; nothing is left to log to
            pass


def _env_bind() -> tuple[str, int]:
    host = (os.environ.get("NOVA_API_HOST") or DEFAULT_API_HOST).strip() or DEFAULT_API_HOST
    raw = (os.environ.get("NOVA_API_PORT") or str(DEFAULT_API_PORT)).strip()
    try:
        port = int(raw)
    except ValueError:
        port = DEFAULT_API_PORT
    return host, port


def _watch_parent(initial_ppid: int, pid_alive, interval_sec: float) -> None:
    while True:
        time.sleep(interval_sec)
        try:
            current = os.getppid()
        except OSError:
            current = 0
        alive = True
        try:
            alive = bool(pid_alive(initial_ppid))
        except Exception:
            logger.debug("api_process_guard: parent alive check failed", exc_info=True)
        if parent_lost(initial_ppid, current, alive):
            logger.error(
                "api_process_guard: parent pid=%s gone -- exiting so the "
                "instance lock can reclaim (no zombie-without-listener)",
                initial_ppid,
            )
            _flush_before_exit()
            os._exit(0)


def _watch_listen(
    host: str,
    port: int,
    started_at: float,
    port_listening,
    interval_sec: float,
    grace_sec: float,
) -> None:
    unknown_since: float | None = None
    while True:
        time.sleep(interval_sec)
        age = time.monotonic() - started_at
        listening: bool | None = None
        try:
            answer = port_listening(host, port)
            listening = None if answer is None else bool(answer)
        except Exception:
            logger.warning("api_process_guard: the listen probe raised -- treated as unknown", exc_info=True)
        if listening is None:
            if unknown_since is None:
                unknown_since = time.monotonic()
                logger.warning(
                    "api_process_guard: cannot tell whether %s:%s is listening -- this PC would not open a "
                    "test connection; staying up (a probe that cannot run never stops the API)",
                    host,
                    port,
                )
        elif unknown_since is not None:
            logger.info("api_process_guard: the listen probe answers again after %.0fs",
                        time.monotonic() - unknown_since)
            unknown_since = None
        if should_exit_for_dark_port(age, listening, grace_sec):
            logger.error(
                "api_process_guard: %s:%s has no listener after %.1fs -- "
                "exiting so a new API can claim the lock (D-005)",
                host,
                port,
                age,
            )
            _flush_before_exit()
            os._exit(1)


def start_guards(
    *,
    pid_alive,
    port_listening,
    host: str | None = None,
    port: int | None = None,
    interval_sec: float = POLL_SEC,
    grace_sec: float = STARTUP_GRACE_SEC,
) -> bool:
    """Start daemon parent + listen watches. Idempotent. Returns True if started."""
    global _started
    with _lock:
        if _started:
            return False
        bind_host, bind_port = _env_bind()
        if host is None:
            host = bind_host
        if port is None:
            port = bind_port
        initial_ppid = os.getppid()
        started_at = time.monotonic()
        threading.Thread(
            target=_watch_parent,
            args=(initial_ppid, pid_alive, interval_sec),
            name="nova-api-parent-watch",
            daemon=True,
        ).start()
        threading.Thread(
            target=_watch_listen,
            args=(host, port, started_at, port_listening, interval_sec, grace_sec),
            name="nova-api-listen-watch",
            daemon=True,
        ).start()
        _started = True
        logger.info(
            "api_process_guard: watching parent=%s bind=%s:%s grace=%.0fs",
            initial_ppid,
            host,
            port,
            grace_sec,
        )
        return True


def _reset_for_tests() -> None:
    global _started
    _started = False
