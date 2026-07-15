"""
Cloudflare R2 upload for Nova OS cold archive (P8).

Content-addressed objects under ``R2_PREFIX`` + sha256. Conditional
no-overwrite (skip if object already exists). Never reports success unless
the put/head path actually succeeded.

Credentials live in ``.env`` only:
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
Optional: R2_BUCKET (defaults to ``R2_BUCKET_DEFAULT``), ARCHIVE_R2_ENABLED.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from archive.compact import cold_root
from archive.manifest import read_manifest, sha256_file, verify_payload
from constants import (
    ARCHIVE_R2_ENABLED,
    ARCHIVE_R2_VERIFIED_INDEX,
    ARCHIVE_SCHEMA_VERSION,
    ARCHIVE_TABLES_COLD,
    R2_BUCKET_DEFAULT,
    R2_ENDPOINT_HOST_SUFFIX,
    R2_PREFIX,
)

logger = logging.getLogger(__name__)

_ENV_ACCOUNT = "R2_ACCOUNT_ID"
_ENV_ACCESS = "R2_ACCESS_KEY_ID"
_ENV_SECRET = "R2_SECRET_ACCESS_KEY"
_ENV_BUCKET = "R2_BUCKET"
_ENV_ENABLED = "ARCHIVE_R2_ENABLED"


def _env_truthy(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def r2_enabled() -> bool:
    return _env_truthy(_ENV_ENABLED, bool(ARCHIVE_R2_ENABLED))


def _credentials() -> dict[str, str | None]:
    return {
        "account_id": (os.environ.get(_ENV_ACCOUNT) or "").strip() or None,
        "access_key_id": (os.environ.get(_ENV_ACCESS) or "").strip() or None,
        "secret_access_key": (os.environ.get(_ENV_SECRET) or "").strip() or None,
        "bucket": (os.environ.get(_ENV_BUCKET) or "").strip() or R2_BUCKET_DEFAULT,
    }


def boto3_available() -> bool:
    try:
        import boto3  # noqa: F401
        return True
    except ImportError:
        return False


def r2_status() -> dict[str, Any]:
    """Loud status — never claims configured when keys/boto3 are missing."""
    creds = _credentials()
    missing = [
        k for k in (_ENV_ACCOUNT, _ENV_ACCESS, _ENV_SECRET)
        if not (os.environ.get(k) or "").strip()
    ]
    has_boto = boto3_available()
    configured = not missing and has_boto
    return {
        "enabled": r2_enabled(),
        "configured": configured,
        "boto3_available": has_boto,
        "bucket": creds["bucket"],
        "prefix": R2_PREFIX,
        "missing_env": missing,
        "message": (
            "R2 ready"
            if configured
            else (
                "boto3 not installed — pip install boto3 for R2 uploads"
                if missing == [] and not has_boto
                else f"R2 not configured — set {', '.join(missing) or 'credentials'} in .env only"
            )
        ),
    }


def content_key(sha256: str) -> str:
    digest = sha256.strip().lower()
    return f"{R2_PREFIX}objects/{digest[:2]}/{digest}"


def _client():
    """Build an S3-compatible client for R2. Raises if not configured."""
    status = r2_status()
    if not status["configured"]:
        raise RuntimeError(status["message"])
    import boto3
    from botocore.config import Config

    creds = _credentials()
    endpoint = f"https://{creds['account_id']}.{R2_ENDPOINT_HOST_SUFFIX}"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        region_name="auto",
        config=Config(signature_version="s3v4"),
    ), creds["bucket"]


def object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception as exc:
        resp = getattr(exc, "response", None)
        if isinstance(resp, dict):
            code = str(resp.get("Error", {}).get("Code", ""))
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            meta = resp.get("ResponseMetadata") or {}
            if meta.get("HTTPStatusCode") == 404:
                return False
        raise


def upload_bytes(
    data: bytes,
    *,
    sha256: str | None = None,
    metadata: dict[str, str] | None = None,
    client=None,
    bucket: str | None = None,
) -> dict[str, Any]:
    """
    Upload content-addressed bytes. Skips put when object already exists
    (conditional no-overwrite). Never returns ok=True on failure.
    """
    from archive.manifest import sha256_bytes

    digest = (sha256 or sha256_bytes(data)).strip().lower()
    key = content_key(digest)
    status = r2_status()
    if not status["configured"]:
        return {
            "ok": False,
            "skipped": False,
            "key": key,
            "sha256": digest,
            "error": status["message"],
            "configured": False,
        }
    try:
        if client is None or bucket is None:
            client, bucket = _client()
        if object_exists(client, bucket, key):
            logger.info("archive.r2: skip existing %s", key)
            return {
                "ok": True,
                "skipped": True,
                "key": key,
                "sha256": digest,
                "bucket": bucket,
                "bytes": len(data),
            }
        extra: dict[str, Any] = {}
        if metadata:
            extra["Metadata"] = {str(k): str(v)[:1024] for k, v in metadata.items()}
        client.put_object(Bucket=bucket, Key=key, Body=data, **extra)
        # Confirm presence — never pretend success without head
        if not object_exists(client, bucket, key):
            return {
                "ok": False,
                "skipped": False,
                "key": key,
                "sha256": digest,
                "error": "put_object completed but head_object missing",
                "bucket": bucket,
            }
        return {
            "ok": True,
            "skipped": False,
            "key": key,
            "sha256": digest,
            "bucket": bucket,
            "bytes": len(data),
        }
    except Exception as exc:
        logger.exception("archive.r2: upload failed key=%s", key)
        return {
            "ok": False,
            "skipped": False,
            "key": key,
            "sha256": digest,
            "error": str(exc),
        }


def upload_file(path: Path, *, metadata: dict[str, str] | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    digest = sha256_file(path)
    meta = dict(metadata or {})
    meta.setdefault("local_name", path.name)
    return upload_bytes(data, sha256=digest, metadata=meta)


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
        client, bucket = _client()
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
