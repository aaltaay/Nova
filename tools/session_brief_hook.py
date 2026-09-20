#!/usr/bin/env python3
"""Fail-open sessionStart hook: inject a short fleet-triage brief.

Reads stdin JSON (ignored — sessionStart carries no task text to act on).
Emits the top fleet cracks from `agent_fleet.py`, the roadmap Product NEXT
one-liner, the Next-move footer seed (`next_moves.py`), deferred items, the
Graphify meter and the repo-hygiene line, so every new chat starts informed
even before the always-apply rules kick in.

Cursor (`.cursor/hooks.json`) reads `{"additional_context": ...}`.
Claude Code (`.claude/settings.json`) passes `--claude` and reads
`{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ...}}`.

Never blocks session start: any failure yields an empty result.
"""

from __future__ import annotations

import argparse
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
# The ledger's "Current position" list item, e.g. `- **Product NEXT:** ...`.
# (Until 2026-09-20 this matched the retired `**Active ops:**` label, so the
# roadmap line silently vanished from every brief.)
PRODUCT_NEXT_RE = re.compile(r"^-\s*\*\*Product NEXT:\*\*\s*(.+)$", re.MULTILINE)


def _roadmap_next() -> str | None:
    if not ROADMAP_STATUS.is_file():
        return None
    text = ROADMAP_STATUS.read_text(encoding="utf-8")
    m = PRODUCT_NEXT_RE.search(text)
    return re.sub(r"\*\*", "", m.group(1)).strip() if m else None


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
    try:
        import next_moves  # noqa: E402  (path inserted above)

        lines.extend(next_moves.session_brief_lines())
    except Exception:
        lines.append("Next-move seed: unavailable -- run `py -3 tools/next_moves.py seed`")
    try:
        import deferred_log  # noqa: E402  (path inserted above)

        lines.extend(deferred_log.format_session_brief_lines())
    except Exception:
        pass
    try:
        from graphify_usage import DEFAULT_STORE, format_status, load_usage

        lines.append(
            "Graphify meter: "
            + format_status(load_usage(DEFAULT_STORE))
            + " (py -3 tools/graphify_ask.py status; delete Graphify if total_saved stays 0)"
        )
    except Exception:
        pass
    try:
        import repo_hygiene  # noqa: E402  (path inserted above)

        lines.extend(repo_hygiene.format_session_brief_lines())
    except Exception:
        pass
    lines.append(
        "Zero-hop default: work in-session; invoke a specialist only if explicitly named. "
        "Cracks? Prefer `py -3 tools/agent_fleet.py` (no hop). (specialist-routing.mdc)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude", action="store_true",
                        help="emit the Claude Code SessionStart hookSpecificOutput shape")
    args = parser.parse_args(argv)

    try:
        raw = sys.stdin.read()
        json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        pass

    try:
        brief = build_brief()
    except Exception:
        brief = None

    if not brief:
        result: dict = {}
    elif args.claude:
        result = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                         "additionalContext": brief}}
    else:
        result = {"additional_context": brief}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
