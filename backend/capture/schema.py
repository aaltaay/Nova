"""Capture-owned v1 schema; changed row shapes must migrate or refuse loudly.

Invalidation: session rollover resets writer state; schema bumps require an
explicit reader migration. Missing versions are the known legacy v1 format.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from capture.constants_capture import CAPTURE_MANIFEST_NAME, CAPTURE_SCHEMA, CAPTURE_SCHEMA_VERSION


def valid_timestamp(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    # Python datetime and chart conversion must both be able to consume it.
    if not 0 < value < 253402300800:
        return False
    try:
        datetime.fromtimestamp(value, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return False
    return True


def validate_version(payload: dict) -> bool:
    version = payload.get("schema_version")
    if version is None:
        if payload.get("schema") not in (None, CAPTURE_SCHEMA):
            raise ValueError("Unsupported capture schema: " + str(payload.get("schema")))
        return True
    if type(version) is not int or version != CAPTURE_SCHEMA_VERSION:
        raise ValueError("Unsupported capture schema_version: " + str(version))
    return False


def read_manifest(root: Path) -> tuple[dict, bool]:
    path = root / CAPTURE_MANIFEST_NAME
    if not path.is_file():
        return {}, True
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Capture manifest is unreadable or malformed") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Capture manifest must be an object")
    return manifest, validate_version(manifest)
