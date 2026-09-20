"""Is an automated code review still running on this pull request head?

Delivery merges without waiting for CI on purpose (AGENTS.md §5: verification
is advisory). A review is different from a check: it reports defects in the
diff rather than a pass/fail on the build, and merging out from under one
means its findings land on `master` and need a whole follow-up PR instead of
a push to the open branch. Twice in one session a review posted correct
findings within four minutes of an auto-merge.

So delivery waits for a review that is *in flight* -- and only for that. It
does not wait on, or block for, what the review concluded; that stays advisory
like everything else.

The signal is the reviewer's own summary comment, which is untrusted external
text written by a bot. It is only ever matched, never executed, and anything
unrecognised reads as "not running" so a reviewer that changes its format,
breaks, or goes away can never wedge delivery shut.
"""

from __future__ import annotations

from collections.abc import Iterable

# The marker the reviewer hides in its summary comment so it can edit that
# comment in place rather than posting a new one per run.
REVIEW_SUMMARY_MARKERS = ("codex-pull-request-review-summary",)

# The summary is a table; a row reads
#   | 📝 **Code Review** | 🔄 **Running** since <time/> | `747985a` | ... |
RUNNING_MARKER = "**Running**"

SHORT_SHA_LEN = 7


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
