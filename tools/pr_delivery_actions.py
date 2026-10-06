"""GitHub squash-merge and conflict-comment calls for PR delivery."""

from __future__ import annotations

import json
import re
import sys
import time
from collections.abc import Callable
from typing import Any

try:
    from tools.pr_delivery_text import (
        closing_issue_numbers,
        conflict_rebase_comment,
        should_post_conflict_comment,
        squash_merge_fields,
    )
except ImportError:
    from pr_delivery_text import (
        closing_issue_numbers,
        conflict_rebase_comment,
        should_post_conflict_comment,
        squash_merge_fields,
    )

GhFn = Callable[..., Any]
DeleteFn = Callable[..., int]

DESKTOP_PACK_WORKFLOW = "desktop-pack.yml"
# A head that moved is not a failure -- the new head simply has to be
# decided again from scratch, and it reads as `settling` (#412).
MERGE_HEAD_MOVED = 3
RELEASE_BRANCH = "master"
MERGE_CONFIRM_ATTEMPTS = 3
MERGE_CONFIRM_DELAY_SECONDS = 1


def merge_now(
    gh: GhFn,
    repo: str,
    number: int,
    head_ref: str,
    title: str,
    body: str,
    delete_closed: DeleteFn,
    sha: str = "",
) -> int:
    payload = squash_merge_fields(number, title, body, sha)
    proc = gh(
        ["api", "-X", "PUT", f"repos/{repo}/pulls/{number}/merge", "--input", "-"],
        check=False,
        stdin=json.dumps(payload),
    )
    if proc.returncode != 0:
        detail = proc.stderr or proc.stdout or f"merge #{number} failed"
        # With `sha` sent, 409 means only "head branch was modified"; a merge
        # that genuinely cannot be performed answers 405.
        if sha and "409" in detail:
            print(f"#{number} skip head_moved", file=sys.stderr)
            return MERGE_HEAD_MOVED
        race = bool(re.search(r"\bHTTP\s*405\b", detail, re.IGNORECASE)) and (
            "merge already in progress" in detail.lower()
        )
        if not (sha and race and _confirm_concurrent_merge(gh, repo, number, sha)):
            print(detail, file=sys.stderr)
            return 2
    print(f"merged #{number}")
    issues_closed = confirm_linked_issue_closure(gh, repo, number, body)
    dispatch_desktop_pack(gh, repo)
    if head_ref:
        delete_closed(head_ref, same_repo=True)
    return 0 if issues_closed else 2



