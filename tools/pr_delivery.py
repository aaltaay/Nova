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
    from tools.pr_delivery_actions import (
        MERGE_HEAD_MOVED, merge_now, merge_pr, signal_conflict,
    )
    from tools.pr_review_status import (
        MIN_PR_AGE_SECONDS,
        head_age_seconds,
        review_in_flight,
        too_young,
    )
except ImportError:  # `python tools/pr_delivery.py` puts tools/ on sys.path
    from branch_cleanup import delete_closed_head
    from pr_delivery_actions import (
        MERGE_HEAD_MOVED, merge_now, merge_pr, signal_conflict,
    )
    from pr_review_status import (
        MIN_PR_AGE_SECONDS,
        head_age_seconds,
        review_in_flight,
        too_young,
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
    age_seconds: float | None = None,
    min_age_seconds: int = MIN_PR_AGE_SECONDS,
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
    # "merge it now": there is no point waiting on a PR that is held anyway.
    # Both gates live HERE, not in a caller, so the merge job, the scheduled
    # sweep and a manual dispatch give one answer. A grace period that lived
    # only in cmd_merge was bypassed by the sweep within the hour (#410).
    # WAIT, not BLOCK -- a later sweep merges it, and CI completing fires one.
    if too_young(age_seconds, min_age=min_age_seconds):
        return Decision(ACTION_WAIT, "settling")
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
            "headRefName,headRefOid,headRepository,headRepositoryOwner,comments,"
            "createdAt,commits",
        ]
    ).stdout
    pr = json.loads(raw)
    # Pending, failing, missing and malformed check results cannot delay delivery.
    return pr, []


def _decision_from_pr(
    pr: dict[str, Any], checks: list[dict[str, Any]], *,
    min_age_seconds: int = MIN_PR_AGE_SECONDS,
) -> Decision:
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
        review_in_flight=review_in_flight(pr),
        age_seconds=head_age_seconds(pr),
        min_age_seconds=min_age_seconds,
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
    min_age_seconds: int = MIN_PR_AGE_SECONDS,
) -> int:
    deadline = time.time() + max(0, wait_desktop_minutes) * 60
    # Nothing re-fires when the floor expires, so this job waits it out rather
    # than leave the PR to the hourly cron. Capped at twice the floor: a head
    # that keeps moving keeps resetting the floor, and that must not pin a runner.
    settle_cap = time.time() + 2 * max(min_age_seconds, 1)
    while True:
        pr, checks = _fetch_pr(number)
        decision = _decision_from_pr(pr, checks, min_age_seconds=min_age_seconds)
        print(f"#{number} {decision.action} {decision.reason}")
        if decision.action == ACTION_MERGE:
            result = _merge_pr(pr)
            if result != MERGE_HEAD_MOVED:
                return result
            # A push landed between the decision and the PUT. Re-decide from
            # the new head rather than merging something nothing evaluated.
            continue
        if decision.reason == "conflict":
            _signal_conflict(number)
        if decision.reason == "settling":
            left = max(0.0, min_age_seconds - (head_age_seconds(pr) or 0.0)) + 5
            deadline = min(max(deadline, time.time() + left), settle_cap)
        if decision.action == ACTION_WAIT and time.time() < deadline:
            time.sleep(20)
            continue
        return 0 if decision.action in {ACTION_SKIP, ACTION_WAIT} else 1


def cmd_sweep(*, min_age_seconds: int = MIN_PR_AGE_SECONDS) -> int:
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
        decision = _decision_from_pr(pr, checks, min_age_seconds=min_age_seconds)
        print(f"#{number} {decision.action} {decision.reason}")
        if decision.action == ACTION_MERGE:
            result = _merge_pr(pr)
            # head_moved is not an error: the next pass decides the new head.
            if result not in (0, MERGE_HEAD_MOVED):
                errors += 1
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
    merge_p.add_argument("--min-age-seconds", type=int, default=MIN_PR_AGE_SECONDS,
                         help="floor on a PR's age before it can merge (0 disables)")

    sweep_p = sub.add_parser("sweep")
    sweep_p.add_argument("--min-age-seconds", type=int, default=MIN_PR_AGE_SECONDS,
                         help="floor on a PR's age before it can merge (0 disables)")

    delete_p = sub.add_parser("delete-closed")
    delete_p.add_argument("--ref", required=True)
    delete_p.add_argument("--same-repo", action="store_true", default=True)
    delete_p.add_argument("--fork", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "decide":
        return cmd_decide(args.pr)
    if args.command == "merge":
        return cmd_merge(args.pr, wait_desktop_minutes=args.wait_desktop_minutes,
                         min_age_seconds=args.min_age_seconds)
    if args.command == "sweep":
        return cmd_sweep(min_age_seconds=args.min_age_seconds)
    if args.command == "delete-closed":
        return cmd_delete_closed(args.ref, same_repo=not args.fork)
    return 2


if __name__ == "__main__":
    sys.exit(main())
