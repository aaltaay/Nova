"""Current-tip proof and conditional deletion for closed PR heads (#369).

Deletion is authorized two ways, and the distinction matters because Nova
squash-merges. A squash lands the branch content on master under a NEW sha, so
a merged head is never an ancestor of master -- judged on ancestry alone every
single merged branch is refused and left on origin forever. So a head whose tip
is exactly the commit a MERGED pull request carried is deleted on the strength
of that merge. Everything else -- a PR closed without merging, or a branch
pushed to after its merge -- still has to prove containment in master first,
which is the protection #369 exists for.

The delete itself is a plain delete, never a push with a force flag (AGENTS.md section 5.1, owner
2026-10-14: no force-push, not even the leased delete this used to send). ``delete_at_tip`` re-reads the
branch's tip right before deleting and deletes only while it is still the verified one. That leaves a
window the lease used to close: a push landing between the re-read and the delete is deleted with the
branch. Its author still has those commits locally, and the Stranded commits sweep (PR #957) reports a
push that lands after a merge.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from urllib.parse import quote

PROTECTED_HEADS = frozenset({"master", "main", "HEAD"})


def delete_at_tip(repo: str, ref: str, tip: str, read_tip: Callable[[], str | None]) -> tuple[bool, str]:
    """Delete ``refs/heads/<ref>`` on GitHub only while its tip is still ``tip``: ``read_tip()`` (None when
    the branch is gone; raises when it cannot look) right before a plain ``git push --delete``. True when
    origin is left without the branch; the string says what happened."""
    now = read_tip()
    if now is None:
        return True, "already absent"
    if now != tip:
        return False, f"its tip moved to {now} after {tip} was verified"
    push = subprocess.run(["git", "push", "--delete", f"https://github.com/{repo}.git", f"refs/heads/{ref}"],
                          capture_output=True, text=True, check=False)
    if push.returncode:
        return False, f"the delete failed: {push.stderr.strip()}"
    return True, "deleted"


def contained_tip(ref: str, *, cwd: str | None = None) -> str | None:
    """Return the immutable tip only when master contains it; errors propagate."""
    tip = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], text=True, cwd=cwd,
        stderr=subprocess.PIPE,
    ).strip()
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", tip, "refs/remotes/origin/master"],
        cwd=cwd, capture_output=True, text=True,
    )
    if result.returncode not in (0, 1):
        raise subprocess.CalledProcessError(result.returncode, result.args, stderr=result.stderr)
    return tip if result.returncode == 0 else None


def delete_closed_head(gh, repo: str, ref: str, *, same_repo: bool) -> int:
    """Fail closed, and delete only while the tip is still the verified SHA (``delete_at_tip``)."""
    if not same_repo or not ref or ref in PROTECTED_HEADS:
        print(f"skip delete {ref}: protected or fork")
        return 0
    valid = subprocess.run(
        ["git", "check-ref-format", f"refs/heads/{ref}"], capture_output=True, text=True,
    )
    if valid.returncode:
        print(f"refuse delete {ref}: invalid branch", file=sys.stderr)
        return 1
    try:
        result = gh([
            "pr", "list", "--repo", repo, "--state", "all", "--head", ref,
            "--limit", "200",
            "--json", "state,headRefName,headRefOid,headRepository,headRepositoryOwner",
        ], check=False)
        if result.returncode:
            raise ValueError("PR lookup failed")
        prs = json.loads(result.stdout)
        # Fork heads may share the same short name; they cannot authorize deletion.
        prs = [p for p in prs if p.get("headRefName") == ref and (
            f"{(p.get('headRepositoryOwner') or {}).get('login', '')}/"
            f"{(p.get('headRepository') or {}).get('name', '')}"
        ).lower() == repo.lower()]
        if any(p.get("state") == "OPEN" for p in prs):
            print(f"skip delete {ref}: open_pr")
            return 0
        if not any(p.get("state") in {"MERGED", "CLOSED"} for p in prs):
            print(f"skip delete {ref}: no closed same-repo PR")
            return 0
        # The exact commits GitHub merged. Nova squash-merges, so a merged head
        # is NEVER an ancestor of master -- its content lands under a new sha --
        # and the ancestry test below refuses every one of them. The merge is
        # the proof the work is safe; ancestry is the wrong question for it.
        merged_oids = {
            str(p.get("headRefOid") or "")
            for p in prs if p.get("state") == "MERGED"
        } - {""}
        result = gh(["api", f"repos/{repo}/git/ref/heads/{quote(ref, safe='')}"], check=False)
        if result.returncode and "HTTP 404" in result.stderr:
            print(f"already absent: {ref}")
            return 0
        if result.returncode:
            raise ValueError("branch lookup failed")
        tip = json.loads(result.stdout)["object"]["sha"]
        if tip not in merged_oids:
            # Not the commit GitHub merged: either this PR closed without
            # merging, or someone pushed to the branch after the merge. Both
            # can hold work that exists nowhere else, so containment in master
            # is the only proof that deleting loses nothing (#369).
            result = gh(["api", f"repos/{repo}/compare/master...{tip}"], check=False)
            if result.returncode:
                raise ValueError("master ancestry lookup failed")
            comparison = json.loads(result.stdout)
            if (comparison.get("status") not in {"behind", "identical"} or
                    (comparison.get("merge_base_commit") or {}).get("sha") != tip):
                print(f"REFUSE delete {ref}: tip {tip} is not contained in master "
                      "and is not the commit a merged PR carried; unmerged, "
                      "recreated, or pushed-after-merge work needs review",
                      file=sys.stderr)
                return 1
        # Check OPEN again after network reads; the tip is read again right before the delete.
        result = gh(["pr", "list", "--repo", repo, "--state", "open", "--head", ref,
                     "--json", "number"], check=False)
        if result.returncode:
            raise ValueError("open PR recheck failed")
        if json.loads(result.stdout):
            print(f"skip delete {ref}: open_pr")
            return 0

        def read_tip() -> str | None:
            again = gh(["api", f"repos/{repo}/git/ref/heads/{quote(ref, safe='')}"], check=False)
            if again.returncode and "HTTP 404" in again.stderr:
                return None
            if again.returncode:
                raise ValueError("branch re-read failed")
            return json.loads(again.stdout)["object"]["sha"]

        gone, why = delete_at_tip(repo, ref, tip, read_tip)
        if not gone:
            print(f"REFUSE delete {ref}: {why}; branch retained.", file=sys.stderr)
            return 1
        if why == "already absent":
            print(f"already absent: {ref}")
            return 0
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        print(f"REFUSE delete {ref}: unable to prove safety ({exc})", file=sys.stderr)
        return 1
    print(f"deleted {ref} at verified tip {tip}")
    return 0
