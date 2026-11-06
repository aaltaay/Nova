"""GitHub plumbing for the backlog tools: fetching issues, milestones and
comments, plus the field accessors that read an issue dict.

Split out of backlog_triage.py so no module exceeds the 400-line limit in
AGENTS.md 2.3. Everything here talks to `gh`; nothing here decides anything."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Callable

DEFAULT_REPO = "aaltaay/Nova"

EXIT_OK = 0
EXIT_GAPS = 1
EXIT_ERROR = 2

SEVERITIES = ("P0", "P1", "P2", "P3")
KINDS = ("bug", "enhancement", "decision", "documentation")

# A package with no milestone is invisible to every GitHub-side consumer,
# so "unassigned" is a gap, not a state.
NO_MILESTONE = "(no package)"

# Without this it would report itself as an untriaged issue forever.

# The inbox. A new issue is assigned here by .github/workflows/backlog-inbox.yml
# the moment it is opened, so it is visible to `next` within minutes instead of
# waiting for the Monday sweep. Routing it onward is a judgement call -- which
# outcome does this issue serve? -- so nothing guesses it from a label. Issues
# leave the inbox by being added to a package in knowledge/backlog-packages.json,
# never by being worked on from here.
INBOX_TITLE = "00 - Untriaged"

# An untriaged P0/P1 is the failure this inbox exists to prevent: `next` would
# hand out routine work while a desk-breaking bug sat unrouted. `check` fails
# on those rather than treating the inbox as uniformly fine.
URGENT = ("P0", "P1")

Runner = Callable[..., subprocess.CompletedProcess[str]]


def repo_slug() -> str:
    return os.environ.get("NOVA_GITHUB_REPO", DEFAULT_REPO)


def run_gh(args: list[str], *, runner: Runner = subprocess.run) -> subprocess.CompletedProcess[str]:
    return runner(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )


def label_names(issue: dict[str, Any]) -> set[str]:
    return {lbl.get("name", "") for lbl in issue.get("labels") or []}


def milestone_title(issue: dict[str, Any]) -> str:
    ms = issue.get("milestone")
    if not ms:
        return NO_MILESTONE
    return ms.get("title") or NO_MILESTONE


def severity_of(issue: dict[str, Any]) -> str:
    names = label_names(issue)
    for sev in SEVERITIES:
        if sev in names:
            return sev
    return ""


def domain_labels(issue: dict[str, Any]) -> set[str]:
    return {n for n in label_names(issue) if n.startswith("domain:")}


def _rest_pages(path: str, *, runner: Runner) -> list[dict[str, Any]]:
    """Every page of a REST list, one flat array.

    REST, not ``gh issue list`` / ``gh issue view``: those ride GraphQL, which
    cloud agent sessions are refused, while the REST routes answer everywhere.
    """
    proc = run_gh(["api", "--paginate", "--slurp", path], runner=runner)
    if proc.returncode != 0:
        raise RuntimeError(f"gh api {path.split('?')[0]} failed: {proc.stderr.strip()}")
    pages = json.loads(proc.stdout or "[]")
    return [item for page in pages for item in (page if isinstance(page, list) else [page])]


def fetch_issues(*, runner: Runner = subprocess.run) -> list[dict[str, Any]]:
    """Open backlog issues.

    Raises on a gh failure rather than returning an empty list: an empty
    backlog and an unreadable one must not look the same.
    """
    rows = _rest_pages(f"repos/{repo_slug()}/issues?state=open&per_page=100", runner=runner)
    return [
        {
            "number": row["number"],
            "title": row.get("title") or "",
            "labels": [{"name": lbl.get("name", "")} for lbl in row.get("labels") or []],
            "milestone": {"title": row["milestone"].get("title")} if row.get("milestone") else None,
            "url": row.get("html_url") or "",
            "createdAt": row.get("created_at") or "",
            "updatedAt": row.get("updated_at") or "",
        }
        for row in rows
        if "pull_request" not in row
    ]


def fetch_milestones(*, runner: Runner = subprocess.run) -> list[dict[str, Any]]:
    proc = run_gh(["api", f"repos/{repo_slug()}/milestones?state=all&per_page=100"], runner=runner)
    if proc.returncode != 0:
        raise RuntimeError(f"gh api milestones failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout or "[]")


def fetch_comments(number: int, *, runner: Runner = subprocess.run) -> list[dict[str, Any]]:
    rows = _rest_pages(f"repos/{repo_slug()}/issues/{number}/comments?per_page=100", runner=runner)
    return [
        {
            "body": row.get("body") or "",
            "createdAt": row.get("created_at") or "",
            "author": {"login": (row.get("user") or {}).get("login", "")},
            "url": row.get("html_url") or "",
        }
        for row in rows
    ]
