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

# A reviewer announces itself a few seconds after the trigger -- 6s, 9s and
# 11s on the three PRs measured. The merge job reads comments faster than
# that, so without a pause the gate inspects an empty list and merges anyway,
# which is what happened on #403 and #405. Four times the slowest observed
# announcement, spent only by a PR that is otherwise about to merge.
ANNOUNCE_GRACE_SECONDS = 45
ANNOUNCE_POLL_SECONDS = 5


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


def await_review_announcement(
    look, *, seconds: int = ANNOUNCE_GRACE_SECONDS,
    poll: int = ANNOUNCE_POLL_SECONDS, sleep=None, clock=None,
) -> bool:
    """Give a reviewer time to announce itself. True if one did.

    ``look`` returns True when a review is in flight; it is re-asked until it
    does or the window closes, so a reviewer that speaks at 6s costs 6s, not
    the whole window. The window is a floor on how long a merge can take, not
    a ceiling on the review: announcing is what defers the merge, and the next
    sweep is what eventually makes it.

    Bounded by construction -- a reviewer that never announces, because none
    is configured or it is down, costs one window and then delivery proceeds.
    """
    import time as _time
    now = clock or _time.monotonic
    rest = sleep or _time.sleep
    deadline = now() + max(0, seconds)
    while True:
        if look():
            return True
        if now() >= deadline:
            return False
        rest(max(1, poll))
