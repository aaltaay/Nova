"""Cloudflare R2 client and status helpers (ADR 004 strangler split)."""
from __future__ import annotations

import logging
import os
from typing import Any

from constants import (
    ARCHIVE_R2_ENABLED,
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
