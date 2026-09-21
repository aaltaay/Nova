"""Truthful progress derived from committed coverage, with a per-run ETA.

Coverage is a set of ranges (``history_coverage``), so progress is the covered
share of the window and the ETA extrapolates coverage gained in this run -- a
jump ahead or a backfill moves the cursor anywhere, so cursor distance means
nothing. ``downloaded_through`` stays the end of the range that starts at the
window start, which is what every pre-range consumer meant by it.
"""
from __future__ import annotations

import math
import time

from sim import history_coverage as coverage
from sim import history_store as store


def progress(job: dict, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    start, end = job['start_ts'], job['end_ts']
    ranges = coverage.job_ranges(job)
    covered = coverage.covered_seconds(ranges)
    age = max(0, now - job['updated'])
    stale = job['status'] in (*store.ACTIVE, 'interrupted') and age > store.stale_after()
    eta = None
    started = job.get('started')
    advanced = covered - job.get('run_covered', covered)
    if job['status'] in store.ACTIVE and not stale and started is not None and advanced > 0:
        elapsed = max(0, job['updated'] - started)
        if elapsed > 0:
            eta = math.ceil((end - start - covered) * elapsed / advanced)
    return dict(job, started=started, coverage=ranges, covered_seconds=covered,
                downloaded_through=coverage.contiguous_through(ranges, start),
                progress_pct=round(100 * covered / (end - start), 2),
                age_seconds=round(age, 1), stale=stale, eta_seconds=eta)
