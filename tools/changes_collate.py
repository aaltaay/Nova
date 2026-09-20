#!/usr/bin/env python3
"""Generate the ledgers. Nobody hand-edits CHANGELOG.md any more.

Two sources, in priority order:

1. **Merged pull requests** -- the authored record. AGENTS.md 7.2b already
   makes the PR body the home for the task narrative (What / Why this
   approach / Verified by), so the changelog entry is derived from work the
   agent already did. It writes nothing extra and touches no shared file.
2. **Fragments** under ``.changes/unreleased/`` -- the escape hatch for work
   with no PR (a direct push, an ops diagnosis, an audit conclusion).

Why this and not per-PR fragments alone: a fragment is one more file an agent
must remember, one more CI check to enforce it, and one more thing to get
wrong. The PR body is already mandatory and already reviewed. Deriving from it
removes a step instead of adding one.

Why this and not "just read the PRs on GitHub": the repo has to explain itself
offline. AGENTS.md 0 exists so a future session gets oriented in minutes
without digging; a ledger that only lives behind an API call does not do that.

Conflict surface: an agent's PR no longer contains a CHANGELOG diff at all, so
two PRs authored in parallel cannot collide on it. Only this job writes the
ledger, and it runs on master alone.

Usage:
  python3 tools/changes_collate.py --since-tag v770 --date 2026-09-20
  python3 tools/changes_collate.py --fragments-only --date 2026-09-20
  python3 tools/changes_collate.py --check          # CI: fragments parse?
  python3 tools/changes_collate.py --dry-run --since-merge-of 371
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Ledger entries carry em dashes and arrows from PR bodies, and the default
# Windows console codepage is cp1252, which cannot encode them -- printing
# would raise UnicodeEncodeError and lose the whole run. Files are always
# written as UTF-8; this only affects what reaches the terminal.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from tools.changes_fragments import (  # noqa: E402
    CHANGELOG,
    CHANGES_DIR,
    Fragment,
    collate,
    load_fragments,
    render_entry,
    splice_entries,
)

EXIT_OK = 0
EXIT_ERROR = 1

REPO = "aaltaay/Nova"

# The highest PR number already folded into the ledger. Committed, because the
# job runs on a fresh checkout every time and has no other memory -- without it
# a re-run would duplicate every entry it already wrote.
WATERMARK = CHANGES_DIR.parent / "last-collated"


def read_watermark() -> int | None:
    try:
        return int(WATERMARK.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def write_watermark(number: int) -> None:
    WATERMARK.parent.mkdir(parents=True, exist_ok=True)
    WATERMARK.write_text(f"{number}\n", encoding="utf-8")


# The PR template's headings. An entry is built from these rather than from the
# whole body, so boilerplate and the attribution footer stay out of the ledger.
SECTIONS = ("What", "Why this approach", "Verified by")


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace",
    )


def merged_prs(limit: int, since_number: int | None) -> list[dict]:
    """Merged PRs newest-first, optionally only those above a number."""
    proc = run_gh([
        "pr", "list", "--repo", REPO, "--state", "merged", "--limit", str(limit),
        "--json", "number,title,body,mergedAt,labels",
    ])
    if proc.returncode != 0:
        raise RuntimeError(f"gh pr list failed: {proc.stderr.strip()}")
    prs = json.loads(proc.stdout or "[]")
    if since_number is not None:
        prs = [p for p in prs if int(p["number"]) > since_number]
    return prs


# Trailing boilerplate every PR body carries. The LAST section would otherwise
# swallow it, because there is no following heading to stop at.
TRAILERS = ("🤖 Generated with", "Generated with [Claude Code]",
            "Co-Authored-By:", "Co-authored-by:")


def section(body: str, heading: str) -> str:
    """Text under a '## <heading>', up to the next '## ' or the PR trailers."""
    marker = f"## {heading}"
    if marker not in body:
        return ""
    after = body.split(marker, 1)[1]
    for line in after.splitlines():
        if line.startswith("## "):
            after = after.split(line, 1)[0]
            break
    kept = []
    for line in after.splitlines():
        if any(trailer in line for trailer in TRAILERS):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def pr_to_fragment(pr: dict) -> Fragment | None:
    """Turn a merged PR into a ledger entry, or None if it carries nothing.

    A PR with no What section is almost always a bot or a pure-chore merge;
    inventing an entry for it would pad the ledger with noise.
    """
    body = pr.get("body") or ""
    what = section(body, "What")
    if not what:
        return None
    parts = [f"- **What:** {what}"]
    why = section(body, "Why this approach")
    if why:
        parts.append(f"- **Why this approach:** {why}")
    verified = section(body, "Verified by")
    if verified:
        parts.append(f"- **Verified by:** {verified}")
    title = pr.get("title") or f"PR #{pr['number']}"
    kind = title.split("(", 1)[0].split(":", 1)[0].strip() or "chore"
    return Fragment(
        path=Path(f"pr-{pr['number']}"),
        kind=kind if kind in ("feat", "fix", "chore", "docs", "perf", "test", "refactor") else "chore",
        scope="",
        pr=str(pr["number"]),
        title=title,
        body="\n".join(parts),
    )


def cmd_check() -> int:
    """CI gate: every fragment parses. Says nothing when there are none."""
    problems: list[str] = []
    for directory in (CHANGES_DIR,):
        try:
            found = load_fragments(directory)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        print(f"{directory.relative_to(CHANGES_DIR.parents[1])}: {len(found)} fragment(s)")
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate CHANGELOG.md")
    parser.add_argument("--date", help="entry date (YYYY-MM-DD); required unless --check")
    parser.add_argument("--since-merge-of", type=int, default=None,
                        help="only PRs numbered above this one")
    parser.add_argument("--limit", type=int, default=30, help="how many merged PRs to scan")
    parser.add_argument("--fragments-only", action="store_true",
                        help="skip the PR source; collate .changes/ only")
    parser.add_argument("--check", action="store_true", help="validate fragments and exit")
    parser.add_argument("--dry-run", action="store_true", help="print entries, write nothing")
    args = parser.parse_args(argv)

    if args.check:
        return cmd_check()
    if not args.date:
        parser.error("--date is required (the workflow passes today's UTC date)")

    entries: list[str] = []
    highest = None
    since = args.since_merge_of if args.since_merge_of is not None else read_watermark()
    if not args.fragments_only:
        try:
            scanned = merged_prs(args.limit, since)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_ERROR
        for pr in scanned:
            highest = max(highest or 0, int(pr["number"]))
            fragment = pr_to_fragment(pr)
            if fragment:
                entries.append(render_entry(fragment, date=args.date))
        if since is None and highest is not None and not args.dry_run:
            # First run on a repo with history: record where we are rather than
            # folding every old PR in again on the next run.
            print(f"watermark initialised at #{highest}")

    if args.dry_run:
        print("\n".join(entries) if entries else "(nothing to write)")
        return EXIT_OK

    written = 0
    if entries:
        CHANGELOG.write_text(
            splice_entries(CHANGELOG.read_text(encoding="utf-8"), entries), encoding="utf-8"
        )
        written += len(entries)

    # Fragments are the no-PR escape hatch; fold them in and delete them.
    for directory, ledger in ((CHANGES_DIR, CHANGELOG),):
        count, consumed = collate(directory, ledger, date=args.date)
        written += count
        for path in consumed:
            print(f"consumed {path.name}")

    if highest is not None:
        write_watermark(highest)

    print(f"{written} entr{'y' if written == 1 else 'ies'} written.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
