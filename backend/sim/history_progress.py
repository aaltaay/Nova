"""Truthful progress derived from committed coverage, with a per-run ETA."""
from __future__ import annotations

import math
import time

from sim import history_store as store


def progress(job: dict, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    start, end = job['start_ts'], job['end_ts']
    cursor = min(end, max(start, job['cursor']))
    age = max(0, now - job['updated'])
    stale = job['status'] in (*store.ACTIVE, 'interrupted') and age > store.stale_after()
    eta = None
    started = job.get('started')
    advanced = cursor - job.get('run_cursor', cursor)
    if job['status'] in store.ACTIVE and not stale and started is not None and advanced > 0:
        elapsed = max(0, job['updated'] - started)
        if elapsed > 0:
            eta = math.ceil((end - cursor) * elapsed / advanced)
    return dict(job, started=started, downloaded_through=cursor,
                progress_pct=round(100 * (cursor - start) / (end - start), 2),
                age_seconds=round(age, 1), stale=stale, eta_seconds=eta)
