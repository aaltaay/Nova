#!/usr/bin/env python3
"""Parse DEFERRED_LOG.md -- ranked status + next durable ID.

Usage:
  py -3 tools/deferred_log.py status
  py -3 tools/deferred_log.py priorities
  py -3 tools/deferred_log.py next-id

`priorities` is an alias of `status`. When the human asks what is on the
to-do / what is missing / what the priorities are, run this tool -- do not
invent a second tracker. The file is repo-root DEFERRED_LOG.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = REPO_ROOT / "DEFERRED_LOG.md"

HEADING_RE = re.compile(r"^## (D-\d+)\s+--\s+(.+)$", re.MULTILINE)
FIELD_RE = re.compile(r"^- \*\*([^*]+):\*\*\s*(.+)$")
ID_RE = re.compile(r"\bD-(\d+)\b")

SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
OPEN_STATUSES = frozenset({"open", "blocked", "parked"})


def _section(text: str, name: str) -> str:
    start = f"<!-- {name}_START -->"
    end = f"<!-- {name}_END -->"
    i = text.find(start)
    j = text.find(end)
    if i < 0 or j < 0 or j <= i:
        return ""
    return text[i + len(start) : j]


def parse_entries(text: str, *, section: str = "OPEN") -> list[dict[str, str]]:
    body = _section(text, section)
    if not body.strip():
        return []
    parts = HEADING_RE.split(body)
    # split -> [preamble, id, title, rest, id, title, rest, ...]
    entries: list[dict[str, str]] = []
    i = 1
    while i + 2 <= len(parts):
        item_id, title, rest = parts[i], parts[i + 1], parts[i + 2]
        fields: dict[str, str] = {
            "id": item_id.strip(),
            "title": title.strip(),
        }
        for line in rest.splitlines():
            m = FIELD_RE.match(line.strip())
            if m:
                fields[m.group(1).strip().lower()] = m.group(2).strip()
        entries.append(fields)
        i += 3
    return entries


def next_id(text: str) -> str:
    nums = [int(n) for n in ID_RE.findall(text)]
    return f"D-{max(nums, default=0) + 1:03d}"


def open_actionable(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for item in entries:
        status = (item.get("status") or "open").split()[0].lower()
        if status in OPEN_STATUSES:
            out.append(item)
    out.sort(
        key=lambda e: (
            SEVERITY_RANK.get((e.get("severity") or "P3").split()[0].upper(), 9),
            -int(ID_RE.search(e.get("id") or "D-0").group(1)),
        )
    )
    return out


def format_status(text: str) -> str:
    items = open_actionable(parse_entries(text, section="OPEN"))
    if not items:
        return "Deferred: 0 open"
    lines = [f"Deferred: {len(items)} open"]
    for item in items:
        sev = (item.get("severity") or "?").split()[0]
        kind = (item.get("kind") or "?").split()[0]
        lines.append(f"- [{sev} {kind}] {item['id']} {item['title']}")
    return "\n".join(lines)


def format_session_brief_lines(text: str | None = None, *, top_n: int = 3) -> list[str]:
    raw = text if text is not None else DEFAULT_PATH.read_text(encoding="utf-8")
    items = open_actionable(parse_entries(raw, section="OPEN"))
    if not items:
        return []
    hot = [
        e
        for e in items
        if (e.get("severity") or "").split()[0].upper() in {"P0", "P1"}
    ]
    if not hot:
        highest = (items[0].get("severity") or "P?").split()[0]
        return [f"Deferred: {len(items)} open (highest {highest}) -- DEFERRED_LOG.md"]
    lines = [f"Deferred ({len(items)} open):"]
    for item in hot[:top_n]:
        sev = (item.get("severity") or "?").split()[0]
        kind = (item.get("kind") or "?").split()[0]
        lines.append(f"- [{sev} {kind}] {item['id']} {item['title']}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DEFERRED_LOG.md helpers")
    parser.add_argument(
        "command",
        choices=("status", "priorities", "next-id"),
        help="status/priorities = ranked open list; next-id = next durable D-NNN",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_PATH,
        help="Override markdown path (tests)",
    )
    args = parser.parse_args(argv)
    try:
        text = args.path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"deferred_log: cannot read {args.path}: {exc}", file=sys.stderr)
        return 1
    if args.command == "next-id":
        print(next_id(text))
        return 0
    print(format_status(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
