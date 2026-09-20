"""Contract tests for the PR delivery (auto-merge + delete-head) workflow."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

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


# `merge` and `sweep` both reach `_merge_now`; `delete-closed` and `decide`
# do not, so only these two need to be able to dispatch.
MERGING_COMMANDS = ("pr_delivery.py merge", "pr_delivery.py sweep")


def _merging_jobs() -> list[tuple[str, str, dict, dict]]:
    """Every job in every workflow that can reach `merge_now`, by what it runs."""
    found = []
    for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.y*ml")):
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        if not isinstance(workflow, dict):
            continue
        for job_id, job in (workflow.get("jobs") or {}).items():
            runs = " ".join(step.get("run", "") for step in job.get("steps") or [])
            if any(command in runs for command in MERGING_COMMANDS):
                found.append((path.name, job_id, workflow, job))
    return found


def _grants_write(permissions, scope: str) -> bool:
    """`write-all` also grants; a job's own block replaces the workflow's."""
    if isinstance(permissions, str):
        return permissions == "write-all"
    return permissions.get(scope) == "write"


def _effective(workflow: dict, job: dict):
    return job.get("permissions", workflow.get("permissions", {}))


def test_every_merge_path_may_dispatch_the_desktop_pack():
    """Every merging job needs `actions: write` or no Release publishes (#346).

    An Actions merge pushes with `GITHUB_TOKEN`, which by design starts no
    `push:` run, so `merge_now` dispatches `desktop-pack.yml` itself. Without
    this permission the dispatch is refused with
    `Resource not accessible by integration (HTTP 403)`, and because a lost
    dispatch is deliberately not allowed to fail the merge, master goes back
    to collecting untagged, unreleased commits in silence -- the v757 symptom.

    Swept across every workflow rather than pinned to one file. #389 granted
    the permission to `pr-delivery.yml` alone and left `deploy.yml`'s
    `auto-merge` -- the job that actually merges most PRs, within seconds of
    opening -- still unable to dispatch, so the bug survived its own fix. A
    third merge path would have slipped through the same way.

    Parsed rather than grepped: both files name `actions: write` in a comment,
    so a substring check passes even with the permission reverted.
    """
    jobs = _merging_jobs()
    assert jobs, "no job merges PRs -- the delivery path moved, so this guard is blind"
    refused = [
        f"{name}:{job_id} runs with {_effective(workflow, job)!r}"
        for name, job_id, workflow, job in jobs
        if not _grants_write(_effective(workflow, job), "actions")
    ]
    assert not refused, (
        "these merge paths cannot dispatch Desktop pack, so the commits they "
        f"merge ship no vNNN tag, Release or EXE (#346): {refused}"
    )
