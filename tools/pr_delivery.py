#!/usr/bin/env python3
"""Merge ready Nova PRs and delete closed heads. GitHub Actions owns this.

Agents open a verified, non-draft PR and stop. They do not wait for a human
to say merge. Draft or label `do-not-merge` holds a PR. Closed heads are
deleted here as well as by GitHub `delete_branch_on_merge`.

Usage:
  python3 tools/pr_delivery.py decide --pr 64
  python3 tools/pr_delivery.py merge --pr 64
  python3 tools/pr_delivery.py sweep
  python3 tools/pr_delivery.py delete-closed --ref some-branch
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

DEFAULT_REPO = "aaltaay/Nova"
REQUIRED_CHECKS: tuple[str, ...] = (
    "Backend tests",
    "Frontend build",
    "Frontend E2E",
    "Agent contract",
)
WAIT_IF_PRESENT: tuple[str, ...] = ("Desktop pack",)
SKIP_LABELS = frozenset({"do-not-merge"})
PROTECTED_HEADS = frozenset({"master", "main", "HEAD"})

ACTION_MERGE = "merge"
ACTION_WAIT = "wait"
ACTION_SKIP = "skip"
ACTION_BLOCK = "block"


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"action": self.action, "reason": self.reason}


def repo_slug() -> str:
    return (os.environ.get("NOVA_GITHUB_REPO") or DEFAULT_REPO).strip()


def label_names(labels: Any) -> set[str]:
    names: set[str] = set()
    for item in labels or []:
        if isinstance(item, str) and item.strip():
            names.add(item.strip().lower())
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("slug") or "").strip()
            if name:
                names.add(name.lower())
    return names


def normalize_check(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw.get("name") or raw.get("context") or "").strip()
    if "conclusion" in raw or raw.get("status") in {
        "queued",
        "in_progress",
        "completed",
        "waiting",
        "requested",
        "pending",
    }:
        return {
            "name": name,
            "status": str(raw.get("status") or "completed"),
            "conclusion": raw.get("conclusion"),
        }
    state = str(raw.get("state") or raw.get("bucket") or "").lower()
    if state in {"pending", "queued"}:
        return {"name": name, "status": "in_progress", "conclusion": None}
    if state in {"pass", "success"}:
        return {"name": name, "status": "completed", "conclusion": "success"}
    if state in {"fail", "failure", "cancelled", "timed_out"}:
        return {"name": name, "status": "completed", "conclusion": "failure"}
    if state in {"skipping", "skipped", "neutral"}:
        return {"name": name, "status": "completed", "conclusion": "skipped"}
    return {"name": name, "status": "in_progress", "conclusion": None}


def check_map(checks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw in checks:
        item = normalize_check(raw)
        if item["name"]:
            out[item["name"]] = item
    return out


def _failed(item: dict[str, Any] | None) -> bool:
    if item is None:
        return False
    conclusion = str(item.get("conclusion") or "").lower()
    return conclusion in {"failure", "cancelled", "timed_out", "startup_failure"}


def _pending(item: dict[str, Any] | None) -> bool:
    if item is None:
        return True
    status = str(item.get("status") or "").lower()
    if status in {"queued", "in_progress", "waiting", "requested", "pending"}:
        return True
    return item.get("conclusion") in (None, "")


def _required_ok(item: dict[str, Any] | None) -> bool:
    if item is None:
        return False
    return str(item.get("conclusion") or "").lower() == "success"


def decide(
    *,
    draft: bool,
    state: str,
    mergeable_state: str,
    labels: Any,
    head_ref: str,
    same_repo: bool,
    checks: list[dict[str, Any]],
) -> Decision:
    if str(state or "OPEN").upper() not in {"OPEN"}:
        return Decision(ACTION_SKIP, "not_open")
    if not same_repo:
        return Decision(ACTION_SKIP, "fork")
    if draft:
        return Decision(ACTION_SKIP, "draft")
    head = str(head_ref or "").strip()
    if head.startswith("origin/"):
        head = head[len("origin/") :]
    if head in PROTECTED_HEADS:
        return Decision(ACTION_SKIP, "protected_head")
    if SKIP_LABELS & label_names(labels):
        return Decision(ACTION_SKIP, "do-not-merge")
    merge_state = str(mergeable_state or "").lower()
    if merge_state in {"dirty", "conflicting"}:
        return Decision(ACTION_BLOCK, "conflict")
    by_name = check_map(checks)
    for name in REQUIRED_CHECKS:
        item = by_name.get(name)
        if _failed(item):
            return Decision(ACTION_BLOCK, f"failed:{name}")
        if not _required_ok(item):
            return Decision(ACTION_WAIT, f"pending:{name}")
    for name in WAIT_IF_PRESENT:
        item = by_name.get(name)
        if item is None:
            continue
        if _failed(item):
            return Decision(ACTION_BLOCK, f"failed:{name}")
        if _pending(item):
            return Decision(ACTION_WAIT, f"pending:{name}")
    return Decision(ACTION_MERGE, "ready")


def can_delete_closed_head(
    ref: str,
    *,
    same_repo: bool,
    open_pr_on_head: bool,
) -> tuple[bool, str]:
    name = str(ref or "").strip()
    if name.startswith("refs/heads/"):
        name = name[len("refs/heads/") :]
    if name.startswith("origin/"):
        name = name[len("origin/") :]
    if not name or name in PROTECTED_HEADS:
        return False, "protected"
    if not same_repo:
        return False, "fork"
    if open_pr_on_head:
        return False, "open_pr"
    return True, "ok"


def _gh(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        text=True,
        capture_output=True,
        check=check,
    )


def _same_repo(head_owner: str, head_name: str) -> bool:
    slug = repo_slug()
    want_owner, _, want_name = slug.partition("/")
    owner = (head_owner or want_owner).strip()
    name = (head_name or want_name).strip()
    return f"{owner}/{name}".lower() == slug.lower()


def _fetch_pr(number: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = _gh(
        [
            "pr",
            "view",
            str(number),
            "--json",
            "number,state,isDraft,mergeStateStatus,labels,headRefName,"
            "headRepository,headRepositoryOwner",
        ]
    ).stdout
    pr = json.loads(raw)
    checks_raw = _gh(
        ["pr", "checks", str(number), "--json", "name,state,bucket"],
        check=False,
    )
    checks: list[dict[str, Any]] = []
    if checks_raw.returncode == 0 and checks_raw.stdout.strip():
        loaded = json.loads(checks_raw.stdout)
        if isinstance(loaded, list):
            checks = loaded
    return pr, checks


def _decision_from_pr(pr: dict[str, Any], checks: list[dict[str, Any]]) -> Decision:
    head_repo = pr.get("headRepository") or {}
    head_owner = pr.get("headRepositoryOwner") or {}
    return decide(
        draft=bool(pr.get("isDraft")),
        state=str(pr.get("state") or "OPEN"),
        mergeable_state=str(pr.get("mergeStateStatus") or ""),
        labels=pr.get("labels") or [],
        head_ref=str(pr.get("headRefName") or ""),
        same_repo=_same_repo(
            str(head_owner.get("login") or ""),
            str(head_repo.get("name") or ""),
        ),
        checks=checks,
    )


def _merge_now(number: int) -> int:
    proc = _gh(
        ["pr", "merge", str(number), "--merge", "--delete-branch"],
        check=False,
    )
    if proc.returncode == 0:
        print(f"merged #{number}")
        return 0
    print(proc.stderr or proc.stdout or f"gh pr merge #{number} failed", file=sys.stderr)
    return 2


def cmd_decide(number: int) -> int:
    pr, checks = _fetch_pr(number)
    decision = _decision_from_pr(pr, checks)
    print(json.dumps(decision.as_dict()))
    return 0


def cmd_merge(number: int, *, wait_desktop_minutes: int) -> int:
    deadline = time.time() + max(0, wait_desktop_minutes) * 60
    while True:
        pr, checks = _fetch_pr(number)
        decision = _decision_from_pr(pr, checks)
        print(f"#{number} {decision.action} {decision.reason}")
        if decision.action == ACTION_MERGE:
            return _merge_now(number)
        if decision.action == ACTION_WAIT and time.time() < deadline:
            time.sleep(20)
            continue
        return 0 if decision.action in {ACTION_SKIP, ACTION_WAIT} else 1


def cmd_sweep() -> int:
    raw = _gh(
        [
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "50",
            "--json",
            "number,title,isDraft,mergeStateStatus,labels,headRefName,"
            "headRepository,headRepositoryOwner,state",
        ]
    ).stdout
    rows = json.loads(raw)
    errors = 0
    for pr in rows:
        number = int(pr["number"])
        _, checks = _fetch_pr(number)
        decision = _decision_from_pr(pr, checks)
        print(f"#{number} {decision.action} {decision.reason}")
        if decision.action == ACTION_MERGE:
            errors += 0 if _merge_now(number) == 0 else 1
    return 1 if errors else 0


def cmd_delete_closed(ref: str, *, same_repo: bool) -> int:
    open_raw = _gh(
        ["pr", "list", "--state", "open", "--head", ref, "--json", "number"],
        check=False,
    )
    open_on_head = False
    if open_raw.returncode == 0 and open_raw.stdout.strip():
        loaded = json.loads(open_raw.stdout)
        open_on_head = bool(loaded)
    ok, reason = can_delete_closed_head(
        ref,
        same_repo=same_repo,
        open_pr_on_head=open_on_head,
    )
    if not ok:
        print(f"skip delete {ref}: {reason}")
        return 0
    slug = repo_slug()
    proc = _gh(
        ["api", "-X", "DELETE", f"repos/{slug}/git/refs/heads/{ref}"],
        check=False,
    )
    if proc.returncode == 0 or "Reference does not exist" in (proc.stderr + proc.stdout):
        print(f"deleted {ref}")
        return 0
    print(proc.stderr or proc.stdout or f"delete {ref} failed", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    decide_p = sub.add_parser("decide")
    decide_p.add_argument("--pr", type=int, required=True)

    merge_p = sub.add_parser("merge")
    merge_p.add_argument("--pr", type=int, required=True)
    merge_p.add_argument("--wait-desktop-minutes", type=int, default=0)

    sub.add_parser("sweep")

    delete_p = sub.add_parser("delete-closed")
    delete_p.add_argument("--ref", required=True)
    delete_p.add_argument("--same-repo", action="store_true", default=True)
    delete_p.add_argument("--fork", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "decide":
        return cmd_decide(args.pr)
    if args.command == "merge":
        return cmd_merge(args.pr, wait_desktop_minutes=args.wait_desktop_minutes)
    if args.command == "sweep":
        return cmd_sweep()
    if args.command == "delete-closed":
        return cmd_delete_closed(args.ref, same_repo=not args.fork)
    return 2


if __name__ == "__main__":
    sys.exit(main())
