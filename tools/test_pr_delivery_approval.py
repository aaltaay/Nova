"""Owner label gate: merge-approved counts only when aaltaay added it last."""

from __future__ import annotations

import json
import subprocess

import pytest

from tools import pr_delivery
from tools.pr_delivery import ACTION_MERGE, ACTION_SKIP, decide
from tools.pr_delivery_approval import (
    ACTOR_COMMENT_MARKER,
    OWNER_LOGIN,
    approval_for_pr,
    fetch_label_events,
    latest_labeled_actor,
    owner_merge_approval,
    parse_issue_events,
    signal_wrong_actor,
    wrong_actor_comment,
)
from tools.release_gate import REQUIRED_CHECKS


@pytest.fixture(autouse=True)
def _no_job_summary(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


def _event(login: str, at: str, label: str = "merge-approved", event: str = "labeled") -> dict:
    return {
        "event": event,
        "created_at": at,
        "actor": {"login": login},
        "label": {"name": label},
    }


def _green() -> list[dict]:
    return [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in REQUIRED_CHECKS
    ]


def _decide(**over):
    args = dict(
        draft=False, state="OPEN", mergeable_state="clean", labels=[],
        head_ref="feature/x", same_repo=True, checks=_green(),
        owner_approved=True,
    )
    args.update(over)
    return decide(**args)


def test_latest_labeled_actor_is_the_most_recent_add_of_this_label():
    events = [
        _event("aaltaay", "2026-10-19T00:00:00Z"),
        _event("aaltaay", "2026-10-19T01:00:00Z", label="do-not-merge"),
        _event("dependabot[bot]", "2026-10-19T02:00:00Z"),
        _event("aaltaay", "2026-10-19T03:00:00Z", event="unlabeled"),
    ]
    assert latest_labeled_actor(events) == "dependabot[bot]"
    events.append(_event("aaltaay", "2026-10-19T04:00:00Z"))
    assert latest_labeled_actor(events) == "aaltaay"


def test_equal_timestamps_keep_the_later_event():
    events = [
        _event("aaltaay", "2026-10-19T00:00:00Z"),
        _event("cursor[bot]", "2026-10-19T00:00:00Z"),
    ]
    assert latest_labeled_actor(events) == "cursor[bot]"


def test_paginated_events_parse_and_the_newer_page_can_lose():
    older = json.dumps([_event("some-bot", "2026-10-18T00:00:00Z")])
    newer = json.dumps([_event("aaltaay", "2026-10-19T00:00:00Z")])
    # Pages arrive oldest-first, but a clock skew must not crown the last page.
    assert latest_labeled_actor(parse_issue_events(newer + older)) == "aaltaay"


def test_owner_approval_refuses_everyone_but_aaltaay():
    ok, reason, actor = owner_merge_approval(True, [_event("aaltaay", "2026-10-19T00:00:00Z")])
    assert (ok, reason, actor) == (True, "ok", "aaltaay")
    ok, reason, actor = owner_merge_approval(True, [_event("Aaltaay", "2026-10-19T00:00:00Z")])
    assert ok is True and reason == "ok"
    ok, reason, actor = owner_merge_approval(
        True, [_event("github-actions[bot]", "2026-10-19T00:00:00Z")],
    )
    assert (ok, reason, actor) == (False, "merge-approved-actor", "github-actions[bot]")


def test_missing_or_unreadable_events_do_not_approve():
    assert owner_merge_approval(False, [_event("aaltaay", "2026-10-19T00:00:00Z")])[1] == (
        "merge-approved-missing"
    )
    assert owner_merge_approval(True, None)[1] == "merge-approved-unverified"
    assert owner_merge_approval(True, [])[1] == "merge-approved-unverified"
    assert owner_merge_approval(True, [_event("", "2026-10-19T00:00:00Z")])[1] == (
        "merge-approved-unverified"
    )


def test_fetch_reads_the_issue_events_api_and_fails_closed():
    seen: list[list[str]] = []

    def gh(args, check=True, stdin=None):
        seen.append(list(args))
        return subprocess.CompletedProcess(
            args, 0, stdout=json.dumps([_event("aaltaay", "2026-10-19T00:00:00Z")]), stderr="",
        )

    events = fetch_label_events(gh, "aaltaay/Nova", 1095)
    assert events is not None and latest_labeled_actor(events) == "aaltaay"
    assert seen == [[
        "api", "--paginate", "repos/aaltaay/Nova/issues/1095/events?per_page=100",
    ]]

    def down(args, check=True, stdin=None):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="HTTP 502")

    assert fetch_label_events(down, "aaltaay/Nova", 1095) is None


def test_removed_label_is_not_approved_even_if_aaltaay_added_it():
    pr = {
        "number": 7,
        "labels": [],
        "label_events": [_event("aaltaay", "2026-10-19T00:00:00Z")],
    }
    approved, reason, _actor = approval_for_pr(pr, gh=None, repo="aaltaay/Nova")
    assert approved is False and reason == "merge-approved-missing"


def test_decide_skips_drafts_even_when_the_owner_approved():
    result = _decide(draft=True, owner_approved=True)
    assert result.action == ACTION_SKIP and result.reason == "draft"


