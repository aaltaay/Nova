"""Which finished archive days still need compacting (#720).

The hourly maintenance used to re-export every finished day still in the hot
``archive.db``: 64 days, 8 GB, every 70-80 minutes, freezing the trading
process for half an hour each time. A finished day only changes when rows are
added to it late, so a table is exported again only when the hot day holds
more rows than its manifest says. A hot day with *fewer* rows than its manifest
was trimmed: its cold copy is kept, never overwritten with less.

Counting rides each table's ``session_date`` index, one grouped query per
table -- the same scan ``compact.list_finished_dates`` already paid.

An in-place update of a finished day's rows (an upsert that keeps the count) is
not seen here. Nothing live writes into a finished day; a tool that rewrites
one compacts it itself (``tools/archive_backfill_bars_from_tape.py``).
"""
from __future__ import annotations

import logging
from pathlib import Path

from archive import db as archive_db
from archive.manifest import read_manifest
from constants import ARCHIVE_SCHEMA_VERSION, ARCHIVE_TABLES_COLD

logger = logging.getLogger(__name__)

_COLD_TABLES = tuple(ARCHIVE_TABLES_COLD)


def hot_counts(before_date: str, tables: tuple[str, ...] = _COLD_TABLES) -> dict[str, dict[str, int]]:
    """``{session_date: {table: rows}}`` for every hot day strictly before ``before_date``.

    A table with no rows on a day is absent from that day's map (zero rows).
    """
    days: dict[str, dict[str, int]] = {}
    conn = archive_db.get_connection()
    try:
        for table in tables:
            cur = conn.execute(
                f"SELECT session_date, COUNT(*) FROM {table} "
                "WHERE session_date < ? GROUP BY session_date",
                (before_date,),
            )
            for session_date, rows in cur.fetchall():
                if session_date:
                    days.setdefault(str(session_date), {})[table] = int(rows)
    finally:
        conn.close()
    return days


def cold_counts(root: Path, session_date: str, tables: tuple[str, ...]) -> dict[str, int | None]:
    """Each table's manifest ``row_count`` for the day; ``None`` when there is no usable one."""
    day_dir = root / session_date / ARCHIVE_SCHEMA_VERSION
    counts: dict[str, int | None] = {}
    for table in tables:
        path = day_dir / f"{table}.manifest.json"
        if not path.is_file():
            counts[table] = None
            continue
        try:
            man = read_manifest(path)
            if man.get("schema_version") != ARCHIVE_SCHEMA_VERSION:
                counts[table] = None
                continue
            counts[table] = int(man["row_count"])
        except (OSError, ValueError, KeyError, TypeError):
            logger.warning("archive.day_state: unreadable manifest %s; exporting it again", path)
            counts[table] = None
    return counts


def tables_to_export(
    hot: dict[str, int],
    cold: dict[str, int | None],
) -> tuple[list[str], list[str]]:
    """``(export, kept)`` for one finished day.

    ``export``: tables with no usable manifest, or more hot rows than the manifest
    counted. ``kept``: tables with fewer hot rows than the manifest -- trimmed hot
    data whose cold copy stays as it is. Every other table is current.
    """
    export: list[str] = []
    kept: list[str] = []
    for table, cold_rows in cold.items():
        hot_rows = int(hot.get(table, 0))
        if cold_rows is None or hot_rows > cold_rows:
            export.append(table)
        elif hot_rows < cold_rows:
            kept.append(table)
    return export, kept


def l2_day_compacted(root: Path, session_date: str, tables: tuple[str, ...]) -> bool:
    """Every L2 table of the day has a manifest.

    ``l2.db`` rows carry the time they were written, so a finished day gains no
    rows and is compacted once. ``l2.db`` has no index that serves a day's count.
    """
    day_dir = root / session_date / ARCHIVE_SCHEMA_VERSION
    return all((day_dir / f"{table}.manifest.json").is_file() for table in tables)
