"""Classifier tests for leftover merged/closed PR head branches."""

from __future__ import annotations

import sys
import json
import subprocess
from pathlib import Path

import pytest

# pytest puts this file's directory on sys.path, so `import tools` fails
# unless the repo root is also present (CI agent-contract job).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.stale_pr_branches import classify_stale_branches  # noqa: E402
from tools import branch_cleanup, stale_pr_branches  # noqa: E402


def test_open_pr_branch_is_kept():
    stale = classify_stale_branches(
        ["origin/master", "origin/fix/ci"],
        [{"head": "fix/ci", "state": "OPEN", "number": 10}],
    )
    assert stale == []


def test_merged_pr_branch_is_stale():
    stale = classify_stale_branches(
        ["origin/master", "origin/feature/news"],
        [{"head": "feature/news", "state": "MERGED", "number": 52}],
    )
    assert stale == [("feature/news", "MERGED", 52)]


def test_closed_unmerged_pr_branch_is_stale():
    stale = classify_stale_branches(
        ["origin/master", "origin/cursor/old"],
        [{"head": "cursor/old", "state": "CLOSED", "number": 51}],
    )
    assert stale == [("cursor/old", "CLOSED", 51)]


def test_protected_branches_never_stale():
    stale = classify_stale_branches(
        ["origin/master", "origin/main", "origin/HEAD"],
        [
            {"head": "master", "state": "MERGED", "number": 1},
            {"head": "main", "state": "CLOSED", "number": 2},
        ],
    )
    assert stale == []


def test_branch_with_open_and_old_closed_pr_is_kept():
    stale = classify_stale_branches(
        ["origin/master", "origin/fix/retry"],
        [
            {"head": "fix/retry", "state": "CLOSED", "number": 3},
            {"head": "fix/retry", "state": "OPEN", "number": 9},
        ],
    )
    assert stale == []


def test_no_pr_yet_is_kept():
    stale = classify_stale_branches(
        ["origin/master", "origin/wip/today"],
        [],
    )
    assert stale == []


def test_strips_origin_prefix():
    stale = classify_stale_branches(
        ["feature/news"],
        [{"head": "feature/news", "state": "MERGED", "number": 52}],
    )
    assert stale == [("feature/news", "MERGED", 52)]


@pytest.fixture
def git_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def git(*args):
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.PIPE).strip()

    git("init", "--initial-branch=master")
    git("config", "user.name", "Cleanup test")
    git("config", "user.email", "cleanup@example.invalid")
    git("-c", "core.hooksPath=", "commit", "--allow-empty", "-m", "base")
    base = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/master", base)
    git("branch", "feature/reused")
    return git, base


def test_recreated_after_merge_is_preserved_and_reported(git_history, monkeypatch, capsys):
    git, base = git_history
    assert branch_cleanup.contained_tip("refs/heads/feature/reused") == base
    git("switch", "feature/reused")
    git("-c", "core.hooksPath=", "commit", "--allow-empty", "-m", "new unmerged work")
    new_tip = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/feature/reused", new_tip)
    assert branch_cleanup.contained_tip("refs/heads/feature/reused") is None
    monkeypatch.setattr(stale_pr_branches, "_git_remote_branches", lambda: ["origin/feature/reused"])
    monkeypatch.setattr(stale_pr_branches, "_gh_all_prs", lambda: [
        {"head": "feature/reused", "state": "MERGED", "number": 365}])
    assert stale_pr_branches.main([]) == 1
    output = capsys.readouterr().out
    assert "REFUSE deletion" in output
    assert "delete-closed --ref" not in output
    assert stale_pr_branches.main(["--json"]) == 1
    assert json.loads(capsys.readouterr().out)[0]["safe_to_delete"] is False
    assert git("rev-parse", "refs/heads/feature/reused") == new_tip


def test_unknown_ancestry_fails_closed(git_history):
    git, _ = git_history
    git("update-ref", "-d", "refs/remotes/origin/master")
    with pytest.raises(subprocess.CalledProcessError):
        branch_cleanup.contained_tip("HEAD")


