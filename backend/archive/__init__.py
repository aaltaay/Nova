"""
Archive package — local capture, cold compact, R2, cold-day reads.

Hot path: SQLite WAL under ``paths.cache_dir()/archive.db`` via ``capture``.
Cold path: finished-day JSONL + sha256 manifests under ``archive_cold/``.
R2: optional content-addressed upload (``r2``) — credentials in ``.env`` only.
Reads: ``replay.bars_by_symbol_for_day`` + ``replay.slice_bars_as_of`` (the
backtest's no-hindsight bars). The ``decide()`` replay was retired (ADR 025).
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
