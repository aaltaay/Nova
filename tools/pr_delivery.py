#!/usr/bin/env python3
"""Merge ready Nova PRs (squash) and delete closed heads.

Agents open a verified, non-draft PR and stop. Draft or `do-not-merge` holds.
Closed heads are deleted here and by GitHub `delete_branch_on_merge`.

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

try:
    from tools.branch_cleanup import delete_closed_head
    from tools.pr_delivery_actions import merge_now, merge_pr, signal_conflict
    from tools.pr_review_status import (
        ANNOUNCE_GRACE_SECONDS,
        await_review_announcement,
        review_running,
    )
except ImportError:  # `python tools/pr_delivery.py` puts tools/ on sys.path
    from branch_cleanup import delete_closed_head
    from pr_delivery_actions import merge_now, merge_pr, signal_conflict
    from pr_review_status import (
        ANNOUNCE_GRACE_SECONDS,
        await_review_announcement,
        review_running,
    )

DEFAULT_REPO = "aaltaay/Nova"
# Owner policy: verification is feedback, never a merge prerequisite.
REQUIRED_CHECKS: tuple[str, ...] = ()
WAIT_IF_PRESENT: tuple[str, ...] = ()
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
    review_in_flight: bool = False,
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
    # After the gates that mean "never merge this", before the ones that mean
    # "merge it now": there is no point waiting on a review for a PR that is
    # held anyway, and no point merging out from under one that is running.
    # WAIT, not BLOCK -- the next sweep merges it, and CI completing fires one.
    if review_in_flight:
        return Decision(ACTION_WAIT, "review_running")
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


def _gh(
    args: list[str],
    *,
    check: bool = True,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        text=True,
        capture_output=True,
        check=check,
        input=stdin,
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
            "number,title,body,state,isDraft,mergeStateStatus,labels,"
            "headRefName,headRefOid,headRepository,headRepositoryOwner,comments",
        ]
    ).stdout
    pr = json.loads(raw)
    # Pending, failing, missing and malformed check results cannot delay delivery.
    return pr, []


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
        review_in_flight=_review_in_flight(pr),
    )


def _review_in_flight(pr: dict[str, Any]) -> bool:
    return review_running(
        [str(c.get("body") or "") for c in (pr.get("comments") or [])],
        head_sha=str(pr.get("headRefOid") or ""),
    )


def _merge_now(number: int, head_ref: str, title: str = "", body: str = "") -> int:
    # REST squash-merge -- `gh pr merge` waits for this Auto-merge job and deadlocks.
    return merge_now(
        _gh, repo_slug(), number, head_ref, title, body, cmd_delete_closed
    )


def _signal_conflict(number: int) -> None:
    signal_conflict(_gh, repo_slug(), number)


def _merge_pr(pr: dict[str, Any]) -> int:
    return merge_pr(_gh, repo_slug(), pr, cmd_delete_closed)


def cmd_decide(number: int) -> int:
    pr, checks = _fetch_pr(number)
    decision = _decision_from_pr(pr, checks)
    print(json.dumps(decision.as_dict()))
    return 0


def cmd_merge(
    number: int, *, wait_desktop_minutes: int,
    announce_grace_seconds: int = ANNOUNCE_GRACE_SECONDS,
) -> int:
    # A "merge" decided in a PR's first seconds may simply predate the
    # reviewer. Only a PR that is otherwise about to merge pays the wait, so
    # a draft, a fork or a conflict still reports instantly.
    pr, checks = _fetch_pr(number)
    if _decision_from_pr(pr, checks).action == ACTION_MERGE:
        await_review_announcement(
            lambda: _review_in_flight(_fetch_pr(number)[0]),
            seconds=announce_grace_seconds,
        )
    deadline = time.time() + max(0, wait_desktop_minutes) * 60
    while True:
        pr, checks = _fetch_pr(number)
        decision = _decision_from_pr(pr, checks)
        print(f"#{number} {decision.action} {decision.reason}")
        if decision.action == ACTION_MERGE:
            return _merge_pr(pr)
        if decision.reason == "conflict":
            _signal_conflict(number)
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
    for row in rows:
        number = int(row["number"])
        pr, checks = _fetch_pr(number)
        decision = _decision_from_pr(pr, checks)
        print(f"#{number} {decision.action} {decision.reason}")
        if decision.action == ACTION_MERGE:
            errors += 0 if _merge_pr(pr) == 0 else 1
        elif decision.reason == "conflict":
            _signal_conflict(number)
            errors += 1
    return 1 if errors else 0


def cmd_delete_closed(ref: str, *, same_repo: bool) -> int:
    return delete_closed_head(_gh, repo_slug(), ref, same_repo=same_repo)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    decide_p = sub.add_parser("decide")
    decide_p.add_argument("--pr", type=int, required=True)

    merge_p = sub.add_parser("merge")
    merge_p.add_argument("--pr", type=int, required=True)
    merge_p.add_argument("--wait-desktop-minutes", type=int, default=0)
    merge_p.add_argument("--announce-grace-seconds", type=int,
                         default=ANNOUNCE_GRACE_SECONDS,
                         help="how long to let a reviewer announce itself (0 disables)")

    sub.add_parser("sweep")

    delete_p = sub.add_parser("delete-closed")
    delete_p.add_argument("--ref", required=True)
    delete_p.add_argument("--same-repo", action="store_true", default=True)
    delete_p.add_argument("--fork", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "decide":
        return cmd_decide(args.pr)
    if args.command == "merge":
        return cmd_merge(args.pr, wait_desktop_minutes=args.wait_desktop_minutes,
                         announce_grace_seconds=args.announce_grace_seconds)
    if args.command == "sweep":
        return cmd_sweep()
    if args.command == "delete-closed":
        return cmd_delete_closed(args.ref, same_repo=not args.fork)
    return 2


if __name__ == "__main__":
    sys.exit(main())
