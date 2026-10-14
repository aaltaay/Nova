#!/usr/bin/env python3
"""Land commits pushed to a PR's branch after Actions merged it (operator report 2026-10-14).

Actions squash-merges a ready PR the moment its checks are green (``pr_delivery.py``). An agent still
answering a review pushes its fix to the same branch a few minutes later; the PR is already merged, so
nothing opens, nothing merges, and the fix never reaches master or a Release. Branch cleanup keeps such
a tip (#369), which is why the work survived at all. On 2026-10-14 seven fixes sat stranded that way
behind PRs #868 to #951 while the operator asked why "9 out of 10 tasks" were not on the desk.

``sweep`` finds every PR merged in the last ``--days`` whose branch still exists on origin with commits
after the merged head, and for each one:

- an open PR on that branch: nothing to do, it will merge on its own;
- otherwise the commits after the merged head (or after the last tip already carried) are cherry-picked
  onto ``recover/<branch>`` from master and opened as a ready PR, so the green-only merge path lands
  them like any other PR. An open recovery PR for the branch gets the new commits instead of a second
  PR. A PR opened with ``GITHUB_TOKEN`` starts no CI run, so CI is dispatched on the recovery branch;
- commits already on master (redone by a later PR) are dropped; nothing left means nothing to land;
- a conflict, or a branch rewritten past its merged head, opens a P1 issue naming the commits instead.

Every action leaves ``stranded-tip: <sha>`` in a body, so a sweep never carries the same tip twice. A person who
lands or retires stranded commits by hand writes the same marker in their PR body (a squash merge keeps it on
master), and ``git cherry-pick -x``'s trailer counts too.

Usage (the `Stranded commits` workflow, on a push to any branch but master, and hourly):
  python3 tools/stranded_commits.py sweep [--branch <name>] [--days 3] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.backlog_github import INBOX_TITLE  # noqa: E402
from tools.release_held import board  # noqa: E402

BASE = "master"
RECOVER_PREFIX = "recover/"
TIP_MARKER = "stranded-tip:"
ISSUE_PREFIX = "Commits pushed after"
LABELS: tuple[str, ...] = ("deferred", "bug", "P1", "domain:ci")
CI_WORKFLOW = "deploy.yml"
PROTECTED = frozenset({"master", "main", "HEAD"})

Runner = Callable[[list[str]], str]
# A GITHUB_TOKEN PR or issue starts no board workflow, so the item goes on Nova Delivery with
# NOVA_PROJECT_TOKEN here (release_held.board; a missing token is a notice, the item stays filed).
Boarder = Callable[[str], None]


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, capture_output=True, text=True, encoding="utf-8", errors="replace")


def gh(args: list[str]) -> str:
    return _run(["gh", *args]).stdout


def git(args: list[str]) -> str:
    return _run(["git", *args]).stdout


@dataclass(frozen=True)
class Merged:
    number: int
    title: str
    branch: str
    head: str


@dataclass(frozen=True)
class Plan:
    """What to do with one merged PR's branch: ``action`` is skip, land, extend or issue."""

    action: str
    reason: str
    base: str = ""


def recorded_tips(bodies: list[str]) -> set[str]:
    """Tips a body says are carried: a ``stranded-tip:`` marker, or ``git cherry-pick -x``'s trailer."""
    found = re.compile(r"(?:" + re.escape(TIP_MARKER) + r"|cherry picked from commit)\s*([0-9a-f]{40})")
    return {m.group(1) for body in bodies for m in found.finditer(body)}


def master_bodies(days: int | None) -> list[str]:
    """Master's commit messages since the window (all of them for None): a squash merge keeps its PR's body."""
    window = []
    if days is not None:
        window = [f"--since={(datetime.now(timezone.utc) - timedelta(days=days + 1)).strftime('%Y-%m-%d')}"]
    return git(["log", f"origin/{BASE}", *window, "--format=%B%x00"]).split("\0")


def plan(pr: Merged, tip: str, *, open_pr: bool, open_recovery: bool, carried: set[str],
         is_ancestor: Callable[[str, str], bool]) -> Plan:
    """Decide from facts only; ``is_ancestor(a, b)`` is True when ``a`` is in ``b``'s history."""
    if not tip or tip == pr.head:
        return Plan("skip", "no commits after the merge")
    if open_pr:
        return Plan("skip", "an open PR carries the branch")
    if tip in carried:
        return Plan("skip", "this tip is already carried")
    if not is_ancestor(pr.head, tip):
        return Plan("issue", "the branch was rewritten past its merged head")
    done = [t for t in carried if t != tip and is_ancestor(t, tip)]
    # The newest tip already carried: its commits are on master or in the open recovery PR.
    base = max(done, key=lambda t: sum(is_ancestor(o, t) for o in done)) if done else pr.head
    return Plan("extend" if open_recovery else "land", "commits after the merge", base)


