#!/usr/bin/env python3
"""Fail-open subagentStop hook for Nova specialist lifecycle footer.

Reads stdin JSON from Cursor. If a registered Nova agent completed without the
Lifecycle footer, emit at most one followup_message. Never edits files, never
blocks completion. Unknown / non-Nova subagent types are a no-op.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / ".cursor" / "agent-system" / "registry.json"
CONTRACT_PATH = REPO_ROOT / ".cursor" / "agent-system" / "contract.json"

LIFECYCLE_FALLBACK = re.compile(
    r"\*\*Lifecycle:\*\*\s*memory=(changed|unchanged)",
    re.IGNORECASE,
)


def _load_nova_agent_ids() -> set[str]:
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {a.get("name", "") for a in data.get("agents", []) if a.get("name")}


def _lifecycle_regex() -> re.Pattern[str]:
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        pattern = contract.get("lifecycle_footer_regex")
        if pattern:
            return re.compile(pattern, re.IGNORECASE)
    except (OSError, json.JSONDecodeError, re.error):
        return LIFECYCLE_FALLBACK
    return LIFECYCLE_FALLBACK


def handle_payload(payload: dict) -> dict:
    """Return Cursor subagentStop output dict (possibly empty)."""
    out: dict = {}
    try:
        status = payload.get("status")
        if status != "completed":
            return out

        loop_count = int(payload.get("loop_count") or 0)
        if loop_count >= 1:
            return out

        subagent_type = str(payload.get("subagent_type") or "").strip()
        nova_ids = _load_nova_agent_ids()
        if not subagent_type or subagent_type not in nova_ids:
            # Custom agent name may not appear as subagent_type on this Cursor
            # build — fail open / no-op rather than guess.
            return out

        summary = str(payload.get("summary") or "")
        transcript = ""
        tpath = payload.get("agent_transcript_path")
        if tpath:
            try:
                transcript = Path(tpath).read_text(encoding="utf-8", errors="replace")
            except OSError:
                transcript = ""

        blob = f"{summary}\n{transcript}"
        if _lifecycle_regex().search(blob):
            return out

        out["followup_message"] = (
            f"Nova agent `{subagent_type}` omitted the mandatory Lifecycle footer. "
            "Please append exactly one line of the form: "
            "**Lifecycle:** memory=unchanged|changed | promotion=none|<what> | "
            "dashboard=clean|refresh-required | handoff=none|<sibling|parent> | "
            "task_log=<path>|skipped|n/a | problem_log=<entry>|skipped|n/a "
            "If the run fixed a bug, prepend PROBLEM_LOG.md (problem-log.mdc). "
            "If the run completed material work, also write "
            "knowledge/task-log/YYYY-MM-DD-*.md (see task-log.mdc). "
            "Then stop. Do not re-run the full audit."
        )
        return out
    except Exception:
        # Fail-open: never block subagent completion.
        return {}


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    result = handle_payload(payload if isinstance(payload, dict) else {})
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
