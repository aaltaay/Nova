#!/usr/bin/env python3
"""Fail-open sessionStart hook: inject a short fleet-triage brief.

Reads stdin JSON from Cursor (ignored — sessionStart carries no task text to
act on). Emits `additional_context` with the top fleet cracks from
`agent_fleet.py` plus the active roadmap NEXT one-liner, so every new chat
starts informed even before the always-apply triage rule kicks in.

Never blocks session start: any failure yields an empty result.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP_STATUS = (
    REPO_ROOT
    / "knowledge"
    / "obsidian"
    / "03-Nova-Decisions"
    / "Nova-Roadmap-Status.md"
)
ACTIVE_OPS_RE = re.compile(r"^\*\*Active ops:\*\*\s*(.+)$", re.MULTILINE)


def _roadmap_next() -> str | None:
    if not ROADMAP_STATUS.is_file():
        return None
    text = ROADMAP_STATUS.read_text(encoding="utf-8")
    m = ACTIVE_OPS_RE.search(text)
    return m.group(1).strip() if m else None


def build_brief() -> str | None:
    tools_dir = str(REPO_ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import agent_fleet  # noqa: E402  (path inserted above)

    report = agent_fleet.build_report()
    brief = agent_fleet.build_session_brief(report, top_n=3)

    lines = [
        f"Nova fleet brief ({brief['crack_count']} crack(s), rev {brief['revision']}):"
    ]
    for line in brief["top_cracks"]:
        lines.append(f"- {line}")
    roadmap = _roadmap_next()
    if roadmap:
        lines.append(f"Roadmap NEXT: {roadmap}")
    lines.append(
        "Multi-domain work? Prefer daddy. Classification/cracks only? Prefer router. "
        "(specialist-routing.mdc)"
    )
    return "\n".join(lines)


def main() -> int:
    try:
        raw = sys.stdin.read()
        json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        pass

    try:
        brief = build_brief()
    except Exception:
        brief = None

    result = {"additional_context": brief} if brief else {}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