def merged_prs(runner: Runner, days: int, branch: str = "") -> list[Merged]:
    """PRs merged in the last ``days``; for one ``branch``, every merged PR on it however old (PR #957 review:
    a push to a branch whose PR merged a week ago must still be carried)."""
    args = ["pr", "list", "--state", "merged", "--limit", "200",
            "--json", "number,title,headRefName,headRefOid,isCrossRepository"]
    if branch:
        args += ["--head", branch]
    else:
        args += ["--search", f"merged:>={(datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%d')}"]
    rows = json.loads(runner(args) or "[]")
    out = [Merged(int(r["number"]), str(r.get("title") or ""), str(r["headRefName"]), str(r["headRefOid"]))
           for r in rows if not r.get("isCrossRepository")]
    return [m for m in out if m.branch not in PROTECTED and not m.branch.startswith(RECOVER_PREFIX)]


def _prs_on(runner: Runner, head: str, state: str) -> list[dict]:
    return json.loads(runner(["pr", "list", "--head", head, "--state", state, "--json", "number,body,url"]) or "[]")


def _issues_about(runner: Runner, number: int) -> list[dict]:
    query = f'"{ISSUE_PREFIX} #{number} merged" in:title'
    return json.loads(runner(["issue", "list", "--state", "all", "--search", query, "--json", "number,body"]) or "[]")


def recovery_branch(branch: str) -> str:
    return RECOVER_PREFIX + branch


def recovery_title(pr: Merged) -> str:
    kind = re.match(r"^([a-z]+(?:\([^)]*\))?)!?:", pr.title)
    return f"{kind.group(1) if kind else 'fix'}: land the commits pushed after #{pr.number} merged"


def pick(commits: list[str]) -> str:
    """Cherry-pick onto HEAD, dropping any already on it; "" on success, else the commit that conflicted."""
    for sha in commits:
        result = _run(["git", "cherry-pick", "-x", sha], check=False)
        if result.returncode == 0:
            continue
        if not git(["ls-files", "-u"]).strip() and not git(["diff", "--cached", "--name-only"]).strip():
            git(["cherry-pick", "--skip"])  # already on master: a later PR redid it
            continue
        _run(["git", "cherry-pick", "--abort"], check=False)
        return sha
    return ""


def _body(pr: Merged, tip: str, commits: list[str], lines: list[str]) -> str:
    listed = [f"- `{c[:12]}` {git(['log', '-1', '--format=%s', c]).strip()}" for c in commits]
    return "\n".join([
        f"These commits were pushed to `{pr.branch}` after Actions merged #{pr.number}, so they never reached "
        f"`{BASE}` or a Release (`tools/stranded_commits.py`).", "", *listed, "", *lines, "",
        f"<!-- {TIP_MARKER} {tip} -->",
    ]) + "\n"


def land(pr: Merged, tip: str, p: Plan, *, runner: Runner, dry_run: bool, boarder: Boarder = board) -> str:
    commits = [c for c in git(["rev-list", "--reverse", "--no-merges", f"{p.base}..{tip}"]).split() if c]
    target = recovery_branch(pr.branch)
    start = f"origin/{target}" if p.action == "extend" else f"origin/{BASE}"
    if dry_run:
        return f"would {p.action} {len(commits)} commit(s) of {pr.branch} onto {target}"
    git(["checkout", "-q", "-B", target, start])
    before = git(["rev-parse", "HEAD"]).strip()
    conflict = pick(commits)
    if conflict:
        return report_issue(pr, tip, commits, f"`{conflict[:12]}` does not apply to `{start}`",
                            runner=runner, boarder=boarder)
    if git(["rev-parse", "HEAD"]).strip() == before:
        return f"#{pr.number}: every commit after the merge is already on {BASE}"
    # A recovery branch with no open PR is the sweep's own leftover (a refused PR): it is rebuilt from master.
    force = [] if p.action == "extend" else ["--force"]
    git(["push", "-q", *force, "origin", f"HEAD:refs/heads/{target}"])
    if p.action == "extend":
        existing = _prs_on(runner, target, "open")[0]
        runner(["pr", "comment", str(existing["number"]), "--body", _body(pr, tip, commits, ["Added to this PR."])])
        url = str(existing["url"])
    else:
        try:
            url = runner(["pr", "create", "--base", BASE, "--head", target, "--title", recovery_title(pr),
                          "--body", _body(pr, tip, commits, [
                              "## What", f"Lands the follow-up commits of #{pr.number} on `{BASE}`.", "",
                              "## Verified by", "CI, dispatched on this branch; it merges only when green."])]).strip()
        except subprocess.CalledProcessError as exc:
            # 2026-10-14: the repository did not allow Actions to open PRs, and the refusal was only a red run.
            return report_issue(pr, tip, commits, refused_why(target, exc), runner=runner, boarder=boarder)
        runner(["pr", "comment", str(pr.number), "--body",
                f"Commits pushed here after this PR merged never reached `{BASE}`; {url} lands them."])
        boarder(url)
    runner(["workflow", "run", CI_WORKFLOW, "--ref", target])
    return f"#{pr.number}: {p.action} {len(commits)} commit(s) -> {url}"


