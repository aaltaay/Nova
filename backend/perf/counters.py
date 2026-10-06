"""Cumulative drop counters the hot paths bump (ADR 026).

``incr`` is called where a queue sheds (the tape viewer queues' drop-oldest) or a viewer skips a
stale item (a Level 2 viewer handed a newer book before it sent the last, ADR 045). Counts never
decrease within a process, so a reader diffs two readings. A bare dict under the GIL; a lost
increment under a race is acceptable for a counter that only has to say "drops are happening".
"""
from __future__ import annotations

# Seeded so a reader sees 0 before the first drop, not a missing gauge.
KNOWN = ("depth.viewer_dropped", "depth.viewer_skipped", "tape.viewer_dropped",
         "l1_timestamp.rate_dropped", "l1_timestamp.queue_dropped",
         "l1_timestamp.tape_discarded", "l1_timestamp.file_dropped", "l1_timestamp.receipt_discarded")
_counts: dict[str, int] = dict.fromkeys(KNOWN, 0)


def incr(name: str, n: int = 1) -> None:
    _counts[name] = _counts.get(name, 0) + n


def read() -> dict[str, int]:
    return dict(_counts)


def reset_for_tests() -> None:
    _counts.clear()
    _counts.update(dict.fromkeys(KNOWN, 0))
