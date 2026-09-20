"""Is this pull request ready to be merged *yet*?

Delivery merges without waiting for CI on purpose (AGENTS.md §5: verification
is advisory). A review is different from a check: it reports defects in the
diff rather than a pass/fail on the build, and merging out from under one
means its findings land on `master` and need a whole follow-up PR instead of
a push to the open branch. In one session that happened six times.

Two gates, both inside `decide()` so that every path -- the merge job, the
scheduled sweep, a manual dispatch -- gets the same answer:

1. A head younger than ``MIN_PR_AGE_SECONDS`` waits -- the newest commit,
   not the PR's opening, so a push restarts the floor. Reviews took two to
   four minutes on every PR measured; the floor gives one time to exist. This is
   what closes the announcement race: a merge job that reads comments before
   the reviewer has posted sees nothing to wait for, and a sweep that fires
   seconds after a PR opens sees the same. Age needs no reviewer at all.
2. A review that is *in flight* on the current head waits. This is the
   backstop for a review slower than the floor.

Neither gate looks at what a review concluded. Findings stay advisory like
every other signal; only their timing changes. ``--min-age-seconds 0``
restores instant merge.

The review signal is the reviewer's own summary comment: untrusted external
text written by a bot. It is only ever matched, never executed, and anything
unrecognised reads as "not running" so a reviewer that changes its format,
breaks, or goes away can never wedge delivery shut. Age fails open the same
way: an unreadable timestamp is not a reason to hold a PR.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

# Every review measured this session finished within four minutes of the PR
# opening (2:02, 2:07, 2:20, 3:57). Five gives one time to exist; the
# in-flight gate covers the slower ones. The cost is a five-minute floor on
# how fast a PR can merge, paid by every PR, and it is a floor on *review*
# having a chance, not on any check passing.
MIN_PR_AGE_SECONDS = 300

# The marker the reviewer hides in its summary comment so it can edit that
# comment in place rather than posting a new one per run.
REVIEW_SUMMARY_MARKERS = ("codex-pull-request-review-summary",)

# The summary is a table; a row reads
#   | 📝 **Code Review** | 🔄 **Running** since <time/> | `747985a` | ... |
RUNNING_MARKER = "**Running**"

SHORT_SHA_LEN = 7


def pr_age_seconds(created_at: str, *, now: datetime | None = None) -> float | None:
    """Seconds since the PR opened, or None when GitHub's stamp is unreadable.

    None rather than 0 or infinity: the caller treats an unknown age as
    "no reason to hold", because a parse failure must never stop delivery.
    """
    stamp = str(created_at or "").strip()
    if not stamp:
        return None
    try:
        opened = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return (current - opened).total_seconds()


def head_age_seconds(pr: dict, *, now: datetime | None = None) -> float | None:
    """Seconds since the CURRENT HEAD landed, never more than the PR's own age.

    The floor is about a review having a chance at the code being merged, and
    a push replaces that code. Measured from `createdAt` alone it protected
    only the first commit: any push to a PR older than the floor was eligible
    at once, before a review of the new head had started -- the same race,
    one push later. So the clock restarts at the newest commit.

    `committedDate` is when the commit was made, not when it was pushed; a
    commit made an hour ago and pushed now reads as old. The rule names that
    gap rather than hiding it. Missing or malformed commit data falls back to
    `createdAt`, and an unreadable `createdAt` to None -- never to "hold".
    """
    stamps = [str(pr.get("createdAt") or "")]
    for commit in pr.get("commits") or []:
        if isinstance(commit, dict):
            stamps.append(str(commit.get("committedDate") or ""))
    ages = [a for a in (pr_age_seconds(s, now=now) for s in stamps) if a is not None]
    return min(ages) if ages else None


def review_in_flight(pr: dict) -> bool:
    """`review_running` over a `gh pr view` payload."""
    return review_running(
        [str(c.get("body") or "") for c in (pr.get("comments") or [])],
        head_sha=str(pr.get("headRefOid") or ""),
    )


def too_young(age_seconds: float | None, *, min_age: int = MIN_PR_AGE_SECONDS) -> bool:
    """True while a PR has not yet lived long enough for a review to exist."""
    if age_seconds is None or min_age <= 0:
        return False
    return age_seconds < min_age


def review_running(comment_bodies: Iterable[str], *, head_sha: str) -> bool:
    """True only while a review is running against ``head_sha`` itself.

    Scoping to the exact head matters: a review of a superseded commit says
    nothing about the code being merged, and treating it as in flight would
    hold a PR forever on a branch that has since been pushed.
    """
    short = str(head_sha or "")[:SHORT_SHA_LEN]
    if not short:
        return False
    for body in comment_bodies:
        text = str(body or "")
        if not any(marker in text for marker in REVIEW_SUMMARY_MARKERS):
            continue
        for line in text.splitlines():
            if RUNNING_MARKER in line and f"`{short}" in line:
                return True
    return False
