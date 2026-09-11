#!/usr/bin/env python3
"""Fail if origin still holds a branch whose pull request is merged or closed.

After a PR is merged or closed, agents MUST delete its head branch in the
same session. GitHub `delete_branch_on_merge` is not reliable here -- do not
wait for it. Open PR heads and branches with no PR yet are kept.

Usage:
  py -3 tools/stale_pr_branches.py
  py -3 tools/stale_pr_branches.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Iterable

PROTECTED = frozenset({"master", "main", "HEAD"})
STALE_STATES = frozenset({"MERGED", "CLOSED"})


def _short_name(ref: str) -> str:
    name = ref.strip()
    if name.startswith("origin/"):
        name = name[len("origin/") :]
    return name


def classify_stale_branches(
    refs: Iterable[str],
    pull_requests: Iterable[dict],
) -> list[tuple[str, str, int]]:
    """Return (branch, state, number) for leftover merged/closed heads.

    A branch with any OPEN PR is kept even if an older PR on the same name
    was closed. Protected names are never reported.
    """
    by_head: dict[str, list[dict]] = {}
    for pr in pull_requests:
        head = _short_name(str(pr.get("head") or ""))
        if not head:
            continue
        by_head.setdefault(head, []).append(pr)

    stale: list[tuple[str, str, int]] = []
    for ref in refs:
        name = _short_name(ref)
        if not name or name in PROTECTED:
            continue
        prs = by_head.get(name, [])
        if any(str(pr.get("state") or "").upper() == "OPEN" for pr in prs):
            continue
        leftover = next(
            (
                pr
                for pr in prs
                if str(pr.get("state") or "").upper() in STALE_STATES
            ),
            None,
        )
        if leftover is None:
            continue
        stale.append(
            (name, str(leftover["state"]).upper(), int(leftover["number"])),
        )
    return stale


def _git_remote_branches() -> list[str]:
    raw = subprocess.check_output(
        ["git", "branch", "-r", "--format=%(refname:short)"],
        text=True,
    )
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _gh_all_prs() -> list[dict]:
    raw = subprocess.check_output(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "all",
            "--limit",
            "200",
            "--json",
            "number,state,headRefName",
        ],
        text=True,
    )
    rows = json.loads(raw)
    return [
        {
            "head": item.get("headRefName") or "",
            "state": item.get("state") or "",
            "number": item.get("number"),
        }
        for item in rows
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    stale = classify_stale_branches(_git_remote_branches(), _gh_all_prs())
    payload = [
        {"branch": name, "state": state, "number": number}
        for name, state, number in stale
    ]
    if args.json:
        print(json.dumps(payload, indent=2))
    elif not stale:
        print("stale_pr_branches: OK (no leftover merged/closed heads)")
    else:
        print("stale_pr_branches: leftover heads after merge/close:")
        for name, state, number in stale:
            print(f"  origin/{name}  PR #{number} {state}")
        print(
            "Delete with: git push origin --delete "
            + " ".join(name for name, _, _ in stale)
        )
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
