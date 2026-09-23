"""GitHub squash-merge and conflict-comment calls for PR delivery."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

try:
    from tools.pr_delivery_text import (
        conflict_rebase_comment,
        should_post_conflict_comment,
        squash_merge_fields,
    )
except ImportError:
    from pr_delivery_text import (
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
        print(detail, file=sys.stderr)
        return 2
    print(f"merged #{number}")
    dispatch_desktop_pack(gh, repo)
    if head_ref:
        delete_closed(head_ref, same_repo=True)
    return 0


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