def _read_resource(gh: GhFn, endpoint: str) -> dict[str, Any]:
    proc = gh(["api", endpoint], check=False)
    if proc.returncode:
        raise ValueError(proc.stderr or proc.stdout or "GitHub read failed")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("GitHub returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("GitHub returned no resource object")
    return data


def _confirm_concurrent_merge(gh: GhFn, repo: str, number: int, sha: str) -> bool:
    """Read only: a failed PUT is successful only when its exact merge completed (#762)."""
    for attempt in range(MERGE_CONFIRM_ATTEMPTS):
        try:
            pr = _read_resource(gh, f"repos/{repo}/pulls/{number}")
        except ValueError as exc:
            print(f"#{number} merge completion read failed: {exc}", file=sys.stderr)
            return False
        head, base = pr.get("head"), pr.get("base")
        if not isinstance(head, dict) or not isinstance(base, dict):
            return False
        if head.get("sha") != sha or base.get("ref") != RELEASE_BRANCH:
            return False
        for endpoint in (head, base):
            repository = endpoint.get("repo")
            if not isinstance(repository, dict):
                return False
            name = repository.get("full_name")
            if not isinstance(name, str) or name.lower() != repo.lower():
                return False
        commit = pr.get("merge_commit_sha")
        if (
            pr.get("merged") is True and pr.get("state") == "closed"
            and isinstance(commit, str) and commit.strip()
        ):
            print(f"#{number} confirmed concurrent merge at {commit}")
            return True
        if pr.get("merged") is not False or pr.get("state") != "open":
            return False
        if attempt + 1 < MERGE_CONFIRM_ATTEMPTS:
            time.sleep(MERGE_CONFIRM_DELAY_SECONDS)
    print(f"#{number} merge remained unconfirmed after {MERGE_CONFIRM_ATTEMPTS} reads", file=sys.stderr)
    return False


def confirm_linked_issue_closure(gh: GhFn, repo: str, pr_number: int, body: str) -> bool:
    """Verify native closure, falling back only for explicit completion lines.

    A failed close is a failed delivery result, while the merge remains landed.
    The caller must still dispatch its pack and attempt guarded head cleanup.
    """
    numbers = closing_issue_numbers(body, repo)
    if not numbers:
        return True
    try:
        pr = _read_resource(gh, f"repos/{repo}/pulls/{pr_number}")
        if pr.get("merged") is not True:
            raise ValueError("PR is not confirmed merged")
        if (pr.get("base") or {}).get("ref") != RELEASE_BRANCH:
            print(f"#{pr_number} skip linked issue closure: base is not {RELEASE_BRANCH}")
            return True
    except ValueError as exc:
        print(f"#{pr_number} issue closure verification failed: {exc}", file=sys.stderr)
        return False
    completed = True
    for number in numbers:
        endpoint = f"repos/{repo}/issues/{number}"
        try:
            issue = _read_resource(gh, endpoint)
            if "pull_request" in issue or issue.get("state") not in {"open", "closed"}:
                raise ValueError("cannot confirm issue (PR reference or unknown state)")
            if issue["state"] == "open":
                proc = gh(
                    ["api", "-X", "PATCH", endpoint, "--input", "-"],
                    check=False,
                    stdin=json.dumps({"state": "closed", "state_reason": "completed"}),
                )
                write_error = (
                    proc.stderr or proc.stdout or "GitHub issue write failed"
                ) if proc.returncode else ""
                # Native GitHub closure may win after our open-state read,
                # making this PATCH fail even though the issue is now closed.
                try:
                    actual = _read_resource(gh, endpoint)
                except ValueError as exc:
                    if write_error:
                        raise ValueError(f"{write_error}; closure readback failed: {exc}") from exc
                    raise
                if actual.get("state") != "closed" or "pull_request" in actual:
                    detail = "issue still open or closure readback invalid"
                    raise ValueError(f"{write_error}; {detail}" if write_error else detail)
            print(f"#{number} confirmed closed after merged PR #{pr_number}")
        except ValueError as exc:
            completed = False
            print(f"#{number} closure after merged PR #{pr_number} failed: {exc}", file=sys.stderr)
    return completed


def dispatch_desktop_pack(gh: GhFn, repo: str, ref: str = RELEASE_BRANCH) -> bool:
    """Start the pack explicitly -- an Actions merge never fires `push:` (#346).

    GitHub suppresses workflow runs for events created with `GITHUB_TOKEN` so a
    workflow cannot trigger itself. The squash-merge above therefore lands on
    master without starting `desktop-pack.yml`, which is how master once went
    hundreds of commits with no packed installer at all. `workflow_dispatch` is
    one of the two documented exceptions to that rule, so the same token can
    start the pack on purpose. Keeping `GITHUB_TOKEN` here means no release PAT.

    This dispatch tags the merged commit `vNNN` and, when the installer packs,
    publishes it as that GitHub Release (operator decision 2026-09-23).
    """
    proc = gh(
        [
            "api",
            "-X",
            "POST",
            f"repos/{repo}/actions/workflows/{DESKTOP_PACK_WORKFLOW}/dispatches",
            "-f",
            f"ref={ref}",
        ],
        check=False,
    )
    if proc.returncode != 0:
        # The merge already landed. A failed dispatch costs this commit its
        # installer build, not the merge, so report it loudly and let the
        # caller return success -- the next pack covers the same code.
        print(
            proc.stderr or proc.stdout or f"desktop pack dispatch on {ref} failed",
            file=sys.stderr,
        )
        return False
    print(f"desktop pack dispatched on {ref}")
    return True


def signal_conflict(gh: GhFn, repo: str, number: int) -> None:
    listed = gh(
        ["api", f"repos/{repo}/issues/{number}/comments?per_page=100"],
        check=False,
    )
    bodies: list[str] = []
    if listed.returncode == 0 and listed.stdout.strip():
        try:
            loaded = json.loads(listed.stdout)
        except json.JSONDecodeError:
            loaded = []
        if isinstance(loaded, list):
            bodies = [
                str(item.get("body") or "")
                for item in loaded
                if isinstance(item, dict)
            ]
    if not should_post_conflict_comment(bodies):
        print(f"#{number} conflict comment already present")
        return
    posted = gh(
        ["pr", "comment", str(number), "--body", conflict_rebase_comment()],
        check=False,
    )
    if posted.returncode != 0:
        print(
            posted.stderr or posted.stdout or f"conflict comment #{number} failed",
            file=sys.stderr,
        )
        return
    print(f"#{number} conflict comment posted")


def merge_pr(gh: GhFn, repo: str, pr: dict[str, Any], delete_closed: DeleteFn) -> int:
    return merge_now(
        gh,
        repo,
        int(pr["number"]),
        str(pr.get("headRefName") or ""),
        str(pr.get("title") or ""),
        str(pr.get("body") or ""),
        delete_closed,
        str(pr.get("headRefOid") or ""),
    )
