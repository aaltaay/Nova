"""Classifier tests for PR auto-merge and closed-head delete."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import pr_delivery
from tools.pr_delivery import (
    ACTION_BLOCK,
    ACTION_MERGE,
    ACTION_SKIP,
    can_delete_closed_head,
    decide,
    normalize_check,
)
from tools.pr_delivery_text import (
    CONFLICT_COMMENT_MARKER,
    conflict_rebase_comment,
    should_post_conflict_comment,
    squash_merge_fields,
)


def _ok_checks() -> list[dict]:
    return [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in ("Backend tests", "Frontend build", "Frontend E2E", "Agent contract")
    ]


def test_ready_pr_merges():
    result = decide(
        draft=False,
        state="OPEN",
        mergeable_state="clean",
        labels=[],
        head_ref="altaaya/fix-f0ca",
        same_repo=True,
        checks=_ok_checks(),
    )
    assert result.action == ACTION_MERGE


def test_draft_is_skipped():
    result = decide(
        draft=True,
        state="OPEN",
        mergeable_state="clean",
        labels=[],
        head_ref="wip",
        same_repo=True,
        checks=_ok_checks(),
    )
    assert result.action == ACTION_SKIP
    assert result.reason == "draft"


def test_do_not_merge_label_holds():
    result = decide(
        draft=False,
        state="OPEN",
        mergeable_state="clean",
        labels=[{"name": "do-not-merge"}],
        head_ref="hold",
        same_repo=True,
        checks=_ok_checks(),
    )
    assert result.action == ACTION_SKIP
    assert result.reason == "do-not-merge"


def test_conflict_blocks():
    result = decide(
        draft=False,
        state="OPEN",
        mergeable_state="dirty",
        labels=[],
        head_ref="stale",
        same_repo=True,
        checks=_ok_checks(),
    )
    assert result.action == ACTION_BLOCK
    assert result.reason == "conflict"


def test_conflicting_state_also_blocks():
    result = decide(
        draft=False,
        state="OPEN",
        mergeable_state="conflicting",
        labels=[],
        head_ref="stale",
        same_repo=True,
        checks=_ok_checks(),
    )
    assert result.action == ACTION_BLOCK
    assert result.reason == "conflict"


def test_squash_merge_fields_use_pr_title():
    fields = squash_merge_fields(239, "PR delivery: auto squash-merge", body="why")
    assert fields["merge_method"] == "squash"
    assert fields["commit_title"] == "PR delivery: auto squash-merge"
    assert fields["commit_message"] == "why"
    assert "Merge pull request" not in fields["commit_title"]


def test_squash_title_fallback_is_not_merge_commit():
    fields = squash_merge_fields(12, "  \n")
    assert fields["commit_title"] == "#12"
    assert fields["merge_method"] == "squash"
    assert "Merge pull request" not in fields["commit_title"]


def test_conflict_comment_is_actionable():
    body = conflict_rebase_comment()
    assert CONFLICT_COMMENT_MARKER in body
    assert "origin/master" in body
    assert "rebase" in body.lower()
    assert "Cursor cloud agent" in body
    assert "ready" in body.lower()


def test_conflict_comment_dedupes():
    assert should_post_conflict_comment([]) is True
    assert should_post_conflict_comment(["unrelated"]) is True
    assert (
        should_post_conflict_comment([f"{CONFLICT_COMMENT_MARKER} already"]) is False
    )


def test_missing_checks_allow_merge():
    result = decide(
        draft=False,
        state="OPEN",
        mergeable_state="clean",
        labels=[],
        head_ref="new",
        same_repo=True,
        checks=_ok_checks()[:-1],
    )
    assert result.action == ACTION_MERGE
    assert result.reason == "ready"


def test_failed_checks_allow_merge():
    checks = _ok_checks()
    checks[0] = {
        "name": "Backend tests",
        "status": "completed",
        "conclusion": "failure",
    }
    result = decide(
        draft=False,
        state="OPEN",
        mergeable_state="clean",
        labels=[],
        head_ref="red",
        same_repo=True,
        checks=checks,
    )
    assert result.action == ACTION_MERGE
    assert result.reason == "ready"


def test_desktop_pack_pending_allows_merge():
    checks = _ok_checks() + [
        {"name": "Desktop pack", "status": "in_progress", "conclusion": None}
    ]
    result = decide(
        draft=False,
        state="OPEN",
        mergeable_state="clean",
        labels=[],
        head_ref="packing",
        same_repo=True,
        checks=checks,
    )
    assert result.action == ACTION_MERGE
    assert result.reason == "ready"


def test_desktop_pack_missing_still_merges():
    result = decide(
        draft=False,
        state="OPEN",
        mergeable_state="clean",
        labels=[],
        head_ref="docs",
        same_repo=True,
        checks=_ok_checks(),
    )
    assert result.action == ACTION_MERGE


def test_fork_is_skipped():
    result = decide(
        draft=False,
        state="OPEN",
        mergeable_state="clean",
        labels=[],
        head_ref="fork-fix",
        same_repo=False,
        checks=_ok_checks(),
    )
    assert result.action == ACTION_SKIP
    assert result.reason == "fork"


def test_gh_check_state_normalizes():
    item = normalize_check({"name": "Backend tests", "state": "pass"})
    assert item["conclusion"] == "success"


def test_delete_refuses_master():
    ok, reason = can_delete_closed_head(
        "master",
        same_repo=True,
        open_pr_on_head=False,
    )
    assert ok is False
    assert reason == "protected"


def test_delete_refuses_open_pr_head():
    ok, reason = can_delete_closed_head(
        "fix/still-open",
        same_repo=True,
        open_pr_on_head=True,
    )
    assert ok is False
    assert reason == "open_pr"


def test_delete_closed_same_repo_ok():
    ok, reason = can_delete_closed_head(
        "cursor/old-f0ca",
        same_repo=True,
        open_pr_on_head=False,
    )
    assert ok is True
    assert reason == "ok"


def _ok_pr(number: int = 239, merge_state: str = "CLEAN", **extra) -> dict:
    payload = {
        "number": number,
        "title": "PR delivery: auto squash-merge",
        "body": "squash please",
        "isDraft": False,
        "state": "OPEN",
        "mergeStateStatus": merge_state,
        "labels": [],
        "headRefName": "altaaya/pr-delivery-squash-239-128b",
        "headRepository": {"name": "Nova"},
        "headRepositoryOwner": {"login": "aaltaay"},
    }
    payload.update(extra)
    return payload


def test_merge_now_sends_squash(monkeypatch):
    calls: list[tuple[list[str], str | None]] = []

    def fake_gh(args, check=True, stdin=None):
        calls.append((list(args), stdin))
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    monkeypatch.setattr(pr_delivery, "_gh", fake_gh)
    monkeypatch.setattr(pr_delivery, "cmd_delete_closed", lambda *a, **k: 0)
    rc = pr_delivery._merge_now(
        239,
        "altaaya/pr-delivery-squash-239-128b",
        title="PR delivery: auto squash-merge",
        body="body",
    )
    assert rc == 0
    args, stdin = calls[0]
    assert "--input" in args
    payload = json.loads(stdin or "{}")
    assert payload["merge_method"] == "squash"
    assert payload["commit_title"] == "PR delivery: auto squash-merge"
    assert "Merge pull request" not in payload["commit_title"]


def test_signal_conflict_posts_actionable_comment(monkeypatch):
    calls: list[list[str]] = []

    def fake_gh(args, check=True, stdin=None):
        calls.append(list(args))
        if args[0] == "api" and "comments" in args[1]:
            return subprocess.CompletedProcess(args, 0, stdout="[]", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr(pr_delivery, "_gh", fake_gh)
    pr_delivery._signal_conflict(239)
    comment_calls = [item for item in calls if item[:2] == ["pr", "comment"]]
    assert comment_calls
    body = comment_calls[0][comment_calls[0].index("--body") + 1]
    assert "gh pr comment" not in body
    assert "origin/master" in body
    assert "rebase" in body.lower()
    assert "Cursor cloud agent" in body


def test_signal_conflict_skips_duplicate(monkeypatch):
    calls: list[list[str]] = []

    def fake_gh(args, check=True, stdin=None):
        calls.append(list(args))
        if args[0] == "api":
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps([{"body": f"{CONFLICT_COMMENT_MARKER} already"}]),
                stderr="",
            )
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr(pr_delivery, "_gh", fake_gh)
    pr_delivery._signal_conflict(239)
    assert not any(item[:2] == ["pr", "comment"] for item in calls)


def test_cmd_merge_signals_conflict(monkeypatch):
    posted: list[int] = []
    monkeypatch.setattr(
        pr_delivery,
        "_fetch_pr",
        lambda n: (_ok_pr(n, merge_state="DIRTY"), _ok_checks()),
    )
    monkeypatch.setattr(pr_delivery, "_signal_conflict", lambda n: posted.append(n))
    rc = pr_delivery.cmd_merge(239, wait_desktop_minutes=0)
    assert rc == 1
    assert posted == [239]


def test_cmd_sweep_signals_conflict(monkeypatch):
    posted: list[int] = []

    def fake_gh(args, check=True, stdin=None):
        if args[:2] == ["pr", "list"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps([{"number": 239}]),
                stderr="",
            )
        return subprocess.CompletedProcess(args, 0, stdout="[]", stderr="")

    monkeypatch.setattr(pr_delivery, "_gh", fake_gh)
    monkeypatch.setattr(
        pr_delivery,
        "_fetch_pr",
        lambda n: (_ok_pr(n, merge_state="DIRTY"), _ok_checks()),
    )
    monkeypatch.setattr(pr_delivery, "_signal_conflict", lambda n: posted.append(n))
    rc = pr_delivery.cmd_sweep()
    assert rc == 1
    assert posted == [239]


def _dispatch_call(calls: list[list[str]]) -> list[str] | None:
    """The desktop-pack workflow_dispatch call, if the merge made one."""
    for args in calls:
        if args[:3] == ["api", "-X", "POST"] and "desktop-pack.yml/dispatches" in args[3]:
            return args
    return None


def test_merge_dispatches_desktop_pack(monkeypatch):
    """An Actions merge must start the pack itself.

    The squash-merge pushes with `GITHUB_TOKEN`, which by design starts no
    `push:` run, so without this dispatch master gets no vNNN tag, Release
    or EXE -- the #346 defect that stalled releases at v757.
    """
    calls: list[list[str]] = []

    def fake_gh(args, check=True, stdin=None):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    monkeypatch.setattr(pr_delivery, "_gh", fake_gh)
    monkeypatch.setattr(pr_delivery, "cmd_delete_closed", lambda *a, **k: 0)
    rc = pr_delivery._merge_now(239, "feature-head", title="t", body="b")

    assert rc == 0
    dispatched = _dispatch_call(calls)
    assert dispatched is not None, "merge did not dispatch Desktop pack"
    # master HEAD, not the merged head -- the head is deleted right after.
    assert "ref=master" in dispatched


def test_desktop_pack_dispatch_follows_the_merge(monkeypatch):
    """Dispatch after the merge lands, never before, and never on a failure."""
    calls: list[list[str]] = []

    def fake_gh(args, check=True, stdin=None):
        calls.append(list(args))
        if args[:3] == ["api", "-X", "PUT"]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="merge blocked")
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    monkeypatch.setattr(pr_delivery, "_gh", fake_gh)
    monkeypatch.setattr(pr_delivery, "cmd_delete_closed", lambda *a, **k: 0)
    rc = pr_delivery._merge_now(239, "feature-head", title="t", body="b")

    assert rc == 2
    assert _dispatch_call(calls) is None, "dispatched a pack for a merge that failed"


def test_failed_dispatch_does_not_fail_the_merge(monkeypatch, capsys):
    """The merge already landed; a lost dispatch costs a Release, not the merge."""
    def fake_gh(args, check=True, stdin=None):
        if args[:3] == ["api", "-X", "POST"]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="no actions scope")
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    monkeypatch.setattr(pr_delivery, "_gh", fake_gh)
    monkeypatch.setattr(pr_delivery, "cmd_delete_closed", lambda *a, **k: 0)
    rc = pr_delivery._merge_now(239, "feature-head", title="t", body="b")

    assert rc == 0
    # Never silent (AGENTS.md 6.3) -- the operator must see the lost Release.
    assert "no actions scope" in capsys.readouterr().err
