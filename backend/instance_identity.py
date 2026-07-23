"""
Per-process Nova API identity for restart/ownership diagnostics.

A hot-reload cascade and a stray second process fighting over :8000 both
look identical from a single health probe ("something answered"). Stamping
every health/liveness response with a process-lifetime instance_id lets
restart tooling (see frontend/scripts/vite-nova-start-api.ts) and future
PROBLEM_LOG evidence prove whether a *new* process actually replaced the old
one, instead of inferring it from response latency alone (see PROBLEM_LOG
2026-07-23).

Module-level constants are captured once at import time. Under
``uvicorn --reload`` each WatchFiles-spawned worker is a fresh interpreter
process, so ``INSTANCE_ID``/``PID`` are naturally unique per worker.
"""
from __future__ import annotations

import os
import time
import uuid

INSTANCE_ID: str = uuid.uuid4().hex[:12]
PID: int = os.getpid()
PARENT_PID: int = os.getppid()
STARTED_AT: float = time.time()
RELOAD_ENABLED: bool = os.environ.get("NOVA_API_RELOAD", "false").strip().lower() in (
    "1", "true", "yes",
)


def snapshot() -> dict[str, object]:
    """Identity fields merged into /api/health, /livez, /readyz."""
    return {
        "instance_id": INSTANCE_ID,
        "pid": PID,
        "parent_pid": PARENT_PID,
        "started_at": STARTED_AT,
        "reload": RELOAD_ENABLED,
    }
