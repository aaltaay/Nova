"""One day of the eyes' journal, read as it grows (operator ask, 2026-09-24).

``JournalDay`` keeps the live lines of one session's file (``source: "live"`` and
that ``date``; a Sim or backtest replay's lines, another session's, an unknown
``schema_version`` or unreadable JSON are left out -- the last two counted),
oldest first, and on each ``refresh`` reads only what was appended, never a line
the writer has not finished. ``eyes/playback.py`` folds them.

Owner: this module (in memory; invalidation: the file only grows -- one that
shrank or vanished is read again from the start and ``generation`` moves on).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from constants_eyes import EYES_SCHEMA_VERSION

SOURCE_LIVE = "live"


class JournalDay:
    """One day's live journal lines, oldest first, read as the file grows."""

    def __init__(self, path: Path, date: str):
        self.path = path
        self.date = date
        self.lines: list[dict[str, Any]] = []
        self.ts: list[float] = []              # sorted: a line's ts, never before the one above it
        self.exists = False
        self.skipped = 0
        self.generation = 0                    # bumped when the file had to be read again from the start
        self._offset = 0

    def refresh(self) -> int:
        """Read what was appended since the last call; the number of lines kept."""
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            if self.exists or self.lines:
                self._restart()
            self.exists = False
            return 0
        self.exists = True
        if size < self._offset:
            self._restart()
        if size == self._offset:
            return 0
        with self.path.open("rb") as fh:
            fh.seek(self._offset)
            chunk = fh.read(size - self._offset)
        end = chunk.rfind(b"\n")
        if end < 0:
            return 0                           # the writer's line is not finished yet
        self._offset += end + 1
        kept = 0
        for raw in chunk[:end].split(b"\n"):
            row = self._parse(raw)
            if row is None:
                continue
            ts = float(row.get("ts") or 0.0)
            self.ts.append(max(ts, self.ts[-1]) if self.ts else ts)
            self.lines.append(row)
            kept += 1
        return kept

    def _restart(self) -> None:
        self.lines, self.ts, self._offset, self.skipped = [], [], 0, 0
        self.generation += 1

    def _parse(self, raw: bytes) -> dict[str, Any] | None:
        if not raw.strip():
            return None
        try:
            row = json.loads(raw)
        except ValueError:
            self.skipped += 1
            return None
        if not isinstance(row, dict) or row.get("schema_version") != EYES_SCHEMA_VERSION:
            self.skipped += 1
            return None
        if row.get("source") != SOURCE_LIVE or row.get("date") != self.date:
            return None                        # a Sim or backtest replay's line, or another session's
        return row

    @property
    def first_ts(self) -> float | None:
        return self.ts[0] if self.ts else None

    @property
    def last_ts(self) -> float | None:
        return self.ts[-1] if self.ts else None
