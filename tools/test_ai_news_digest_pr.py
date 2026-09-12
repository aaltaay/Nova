"""Tests for digest-via-PR publish (never push master)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.ai_news_digest_pr import (  # noqa: E402
    BASE_BRANCH,
    DIGEST_BRANCH,
    DIGEST_PATHS,
    EXIT_OK,
    assert_push_ref_allowed,
    pr_create_command,
    publish,
    push_command,
)

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ai-news.yml"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy.yml"


def _proc(cmd, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)


def _runner(*, dirty: bool, existing=None, commit_empty: bool = False):
    calls: list[list[str]] = []

    def runner(cmd, **_kwargs):
        calls.append(list(cmd))
        if cmd[:3] == ["git", "status", "--porcelain"]:
            stdout = " M site/index.html\n" if dirty else ""
            return _proc(cmd, stdout=stdout)
        if cmd[:2] == ["git", "commit"]:
            if commit_empty:
                return _proc(cmd, returncode=1, stderr="nothing to commit, working tree clean")
            return _proc(cmd)
        if cmd[:2] == ["gh", "pr"] and cmd[2] == "list":
            return _proc(cmd, stdout=json.dumps(existing or []))
        if cmd[:3] == ["gh", "pr", "create"]:
            return _proc(cmd, stdout="https://github.com/aaltaay/Nova/pull/999\n")
        return _proc(cmd)

    return runner, calls


def test_empty_diff_is_quiet_success():
    runner, calls = _runner(dirty=False)
    assert publish(runner=runner) == EXIT_OK
    joined = [" ".join(cmd) for cmd in calls]
    assert any(cmd.startswith("git status") for cmd in joined)
    assert not any("git push" in cmd for cmd in joined)
    assert not any("gh pr create" in cmd for cmd in joined)


def test_nothing_to_commit_is_quiet_success():
    runner, calls = _runner(dirty=True, commit_empty=True)
    assert publish(runner=runner) == EXIT_OK
    assert not any(cmd[0:2] == ["git", "push"] for cmd in calls)
    assert not any(cmd[0:3] == ["gh", "pr", "create"] for cmd in calls)


def test_changes_open_ready_pr_on_digest_branch():
    runner, calls = _runner(dirty=True, existing=[])
    assert publish(runner=runner) == EXIT_OK
    assert ["git", "checkout", "-B", DIGEST_BRANCH] in calls
    assert ["git", "add", "--", *DIGEST_PATHS] in calls
    assert push_command(DIGEST_BRANCH) in calls
    create = pr_create_command()
    assert create in calls
    assert "--draft" not in create
    assert not any(cmd == ["git", "push"] for cmd in calls)
    for cmd in calls:
        if cmd[:2] == ["git", "push"]:
            assert DIGEST_BRANCH in cmd
            assert BASE_BRANCH not in cmd


def test_existing_open_pr_is_updated_not_recreated():
    runner, calls = _runner(
        dirty=True,
        existing=[{"number": 77, "url": "https://github.com/aaltaay/Nova/pull/77", "isDraft": False}],
    )
    assert publish(runner=runner) == EXIT_OK
    assert push_command(DIGEST_BRANCH) in calls
    assert not any(cmd[:3] == ["gh", "pr", "create"] for cmd in calls)
    assert not any(cmd[:3] == ["gh", "pr", "ready"] for cmd in calls)


def test_existing_draft_is_marked_ready():
    runner, calls = _runner(
        dirty=True,
        existing=[{"number": 81, "url": "https://github.com/aaltaay/Nova/pull/81", "isDraft": True}],
    )
    assert publish(runner=runner) == EXIT_OK
    assert ["gh", "pr", "ready", "81"] in calls
    assert not any(cmd[:3] == ["gh", "pr", "create"] for cmd in calls)


@pytest.mark.parametrize("ref", ["master", "main", "HEAD", "refs/heads/master", "origin/master"])
def test_push_refuses_protected_branches(ref):
    with pytest.raises(ValueError, match="refusing to push digest"):
        assert_push_ref_allowed(ref)
    with pytest.raises(ValueError, match="refusing to push digest"):
        push_command(ref)


def test_push_command_targets_digest_branch_only():
    cmd = push_command(DIGEST_BRANCH)
    assert cmd == ["git", "push", "--force", "-u", "origin", DIGEST_BRANCH]


def test_workflow_keeps_tests_rebuild_and_never_pushes_master():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "python -m pytest tools/test_ai_news_digest.py" in text
    assert "python tools/ai_news_digest.py --limit 6 --feed-limit 60" in text
    assert "python tools/ai_news_digest_pr.py" in text
    assert "contents: write" in text
    assert "pull-requests: write" in text
    assert "NOVA_PROJECT_TOKEN" in text
    assert "secrets.GITHUB_TOKEN" in text
    assert "git push" not in text
    assert "git commit" not in text


def test_ci_runs_digest_pr_tests():
    text = DEPLOY.read_text(encoding="utf-8")
    assert "test_ai_news_digest_pr.py" in text