def refused_why(target: str, exc: subprocess.CalledProcessError) -> str:
    repo = os.environ.get("GITHUB_REPOSITORY") or "aaltaay/Nova"
    said = " ".join(str(exc.stderr or exc).split())[:300]
    return (f"GitHub refused to let Actions open the recovery PR ({said}). The commits are already on "
            f"`{target}`: open the PR from https://github.com/{repo}/compare/{BASE}...{target}?expand=1 , or allow "
            "Actions to create pull requests (Settings > Actions > General > Workflow permissions)")


def report_issue(pr: Merged, tip: str, commits: list[str], why: str, *, runner: Runner,
                 boarder: Boarder = board) -> str:
    title = f"{ISSUE_PREFIX} #{pr.number} merged did not land ({pr.branch} @ {tip[:7]})"
    text = _body(pr, tip, commits, [
        f"They could not be carried automatically: {why}.", "",
        f"**Next:** branch from `origin/{BASE}`, cherry-pick them, resolve, and open a PR -- or close this issue "
        "if a later PR already did the same work."])
    labels = [arg for label in LABELS for arg in ("--label", label)]
    url = runner(["issue", "create", "--title", title, "--body", text, *labels, "--milestone", INBOX_TITLE]).strip()
    boarder(url)
    return f"#{pr.number}: {why} -> {url}"


def _is_ancestor(a: str, b: str) -> bool:
    return _run(["git", "merge-base", "--is-ancestor", a, b], check=False).returncode == 0


def sweep(*, days: int, branch: str, dry_run: bool, runner: Runner = gh) -> int:
    heads = {}
    for line in git(["ls-remote", "--heads", "origin"]).splitlines():
        sha, _, ref = line.partition("\trefs/heads/")
        heads[ref] = sha
    errors = 0
    seen: set[str] = set()
    on_master = master_bodies(None if branch else days)
    for pr in merged_prs(runner, days, branch):
        tip = heads.get(pr.branch, "")
        if not tip or tip == pr.head or pr.branch in seen:
            continue
        seen.add(pr.branch)  # newest merged PR on a reused name decides (gh lists newest first)
        try:
            git(["fetch", "-q", "origin", f"refs/pull/{pr.number}/head", f"refs/heads/{pr.branch}"])
            target = recovery_branch(pr.branch)
            recoveries = _prs_on(runner, target, "all")
            bodies = [str(r.get("body") or "") for r in recoveries + _issues_about(runner, pr.number)]
            open_recovery = bool(_prs_on(runner, target, "open"))
            if open_recovery:
                git(["fetch", "-q", "origin", f"refs/heads/{target}:refs/remotes/origin/{target}"])
            p = plan(pr, tip, open_pr=bool(_prs_on(runner, pr.branch, "open")), open_recovery=open_recovery,
                     carried=recorded_tips(bodies + on_master), is_ancestor=_is_ancestor)
            if p.action == "skip":
                print(f"#{pr.number} {pr.branch}: {p.reason}")
            elif p.action == "issue":
                print(f"would open an issue for #{pr.number}" if dry_run
                      else report_issue(pr, tip, [tip], p.reason, runner=runner))
            else:
                print(land(pr, tip, p, runner=runner, dry_run=dry_run))
        except subprocess.CalledProcessError as exc:
            errors += 1
            print(f"::error::#{pr.number} {pr.branch}: {exc.stderr or exc}", file=sys.stderr)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sweep")
    s.add_argument("--days", type=int, default=3)
    s.add_argument("--branch", default="")
    s.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return sweep(days=args.days, branch=args.branch, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
