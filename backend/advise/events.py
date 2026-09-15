"""JSONL / WebSocket event helpers for an Advise run."""
from __future__ import annotations

import json
import time
from typing import Any


def make_event(kind: str, **fields: Any) -> dict[str, Any]:
    event: dict[str, Any] = {"type": kind, "ts": time.time()}
    event.update(fields)
    return event


def encode_event(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=True, separators=(",", ":"))


def decode_event(line: str) -> dict[str, Any] | None:
    text = (line or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or not obj.get("type"):
        return None
    return obj
