"""
Checksummed day manifests for Nova OS cold archive (P7).

A manifest describes one exported table for one ``session_date``: schema
version, row count, sha256 of the payload file, and relative path.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from constants import ARCHIVE_SCHEMA_VERSION


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(
    *,
    session_date: str,
    table_name: str,
    row_count: int,
    sha256: str,
    rel_path: str,
    schema_version: str = ARCHIVE_SCHEMA_VERSION,
    format: str = "jsonl",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "session_date": session_date,
        "table_name": table_name,
        "row_count": int(row_count),
        "sha256": sha256,
        "path": rel_path.replace("\\", "/"),
        "format": format,
    }
    if extra:
        payload["extra"] = extra
    return payload


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Write the manifest atomically so a crash mid-write never leaves a
    truncated/partial manifest that could be read as valid JSON with
    misleading (or no) content — write to a sibling temp file, flush+fsync,
    then rename into place (atomic on POSIX and Windows)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_payload(path: Path, expected_sha256: str) -> bool:
    if not path.is_file():
        return False
    return sha256_file(path) == expected_sha256
