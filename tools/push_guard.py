"""Refuse to add commits to a merged PR's branch -- here, before the push (follow-up to PR #957).

Actions squash-merges a ready PR the moment its checks are green. A session still answering a review
pushes its fix to the same branch minutes later; the PR is already merged, so the fix lands on a branch
nothing will ever merge. ``stranded_commits.py`` recovers such pushes after the fact. This module is the
local half: it tells the session before the push (the opt-in git ``pre-push`` hook) or before the turn
ends (the Claude Code Stop hook, ``repo_hygiene.py stop-gate``).

The check: the branch has no open PR, its newest merged PR's head is known, and the tip carries commits
that are neither in that merged head nor on ``origin/master``. Anything that cannot be answered -- no
``gh``, offline, unauthenticated, the merged head not fetchable -- fails open and says why.

Usage (through repo_hygiene.py):
  py -3 tools/repo_hygiene.py install-push-guard [--uninstall]
  (git runs) tools/repo_hygiene.py push-guard <remote> <url>   # pre-push hook, stdin = refs
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

GH_TIMEOUT_SEC = 20  # gh alone takes 1.5 s here and the desk link stalls; a timeout fails open
GIT_FETCH_TIMEOUT_SEC = 20
PROTECTED = frozenset({"master", "main", "HEAD"})
ZERO_SHA = "0" * 40
SHOWN_COMMITS = 10
HOOK_MARKER = "nova-push-guard"
HOOK_SCRIPT = f"""#!/bin/sh
# {HOOK_MARKER}: installed by tools/repo_hygiene.py install-push-guard (remove: --uninstall).
# Refuses a push that adds commits to a merged PR's branch. Fails open: no tool, no Python,
# no gh, offline or any error lets the push through; only the guard's own "refuse" (1) stops it.
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
tool="$root/tools/repo_hygiene.py"
[ -f "$tool" ] || exit 0
if command -v py >/dev/null 2>&1; then
  py -3 "$tool" push-guard "$@"
elif command -v python3 >/dev/null 2>&1; then
  python3 "$tool" push-guard "$@"
else
  exit 0
fi
[ $? -eq 1 ] && exit 1
exit 0
"""

PrLookup = Callable[[str, "str | None"], "list[dict] | None"]


@dataclass(frozen=True)
class LatePush:
    """Commits on ``branch`` after its merged PR's head, oldest first."""

    pr: int
    url: str
    branch: str
    merged_head: str
    commits: list[tuple[str, str]] = field(default_factory=list)  # (sha, subject)


@dataclass(frozen=True)
class Verdict:
    late: LatePush | None = None
    unknown: str = ""  # non-empty: the check could not run, and why (the caller fails open)


# --- pure ---------------------------------------------------------------------

def merged_pr_for(prs: list[dict]) -> dict | None:
    """The newest merged PR of a branch, unless the branch has an open PR (that one will merge)."""
    if any(p.get("state") == "OPEN" for p in prs):
        return None
    merged = [p for p in prs if p.get("state") == "MERGED" and p.get("headRefOid")]
    return max(merged, key=lambda p: int(p.get("number") or 0)) if merged else None


def parse_pre_push(stdin: str) -> list[tuple[str, str]]:
    """git's pre-push lines -> (branch, local sha) for every branch push that is not a delete."""
    out: list[tuple[str, str]] = []
    for line in stdin.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        _local_ref, local_sha, remote_ref, _remote_sha = parts
        if local_sha == ZERO_SHA or not remote_ref.startswith("refs/heads/"):
            continue
        out.append((remote_ref[len("refs/heads/"):], local_sha))
    return out


def refusal(late: LatePush, *, pushed: bool) -> str:
    """Plain words: what happened and the three steps that land the commits."""
    n = len(late.commits)
    listed = "; ".join(f"{sha[:10]} {subject}" for sha, subject in late.commits[:SHOWN_COMMITS])
    if n > SHOWN_COMMITS:
        listed += f"; ... {n - SHOWN_COMMITS} more"
    shas = " ".join(sha[:12] for sha, _ in late.commits)
    head = (f"PR #{late.pr} ({late.url}) is already merged, at {late.merged_head[:10]}. "
            f"Branch '{late.branch}' has {n} commit(s) after it: {listed}.")
    steps = (f"Branch from origin/master, cherry-pick the commits, open a new PR: "
             f"git fetch origin && git switch -c <new-branch> origin/master && "
             f"git cherry-pick -x {shas} && git push -u origin HEAD && gh pr create.")
    if pushed:
        return (f"{head} They are pushed, but no open PR carries them, so they never reach master. "
                f"The Stranded commits workflow opens recover/{late.branch} for them within the hour "
                f"(gh pr list --head recover/{late.branch}); if it has not, land them yourself. {steps} "
                f"(-x leaves the trailer that marks them handled.)")
    return (f"{head} Do not push them here: nothing merges a merged PR's branch again. {steps} "
            f"(-x leaves the trailer that marks them handled.)")


