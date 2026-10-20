"""The checks a PR's head must pass before Actions merges it (operator decision 2026-10-13).

"Merge only green PRs too." Every automated merge path -- CI's Auto-merge job,
the CI-completion and hourly sweeps, a manual dispatch -- goes through
``pr_delivery.decide()``, which reads this verdict on the PR's head commit.
Backend tests, Frontend build, Frontend E2E and Agent contract (the four a
Release waits for, ``release_gate.REQUIRED_CHECKS``, one list) must each have
concluded ``success`` at its newest run, so a green re-run counts.

* Not reported yet, queued or running: WAIT. Auto-merge itself starts only once
  the four have finished, and a sweep decides again when CI completes.
* Failed, cancelled, timed out or skipped: BLOCK. The PR gets one comment per
  head naming the check, and the job summary says it too. A green re-run of the
  failed jobs re-runs Auto-merge, which then merges.

Change-aware scope never skips one of the four at GitHub's level. Each job runs
with ``if: always()`` and, when the diff does not need it, its "Verify scope
decision" step says "Unaffected" and the job concludes ``success``
(docs/ci.md). So a docs-only PR is green and merges; a ``skipped`` conclusion
means the job never ran, and holds.

Only GitHub Actions' own check runs count: a check another app reports under the
same name never stands in for CI. Unreadable checks are not green ones.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    from tools.release_gate import REQUIRED_CHECKS, check_states, documents, load_jobs
except ImportError:  # `python tools/pr_delivery.py` puts tools/ on sys.path
    from release_gate import REQUIRED_CHECKS, check_states, documents, load_jobs

GhFn = Callable[..., Any]
ACTIONS_APP = "github-actions"
CHECKS_RED = "checks_red"
CHECKS_PENDING = "checks_pending"
HELD_COMMENT_MARKER = "<!-- nova-merge-held -->"
SHORT_SHA = 7


def fetch_head_checks(gh: GhFn, repo: str, sha: str) -> list[dict[str, Any]]:
    """Every check run on ``sha``, every attempt (``filter=all``); the verdict takes the newest."""
    if not sha:
        raise ValueError("the PR has no head commit")
    proc = gh(
        ["api", "--paginate", f"repos/{repo}/commits/{sha}/check-runs?filter=all&per_page=100"],
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError(proc.stderr or proc.stdout or f"check runs of {sha} are unreadable")
    runs = load_jobs(proc.stdout, key="check_runs")
    return [run for run in runs
            if str((run.get("app") or {}).get("slug") or ACTIONS_APP) == ACTIONS_APP]


def merge_verdict(runs: list[dict[str, Any]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """``(red, pending)``: checks that need a re-run or a fix, and checks that may still pass."""
    states = check_states(runs, {check: [check] for check in REQUIRED_CHECKS})
    red = [(check, state) for check, state, finished in states if finished]
    pending = [(check, state) for check, state, finished in states if not finished]
    return red, pending


def describe(held: list[tuple[str, str]]) -> str:
    return "; ".join(f"{check} {state}" for check, state in held)


def held_comment(sha: str, red: list[tuple[str, str]]) -> str:
    return (
        f"**Not merged: {describe(red)}** on `{sha[:SHORT_SHA]}`.\n\n"
        f"Actions merges a PR only when {', '.join(REQUIRED_CHECKS[:-1])} and "
        f"{REQUIRED_CHECKS[-1]} all pass on its head (operator decision 2026-10-13), "
        "and only when `aaltaay` added `merge-approved`. Agents never add that label. "
        "Re-run the failed jobs or push a fix. A draft or the `do-not-merge` label still holds it.\n\n"
        f"{HELD_COMMENT_MARKER}<!-- head={sha} -->"
    )


def signal_checks_held(gh: GhFn, repo: str, number: int, sha: str,
                       red: list[tuple[str, str]]) -> None:
    """One comment per head and verdict: a sweep that finds the same red PR stays quiet."""
    body = held_comment(sha, red)
    listed = gh(["api", "--paginate", f"repos/{repo}/issues/{number}/comments?per_page=100"],
                check=False)
    bodies: list[str] = []
    if listed.returncode == 0:
        try:
            for page in documents(listed.stdout):
                bodies += [str(c.get("body") or "") for c in page if isinstance(c, dict)]
        except (ValueError, TypeError) as exc:
            print(f"#{number} comments unreadable ({exc}); posting the hold", file=sys.stderr)
    if any(existing.strip() == body.strip() for existing in bodies):
        print(f"#{number} hold comment already present")
        return
    posted = gh(["pr", "comment", str(number), "--body", body], check=False)
    if posted.returncode != 0:
        print(posted.stderr or posted.stdout or f"hold comment #{number} failed", file=sys.stderr)
        return
    print(f"#{number} hold comment posted")


def write_summary(line: str) -> None:
    """The decision on the job's summary page, so a held PR never holds in silence."""
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(line.rstrip("\n") + "\n\n")


def summary_line(number: int, action: str, reason: str, sha: str = "") -> str:
    head = f" (head `{sha[:SHORT_SHA]}`)" if sha else ""
    return f"- #{number}{head}: **{action}** -- {reason}"

