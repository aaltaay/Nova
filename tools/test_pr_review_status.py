"""Delivery waits for an in-flight review, and for nothing else about it.

Twice in one session an automated review posted correct findings within four
minutes of an auto-merge, so the fixes needed follow-up PRs instead of a push
to the still-open branch. These tests pin the narrow rule that prevents that:
a review RUNNING on the exact head defers the merge to the next sweep. What it
concluded stays advisory, and an unrecognised comment never holds a PR.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import pr_delivery
from tools.pr_delivery import ACTION_MERGE, ACTION_SKIP, ACTION_WAIT, decide
from tools.pr_review_status import review_running

HEAD = "747985ab944b60dc68b0ac1e2181a71d16dd81bd"
OTHER = "05e2db0b099360683c00673748f07d56ff0ae1c2"

# Captured verbatim from the reviewer's own summary comment on #396.
RUNNING = """<!-- codex-pull-request-review-summary -->

## Codex Review Summary

| Review | Status | Commit | Review trigger |
| --- | --- | --- | --- |
| \U0001f4dd **Code Review** | \U0001f504 **Running** since <relative-time datetime="2026-09-20T14:51:09Z">x</relative-time> | `747985a` | Draft marked ready |
"""

COMPLETED = RUNNING.replace(
    "\U0001f504 **Running** since", "✅ **Completed** ")


def _decide(**over):
    args = {
        "draft": False, "state": "OPEN", "mergeable_state": "clean",
        "labels": [], "head_ref": "claude/x", "same_repo": True, "checks": [],
    }
    args.update(over)
    return decide(**args)


# --------------------------------------------------------------------------
# the detector


def test_a_review_running_on_this_head_is_in_flight():
    assert review_running([RUNNING], head_sha=HEAD) is True


def test_a_finished_review_is_not_in_flight():
    assert review_running([COMPLETED], head_sha=HEAD) is False


def test_a_review_of_a_superseded_commit_is_not_in_flight():
    # The branch was pushed after that review started. Holding the PR on it
    # would wait forever for a verdict on code nobody is merging.
    assert review_running([RUNNING], head_sha=OTHER) is False


def test_ordinary_comments_are_not_reviews():
    assert review_running(
        ["Deployment has completed", "LGTM, **Running** the tests locally"],
        head_sha=HEAD) is False


def test_nothing_recognisable_never_holds_a_pr():
    # Fail-open is deliberate: the signal is a bot's markdown, so a format
    # change or an outage must not wedge delivery shut.
    for bodies in ([], [""], [None], ["<!-- codex-pull-request-review-summary -->"],
                   ["garbage"], ["<!-- codex-pull-request-review-summary -->\n| ?? |"]):
        assert review_running(bodies, head_sha=HEAD) is False


def test_an_unknown_head_never_holds_a_pr():
    assert review_running([RUNNING], head_sha="") is False


# --------------------------------------------------------------------------
# the decision


def test_a_running_review_defers_the_merge():
    result = _decide(review_in_flight=True)
    assert result.action == ACTION_WAIT
    assert result.reason == "review_running"


def test_no_running_review_merges_as_before():
    assert _decide(review_in_flight=False).action == ACTION_MERGE


def test_waiting_is_not_blocking():
    # WAIT, so the next sweep merges it -- and CI completing fires one, which
    # lands well after a review of the same push. BLOCK would strand the PR.
    assert _decide(review_in_flight=True).action != "block"


def test_a_held_pr_does_not_wait_on_a_review_first():
    # No point deferring a merge that is never going to happen; the reason a
    # human reads should name the real hold.
    for over in ({"draft": True}, {"labels": [{"name": "do-not-merge"}]},
                 {"same_repo": False}):
        result = _decide(review_in_flight=True, **over)
        assert result.action == ACTION_SKIP
        assert result.reason != "review_running"
    conflicted = _decide(review_in_flight=True, mergeable_state="dirty")
    assert conflicted.reason == "conflict"


def test_the_pr_query_asks_for_what_the_gate_needs(monkeypatch):
    # Losing `comments` or `headRefOid` from the query would silently return
    # delivery to merging out from under every review.
    seen: list[list[str]] = []

    def fake_gh(args, check=True, stdin=None):
        seen.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    monkeypatch.setattr(pr_delivery, "_gh", fake_gh)
    pr_delivery._fetch_pr(396)
    fields = seen[0][seen[0].index("--json") + 1]
    assert "comments" in fields and "headRefOid" in fields
