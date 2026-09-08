#!/usr/bin/env python3
"""GitHub Issues backend for the Nova deferred tracker.

Source of truth is issues labeled ``deferred`` on the Nova repo.
Title contract: ``D-NNN -- short title`` (ASCII double hyphen).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Owner: tools/deferred_github.py (read + write).
# Invalidation: rewrite when a deferred issue is opened or closed.
# schema_version: 1 (see INDEX_SCHEMA_VERSION).
INDEX_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "deferred-index.json"
INDEX_SCHEMA_VERSION = 1

DEFAULT_REPO = "aaltaay/Nova"
DEFERRED_LABEL = "deferred"
ISSUES_QUERY = "is:issue label:deferred"
TITLE_RE = re.compile(r"^(D-\d+)\s+--\s+(.+)$")

KIND_TO_LABEL = {
    "bug": "bug",
    "feature": "enhancement",
    "decision": "decision",
}
LABEL_TO_KIND = {
    "bug": "bug",
    "enhancement": "feature",
    "decision": "decision",
}

SEVERITY_LABELS = ("P0", "P1", "P2", "P3")
STATUS_LABELS = ("blocked", "parked")

DOMAIN_PREFIX = "domain:"
KNOWN_DOMAINS = (
    "docs",
    "execution",
    "frontend",
    "hod-momo",
    "ibkr-ops",
    "market-feed",
    "news",
    "security",
    "tester",
    "widgets",
)

# name, color (no #), description
TRACKER_LABELS: tuple[tuple[str, str, str], ...] = (
    (DEFERRED_LABEL, "5319e7", "Parked bug or feature (Nova D-NNN)"),
    ("P0", "b60205", "Desk-broken, wrong money, cannot operate"),
    ("P1", "d93f0b", "Daily-use wrong"),
    ("P2", "fbca04", "Edge session / honesty / annoying"),
    ("P3", "0e8a16", "Polish"),
    ("decision", "d4c5f9", "Blocked on a human call"),
    ("blocked", "e11d48", "Cannot start until Unblock is met"),
    ("parked", "c5def5", "Do not start until the operator names this ID"),
    *((f"{DOMAIN_PREFIX}{d}", "1d76db", f"Nova domain {d}") for d in KNOWN_DOMAINS),
)


def repo_slug() -> str:
    return (os.environ.get("NOVA_GITHUB_REPO") or DEFAULT_REPO).strip()


def issues_url(*, open_only: bool = True) -> str:
    q = ISSUES_QUERY + (" is:open" if open_only else "")
    return f"https://github.com/{repo_slug()}/issues?q={q.replace(' ', '+')}"


def _label_names(issue: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for raw in issue.get("labels") or []:
        if isinstance(raw, dict):
            name = raw.get("name") or ""
        else:
            name = str(raw)
        if name:
            out.append(name)
    return out


def parse_issue(issue: dict[str, Any]) -> dict[str, str] | None:
    """Map a ``gh`` issue JSON object to a deferred_log entry dict."""
    title = (issue.get("title") or "").strip()
    match = TITLE_RE.match(title)
    if not match:
        return None
    names = _label_names(issue)
    name_set = {n.lower(): n for n in names}
    kind = "bug"
    for label, mapped in LABEL_TO_KIND.items():
        if label in name_set:
            kind = mapped
            break
    severity = "?"
    for sev in SEVERITY_LABELS:
        if sev.lower() in name_set:
            severity = sev
            break
    state = (issue.get("state") or "OPEN").upper()
    if state == "CLOSED":
        status = "done"
    elif "parked" in name_set:
        status = "parked"
    elif "blocked" in name_set:
        status = "blocked"
    else:
        status = "open"
    domains = [
        n.split(":", 1)[1]
        for n in names
        if n.lower().startswith(DOMAIN_PREFIX)
    ]
    return {
        "id": match.group(1),
        "title": match.group(2).strip(),
        "kind": kind,
        "severity": severity,
        "status": status,
        "domain": " | ".join(domains),
        "number": str(issue.get("number") or ""),
        "url": (issue.get("url") or "").strip(),
        "state": state,
    }


def labels_for_entry(entry: dict[str, str]) -> list[str]:
    labels = [DEFERRED_LABEL]
    sev = (entry.get("severity") or "").split()[0].upper()
    if sev in SEVERITY_LABELS:
        labels.append(sev)
    kind = (entry.get("kind") or "bug").split()[0].lower()
    labels.append(KIND_TO_LABEL.get(kind, "bug"))
    status = (entry.get("status") or "open").split()[0].lower()
    if status in STATUS_LABELS:
        labels.append(status)
    raw_domain = entry.get("domain") or ""
    for part in re.split(r"[|,]", raw_domain):
        token = part.strip().lower()
        if token in KNOWN_DOMAINS:
            labels.append(f"{DOMAIN_PREFIX}{token}")
    return labels


def run_gh(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "gh failed").strip()
        raise RuntimeError(err)
    return proc


def list_issues(*, state: str = "open") -> list[dict[str, Any]]:
    """``state`` is open | closed | all."""
    proc = run_gh(
        [
            "issue",
            "list",
            "--repo",
            repo_slug(),
            "--label",
            DEFERRED_LABEL,
            "--state",
            state,
            "--limit",
            "200",
            "--json",
            "number,title,labels,state,url",
        ]
    )
    data = json.loads(proc.stdout) if proc.stdout.strip() else []
    if not isinstance(data, list):
        raise RuntimeError("gh issue list returned non-list JSON")
    return data


def load_index(path: Path | None = None) -> list[dict[str, str]]:
    target = path or INDEX_PATH
    data = json.loads(target.read_text(encoding="utf-8"))
    version = data.get("schema_version")
    if version != INDEX_SCHEMA_VERSION:
        raise RuntimeError(
            f"unsupported deferred-index schema_version={version!r} (want {INDEX_SCHEMA_VERSION})"
        )
    items = data.get("items") or []
    if not isinstance(items, list):
        raise RuntimeError("deferred-index items must be a list")
    return items


def write_index(items: list[dict[str, str]], path: Path | None = None) -> None:
    target = path or INDEX_PATH
    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "source": "github",
        "repo": repo_slug(),
        "updated": __import__("datetime").date.today().isoformat(),
        "items": items,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _entries_from_index(state: str) -> list[dict[str, str]]:
    items = load_index()
    if state == "all":
        return items
    if state == "closed":
        return [e for e in items if (e.get("status") or "") == "done"]
    return [
        e
        for e in items
        if (e.get("status") or "open").split()[0].lower()
        in {"open", "blocked", "parked"}
    ]


def fetch_entries(*, state: str = "open") -> list[dict[str, str]]:
    live: list[dict[str, str]] | None
    try:
        live = []
        for issue in list_issues(state=state):
            parsed = parse_issue(issue)
            if parsed:
                live.append(parsed)
    except Exception as exc:
        print(
            f"deferred_github: gh list failed ({exc}); using {INDEX_PATH.name} snapshot",
            file=sys.stderr,
        )
        return _entries_from_index(state)
    if live:
        return live
    # Some tokens return [] with exit 0 instead of 403. Prefer a nonempty snapshot.
    try:
        indexed = _entries_from_index(state)
    except Exception:
        return live
    if indexed:
        print(
            f"deferred_github: gh returned 0 issues; using {INDEX_PATH.name} snapshot",
            file=sys.stderr,
        )
        return indexed
    return live


def existing_ids() -> dict[str, dict[str, str]]:
    return {e["id"]: e for e in fetch_entries(state="all")}


def next_id_from_issues(entries: list[dict[str, str]] | None = None) -> str:
    rows = entries if entries is not None else fetch_entries(state="all")
    nums = []
    for item in rows:
        match = re.search(r"D-(\d+)", item.get("id") or "")
        if match:
            nums.append(int(match.group(1)))
    return f"D-{max(nums, default=0) + 1:03d}"


def ensure_labels() -> None:
    """Best-effort. Some tokens can create issues but not labels (HTTP 403)."""
    proc = run_gh(
        ["label", "list", "--repo", repo_slug(), "--limit", "200", "--json", "name"],
        check=False,
    )
    have: set[str] = set()
    if proc.returncode == 0 and proc.stdout.strip():
        have = {row["name"] for row in json.loads(proc.stdout)}
    for name, color, desc in TRACKER_LABELS:
        if name in have:
            continue
        created = run_gh(
            [
                "label",
                "create",
                name,
                "--repo",
                repo_slug(),
                "--color",
                color,
                "--description",
                desc,
            ],
            check=False,
        )
        if created.returncode != 0:
            err = (created.stderr or created.stdout or "").strip()
            if "already exists" in err.lower():
                continue
            print(f"deferred_github: skip label {name!r}: {err}", file=sys.stderr)


def create_issue(*, title: str, body: str, labels: list[str]) -> int:
    args = [
        "issue",
        "create",
        "--repo",
        repo_slug(),
        "--title",
        title,
        "--body",
        body,
    ]
    for label in labels:
        args.extend(["--label", label])
    proc = run_gh(args)
    # URL like https://github.com/aaltaay/Nova/issues/12
    url = (proc.stdout or "").strip().splitlines()[-1]
    match = re.search(r"/issues/(\d+)", url)
    if not match:
        raise RuntimeError(f"could not parse issue number from: {url}")
    return int(match.group(1))


def close_issue(number: int) -> None:
    run_gh(
        [
            "issue",
            "close",
            str(number),
            "--repo",
            repo_slug(),
            "--reason",
            "completed",
        ]
    )
