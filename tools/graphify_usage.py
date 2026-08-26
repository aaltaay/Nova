"""Honest Graphify token-savings meter.

Owner: tools/graphify_ask.py (this module is the read/write helper).
Invalidation: delete graphify-out/usage.json to reset the scoreboard.
schema_version: 1

Savings are cited-note only: tokens in unique source files named by the
query output, minus tokens in that output. Missing/None src => 0 avoided.
This does not count a full-vault read. If the number stays 0, delete Graphify.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
CHARS_PER_TOKEN = 4
MAX_EVENTS = 40
SRC_RE = re.compile(r"src=([^\s\]]+)")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE = REPO_ROOT / "graphify-out" / "usage.json"

EMPTY_USAGE: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "owner": "tools/graphify_ask.py",
    "invalidation": "delete this file to reset the scoreboard",
    "query_count": 0,
    "total_used_tokens": 0,
    "total_avoided_tokens": 0,
    "total_saved_tokens": 0,
    "events": [],
}


def tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def parse_source_paths(graphify_stdout: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in SRC_RE.findall(graphify_stdout or ""):
        path = raw.strip()
        if not path or path.lower() == "none":
            continue
        if path not in seen:
            seen.add(path)
            found.append(path)
    return found


def _resolve(path_str: str, repo_root: Path) -> Path | None:
    candidate = Path(path_str)
    if candidate.is_file():
        return candidate
    rel = repo_root / path_str
    if rel.is_file():
        return rel
    return None


def avoided_tokens(paths: list[str], repo_root: Path) -> int:
    total = 0
    for path_str in paths:
        resolved = _resolve(path_str, repo_root)
        if resolved is None:
            continue
        total += tokens_from_text(resolved.read_text(encoding="utf-8", errors="replace"))
    return total


def load_usage(store_path: Path | None = None) -> dict[str, Any]:
    path = store_path or DEFAULT_STORE
    if not path.is_file():
        return dict(EMPTY_USAGE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(EMPTY_USAGE)
    if data.get("schema_version") != SCHEMA_VERSION:
        return dict(EMPTY_USAGE)
    merged = dict(EMPTY_USAGE)
    merged.update(data)
    return merged


def format_footer(event: dict[str, Any], totals: dict[str, Any]) -> str:
    return (
        "graphify_usage "
        f"used={event['used_tokens']} "
        f"avoided={event['avoided_tokens']} "
        f"saved={event['saved_tokens']} "
        f"queries={totals['query_count']} "
        f"total_saved={totals['total_saved_tokens']}"
    )


def format_status(payload: dict[str, Any]) -> str:
    return (
        "graphify_usage "
        f"queries={payload.get('query_count', 0)} "
        f"used={payload.get('total_used_tokens', 0)} "
        f"avoided={payload.get('total_avoided_tokens', 0)} "
        f"total_saved={payload.get('total_saved_tokens', 0)}"
    )


def record_event(
    *,
    command: str,
    question: str,
    stdout: str,
    repo_root: Path | None = None,
    store_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    path = store_path or DEFAULT_STORE
    used = tokens_from_text(stdout)
    avoided = avoided_tokens(parse_source_paths(stdout), root)
    saved = max(0, avoided - used)
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "question": question[:240],
        "used_tokens": used,
        "avoided_tokens": avoided,
        "saved_tokens": saved,
        "cited_files": parse_source_paths(stdout),
    }
    payload = load_usage(path)
    payload["query_count"] = int(payload.get("query_count", 0)) + 1
    payload["total_used_tokens"] = int(payload.get("total_used_tokens", 0)) + used
    payload["total_avoided_tokens"] = int(payload.get("total_avoided_tokens", 0)) + avoided
    payload["total_saved_tokens"] = int(payload.get("total_saved_tokens", 0)) + saved
    events = list(payload.get("events") or [])
    events.append(event)
    payload["events"] = events[-MAX_EVENTS:]
    payload["schema_version"] = SCHEMA_VERSION
    payload["owner"] = "tools/graphify_ask.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return event
