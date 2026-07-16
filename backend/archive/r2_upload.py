"""Cloudflare R2 upload helpers (ADR 004 strangler split)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from archive.manifest import sha256_file
from archive.r2_client import content_key, object_exists

logger = logging.getLogger(__name__)


def _facade():
    """Lazy import so tests can monkeypatch archive.r2 (ADR 004 facade)."""
    import archive.r2 as facade

    return facade


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
    status = _facade().r2_status()
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
            client, bucket = _facade()._client()
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
