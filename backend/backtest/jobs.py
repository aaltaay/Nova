"""
Optional in-memory backtest job registry (v1 — sync run is primary).

Tracks status for long-running backtests without requiring a worker process.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from constants import BACKTEST_JOB_TTL_SEC

_jobs: dict[str, dict[str, Any]] = {}


def _prune_expired() -> None:
    now = time.time()
    expired = [
        jid for jid, job in _jobs.items()
        if now - float(job.get("created_at") or 0) > BACKTEST_JOB_TTL_SEC
    ]
    for jid in expired:
        _jobs.pop(jid, None)


def create_job(session_date: str, setup: str) -> str:
    _prune_expired()
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "id": job_id,
        "session_date": session_date,
        "setup": setup,
        "status": "pending",
        "created_at": time.time(),
        "result": None,
        "error": None,
    }
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    _prune_expired()
    return _jobs.get(job_id)


def run_job_sync(job_id: str, runner: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise KeyError(f"unknown job: {job_id}")
    job["status"] = "running"
    try:
        result = runner()
        job["status"] = "completed"
        job["result"] = result
        job["completed_at"] = time.time()
        return result
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        job["completed_at"] = time.time()
        raise