def _remote(monkeypatch, *, state="MERGED", comparison="behind", fail_at=None,
            absent=False, push_code=0, owner="aaltaay", recheck=None):
    calls, pushes = [], []
    tip = "a" * 40

    def gh(args, check=False):
        calls.append(args)
        index = len(calls)
        rows = [{"state": state, "headRefName": "feature/reused",
                 "headRepository": {"name": "Nova"}, "headRepositoryOwner": {"login": owner}}]
        outputs = {1: rows, 2: {"object": {"sha": tip}},
                   3: {"status": comparison, "merge_base_commit": {"sha": tip}},
                   4: recheck or []}
        return subprocess.CompletedProcess(args, 1 if index == fail_at or absent and index == 2 else 0,
                                           json.dumps(outputs[index]),
                                           "HTTP 404" if absent and index == 2 else "unavailable")

    def run(args, **kwargs):
        if args[1] == "push":
            pushes.append(args)
        return subprocess.CompletedProcess(args, push_code if args[1] == "push" else 0, "", "stale info")

    monkeypatch.setattr(branch_cleanup.subprocess, "run", run)
    return gh, calls, pushes, tip


@pytest.mark.parametrize("status", ["ahead", "diverged"])
def test_remote_recreated_head_never_deletes(monkeypatch, capsys, status):
    gh, _, pushes, _ = _remote(monkeypatch, comparison=status)
    assert branch_cleanup.delete_closed_head(gh, "aaltaay/Nova", "feature/reused", same_repo=True) == 1
    assert pushes == []
    assert "not contained in master" in capsys.readouterr().err


@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_remote_lookup_failures_never_delete(monkeypatch, step):
    gh, _, pushes, _ = _remote(monkeypatch, fail_at=step)
    assert branch_cleanup.delete_closed_head(gh, "aaltaay/Nova", "feature/reused", same_repo=True) == 1
    assert pushes == []


@pytest.mark.parametrize("options", [{"state": "OPEN"}, {"owner": "other"},
                                    {"absent": True}, {"recheck": [{"number": 999}]}])
def test_remote_open_fork_or_missing_heads_stay_untouched(monkeypatch, options):
    gh, _, pushes, _ = _remote(monkeypatch, **options)
    assert branch_cleanup.delete_closed_head(gh, "aaltaay/Nova", "feature/reused", same_repo=True) == 0
    assert pushes == []


@pytest.mark.parametrize("ref,same_repo", [("master", True), ("main", True),
                                          ("feature/reused", False)])
def test_protected_or_fork_does_not_query_or_delete(monkeypatch, ref, same_repo):
    gh, calls, pushes, _ = _remote(monkeypatch)
    assert branch_cleanup.delete_closed_head(gh, "aaltaay/Nova", ref, same_repo=same_repo) == 0
    assert calls == pushes == []


@pytest.mark.parametrize("push_code", [0, 1])
def test_remote_delete_uses_exact_tip_lease(monkeypatch, push_code):
    gh, calls, pushes, tip = _remote(monkeypatch, push_code=push_code)
    assert branch_cleanup.delete_closed_head(gh, "aaltaay/Nova", "feature/reused", same_repo=True) == push_code
    assert pushes == [["git", "push", f"--force-with-lease=refs/heads/feature/reused:{tip}",
                       "https://github.com/aaltaay/Nova.git", ":refs/heads/feature/reused"]]
    assert not any("DELETE" in c for c in calls)


def test_lease_rejects_real_push_after_check(git_history, tmp_path):
    git, base = git_history
    remote = str(tmp_path / "remote.git")
    git("init", "--bare", remote)
    git("push", remote, "feature/reused")
    git("switch", "feature/reused")
    git("-c", "core.hooksPath=", "commit", "--allow-empty", "-m", "concurrent work")
    tip = git("rev-parse", "HEAD")
    git("push", remote, "feature/reused")
    with pytest.raises(subprocess.CalledProcessError):
        git("push", f"--force-with-lease=refs/heads/feature/reused:{base}", remote,
            ":refs/heads/feature/reused")
    assert tip in git("ls-remote", remote, "refs/heads/feature/reused")
