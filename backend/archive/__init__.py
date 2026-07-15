"""
Nova OS permanent market-data archive (P6 local capture + P7 cold archive).

Hot path: SQLite WAL under ``paths.cache_dir()/archive.db`` via ``capture``.
Cold path: finished-day JSONL + sha256 manifests under ``archive_cold/``.
``/api/l2/*`` remains the live recall facade; this package is the durable store.

L2 changed-book capture: see ``capture.record_l2_snapshot`` (stub + TODO until
wired from ``ibkr/depth`` without fighting continuous sampler volume).
"""
from __future__ import annotations

from archive.capture import (
    bump_counter,
    mark_incomplete_window,
    record_bar,
    record_gap,
    record_l2_snapshot,
    record_tape_print,
)

__all__ = (
    "bump_counter",
    "mark_incomplete_window",
    "record_bar",
    "record_gap",
    "record_l2_snapshot",
    "record_tape_print",
)
