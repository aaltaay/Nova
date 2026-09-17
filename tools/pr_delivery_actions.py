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


def merge_now(
    gh: GhFn,
    repo: str,
    number: int,
    head_ref: str,
    title: str,
    body: str,
    delete_closed: DeleteFn,
) -> int:
    payload = squash_merge_fields(number, title, body)
    proc = gh(
        ["api", "-X", "PUT", f"repos/{repo}/pulls/{number}/merge", "--input", "-"],
        check=False,
        stdin=json.dumps(payload),
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout or f"merge #{number} failed", file=sys.stderr)
        return 2
    print(f"merged #{number}")
    if head_ref:
        delete_closed(head_ref, same_repo=True)
    return 0


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
    )
