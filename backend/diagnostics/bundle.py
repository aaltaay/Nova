"""Plain-text rendering of the diagnostics checklist for copy/paste (ADR 021)."""
from __future__ import annotations

import json
import time
from typing import Any

from constants_diagnostics import DIAG_BUNDLE_HEADER

_MARK = {"ok": "[ok]  ", "warn": "[warn]", "fail": "[FAIL]", "off": "[off] ", "unknown": "[??]  "}


def render_bundle(payload: dict[str, Any]) -> str:
    """One line per row plus indented cause / fix / evidence. Never a secret."""
    generated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(payload.get("generated_at") or 0)))
    process = payload.get("process") or {}
    lines = [
        f"{DIAG_BUNDLE_HEADER} -- {generated}",
        f"process pid={process.get('pid')} instance={process.get('instance_id')} "
        f"revision={process.get('release_tag')} root={process.get('repo_root')}",
        "counts " + " ".join(f"{k}={v}" for k, v in (payload.get("counts") or {}).items()),
        "",
    ]
    titles = {g["id"]: g["title"] for g in payload.get("groups") or []}
    rows_by_group: dict[str, list[dict[str, Any]]] = {}
    for item in payload.get("rows") or []:
        rows_by_group.setdefault(str(item.get("group")), []).append(item)
    for gid, rows in rows_by_group.items():
        lines.append(f"## {titles.get(gid, gid)}")
        for item in rows:
            lines.append(f"{_MARK.get(str(item.get('state')), '[??]  ')} {item.get('title')}: {item.get('detail')}")
            if item.get("cause"):
                lines.append(f"       cause: {item['cause']}")
            if item.get("fix"):
                lines.append(f"       fix:   {item['fix']}")
            if item.get("evidence"):
                lines.append(f"       evidence: {json.dumps(item['evidence'], default=str, sort_keys=True)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
