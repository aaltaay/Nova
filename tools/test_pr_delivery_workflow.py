"""Contract tests for the PR delivery (auto-merge + delete-head) workflow."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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


def test_pr_delivery_auto_merge_is_squash():
    from tools.pr_delivery_text import squash_merge_fields

    fields = squash_merge_fields(239, "PR delivery: auto squash-merge")
    assert fields["merge_method"] == "squash"
    assert fields["commit_title"] == "PR delivery: auto squash-merge"
    assert "Merge pull request" not in fields["commit_title"]
    source = (REPO_ROOT / "tools" / "pr_delivery.py").read_text(encoding="utf-8")
    assert "merge_method=merge" not in source
    assert "_merge_now" in source
