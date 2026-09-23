"""Single Nova API instance lock (one process on :8000 / clientId 17).

Owner: this module (read + write).
Invalidation: process start -- a lock whose PID is dead is stale.
A live PID with no API listener after startup grace is an orphan: terminate
it, then reclaim. Never start a second clientId 17 beside a living holder.
schema_version: 1.

A second ``uvicorn`` / ``run_api.py`` used to bind beside a living sidecar
(Windows SO_REUSEADDR). Both then fought IBKR clientId 17 (Error 326), the
desk stayed ``connecting``, and new HTTP (door trail) got ``Failed to fetch``.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from api_process_guard import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    STARTUP_GRACE_SEC,
    start_guards,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
LOCK_NAME = "api-instance.lock"
LISTEN_PROBE_TIMEOUT_SEC = 0.4
TERMINATE_WAIT_SEC = 2.0


def _cache_dir() -> Path:
    raw = (os.environ.get("NOVA_CACHE_DIR") or "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent / ".cache"


def lock_path() -> Path:
    return _cache_dir() / LOCK_NAME


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        # OpenProcess(SYNCHRONIZE) can succeed on a just-killed PID. Query the
        # exit code: 259 (STILL_ACTIVE) is the only "alive" signal.
        process_query_limited = 0x1000
        still_active = 259
        access_denied = 5
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited, False, int(pid)
        )
        if not handle:
            return ctypes.GetLastError() == access_denied
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        if not ok:
            return True
        return int(code.value) == still_active
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def pid_alive(pid: int) -> bool:
    """Whether *pid* is a running process (shared with the capture marker)."""
    return _pid_alive(int(pid))


def pid_image_name(pid: int) -> str | None:
    """The executable path of *pid*, or ``None`` when it cannot be read."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited, False, int(pid))
        if not handle:
            return None
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(
                handle, 0, buf, ctypes.byref(size)
            )
            return buf.value if ok else None
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        return os.readlink(f"/proc/{int(pid)}/exe")
    except OSError:
        return None


def classify_holder(
    *,
    alive: bool,
    listening: bool,
    age_sec: float,
    grace_sec: float = STARTUP_GRACE_SEC,
) -> str:
    """healthy | starting | orphan | dead -- never start beside a healthy holder."""
    if not alive:
        return "dead"
    if listening:
        return "healthy"
    if age_sec < grace_sec:
        return "starting"
    return "orphan"


def _api_bind() -> tuple[str, int]:
    host = (os.environ.get("NOVA_API_HOST") or DEFAULT_API_HOST).strip() or DEFAULT_API_HOST
    raw = (os.environ.get("NOVA_API_PORT") or str(DEFAULT_API_PORT)).strip()
    try:
        port = int(raw)
    except ValueError:
        port = DEFAULT_API_PORT
    return host, port


def _port_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=LISTEN_PROBE_TIMEOUT_SEC):
            return True
    except OSError:
        return False


def _terminate_pid(pid: int) -> None:
    if pid <= 0 or pid == os.getpid():
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            check=False,
            capture_output=True,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + TERMINATE_WAIT_SEC
    while time.time() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


def _holder_age_sec(existing: dict[str, Any], path: Path) -> float:
    raw = existing.get("started_at")
    if isinstance(raw, (int, float)) and raw > 0:
        return max(0.0, time.time() - float(raw))
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return STARTUP_GRACE_SEC


def _read_lock(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        logger.warning("api_instance_lock: ignoring unreadable %s", path)
        return None
    if not isinstance(raw, dict):
        return None
    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        logger.warning(
            "api_instance_lock: unknown schema_version %r -- treating as stale",
            version,
        )
        return None
    return raw


def acquire() -> tuple[bool, str]:
    """Claim the API instance lock for this PID.

    Returns ``(True, "ok"|"reclaimed")`` or ``(False, detail)``.
    Same-PID re-entry is ok (import + run_api both call this).
    """
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_lock(path)
    my_pid = os.getpid()
    if existing is not None:
        try:
            holder = int(existing.get("pid") or 0)
        except (TypeError, ValueError):
            holder = 0
        if holder == my_pid:
            return True, "ok"
        host, port = _api_bind()
        kind = classify_holder(
            alive=_pid_alive(holder),
            listening=_port_listening(host, port),
            age_sec=_holder_age_sec(existing, path),
        )
        if kind == "healthy":
            detail = (
                f"another Nova API is already running (pid={holder}). "
                "Stop it before starting a second process -- two APIs share "
                "clientId 17 and Error 326 wedges the desk."
            )
            logger.error("api_instance_lock: %s", detail)
            return False, detail
        if kind == "starting":
            detail = (
                f"another Nova API is still starting (pid={holder}). "
                "Wait for it to bind :{port} -- do not start a second clientId 17."
            )
            logger.error("api_instance_lock: %s", detail)
            return False, detail
        if kind == "orphan":
            logger.warning(
                "api_instance_lock: terminating non-listening orphan pid=%s "
                "then reclaiming (no second clientId 17)",
                holder,
            )
            _terminate_pid(holder)
            if _pid_alive(holder):
                detail = (
                    f"orphan API pid={holder} is still alive and not listening. "
                    "Stop it before starting a second process -- two APIs share "
                    "clientId 17 and Error 326 wedges the desk."
                )
                logger.error("api_instance_lock: %s", detail)
                return False, detail
        else:
            logger.warning(
                "api_instance_lock: reclaiming stale lock from dead pid=%s",
                holder,
            )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pid": my_pid,
        "parent_pid": os.getppid(),
        "argv0": Path(sys.argv[0]).name if sys.argv else "",
        "started_at": time.time(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    claimed = "reclaimed" if existing is not None else "ok"
    logger.info("api_instance_lock: claimed pid=%s path=%s (%s)", my_pid, path, claimed)
    return True, claimed


def acquire_or_exit() -> None:
    """Refuse to start a second API. No-op under pytest."""
    if os.environ.get("NOVA_SKIP_INSTANCE_LOCK", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    ok, detail = acquire()
    if ok:
        start_guards(pid_alive=_pid_alive, port_listening=_port_listening)
        return
    raise SystemExit(f"Nova API instance lock: {detail}")
