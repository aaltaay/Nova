"""Linked branches for a claimed backlog batch (#344).

A claim records who holds a batch; it could not say whether anyone actually cut
a branch for it. The branch name in a claim comment was an intention -- nothing
verified it -- so an agent that died between `claim` and its first push left an
issue labelled `claimed` naming a ref nobody could fetch.

Creating the branch at claim time fixes that and buys the GitHub Development
link for free: `gh issue develop` is the only surface that links a branch to an
issue with no pull request open yet (GraphQL `createLinkedBranch`; REST has no
equivalent, and a plain ref create does not link).

One branch serves a whole PR batch, but a Development link is per issue and the
mutation *creates* the ref. So the batch's lowest open issue is the anchor that
certainly carries the link; the rest are attempted and never fatal, because
whether GitHub links an existing ref to a second issue is unverified here.

The `gh` argument everywhere is the `backlog_github.run_gh` contract: called as
``gh([...])``, returns a CompletedProcess, never raises on a non-zero exit.

Deletion is compare-and-delete against a verified tip, never an unconditional
DELETE (#369): a branch carrying real commits is retained and reported, whatever
the claim said about it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote

BASE_BRANCH = "master"

PROTECTED_HEADS = frozenset({"master", "main", "HEAD"})

# A token that can comment but not write contents fails the create. That is a
# reportable limitation, never a silent success -- the same posture the
# constitution takes on Projects scope.
PERMISSION_MARKERS = (
    "HTTP 403",
    "Resource not accessible",
    "not accessible by personal access token",
    "must have admin rights",
)


class BranchLookupError(RuntimeError):
    """origin could not be read -- absence was not proven, so assume nothing."""


@dataclass(frozen=True)
class BranchLink:
    """What a claim can now assert about its branch."""

    branch: str
    tip: str | None = None
    created: bool = False
    linked: tuple[int, ...] = field(default_factory=tuple)
    denied: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        """True only when the ref is on origin. The link is a bonus; the ref
        is the promise `claim` now keeps."""
        return bool(self.tip) and not self.error


def is_permission_error(stderr: str) -> bool:
    text = stderr or ""
    return any(marker.lower() in text.lower() for marker in PERMISSION_MARKERS)


def branch_tip(gh, repo: str, ref: str) -> str | None:
    """Tip SHA of ``ref`` on origin, or None when it demonstrably does not exist.

    A failure that is not a 404 raises: "I could not look" must never be
    mistaken for "it is not there", or a re-claim would try to create a branch
    that already carries work.
    """
    result = gh(["api", f"repos/{repo}/git/ref/heads/{quote(ref, safe='')}"])
    if result.returncode:
        if "HTTP 404" in (result.stderr or ""):
            return None
        raise BranchLookupError((result.stderr or "").strip() or "ref lookup failed")
    try:
        return json.loads(result.stdout)["object"]["sha"]
    except (ValueError, KeyError, TypeError) as exc:
        raise BranchLookupError(f"unreadable ref payload: {exc}") from exc


def last_commit_at(gh, repo: str, ref: str) -> datetime | None:
    """When the claimed branch last moved, or None if that cannot be read.

    One call per live claim -- there are rarely more than a handful -- and only
    the human-facing `claims` view pays it. `next` stays on the cheap path.
    """
    try:
        result = gh(["api", f"repos/{repo}/branches/{quote(ref, safe='')}"])
        if result.returncode:
            return None
        stamp = json.loads(result.stdout)["commit"]["commit"]["committer"]["date"]
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # Enrichment only: a `claims` listing that cannot reach GitHub still
        # prints every holder, it just falls back to claim age for staleness.
        return None


def linked_branch_names(gh, repo: str, issue: int) -> tuple[str, ...]:
    """Branches GitHub shows in this issue's Development panel."""
    result = gh(["issue", "develop", str(issue), "--repo", repo, "--list"])
    if result.returncode:
        return ()
    names = []
    for line in (result.stdout or "").splitlines():
        name = line.split("\t", 1)[0].strip()
        if name:
            names.append(name)
    return tuple(names)


def _create(gh, repo: str, issue: int, branch: str, base: str):
    return gh(["issue", "develop", str(issue), "--repo", repo,
               "--base", base, "--name", branch])