# --- gather -------------------------------------------------------------------

def _git(args: list[str], cwd: str | None = None, timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def gh_prs(branch: str, cwd: str | None = None) -> list[dict] | None:
    """Every PR with ``branch`` as its head; None when gh is missing, offline or unauthenticated."""
    try:
        res = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--state", "all", "--limit", "30",
             "--json", "number,state,headRefOid,url"],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=GH_TIMEOUT_SEC)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode:
        return None
    try:
        rows = json.loads(res.stdout or "[]")
    except ValueError:
        return None
    return rows if isinstance(rows, list) else None


def _have_commit(sha: str, cwd: str | None) -> bool:
    return _git(["cat-file", "-e", f"{sha}^{{commit}}"], cwd).returncode == 0


def check(branch: str, tip: str, *, cwd: str | None = None, lookup: PrLookup = gh_prs) -> Verdict:
    """Does ``tip`` add commits to ``branch`` after its PR merged? Never raises."""
    if not branch or branch in PROTECTED:
        return Verdict()
    try:
        prs = lookup(branch, cwd)
        if prs is None:
            return Verdict(unknown="gh is unavailable or offline, so the PR state could not be read")
        pr = merged_pr_for(prs)
        if pr is None:
            return Verdict()
        merged = str(pr["headRefOid"])
        if not _have_commit(merged, cwd):
            # The branch may be deleted on origin; the PR ref keeps the merged head fetchable.
            _git(["fetch", "--quiet", "origin", f"refs/pull/{pr['number']}/head"], cwd,
                 timeout=GIT_FETCH_TIMEOUT_SEC)
            if not _have_commit(merged, cwd):
                return Verdict(unknown=f"PR #{pr['number']} is merged but its head {merged[:10]} "
                                       "is not in this clone and could not be fetched")
        exclude = [f"^{merged}"]
        if _git(["rev-parse", "--verify", "--quiet", "origin/master"], cwd).returncode == 0:
            exclude.append("^origin/master")
        res = _git(["log", "--reverse", "--no-merges", "--format=%H%x09%s", tip, *exclude], cwd)
        if res.returncode:
            return Verdict(unknown=f"git could not compare {tip[:10]} with the merged head")
        commits = [tuple(line.split("\t", 1)) for line in res.stdout.splitlines() if "\t" in line]
        if not commits:
            return Verdict()
        return Verdict(late=LatePush(pr=int(pr["number"]), url=str(pr.get("url") or ""),
                                     branch=branch, merged_head=merged, commits=commits))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        return Verdict(unknown=f"the check failed ({type(exc).__name__})")


# --- the pre-push hook ----------------------------------------------------------

def run_pre_push(stdin: str, *, cwd: str | None = None, lookup: PrLookup = gh_prs,
                 err: Callable[[str], None] = print) -> int:
    """0 = push, 1 = refuse. Every branch in the push is checked; unknowns are said, never blocking."""
    refused = False
    for branch, sha in parse_pre_push(stdin):
        verdict = check(branch, sha, cwd=cwd, lookup=lookup)
        if verdict.late:
            refused = True
            err(f"push-guard: refused. {refusal(verdict.late, pushed=False)}")
        elif verdict.unknown:
            err(f"push-guard: could not check '{branch}' ({verdict.unknown}); pushing anyway.")
    return 1 if refused else 0


def hooks_dir(cwd: str | None = None) -> Path:
    """Where git looks for hooks here (honours core.hooksPath)."""
    raw = _git(["rev-parse", "--git-path", "hooks"], cwd).stdout.strip()
    path = Path(raw)
    return path if path.is_absolute() else Path(cwd or os.getcwd()) / path


def install(cwd: str | None = None, *, uninstall: bool = False) -> tuple[int, str]:
    """Write (or remove) the pre-push hook. Never overwrites a hook it did not write."""
    target = hooks_dir(cwd) / "pre-push"
    ours = target.is_file() and HOOK_MARKER in target.read_text(encoding="utf-8", errors="replace")
    if uninstall:
        if not ours:
            return 0, f"push-guard: no Nova pre-push hook at {target}; nothing removed"
        target.unlink()
        return 0, f"push-guard: removed {target}"
    if target.exists() and not ours:
        return 2, (f"push-guard: {target} already holds another pre-push hook; not overwritten. "
                   "Merge it by hand or remove it first.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(HOOK_SCRIPT, encoding="utf-8", newline="\n")
    target.chmod(0o755)
    custom = _git(["config", "core.hooksPath"], cwd).stdout.strip()
    where = f" (core.hooksPath = {custom})" if custom else ""
    return 0, f"push-guard: installed {target}{where}"
