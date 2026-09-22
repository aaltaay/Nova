"""Download coverage as merged, half-open second ranges (architecture/historical-replay.md).

A trades job used to cover [start, cursor): one contiguous prefix. Playhead-first
acquisition lets the worker jump to where the operator scrubbed, so coverage is
a set of ranges with gaps. Every range is ``[a, b)`` in whole epoch seconds: all
prints with ``a <= ts < b`` are downloaded. IBKR historical ticks are whole
seconds and a page always completes its final second, so a second is never
split across ranges.

Pure on purpose: the store, the worker, playback and progress all read the same
arithmetic, and it is testable without a database.
"""
from __future__ import annotations

Ranges = list[list[int]]


def normalize(ranges) -> Ranges:
    """Sorted, merged (touching ranges join), empty ranges dropped."""
    out: Ranges = []
    for a, b in sorted((int(a), int(b)) for a, b in ranges if int(b) > int(a)):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def add(ranges, a: int, b: int) -> Ranges:
    return normalize([*ranges, [a, b]])


def range_at(ranges, t: int) -> list[int] | None:
    """The range containing second ``t``, if any."""
    for a, b in ranges:
        if a <= t < b:
            return [a, b]
        if a > t:
            break
    return None


def contains(ranges, t: int) -> bool:
    return range_at(ranges, int(t)) is not None


def covers(ranges, a: int, b: int) -> bool:
    """[a, b) lies wholly inside one range."""
    hit = range_at(ranges, int(a))
    return hit is not None and int(b) <= hit[1]


def covered_seconds(ranges) -> int:
    return sum(b - a for a, b in ranges)


def contiguous_through(ranges, start: int) -> int:
    """End of the range that begins at ``start`` (the legacy cursor), else ``start``."""
    hit = range_at(ranges, start)
    return hit[1] if hit and hit[0] <= start else start


def next_covered_start(ranges, t: int) -> int | None:
    """Start of the first range beginning after ``t`` -- where a page must stop."""
    for a, _ in ranges:
        if a > t:
            return a
    return None


def gap_from(ranges, t: int, end: int) -> int | None:
    """First uncovered second at or after ``t`` and before ``end``, else None."""
    t = int(t)
    for a, b in ranges:
        if b <= t:
            continue
        if a > t:
            break
        t = b
    return t if t < end else None


def next_fetch(ranges, cursor: int, start: int, end: int) -> int | None:
    """Where the worker fetches next: forward from ``cursor``, then wrap to backfill.

    None means the whole window is covered.
    """
    ahead = gap_from(ranges, cursor, end)
    return ahead if ahead is not None else gap_from(ranges, start, end)


def job_ranges(job: dict) -> Ranges:
    """A job's coverage, reading pre-range jobs as their contiguous prefix.

    A candles job fetches its whole window in one request: complete, it covers
    the window (jobs finished before that was stored carry ``ranges: []``,
    which read "complete - 0%"); otherwise nothing (QA 2026-09-22, C40).
    """
    if job.get("kind") == "bars":
        start, end = int(job["start_ts"]), int(job["end_ts"])
        return [[start, end]] if job.get("status") == "complete" and end > start else []
    if "ranges" in job and job["ranges"] is not None:
        return normalize(job["ranges"])
    start, cursor = int(job["start_ts"]), int(job.get("cursor") or job["start_ts"])
    return [[start, cursor]] if cursor > start else []
