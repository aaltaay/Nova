"""Cloudflare R2 day upload and verified index (ADR 004 strangler split)."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from archive.compact import cold_root
from archive.manifest import read_manifest, sha256_file, verify_payload
from archive.r2_client import r2_enabled
from archive.r2_upload import upload_bytes
from constants import (
    ARCHIVE_R2_VERIFIED_INDEX,
    ARCHIVE_SCHEMA_VERSION,
    ARCHIVE_TABLES_COLD,
)

logger = logging.getLogger(__name__)


def _facade():
    """Lazy import so tests can monkeypatch archive.r2 (ADR 004 facade)."""
    import archive.r2 as facade

    return facade


def verified_index_path(cold_dir: Path | None = None) -> Path:
    return (cold_dir or cold_root()) / ARCHIVE_R2_VERIFIED_INDEX


def load_verified_index(cold_dir: Path | None = None) -> dict[str, Any]:
    path = verified_index_path(cold_dir)
    if not path.is_file():
        return {"days": {}, "updated_ts": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("archive.r2: corrupt verified index %s", path)
        return {"days": {}, "updated_ts": None, "corrupt": True}


def save_verified_index(index: dict[str, Any], cold_dir: Path | None = None) -> None:
    path = verified_index_path(cold_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    index = dict(index)
    index["updated_ts"] = time.time()
    path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def is_day_verified_remote(session_date: str, cold_dir: Path | None = None) -> bool:
    index = load_verified_index(cold_dir)
    day = index.get("days", {}).get(session_date)
    return bool(isinstance(day, dict) and day.get("ok"))


def upload_day(
    session_date: str,
    *,
    cold_dir: Path | None = None,
    schema_version: str = ARCHIVE_SCHEMA_VERSION,
) -> dict[str, Any]:
    """
    Upload all cold payloads for a session day. Marks the day verified only
    when every table file uploads (or already exists) successfully.
    """
    root = cold_dir or cold_root()
    day_dir = root / session_date / schema_version
    status = _facade().r2_status()
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
        client, bucket = _facade()._client()
    except Exception as exc:
        return {
            "ok": False,
            "session_date": session_date,
            "error": str(exc),
            "uploads": [],
            "configured": False,
        }

    for table in ARCHIVE_TABLES_COLD:
        man_path = day_dir / f"{table}.manifest.json"
        if not man_path.is_file():
            # A missing manifest means compact_day either never ran for this
            # table or crashed before writing it — never a "nothing to do
            # here" case. Treating it as ok=True (the old behavior: silent
            # `continue`) let a day with an incomplete compaction still be
            # marked verified in R2 as long as the OTHER tables' manifests
            # existed. Fail loud instead.
            uploads.append({
                "ok": False,
                "table": table,
                "error": f"missing manifest: {table}.manifest.json (compact_day incomplete for this day)",
            })
            continue
        man = read_manifest(man_path)
        payload = root / man["path"]
        if not payload.is_file():
            uploads.append({"ok": False, "table": table, "error": "payload missing"})
            continue
        expected_sha256 = man.get("sha256")
        if not expected_sha256 or not verify_payload(payload, expected_sha256):
            # The local file no longer matches the manifest written at
            # compaction time (e.g. a later crashed re-compaction truncated
            # it, or the file changed on disk after compaction). Uploading
            # it anyway would let R2 "verify" a day that is actually stale
            # or corrupt.
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
        result["manifest_sha256"] = man.get("sha256")
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
    index = load_verified_index(root)
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
    # Persist failure loudly so health can fail-loud either way.
    save_verified_index(index, root)
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
                },
            )
        except Exception:
            logger.exception("archive.r2: failed to journal archive_upload_failed event")

    return {
        "ok": ok,
        "session_date": session_date,
        "schema_version": schema_version,
        "uploads": uploads,
        "verified_remote": ok,
        "r2": status,
    }
