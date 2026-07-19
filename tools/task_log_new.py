#!/usr/bin/env python3
"""Scaffold a new knowledge/task-log entry and prepend INDEX.md.

Usage:
  py -3 tools/task_log_new.py --slug sec-remediation --title "SEC-001–008 remediation"
  py -3 tools/task_log_new.py --slug my-fix --title "Title" --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "knowledge" / "task-log"
INDEX_PATH = LOG_DIR / "INDEX.md"
TEMPLATE_PATH = LOG_DIR / "_template.md"


def _slugify(raw: str) -> str:
    s = raw.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80] or "task"


def _load_template(title: str, today: str) -> str:
    if TEMPLATE_PATH.is_file():
        text = TEMPLATE_PATH.read_text(encoding="utf-8")
        text = text.replace("# YYYY-MM-DD — Short title", f"# {today} — {title}", 1)
        return text
    return (
        f"# {today} — {title}\n\n"
        "- **Status:** completed\n"
        "- **Agents:** \n"
        "- **Domain:** \n"
        "- **Related:** \n\n"
        "## Task\n\n\n"
        "## Goal\n\n\n"
        "## Why it mattered\n\n\n"
        "## What we changed\n\n\n"
        "## How it works now\n\n\n"
        "## Why this approach\n\n\n"
        "## Verification\n\n\n"
        "## Follow-ups\n\n\n"
        "## Keywords\n\n\n"
    )


def _prepend_index(rel_name: str, title: str, today: str, summary: str) -> None:
    link = f"[{title}]({rel_name})"
    row = f"| {today} | {link} | {summary} |"
    if not INDEX_PATH.is_file():
        INDEX_PATH.write_text(
            "# Task log index\n\nNewest first.\n\n"
            "| Date | Entry | One-line summary |\n"
            "|------|-------|------------------|\n"
            f"{row}\n",
            encoding="utf-8",
        )
        return
    text = INDEX_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[str] = []
    inserted = False
    for i, line in enumerate(lines):
        out.append(line)
        if not inserted and line.startswith("|------"):
            out.append(row)
            inserted = True
    if not inserted:
        out.append(row)
    INDEX_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold a Nova task-log entry")
    parser.add_argument("--slug", required=True, help="kebab-case filename slug")
    parser.add_argument("--title", required=True, help="Human title for H1 and INDEX")
    parser.add_argument(
        "--summary",
        default="",
        help="One-line INDEX summary (defaults to title)",
    )
    parser.add_argument(
        "--date",
        default="",
        help="YYYY-MM-DD (default: today local)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    today = args.date.strip() or date.today().isoformat()
    slug = _slugify(args.slug)
    fname = f"{today}-{slug}.md"
    path = LOG_DIR / fname
    summary = (args.summary or args.title).strip().replace("|", "/")

    if path.exists() and not args.dry_run:
        print(f"ERROR: already exists: {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1

    body = _load_template(args.title.strip(), today)
    rel = f"knowledge/task-log/{fname}"

    if args.dry_run:
        print(f"Would write {rel}")
        print(f"Would prepend INDEX: {today} | {args.title} | {summary}")
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _prepend_index(fname, args.title.strip(), today, summary)
    print(rel)
    print("Fill Why this approach, then set Lifecycle task_log=" + rel.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
