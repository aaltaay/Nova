"""Delivery waits for a review to have a chance to exist, and for nothing
else about it.

Twice in one session an automated review posted correct findings within four
minutes of an auto-merge, so the fixes needed follow-up PRs instead of a push
to the still-open branch. These tests pin the narrow rule that prevents that:
a review RUNNING on the exact head defers the merge to the next sweep. What it
concluded stays advisory, and an unrecognised comment never holds a PR.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import pr_delivery
from tools.pr_delivery import ACTION_MERGE, ACTION_SKIP, ACTION_WAIT, decide
from tools.pr_review_status import (
    MIN_PR_AGE_SECONDS,
    REVIEW_STALE_SECONDS,
    head_age_seconds,
    pr_age_seconds,
    review_ages,
    review_in_flight,
    review_running,
    stale_review_note,
    too_young,
)

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

STARTED = datetime(2026, 9, 20, 14, 51, 9, tzinfo=timezone.utc)
# Two minutes into the review above: the moment the in-flight gate exists for.
WHILE_RUNNING = STARTED + timedelta(minutes=2)


def running_since(stamp: str) -> str:
    """The captured summary with its "Running since" stamp replaced."""
    return RUNNING.replace("2026-09-20T14:51:09Z", stamp)


def _green() -> list[dict]:
    """The four required checks passed: these tests are about timing, not checks."""
    from tools.release_gate import REQUIRED_CHECKS

    return [{"id": i, "name": name, "status": "completed", "conclusion": "success"}
            for i, name in enumerate(REQUIRED_CHECKS, start=1)]


def _decide(**over):
    args = {
        "draft": False, "state": "OPEN", "mergeable_state": "clean",
        "labels": [], "head_ref": "claude/x", "same_repo": True, "checks": _green(),
    }
    args.update(over)
    return decide(**args)


# --------------------------------------------------------------------------
# the detector


def test_a_review_running_on_this_head_is_in_flight():
    assert review_running([RUNNING], head_sha=HEAD, now=WHILE_RUNNING) is True


def test_a_finished_review_is_not_in_flight():
    assert review_running([COMPLETED], head_sha=HEAD, now=WHILE_RUNNING) is False


def test_a_review_of_a_superseded_commit_is_not_in_flight():
    # The branch was pushed after that review started. Holding the PR on it
    # would wait forever for a verdict on code nobody is merging.
    assert review_running([RUNNING], head_sha=OTHER, now=WHILE_RUNNING) is False


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
    assert review_running([RUNNING], head_sha="", now=WHILE_RUNNING) is False


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



# --------------------------------------------------------------------------
# the age floor
#
# The in-flight gate only sees a reviewer that has already spoken. A grace
# period in cmd_merge closed that on the merge job -- and the sweep, which
# never called it, merged #410 one second after the reviewer announced. The
# floor lives in decide(), so there is no path that does not pay it.


def test_a_pr_seconds_old_settles_first():
    result = _decide(age_seconds=23)          # #410: opened 15:44:41, merged 15:45:04
    assert result.action == ACTION_WAIT
    assert result.reason == "settling"


def test_a_pr_past_the_floor_merges():
    assert _decide(age_seconds=MIN_PR_AGE_SECONDS + 1).action == ACTION_MERGE


def test_an_unknown_age_never_holds_a_pr():
    # A missing or unparseable createdAt is not a reason to stop delivery.
    assert _decide(age_seconds=None).action == ACTION_MERGE
    assert too_young(None) is False


def test_a_zero_floor_restores_instant_merge():
    assert _decide(age_seconds=1, min_age_seconds=0).action == ACTION_MERGE
    assert too_young(1, min_age=0) is False


def test_a_held_pr_reports_its_own_reason_before_settling():
    for over in ({"draft": True}, {"labels": [{"name": "do-not-merge"}]},
                 {"same_repo": False}):
        result = _decide(age_seconds=1, **over)
        assert result.action == ACTION_SKIP and result.reason != "settling"
    assert _decide(age_seconds=1, mergeable_state="dirty").reason == "conflict"


def test_the_floor_covers_every_observed_review():
    # Measured this session: 2:02, 2:07, 2:20 and 3:57 from open to verdict.
    assert MIN_PR_AGE_SECONDS >= 4 * 60


def test_age_reads_githubs_timestamp():
    from datetime import datetime, timezone
    now = datetime(2026, 9, 20, 15, 45, 4, tzinfo=timezone.utc)
    assert pr_age_seconds("2026-09-20T15:44:41Z", now=now) == 23.0
    for bad in ("", None, "yesterday", "2026-13-45T99:99:99Z"):
        assert pr_age_seconds(bad, now=now) is None


# --------------------------------------------------------------------------
# both paths


def pr_payload(*, created_at, comments=(), draft=False, commits=()):
    return {
        "commits": [{"oid": HEAD, "committedDate": d} for d in commits],
        "number": 410, "title": "t", "body": "b", "isDraft": draft,
        "state": "OPEN", "mergeStateStatus": "CLEAN", "labels": [],
        "headRefName": "claude/x", "headRefOid": HEAD,
        "headRepository": {"name": "Nova"},
        "headRepositoryOwner": {"login": "aaltaay"},
        "comments": [{"body": b} for b in comments],
        "createdAt": created_at,
    }


def fresh():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def wire(monkeypatch, payload):
    merged = []
    monkeypatch.setattr(pr_delivery, "_fetch_pr", lambda n: (payload, _green()))
    monkeypatch.setattr(pr_delivery, "_merge_pr", lambda pr: merged.append(pr) or 0)
    monkeypatch.setattr(pr_delivery, "_signal_conflict", lambda n: None)
    monkeypatch.setattr(pr_delivery, "_gh", lambda *a, **k: subprocess.CompletedProcess(
        a, 0, stdout='[{"number": 410}]', stderr=""))
    return merged


def test_the_sweep_leaves_a_fresh_pr_alone(monkeypatch):
    # The regression that motivated the floor: cmd_sweep merged #410 within
    # the announcement race because the grace period lived only in cmd_merge.
    merged = wire(monkeypatch, pr_payload(created_at=fresh()))
    assert pr_delivery.cmd_sweep() == 0
    assert merged == []


def test_both_paths_merge_a_settled_pr(monkeypatch):
    merged = wire(monkeypatch, pr_payload(created_at="2026-01-01T00:00:00Z"))
    assert pr_delivery.cmd_sweep() == 0
    assert pr_delivery.cmd_merge(410, wait_desktop_minutes=0) == 0
    assert len(merged) == 2


def test_a_settled_pr_still_waits_on_a_running_review(monkeypatch):
    # The backstop for a review slower than the floor.
    merged = wire(monkeypatch, pr_payload(created_at="2026-01-01T00:00:00Z",
                                          comments=[running_since(fresh())]))
    assert pr_delivery.cmd_sweep() == 0
    assert merged == []


def test_the_pr_query_asks_for_the_age_of_the_head(monkeypatch):
    seen: list[list[str]] = []

    def fake_gh(args, check=True, stdin=None):
        seen.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    monkeypatch.setattr(pr_delivery, "_gh", fake_gh)
    pr_delivery._fetch_pr(410)
    fields = seen[0][seen[0].index("--json") + 1]
    assert "createdAt" in fields and "commits" in fields


# --------------------------------------------------------------------------
# the floor follows the head (review finding on #411, P1)
#
# Measured from createdAt the floor protected only the first commit: a push to
# a PR older than five minutes was eligible at once, before a review of the
# new head had started.

NOW = __import__("datetime").datetime(2026, 9, 20, 16, tzinfo=__import__("datetime").timezone.utc)


def test_a_push_restarts_the_floor():
    pr = pr_payload(created_at="2026-09-20T15:00:00Z", commits=["2026-09-20T15:59:50Z"])
    assert head_age_seconds(pr, now=NOW) == 10.0
    assert _decide(age_seconds=head_age_seconds(pr, now=NOW)).reason == "settling"


def test_an_old_pr_with_an_old_head_merges():
    pr = pr_payload(created_at="2026-09-20T15:00:00Z", commits=["2026-09-20T15:00:00Z"])
    assert _decide(age_seconds=head_age_seconds(pr, now=NOW)).action == ACTION_MERGE


def test_missing_commit_data_falls_back_to_the_prs_own_age():
    pr = pr_payload(created_at="2026-09-20T15:59:50Z")
    del pr["commits"]
    assert head_age_seconds(pr, now=NOW) == 10.0
    pr["commits"] = [{"oid": HEAD}, "garbage", None, {"committedDate": "nonsense"}]
    assert head_age_seconds(pr, now=NOW) == 10.0
    assert head_age_seconds({"createdAt": "", "commits": []}, now=NOW) is None


def test_review_in_flight_reads_a_pr_payload():
    assert review_in_flight(pr_payload(created_at="x", comments=[RUNNING]),
                            now=WHILE_RUNNING) is True
    assert review_in_flight(pr_payload(created_at="x", comments=[COMPLETED]),
                            now=WHILE_RUNNING) is False


# --------------------------------------------------------------------------
# the merge job waits the floor out (review finding on #411, P2)
#
# Nothing fires when the floor expires. Without this a PR whose CI finished
# inside five minutes sat until the hourly cron -- up to an hour for a gate
# meant to cost five minutes.


# Every cmd_merge call in this file goes through fake_clock: since the P2 fix
# the merge job sleeps out the settling floor with real time.sleep(20)s, so
# a fresh-PR test on the wall clock hangs for five minutes.
def fake_clock(monkeypatch, start=1000.0):
    clock = {"t": start}
    monkeypatch.setattr(pr_delivery.time, "time", lambda: clock["t"])
    monkeypatch.setattr(pr_delivery.time, "sleep",
                        lambda s: clock.__setitem__("t", clock["t"] + s))
    return clock


def test_the_merge_job_waits_out_the_floor_rather_than_the_cron(monkeypatch):
    clock = fake_clock(monkeypatch)
    # the head landed at t=1000; its age grows with the fake clock
    monkeypatch.setattr(pr_delivery, "head_age_seconds",
                        lambda pr, now=None: clock["t"] - 1000.0)
    merged = wire(monkeypatch, pr_payload(created_at="2026-09-20T15:59:50Z"))
    assert pr_delivery.cmd_merge(411, wait_desktop_minutes=0, min_age_seconds=60) == 0
    assert len(merged) == 1, "waited the floor out and merged in the same job"
    waited = clock["t"] - 1000.0
    assert 60 <= waited <= 60 + 25, waited


def test_the_settle_wait_is_capped_when_the_head_keeps_moving(monkeypatch):
    # A push on every poll resets the floor forever; the job must not pin a
    # runner forever with it.
    clock = fake_clock(monkeypatch)
    monkeypatch.setattr(pr_delivery, "head_age_seconds", lambda pr, now=None: 0.0)
    merged = wire(monkeypatch, pr_payload(created_at="2026-09-20T15:59:50Z"))
    assert pr_delivery.cmd_merge(411, wait_desktop_minutes=0, min_age_seconds=60) == 0
    assert merged == []
    assert clock["t"] - 1000.0 <= 2 * 60 + 25


def test_a_held_pr_does_not_wait_at_all(monkeypatch):
    clock = fake_clock(monkeypatch)
    merged = wire(monkeypatch, pr_payload(created_at=fresh(), draft=True))
    assert pr_delivery.cmd_merge(411, wait_desktop_minutes=0) == 0
    assert merged == [] and clock["t"] == 1000.0


# --------------------------------------------------------------------------
# a review stuck on "running" (#1140)
#
# On 2026-10-22 the reviewer's summary on #1140 read "Running since 05:30:17Z"
# for more than ten hours while every required check was green, and each sweep
# logged `#1140 wait review_running`. The module promises that a reviewer that
# breaks can never wedge delivery shut; a run that never finishes is one.

# Captured verbatim from the reviewer's summary row on #1140: note the
# fractional seconds in the stamp.
RUNNING_1140 = """<!-- codex-pull-request-review-summary -->

