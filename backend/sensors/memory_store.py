"""Brain memory -- last N go/no-go decisions.

Owner: this module (read + write).
Invalidation: schema bump refuses unknown versions; load migrates missing version.
schema_version: SENSOR_MEMORY_SCHEMA_VERSION.
Pytest must not write backend/.cache -- uses NOVA_CACHE_DIR.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from constants_sensors import (
    SENSOR_MEMORY_DECISIONS,
    SENSOR_MEMORY_FILENAME,
    SENSOR_MEMORY_MAX,
    SENSOR_MEMORY_SCHEMA_VERSION,
)
from paths import cache_dir

logger = logging.getLogger(__name__)

_lock = threading.RLock()


def _path() -> Path:
    return cache_dir() / SENSOR_MEMORY_FILENAME


def empty_payload() -> dict[str, Any]:
    return {"schema_version": SENSOR_MEMORY_SCHEMA_VERSION, "decisions": []}


def _load_unlocked() -> dict[str, Any]:
    path = _path()
    if not path.is_file():
        return empty_payload()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("sensor memory: refuse-loud unreadable %s", path)
        raise
    if not isinstance(raw, dict):
        raise ValueError("sensor memory payload is not an object")
    if "schema_version" not in raw:
        raw["schema_version"] = SENSOR_MEMORY_SCHEMA_VERSION
        raw.setdefault("decisions", [])
        return raw
    version = int(raw.get("schema_version"))
    if version != SENSOR_MEMORY_SCHEMA_VERSION:
        raise ValueError(f"sensor memory schema_version={version} unsupported")
    rows = raw.get("decisions")
    if not isinstance(rows, list):
        raw["decisions"] = []
    return raw


def _save_unlocked(payload: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def list_decisions(symbol: str | None = None, limit: int = SENSOR_MEMORY_MAX) -> list[dict[str, Any]]:
    with _lock:
        payload = _load_unlocked()
    rows = list(payload.get("decisions") or [])
    if symbol:
        sym = symbol.strip().upper()
        rows = [r for r in rows if str(r.get("symbol") or "").upper() == sym]
    cap = max(1, min(int(limit), SENSOR_MEMORY_MAX))
    return rows[-cap:]


def append_decision(
    *,
    symbol: str,
    decision: str,
    confidence: float | None,
    outcome: str | None = None,
    note: str | None = None,
    ts: float | None = None,
) -> dict[str, Any]:
    kind = (decision or "").strip().lower()
    if kind not in SENSOR_MEMORY_DECISIONS:
        raise ValueError(f"decision must be one of {SENSOR_MEMORY_DECISIONS}")
    conf = None
    if confidence is not None:
        conf = max(0.0, min(1.0, float(confidence)))
    row = {
        "symbol": symbol.strip().upper(),
        "decision": kind,
        "confidence": conf,
        "outcome": (outcome or "").strip() or None,
        "note": (note or "").strip() or None,
        "ts": float(ts if ts is not None else time.time()),
    }
    with _lock:
        payload = _load_unlocked()
        rows = list(payload.get("decisions") or [])
        rows.append(row)
        payload["decisions"] = rows[-SENSOR_MEMORY_MAX:]
        payload["schema_version"] = SENSOR_MEMORY_SCHEMA_VERSION
        _save_unlocked(payload)
    return row


def reset_for_tests() -> None:
    with _lock:
        path = _path()
        if path.is_file():
            path.unlink()
