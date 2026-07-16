"""
Bridge the pre-existing l2/db.py L2-depth + tape-trades recorder into the
Nova OS checksummed cold-archive + R2 pattern (P7/P8), so continuous-depth
snapshots and prints get the same durable local export and remote backup as
bars_1m/bars_1d/tape_ibkr — instead of only being subject to local retention
purge (currently blanket-skipped by ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM).

l2_snapshots and tape_trades live in a *different* sqlite file (l2/db.py,
under paths.cache_dir() as l2.db) with no session_date column, so they are
deliberately kept out of ARCHIVE_TABLES_COLD / archive.compact.compact_day —
mixing them in would mean compact_day's default export (used by tests and
call sites that never touch l2.db) starts querying a second database. This
module owns its own compact/upload/restore functions instead, reusing the
same atomic-write, manifest, and content-addressed-upload building blocks so
a day's L2 backup is exactly as crash-safe as the bars/tape backup.

L2 snapshots are only recorded while a depth session is open (viewer-gated,
see ibkr/depth.py + l2/continuous.py) — an empty/missing day here can be a
genuinely quiet day, not a bug. Contrast with bars/tape_ibkr, which run
continuously.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from archive.compact import cold_root, write_jsonl_atomic
from archive.manifest import build_manifest, read_manifest, sha256_file, verify_payload, write_manifest
from archive.r2 import r2_enabled, r2_status, upload_bytes
from constants import (
    ARCHIVE_R2_VERIFIED_INDEX_L2,
    ARCHIVE_SCHEMA_VERSION,
    ARCHIVE_TABLES_COLD_L2,
)
from l2.db import get_connection as l2_connection

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


def et_day_bounds(session_date: str) -> tuple[float, float]:
    """Unix ts [start, end) for one America/New_York calendar day."""
    year, month, day = (int(part) for part in session_date.split("-"))
    start = datetime(year, month, day, tzinfo=_ET)
    end = start + timedelta(days=1)
    return start.timestamp(), end.timestamp()


def rows_for_day(table: str, session_date: str) -> list[dict[str, Any]]:
    """All rows for one l2.db table with ts inside the ET calendar day."""
    if table not in ARCHIVE_TABLES_COLD_L2:
        raise ValueError(f"unknown l2 cold table: {table}")
    start_ts, end_ts = et_day_bounds(session_date)
    conn = l2_connection()
    try:
        cur = conn.execute(
            f"SELECT * FROM {table} WHERE ts >= ? AND ts < ? ORDER BY ts ASC",
            (start_ts, end_ts),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        conn.close()


def compact_l2_day(
    session_date: str,
    *,
    cold_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Export one day of l2_snapshots + tape_trades to checksummed JSONL under
    the same archive_cold/{date}/{schema_version}/ tree as compact_day, using
    the same atomic-write manifest format. A day with zero L2 activity still
    gets a (row_count=0) manifest, so a later "missing manifest" check can
    tell "genuinely quiet day" apart from "compaction never ran."
    """
    root = cold_dir or cold_root()
    day_dir = root / session_date / ARCHIVE_SCHEMA_VERSION
    day_dir.mkdir(parents=True, exist_ok=True)

    manifests: list[dict[str, Any]] = []
    for table in ARCHIVE_TABLES_COLD_L2:
        rows = rows_for_day(table, session_date)
        rel_jsonl = f"{session_date}/{ARCHIVE_SCHEMA_VERSION}/{table}.jsonl"
        jsonl_path = root / rel_jsonl
        count = write_jsonl_atomic(jsonl_path, rows)
        digest = sha256_file(jsonl_path)
        man = build_manifest(
            session_date=session_date,
            table_name=table,
            row_count=count,
            sha256=digest,
            rel_path=rel_jsonl,
            schema_version=ARCHIVE_SCHEMA_VERSION,
            format="jsonl",
        )
        write_manifest(day_dir / f"{table}.manifest.json", man)
        manifests.append(man)
        logger.info(
            "archive.l2_bridge: %s %s rows=%d sha256=%s…",
            session_date, table, count, digest[:12],
        )
    return manifests


def l2_verified_index_path(cold_dir: Path | None = None) -> Path:
    return (cold_dir or cold_root()) / ARCHIVE_R2_VERIFIED_INDEX_L2


