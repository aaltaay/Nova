"""Registry load / save / merge for security/findings-registry.json.

Side-effect-free except when write=True is passed to merge_findings().
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from tools.security_lib.normalize import RawFinding, format_id, raw_to_registry_entry, today_iso

REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "security" / "findings-registry.json"

_EMPTY_REGISTRY: dict[str, Any] = {
    "version": 1,
    "updated": "",
    "next_id": 1,
    "findings": [],
    "scan_runs": [],
}


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load and return the registry dict.  Returns an empty skeleton if missing."""
    if not path.exists():
        import copy
        reg = copy.deepcopy(_EMPTY_REGISTRY)
        reg["updated"] = today_iso()
        return reg
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def save_registry(registry: dict[str, Any], path: Path = REGISTRY_PATH) -> None:
    """Write registry to disk (atomic: write + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def merge_findings(
    raw_findings: list[RawFinding],
    registry: dict[str, Any],
    tools_run: list[str],
    blocked_tools: list[str],
    write: bool = False,
    path: Path = REGISTRY_PATH,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Merge *raw_findings* into *registry*.

    Rules:
    - Matching fingerprint → update last_seen only; preserve id/status/rationale.
    - New fingerprint → assign next SEC-NNN id, status=open.
    - Never auto-close absent findings.

    Returns:
        (updated_registry, new_ids, updated_ids)
    """
    existing: dict[str, dict[str, Any]] = {
        f["fingerprint"]: f for f in registry.get("findings", [])
    }

    today = today_iso()
    new_ids: list[str] = []
    updated_ids: list[str] = []
    next_id: int = registry.get("next_id", 1)

    for raw in raw_findings:
        fp = raw.fp
        if fp in existing:
            existing[fp]["last_seen"] = today
            updated_ids.append(existing[fp]["id"])
        else:
            sec_id = format_id(next_id)
            next_id += 1
            entry = raw_to_registry_entry(raw, sec_id, today, today)
            existing[fp] = entry
            new_ids.append(sec_id)

    registry["findings"] = list(existing.values())
    registry["next_id"] = next_id
    registry["updated"] = today

    run_record: dict[str, Any] = {
        "run_id": str(uuid.uuid4()),
        "date": today,
        "tools": tools_run,
        "blocked_tools": blocked_tools,
        "new_findings": new_ids,
        "updated_findings": updated_ids,
        "summary": (
            f"{len(new_ids)} new, {len(updated_ids)} updated, "
            f"{len(blocked_tools)} tool(s) blocked"
        ),
    }
    registry.setdefault("scan_runs", []).append(run_record)

    if write:
        save_registry(registry, path)

    return registry, new_ids, updated_ids