def test_decide_merges_only_when_the_owner_approved_and_checks_are_green():
    refused = _decide(owner_approved=False)
    assert refused.action == ACTION_SKIP and refused.reason == "merge-approved-missing"
    wrong = _decide(
        owner_approved=False,
        approval_reason="merge-approved-actor",
        approval_actor="cursor[bot]",
    )
    assert wrong.reason == "merge-approved-actor" and wrong.detail == "cursor[bot]"
    assert _decide(owner_approved=True).action == ACTION_MERGE


def test_unreadable_comments_do_not_post_or_remove_the_label():
    calls: list[list[str]] = []

    def gh(args, check=True, stdin=None):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="HTTP 502")

    signal_wrong_actor(gh, "aaltaay/Nova", 7, "cursor[bot]")
    assert calls and not any(item[:2] == ["pr", "comment"] for item in calls)
    assert not any("labels/" in " ".join(item) for item in calls)


def test_wrong_actor_comment_is_once_and_does_not_remove_the_label():
    body = wrong_actor_comment("cursor[bot]")
    assert ACTOR_COMMENT_MARKER in body
    assert "cursor[bot]" in body and OWNER_LOGIN in body
    assert "left in place" in body
    assert "Agents never add" in body
    calls: list[list[str]] = []
    posted: list[str] = []

    def gh(args, check=True, stdin=None):
        calls.append(list(args))
        if args[:2] == ["api", "--paginate"] and "/comments" in args[2]:
            return subprocess.CompletedProcess(
                args, 0, stdout=json.dumps([{"body": b} for b in posted]), stderr="",
            )
        if args[:2] == ["pr", "comment"]:
            posted.append(args[args.index("--body") + 1])
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        raise AssertionError(args)

    signal_wrong_actor(gh, "aaltaay/Nova", 7, "cursor[bot]")
    signal_wrong_actor(gh, "aaltaay/Nova", 7, "cursor[bot]")
    assert len(posted) == 1
    assert not any("labels/" in " ".join(call) or "DELETE" in call for call in calls)


def _pr(**over) -> dict:
    payload = {
        "number": 7,
        "title": "t",
        "body": "",
        "isDraft": False,
        "state": "OPEN",
        "mergeStateStatus": "CLEAN",
        "labels": [{"name": "merge-approved"}],
        "label_events": [_event("aaltaay", "2026-10-19T00:00:00Z")],
        "headRefName": "feature/x",
        "headRefOid": "a" * 40,
        "headRepository": {"name": "Nova"},
        "headRepositoryOwner": {"login": "aaltaay"},
        "createdAt": "2020-01-01T00:00:00Z",
    }
    payload.update(over)
    return payload


def test_cmd_merge_posts_one_comment_and_does_not_merge_a_foreign_label(monkeypatch):
    posted: list[str] = []
    merged: list[int] = []

    def gh(args, check=True, stdin=None):
        if args[:2] == ["api", "--paginate"] and "/comments" in args[2]:
            return subprocess.CompletedProcess(
                args, 0, stdout=json.dumps([{"body": b} for b in posted]), stderr="",
            )
        if args[:2] == ["pr", "comment"]:
            posted.append(args[args.index("--body") + 1])
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        raise AssertionError(args)

    monkeypatch.setattr(pr_delivery, "_gh", gh)
    monkeypatch.setattr(pr_delivery, "_fetch_pr", lambda n: (
        _pr(label_events=[_event("cursor[bot]", "2026-10-19T00:00:00Z")]), _green(),
    ))
    monkeypatch.setattr(pr_delivery, "_merge_pr", lambda pr: merged.append(pr["number"]) or 0)
    assert pr_delivery.cmd_merge(7, wait_desktop_minutes=0, min_age_seconds=0) == 0
    assert pr_delivery.cmd_merge(7, wait_desktop_minutes=0, min_age_seconds=0) == 0
    assert merged == []
    assert len(posted) == 1
    assert "cursor[bot]" in posted[0]


def test_cmd_merge_and_sweep_skip_a_removed_label_without_commenting(monkeypatch):
    merged: list[int] = []
    monkeypatch.setattr(pr_delivery, "_fetch_pr", lambda n: (_pr(labels=[]), _green()))
    monkeypatch.setattr(pr_delivery, "_merge_pr", lambda pr: merged.append(pr["number"]) or 0)
    monkeypatch.setattr(pr_delivery, "signal_wrong_actor", lambda *a, **k: pytest.fail("commented"))
    monkeypatch.setattr(pr_delivery, "_gh", lambda args, check=True, stdin=None: subprocess.CompletedProcess(
        args, 0, stdout=json.dumps([{"number": 7}]), stderr="",
    ))
    assert pr_delivery.cmd_merge(7, wait_desktop_minutes=0, min_age_seconds=0) == 0
    assert pr_delivery.cmd_sweep(min_age_seconds=0) == 0
    assert merged == []


def test_cmd_paths_merge_when_aaltaay_added_the_label(monkeypatch):
    merged: list[int] = []
    monkeypatch.setattr(pr_delivery, "_fetch_pr", lambda n: (_pr(), _green()))
    monkeypatch.setattr(pr_delivery, "_merge_pr", lambda pr: merged.append(pr["number"]) or 0)
    monkeypatch.setattr(pr_delivery, "_gh", lambda args, check=True, stdin=None: subprocess.CompletedProcess(
        args, 0, stdout=json.dumps([{"number": 7}]), stderr="",
    ))
    assert pr_delivery.cmd_merge(7, wait_desktop_minutes=0, min_age_seconds=0) == 0
    assert pr_delivery.cmd_sweep(min_age_seconds=0) == 0
    assert merged == [7, 7]
