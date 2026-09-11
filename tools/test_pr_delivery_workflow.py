"""Contract tests for the PR delivery (auto-merge + delete-head) workflow."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-delivery.yml"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy.yml"


def test_pr_delivery_workflow_exists():
    assert WORKFLOW.is_file()


def test_pr_delivery_workflow_merges_and_deletes():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pr_delivery.py sweep" in text
    assert "pr_delivery.py delete-closed" in text
    assert "pull_request:" in text
    assert "types: [closed]" in text
    assert "workflow_run:" in text
    assert "contents: write" in text
    assert "pull-requests: write" in text
    assert "do-not-merge" in text


def test_ci_auto_merge_job_is_wired():
    text = DEPLOY.read_text(encoding="utf-8")
    assert "pr_delivery.py merge" in text
    assert "test_pr_delivery.py" in text
    assert "test_master_branch_protection.py" in text
