"""One day of the eyes' journal, read as it grows (operator ask, 2026-09-24).

``JournalTail`` reads the live lines of one session's file (``source: "live"`` and
that ``date``; a Sim or backtest replay's lines, another session's, an unknown
``schema_version`` or unreadable JSON are left out -- the last two counted): each
``read`` answers only what was appended since the last one, never a line the
writer has not finished. ``JournalDay`` keeps them, oldest first, for
``eyes/playback.py`` to fold; ``stock_read/past_setups.py`` folds them as they
come and keeps nothing else.

Owner: this module (in memory; invalidation: the file only grows -- one that
shrank or vanished is read again from the start and ``generation`` moves on).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from constants_eyes import EYES_SCHEMA_VERSION

SOURCE_LIVE = "live"


class JournalTail:
    """One day's live journal lines, handed out once each, as the file grows."""

    def __init__(self, path: Path, date: str):
        self.path = path
        self.date = date
        self.exists = False
        self.skipped = 0
        self.generation = 0                    # bumped when the file had to be read again from the start
        self._offset = 0

    def read(self) -> list[dict[str, Any]]:
        """The lines appended since the last call. After a restart (``generation`` moved on) they are
        the file's from its start."""
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            if self.exists or self._offset:
                self._restart()
            self.exists = False
            return []
        self.exists = True
        if size < self._offset:
            self._restart()
        if size == self._offset:
            return []
        with self.path.open("rb") as fh:
            fh.seek(self._offset)
            chunk = fh.read(size - self._offset)
        end = chunk.rfind(b"\n")
        if end < 0:
            return []                          # the writer's line is not finished yet
        self._offset += end + 1
        out: list[dict[str, Any]] = []
        for raw in chunk[:end].split(b"\n"):
            row = self._parse(raw)
            if row is not None:
                out.append(row)
        return out

    def _restart(self) -> None:
        self._offset, self.skipped = 0, 0
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


class JournalDay:
    """One day's live journal lines, oldest first, read as the file grows."""

    def __init__(self, path: Path, date: str):
        self._tail = JournalTail(path, date)
        self.lines: list[dict[str, Any]] = []
        self.ts: list[float] = []              # sorted: a line's ts, never before the one above it

    @property
    def path(self) -> Path:
        return self._tail.path

    @property
    def date(self) -> str:
        return self._tail.date

    @property
    def exists(self) -> bool:
        return self._tail.exists

    @property
    def skipped(self) -> int:
        return self._tail.skipped

    @property
    def generation(self) -> int:
        return self._tail.generation

    def refresh(self) -> int:
        """Read what was appended since the last call; the number of lines kept."""
        generation = self._tail.generation
        rows = self._tail.read()
        if self._tail.generation != generation:
            self.lines, self.ts = [], []
        for row in rows:
            ts = float(row.get("ts") or 0.0)
            self.ts.append(max(ts, self.ts[-1]) if self.ts else ts)
            self.lines.append(row)
        return len(rows)

    @property
    def first_ts(self) -> float | None:
        return self.ts[0] if self.ts else None

    @property
    def last_ts(self) -> float | None:
        return self.ts[-1] if self.ts else None
