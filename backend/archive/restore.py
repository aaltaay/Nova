"""
Restore cold archive days into a temporary SQLite and compare row counts (P7).

Used for local restore drills — does not mutate the live hot ``archive.db``.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from archive.compact import cold_root
from archive.db import _SCHEMA
from archive.manifest import read_manifest, verify_payload
from constants import ARCHIVE_SCHEMA_VERSION, ARCHIVE_TABLES_COLD

logger = logging.getLogger(__name__)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _insert_rows(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    cols = [c for c in rows[0].keys() if c != "id"]
    placeholders = ", ".join("?" for _ in cols)
    col_sql = ", ".join(cols)
    sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
    payload = [tuple(row.get(c) for c in cols) for row in rows]
    conn.executemany(sql, payload)
    return len(payload)


def restore_day_to_temp(
    session_date: str,
    *,
    cold_dir: Path | None = None,
    schema_version: str = ARCHIVE_SCHEMA_VERSION,
) -> dict[str, Any]:
    """
    Materialize a finished day from cold JSONL into a temp DB.

    Returns ``{ok, temp_dir, db_path, expected, actual, mismatches}``.
    """
    root = cold_dir or cold_root()
    day_dir = root / session_date / schema_version
    if not day_dir.is_dir():
        return {
            "ok": False,
            "error": f"missing cold day dir: {day_dir}",
            "expected": {},
            "actual": {},
            "mismatches": {},
        }

    tmp = Path(tempfile.mkdtemp(prefix=f"nova_archive_restore_{session_date}_"))
    db_path = tmp / "archive_restore.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)

    expected: dict[str, int] = {}
    actual: dict[str, int] = {}
    mismatches: dict[str, dict[str, Any]] = {}

    try:
        for table in ARCHIVE_TABLES_COLD:
            man_path = day_dir / f"{table}.manifest.json"
            if not man_path.is_file():
                # Same class of bug as the R2 upload path: a missing manifest
                # means compaction never finished for this table, not that
                # there was nothing to restore. Silently skipping let a
                # restore drill report ok=True for a day that is actually
                # missing a whole table.
                mismatches[table] = {"error": "manifest_missing"}
                continue
            man = read_manifest(man_path)
            rel = man["path"]
            payload_path = root / rel
            if not verify_payload(payload_path, man["sha256"]):
                mismatches[table] = {
                    "error": "sha256_mismatch",
                    "expected_sha256": man["sha256"],
                }
                continue
            rows = _load_jsonl(payload_path)
            expected[table] = int(man["row_count"])
            inserted = _insert_rows(conn, table, rows)
            actual[table] = inserted
            if inserted != expected[table]:
                mismatches[table] = {
                    "error": "row_count_mismatch",
                    "expected": expected[table],
                    "actual": inserted,
                }
        conn.commit()
    finally:
        conn.close()

    ok = not mismatches and bool(expected)
    result = {
        "ok": ok,
        "temp_dir": str(tmp),
        "db_path": str(db_path),
        "session_date": session_date,
        "schema_version": schema_version,
        "expected": expected,
        "actual": actual,
        "mismatches": mismatches,
    }
    if ok:
        logger.info("archive.restore: day %s ok tables=%s", session_date, list(expected))
    else:
        logger.warning("archive.restore: day %s failed mismatches=%s", session_date, mismatches)
    return result


def compare_row_counts(expected: dict[str, int], actual: dict[str, int]) -> dict[str, dict[str, int]]:
    """Return per-table diffs where counts disagree."""
    keys = set(expected) | set(actual)
    out: dict[str, dict[str, int]] = {}
    for k in keys:
        e = int(expected.get(k, 0))
        a = int(actual.get(k, 0))
        if e != a:
            out[k] = {"expected": e, "actual": a}
    return out
