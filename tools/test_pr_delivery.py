"""Classifier tests for PR auto-merge and closed-head delete."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.pr_delivery import (
    ACTION_BLOCK,
    ACTION_MERGE,
    ACTION_SKIP,
    ACTION_WAIT,
    REQUIRED_CHECKS,
    can_delete_closed_head,
    decide,
    normalize_check,
)


def _ok_checks() -> list[dict]:
    return [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in REQUIRED_CHECKS
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


def test_missing_required_check_waits():
    result = decide(
        draft=False,
        state="OPEN",
        mergeable_state="clean",
        labels=[],
        head_ref="new",
        same_repo=True,
        checks=_ok_checks()[:-1],
    )
    assert result.action == ACTION_WAIT
    assert result.reason.startswith("pending:")


def test_failed_required_check_blocks():
    checks = _ok_checks()
    checks[0] = {
        "name": REQUIRED_CHECKS[0],
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
    assert result.action == ACTION_BLOCK
    assert "Backend tests" in result.reason


def test_desktop_pack_pending_waits():
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
    assert result.action == ACTION_WAIT
    assert result.reason == "pending:Desktop pack"


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
