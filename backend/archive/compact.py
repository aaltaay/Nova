"""
Compact finished archive days to checksummed cold files (Nova OS P7).

Stdlib-only default: one JSONL file per table + a JSON manifest (row_count +
sha256). If ``pyarrow`` is importable, the same rows may also be written as
Parquet beside the JSONL (optional; not required for restore).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from archive import db as archive_db
from archive.manifest import build_manifest, sha256_file, write_manifest
from constants import ARCHIVE_COLD_DIRNAME, ARCHIVE_SCHEMA_VERSION, ARCHIVE_TABLES_COLD
from paths import cache_dir

logger = logging.getLogger(__name__)

_COLD_TABLES = tuple(ARCHIVE_TABLES_COLD)


def cold_root(base: Path | None = None) -> Path:
    root = (base or cache_dir()) / ARCHIVE_COLD_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _pyarrow_available() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


def _rows_as_dicts(conn: sqlite3.Connection, table: str, session_date: str) -> list[dict[str, Any]]:
    cur = conn.execute(f"SELECT * FROM {table} WHERE session_date = ?", (session_date,))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def write_jsonl_atomic(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Write rows as JSONL, crash-safely.

    A crash mid-write must never leave the final ``path`` holding a
    truncated file whose sha256 no longer matches a manifest written on a
    *previous* successful compaction (the exact "partial local file rewrite
    + stale manifest lets the upload proceed as if everything is valid"
    failure mode flagged by the P7 hardening audit). Writing full content to
    a temp file first and only ``os.replace``-ing it into the final path once
    complete means the final path is either the old complete file or the new
    complete file — never a half-written one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    n = 0
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
                n += 1
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return n


def _maybe_write_parquet(path: Path, rows: list[dict[str, Any]]) -> bool:
    if not rows or not _pyarrow_available():
        return False
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, path)
        return True
    except Exception:
        logger.exception("archive.compact: parquet export failed for %s", path)
        return False


def compact_day(
    session_date: str,
    *,
    tables: tuple[str, ...] | None = None,
    cold_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Export finished-day rows for each table to JSONL (+ optional Parquet).

    Returns the list of written manifests. Idempotent: overwrites same paths
    for the same schema version.
    """
    export_tables = tables or _COLD_TABLES
    root = cold_dir or cold_root()
    day_dir = root / session_date / ARCHIVE_SCHEMA_VERSION
    day_dir.mkdir(parents=True, exist_ok=True)

    manifests: list[dict[str, Any]] = []
    conn = archive_db.get_connection()
    try:
        for table in export_tables:
            rows = _rows_as_dicts(conn, table, session_date)
            rel_jsonl = f"{session_date}/{ARCHIVE_SCHEMA_VERSION}/{table}.jsonl"
            jsonl_path = root / rel_jsonl
            count = write_jsonl_atomic(jsonl_path, rows)
            digest = sha256_file(jsonl_path)
            extra: dict[str, Any] = {}
            parquet_name = f"{table}.parquet"
            if _maybe_write_parquet(day_dir / parquet_name, rows):
                extra["parquet"] = f"{session_date}/{ARCHIVE_SCHEMA_VERSION}/{parquet_name}"
            man = build_manifest(
                session_date=session_date,
                table_name=table,
                row_count=count,
                sha256=digest,
                rel_path=rel_jsonl,
                schema_version=ARCHIVE_SCHEMA_VERSION,
                format="jsonl",
                extra=extra or None,
            )
            write_manifest(day_dir / f"{table}.manifest.json", man)
            manifests.append(man)
            logger.info(
                "archive.compact: %s %s rows=%d sha256=%s…",
                session_date, table, count, digest[:12],
            )
    finally:
        conn.close()
    return manifests


def list_finished_dates(before_date: str) -> list[str]:
    """
    Distinct session_date values strictly before ``before_date`` (YYYY-MM-DD)
    across hot archive tables that carry session_date.
    """
    dates: set[str] = set()
    conn = archive_db.get_connection()
    try:
        for table in _COLD_TABLES:
            cur = conn.execute(
                f"SELECT DISTINCT session_date FROM {table} WHERE session_date < ?",
                (before_date,),
            )
            dates.update(row[0] for row in cur.fetchall() if row[0])
    finally:
        conn.close()
    return sorted(dates)