def load_l2_verified_index(cold_dir: Path | None = None) -> dict[str, Any]:
    path = l2_verified_index_path(cold_dir)
    if not path.is_file():
        return {"days": {}, "updated_ts": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("archive.l2_bridge: corrupt verified index %s", path)
        return {"days": {}, "updated_ts": None, "corrupt": True}


def save_l2_verified_index(index: dict[str, Any], cold_dir: Path | None = None) -> None:
    path = l2_verified_index_path(cold_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    index = dict(index)
    index["updated_ts"] = time.time()
    path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def is_l2_day_verified_remote(session_date: str, cold_dir: Path | None = None) -> bool:
    index = load_l2_verified_index(cold_dir)
    day = index.get("days", {}).get(session_date)
    return bool(isinstance(day, dict) and day.get("ok"))


def upload_l2_day(
    session_date: str,
    *,
    cold_dir: Path | None = None,
    schema_version: str = ARCHIVE_SCHEMA_VERSION,
) -> dict[str, Any]:
    """
    Same crash-safe contract as archive.r2.upload_day, scoped to the two
    l2-bridged tables and its own verified index — a stalled/failed L2 backup
    never marks the bars/tape_ibkr day as unverified, and vice versa.
    """
    root = cold_dir or cold_root()
    day_dir = root / session_date / schema_version
    status = r2_status()
    if not r2_enabled():
        return {
            "ok": False,
            "session_date": session_date,
            "error": "ARCHIVE_R2_ENABLED is false — enable in .env to upload",
            "r2": status,
            "uploads": [],
        }
    if not status["configured"]:
        return {
            "ok": False,
            "session_date": session_date,
            "error": status["message"],
            "r2": status,
            "uploads": [],
            "configured": False,
        }
    if not day_dir.is_dir():
        return {
            "ok": False,
            "session_date": session_date,
            "error": f"missing cold day dir: {day_dir}",
            "uploads": [],
        }

    uploads: list[dict[str, Any]] = []
    try:
        from archive.r2 import _client

        client, bucket = _client()
    except Exception as exc:
        return {
            "ok": False,
            "session_date": session_date,
            "error": str(exc),
            "uploads": [],
            "configured": False,
        }

    for table in ARCHIVE_TABLES_COLD_L2:
        man_path = day_dir / f"{table}.manifest.json"
        if not man_path.is_file():
            uploads.append({
                "ok": False,
                "table": table,
                "error": f"missing manifest: {table}.manifest.json (compact_l2_day incomplete for this day)",
            })
            continue
        man = read_manifest(man_path)
        payload = root / man["path"]
        if not payload.is_file():
            uploads.append({"ok": False, "table": table, "error": "payload missing"})
            continue
        expected_sha256 = man.get("sha256")
        if not expected_sha256 or not verify_payload(payload, expected_sha256):
            uploads.append({
                "ok": False,
                "table": table,
                "error": "local payload sha256 mismatch vs manifest — refusing to upload",
                "manifest_sha256": expected_sha256,
                "actual_sha256": sha256_file(payload) if payload.is_file() else None,
            })
            continue
        result = upload_bytes(
            payload.read_bytes(),
            sha256=expected_sha256,
            metadata={
                "session_date": session_date,
                "table": table,
                "schema_version": schema_version,
                "row_count": str(man.get("row_count", "")),
            },
            client=client,
            bucket=bucket,
        )
        result["table"] = table
        result["manifest_sha256"] = expected_sha256
        uploads.append(result)

        man_up = upload_bytes(
            man_path.read_bytes(),
            metadata={
                "session_date": session_date,
                "table": table,
                "kind": "manifest",
                "schema_version": schema_version,
            },
            client=client,
            bucket=bucket,
        )
        man_up["table"] = f"{table}.manifest"
        uploads.append(man_up)

    ok = bool(uploads) and all(u.get("ok") for u in uploads)
    index = load_l2_verified_index(root)
    days = dict(index.get("days") or {})
    days[session_date] = {
        "ok": ok,
        "schema_version": schema_version,
        "uploads": [
            {"table": u.get("table"), "key": u.get("key"), "sha256": u.get("sha256"), "ok": u.get("ok")}
            for u in uploads
        ],
        "verified_ts": time.time() if ok else None,
        "error": None if ok else "one or more uploads failed",
    }
    index["days"] = days
    save_l2_verified_index(index, root)
    if not ok:
        failed_tables = [u.get("table") for u in uploads if not u.get("ok")]
        try:
            from nova_os.events import KIND_SYSTEM, record_receipt

            record_receipt(
                kind=KIND_SYSTEM,
                payload={
                    "event": "archive_upload_failed",
                    "session_date": session_date,
                    "failed_tables": failed_tables,
                    "source": "l2_bridge",
                },
            )
        except Exception:
            logger.exception("archive.l2_bridge: failed to journal archive_upload_failed event")

    return {
        "ok": ok,
        "session_date": session_date,
        "schema_version": schema_version,
        "uploads": uploads,
        "verified_remote": ok,
        "r2": status,
    }


def restore_l2_day_to_temp(
    session_date: str,
    *,
    cold_dir: Path | None = None,
    schema_version: str = ARCHIVE_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Same restore-drill contract as archive.restore.restore_day_to_temp,
    scoped to l2_snapshots/tape_trades, materialized into a temp l2.db-shaped
    sqlite file (not the live archive.db or l2.db)."""
    import sqlite3
    import tempfile

    from archive.restore import _insert_rows, _load_jsonl
    from l2.db import _SCHEMA as l2_schema

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

    tmp = Path(tempfile.mkdtemp(prefix=f"nova_l2_restore_{session_date}_"))
    db_path = tmp / "l2_restore.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(l2_schema)

    expected: dict[str, int] = {}
    actual: dict[str, int] = {}
    mismatches: dict[str, dict[str, Any]] = {}

    try:
        for table in ARCHIVE_TABLES_COLD_L2:
            man_path = day_dir / f"{table}.manifest.json"
            if not man_path.is_file():
                mismatches[table] = {"error": "manifest_missing"}
                continue
            man = read_manifest(man_path)
            payload_path = root / man["path"]
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
        logger.info("archive.l2_bridge: restore day %s ok tables=%s", session_date, list(expected))
    else:
        logger.warning("archive.l2_bridge: restore day %s failed mismatches=%s", session_date, mismatches)
    return result
