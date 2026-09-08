#!/usr/bin/env python3
"""Nova deferred tracker -- ranked status + next durable ID.

Source of truth is GitHub Issues labeled ``deferred``
(https://github.com/aaltaay/Nova/issues?q=is%3Aissue+label%3Adeferred).

Usage:
  py -3 tools/deferred_log.py status
  py -3 tools/deferred_log.py priorities
  py -3 tools/deferred_log.py next-id
  py -3 tools/deferred_log.py publish [--path DEFERRED_LOG.md]

``priorities`` is an alias of ``status``. When the human asks what is on the
to-do / what is missing / what the priorities are, run this tool -- do not
invent a second tracker.

``--path`` reads a markdown snapshot (tests + one-shot publish). Live
status/next-id talk to GitHub via ``gh``.
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
FENCE_RE = {
    "OPEN": (
        re.compile(r"^<!-- OPEN_START -->\s*$", re.MULTILINE),
        re.compile(r"^<!-- OPEN_END -->\s*$", re.MULTILINE),
    ),
    "CLOSED": (
        re.compile(r"^<!-- CLOSED_START -->\s*$", re.MULTILINE),
        re.compile(r"^<!-- CLOSED_END -->\s*$", re.MULTILINE),
    ),
}

SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
OPEN_STATUSES = frozenset({"open", "blocked", "parked"})


def _section(text: str, name: str) -> str:
    """Slice a fenced section. Markers must sit alone on a line.

    Inline mentions in how-to prose (``<!-- CLOSED_START -->`` inside a
    sentence) are ignored so CLOSED does not swallow the open list.
    """
    start_re, end_re = FENCE_RE[name]
    start = start_re.search(text)
    end = end_re.search(text)
    if not start or not end or end.start() <= start.end():
        return ""
    return text[start.end() : end.start()]


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


def iter_raw_sections(text: str, *, section: str) -> list[tuple[str, str, str]]:
    """(id, title, raw body) for each heading in a fenced section."""
    body = _section(text, section)
    matches = list(HEADING_RE.finditer(body))
    out: list[tuple[str, str, str]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        raw = body[match.end() : end].strip()
        out.append((match.group(1).strip(), match.group(2).strip(), raw))
    return out


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


def format_status_items(items: list[dict[str, str]]) -> str:
    if not items:
        return "Deferred: 0 open"
    lines = [f"Deferred: {len(items)} open"]
    for item in items:
        sev = (item.get("severity") or "?").split()[0]
        kind = (item.get("kind") or "?").split()[0]
        number = (item.get("number") or "").strip()
        extra = f" #{number}" if number else ""
        lines.append(f"- [{sev} {kind}] {item['id']}{extra} {item['title']}")
    return "\n".join(lines)


def format_status(text: str) -> str:
    return format_status_items(open_actionable(parse_entries(text, section="OPEN")))


def format_session_brief_items(items: list[dict[str, str]], *, top_n: int = 3) -> list[str]:
    if not items:
        return []
    hot = [
        e
        for e in items
        if (e.get("severity") or "").split()[0].upper() in {"P0", "P1"}
    ]
    if not hot:
        highest = (items[0].get("severity") or "P?").split()[0]
        return [f"Deferred: {len(items)} open (highest {highest}) -- deferred tracker"]
    lines = [f"Deferred ({len(items)} open):"]
    for item in hot[:top_n]:
        sev = (item.get("severity") or "?").split()[0]
        kind = (item.get("kind") or "?").split()[0]
        number = (item.get("number") or "").strip()
        extra = f" #{number}" if number else ""
        lines.append(f"- [{sev} {kind}] {item['id']}{extra} {item['title']}")
    return lines


def format_session_brief_lines(text: str | None = None, *, top_n: int = 3) -> list[str]:
    if text is not None:
        items = open_actionable(parse_entries(text, section="OPEN"))
        return format_session_brief_items(items, top_n=top_n)
    try:
        from deferred_github import fetch_entries
    except ImportError:
        tools_dir = str(Path(__file__).resolve().parent)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from deferred_github import fetch_entries  # type: ignore[no-redef]
    try:
        items = open_actionable(fetch_entries(state="open"))
    except Exception:
        return []
    return format_session_brief_items(items, top_n=top_n)


def _issue_body(item_id: str, raw: str, *, migrated: bool) -> str:
    footer = (
        "\n\n---\n"
        f"Durable id: `{item_id}`.\n"
        "Tracker: GitHub Issues with label `deferred`.\n"
        "Do not add a second copy in `DEFERRED_LOG.md`.\n"
    )
    if migrated:
        footer += "Migrated from `DEFERRED_LOG.md` on 2026-09-08.\n"
    return raw.strip() + footer


def publish_markdown(path: Path) -> int:
    tools_dir = str(Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from deferred_github import (
        close_issue,
        create_issue,
        ensure_labels,
        existing_ids,
        labels_for_entry,
    )

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"deferred_log: cannot read {path}: {exc}", file=sys.stderr)
        return 1
    ensure_labels()
    have = existing_ids()
    created = 0
    skipped = 0
    closed = 0
    by_id = {
        e["id"]: e
        for section in ("OPEN", "CLOSED")
        for e in parse_entries(text, section=section)
    }
    for section, close_after in (("OPEN", False), ("CLOSED", True)):
        for item_id, title, raw in iter_raw_sections(text, section=section):
            issue_title = f"{item_id} -- {title}"
            if item_id in have:
                skipped += 1
                if close_after and (have[item_id].get("state") or "") != "CLOSED":
                    close_issue(int(have[item_id]["number"]))
                    closed += 1
                continue
            entry = by_id.get(item_id) or {
                "id": item_id,
                "title": title,
                "kind": "bug",
                "severity": "P2",
                "status": "done" if close_after else "open",
            }
            number = create_issue(
                title=issue_title,
                body=_issue_body(item_id, raw, migrated=True),
                labels=labels_for_entry(entry),
            )
            print(f"created {item_id} #{number} {title}")
            created += 1
            if close_after:
                close_issue(number)
                closed += 1
    print(f"publish: created={created} skipped={skipped} closed={closed}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova deferred tracker (GitHub Issues)")
    parser.add_argument(
        "command",
        choices=("status", "priorities", "next-id", "publish"),
        help="status/priorities = ranked open list; next-id = next durable D-NNN; "
        "publish = one-shot markdown -> GitHub",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Markdown snapshot (tests, or publish source). Omit to use GitHub.",
    )
    args = parser.parse_args(argv)

    if args.command == "publish":
        return publish_markdown(args.path or DEFAULT_PATH)

    if args.path is not None:
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

    tools_dir = str(Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        from deferred_github import fetch_entries, issues_url, next_id_from_issues
    except Exception as exc:
        print(f"deferred_log: cannot import GitHub helper: {exc}", file=sys.stderr)
        return 1
    try:
        if args.command == "next-id":
            print(next_id_from_issues())
            return 0
        items = open_actionable(fetch_entries(state="open"))
    except Exception as exc:
        print(f"deferred_log: GitHub list failed: {exc}", file=sys.stderr)
        print(f"Browse {issues_url()} or install/auth `gh`.", file=sys.stderr)
        return 1
    print(format_status_items(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