def ensure_linked_branch(
    gh,
    repo: str,
    *,
    anchor: int,
    branch: str,
    base: str = BASE_BRANCH,
    extra_issues: tuple[int, ...] = (),
) -> BranchLink:
    """Put ``branch`` on origin and in ``anchor``'s Development panel.

    Idempotent: a re-claim or ``--force`` finds the ref already there and only
    tops up the link, so an agent resuming its own batch never destroys work.
    """
    try:
        tip = branch_tip(gh, repo, branch)
    except BranchLookupError as exc:
        return BranchLink(branch=branch, error=str(exc))

    created = False
    linked: list[int] = []

    if tip is None:
        result = _create(gh, repo, anchor, branch, base)
        if result.returncode:
            stderr = (result.stderr or "").strip()
            return BranchLink(branch=branch, denied=is_permission_error(stderr),
                              error=stderr or "gh issue develop failed")
        created = True
        linked.append(anchor)
        try:
            tip = branch_tip(gh, repo, branch)
        except BranchLookupError as exc:
            return BranchLink(branch=branch, created=True, error=str(exc))
        if tip is None:
            # gh reported success but origin does not have it: the likeliest
            # cause is a name collision resolved into a suffixed branch, which
            # is not the branch the claim comment promised.
            return BranchLink(branch=branch, created=True,
                              error=f"{branch} is not on origin after create")
    elif branch in linked_branch_names(gh, repo, anchor):
        linked.append(anchor)
    else:
        result = _create(gh, repo, anchor, branch, base)
        if not result.returncode:
            linked.append(anchor)

    # Whether GitHub links an existing ref to a second issue is unverified, so
    # a batch's remaining issues are best-effort. They keep their claim comment
    # either way, which is what `claims` and `next` actually read.
    for issue in extra_issues:
        if branch in linked_branch_names(gh, repo, issue):
            linked.append(issue)
            continue
        result = _create(gh, repo, issue, branch, base)
        if not result.returncode:
            linked.append(issue)

    return BranchLink(branch=branch, tip=tip, created=created, linked=tuple(linked))


def delete_unused_branch(gh, repo: str, ref: str) -> int:
    """Delete a released claim's branch, but only while it carries no work.

    `branch_cleanup.delete_closed_head` cannot serve here: it authorizes on a
    closed same-repo PR, and a released claim has no PR at all. The safety is
    the same and deliberately stricter -- any PR, or any commit beyond master,
    means a human decides. Returns 0 when origin is left correct, 1 on refusal.
    """
    if not ref or ref in PROTECTED_HEADS:
        print(f"skip delete {ref}: protected")
        return 0
    valid = subprocess.run(
        ["git", "check-ref-format", f"refs/heads/{ref}"], capture_output=True, text=True,
        check=False,
    )
    if valid.returncode:
        print(f"refuse delete {ref}: invalid branch", file=sys.stderr)
        return 1
    try:
        result = gh(["pr", "list", "--repo", repo, "--state", "all", "--head", ref,
                     "--limit", "50", "--json", "number,state"])
        if result.returncode:
            raise ValueError("PR lookup failed")
        if json.loads(result.stdout):
            print(f"skip delete {ref}: it has a pull request")
            return 0
        try:
            tip = branch_tip(gh, repo, ref)
        except BranchLookupError as exc:
            raise ValueError(str(exc)) from exc
        if tip is None:
            print(f"already absent: {ref}")
            return 0
        result = gh(["api", f"repos/{repo}/compare/{BASE_BRANCH}...{tip}"])
        if result.returncode:
            raise ValueError("master ancestry lookup failed")
        comparison = json.loads(result.stdout)
        if (comparison.get("status") not in {"behind", "identical"} or
                (comparison.get("merge_base_commit") or {}).get("sha") != tip):
            print(f"RETAIN {ref}: tip {tip} carries work not in {BASE_BRANCH}; "
                  "the release cleared the claim, not the branch", file=sys.stderr)
            return 1
        push = subprocess.run([
            "git", "push", f"--force-with-lease=refs/heads/{ref}:{tip}",
            f"https://github.com/{repo}.git", f":refs/heads/{ref}",
        ], capture_output=True, text=True, check=False)
        if push.returncode:
            print(f"RETAIN {ref}: conditional delete failed; a concurrent push "
                  f"may have landed. {push.stderr.strip()}", file=sys.stderr)
            return 1
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        print(f"RETAIN {ref}: unable to prove it is unused ({exc})", file=sys.stderr)
        return 1
    print(f"deleted unused branch {ref} at verified tip {tip}")
    return 0
