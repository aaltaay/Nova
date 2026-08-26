"""Single Nova API instance lock (one process on :8000 / clientId 17).

Owner: this module (read + write).
Invalidation: process start -- a lock whose PID is dead is stale.
schema_version: 1.

A second ``uvicorn`` / ``run_api.py`` used to bind beside a living sidecar
(Windows SO_REUSEADDR). Both then fought IBKR clientId 17 (Error 326), the
desk stayed ``connecting``, and new HTTP (door trail) got ``Failed to fetch``.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
LOCK_NAME = "api-instance.lock"


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

        # SYNCHRONIZE is enough to prove the PID still exists.
        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, 0, int(pid))
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


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
        if _pid_alive(holder):
            detail = (
                f"another Nova API is already running (pid={holder}). "
                "Stop it before starting a second process -- two APIs share "
                "clientId 17 and Error 326 wedges the desk."
            )
            logger.error("api_instance_lock: %s", detail)
            return False, detail
        logger.warning(
            "api_instance_lock: reclaiming stale lock from dead pid=%s",
            holder,
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pid": my_pid,
        "parent_pid": os.getppid(),
        "argv0": Path(sys.argv[0]).name if sys.argv else "",
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
        return
    raise SystemExit(f"Nova API instance lock: {detail}")
