"""
Nova OS archive package — local capture, cold compact, R2, replay (P6–P9).

Hot path: SQLite WAL under ``paths.cache_dir()/archive.db`` via ``capture``.
Cold path: finished-day JSONL + sha256 manifests under ``archive_cold/``.
R2: optional content-addressed upload (``r2``) — credentials in ``.env`` only.
Replay: ``replay.walk_day``/``replay.replay_at`` → ``nova_os.decide(record=False)``,
no-hindsight (bars sliced to each as-of moment). ``replay.replay_day`` without
``as_of_ts`` keeps the old whole-day (hindsight=True) shape for the legacy
CLI/route default only.
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