| Review | Status | Commit | Review trigger |
| --- | --- | --- | --- |
| 📝 **Code Review** | 🔄 **Running** since <relative-time datetime="2026-10-22T05:30:17.770448Z">2026-10-22T05:30:17.770448Z</relative-time> | `39d0e8a` | PR opened |
"""
HEAD_1140 = "39d0e8a3d86eed449fd48e3dc31dad8f250d7d1c"


def test_a_recent_running_review_still_waits():
    now = datetime(2026, 10, 22, 5, 33, tzinfo=timezone.utc)
    assert review_running([RUNNING_1140], head_sha=HEAD_1140, now=now) is True
    pr = pr_payload(created_at="2026-10-22T05:00:00Z", comments=[RUNNING_1140])
    pr["headRefOid"] = HEAD_1140
    assert _decide(review_in_flight=review_in_flight(pr, now=now)).reason == "review_running"
    assert stale_review_note(pr, now=now) == ""


def test_a_review_running_past_the_cap_merges():
    now = datetime(2026, 10, 22, 15, 18, tzinfo=timezone.utc)   # the symptom
    assert review_running([RUNNING_1140], head_sha=HEAD_1140, now=now) is False
    pr = pr_payload(created_at="2026-10-22T05:00:00Z", comments=[RUNNING_1140])
    pr["headRefOid"] = HEAD_1140
    assert _decide(review_in_flight=review_in_flight(pr, now=now)).action == ACTION_MERGE


def test_the_cap_is_measured_from_the_reviews_own_start():
    just_under = STARTED + timedelta(seconds=REVIEW_STALE_SECONDS - 1)
    at_cap = STARTED + timedelta(seconds=REVIEW_STALE_SECONDS)
    assert review_running([RUNNING], head_sha=HEAD, now=just_under) is True
    assert review_running([RUNNING], head_sha=HEAD, now=at_cap) is False


def test_the_cap_is_well_past_every_measured_review():
    # Reviews took 2-4 minutes; the cap is a broken reviewer, not a slow one,
    # and it must still clear before the next hourly sweep.
    assert 10 * 60 <= REVIEW_STALE_SECONDS <= 60 * 60


def test_an_unreadable_start_time_never_holds_a_pr():
    for since in ("", "yesterday", "2026-13-45T99:99:99Z"):
        assert review_running([running_since(since)], head_sha=HEAD,
                              now=WHILE_RUNNING) is False
    no_stamp = RUNNING.replace('<relative-time datetime="2026-09-20T14:51:09Z">x</relative-time>', "")
    assert review_ages([no_stamp], head_sha=HEAD, now=WHILE_RUNNING) == [None]
    assert review_running([no_stamp], head_sha=HEAD, now=WHILE_RUNNING) is False


def test_a_stuck_run_on_another_head_is_ignored_as_before():
    now = datetime(2026, 10, 22, 5, 33, tzinfo=timezone.utc)
    assert review_ages([RUNNING_1140], head_sha=OTHER, now=now) == []
    assert review_running([RUNNING_1140], head_sha=OTHER, now=now) is False
    pr = pr_payload(created_at="x", comments=[RUNNING_1140])    # head is HEAD
    assert stale_review_note(pr, now=now) == ""


def test_skipping_a_stale_review_is_said_not_silent():
    now = datetime(2026, 10, 22, 15, 18, tzinfo=timezone.utc)
    pr = pr_payload(created_at="x", comments=[RUNNING_1140])
    pr["headRefOid"] = HEAD_1140
    note = stale_review_note(pr, now=now)
    assert note.startswith("review_stale on 39d0e8a")
    assert "running 588 min" in note and "cap 30 min" in note
    unreadable = pr_payload(created_at="x", comments=[running_since("garbage")])
    assert "start time unreadable" in stale_review_note(unreadable, now=WHILE_RUNNING)


def test_the_sweep_merges_past_a_stuck_review_and_logs_it(monkeypatch, capsys):
    stuck = (datetime.now(timezone.utc) - timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    merged = wire(monkeypatch, pr_payload(created_at="2026-01-01T00:00:00Z",
                                          comments=[running_since(stuck)]))
    assert pr_delivery.cmd_sweep() == 0
    assert len(merged) == 1
    out = capsys.readouterr().out
    assert "#410 review_stale on 747985a" in out and "#410 merge ready" in out
