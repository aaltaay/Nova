"""
Cloudflare R2 upload for Nova OS cold archive (P8).

Strangler facade (ADR 004). Implementation lives in:
  archive.r2_client, archive.r2_upload, archive.r2_day.

Content-addressed objects under ``R2_PREFIX`` + sha256. Conditional
no-overwrite (skip if object already exists). Never reports success unless
the put/head path actually succeeded.

Credentials live in ``.env`` only:
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
Optional: R2_BUCKET (defaults to ``R2_BUCKET_DEFAULT``), ARCHIVE_R2_ENABLED.

Facade owner: Nova OS P8 / Pattern-Driven Architecture.
Removal criterion: no production imports of ``archive.r2`` private helpers;
callers use focused ``archive.r2_*`` modules or a public archive API only.
"""
from __future__ import annotations

from archive.r2_client import (
    _client,
    boto3_available,
    content_key,
    object_exists,
    r2_enabled,
    r2_status,
)
from archive.r2_day import (
    is_day_verified_remote,
    load_verified_index,
    save_verified_index,
    upload_day,
    verified_index_path,
)
from archive.r2_upload import upload_bytes, upload_file

__all__ = [
    "_client",
    "boto3_available",
    "content_key",
    "is_day_verified_remote",
    "load_verified_index",
    "object_exists",
    "r2_enabled",
    "r2_status",
    "save_verified_index",
    "upload_bytes",
    "upload_day",
    "upload_file",
    "verified_index_path",
]
