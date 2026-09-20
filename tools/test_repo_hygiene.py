"""Classifier tests for repo_hygiene (plain data, no git, no gh)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# pytest puts this file's directory on sys.path, so `import tools` fails
# unless the repo root is also present (CI agent-contract job).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.repo_hygiene_lib import (  # noqa: E402
    classify_local_branches,
    classify_remote_refs,
    classify_stashes,
    classify_stop,
    classify_working_tree,
    classify_worktrees,
    index_prs,
)

NOW = 1_800_000_000.0
DAY = 86_400.0
PRS = index_prs([
    {"head": "feat/done", "state": "MERGED", "number": 1},
    {"head": "fix/closed", "state": "CLOSED", "number": 2},
    {"head": "feat/live", "state": "OPEN", "number": 3},
    {"head": "feat/reopened", "state": "CLOSED", "number": 4},
    {"head": "feat/reopened", "state": "OPEN", "number": 5},
])


def _kinds(findings):
    return {(f.kind, f.subject, f.fixable) for f in findings}


# --- branches -----------------------------------------------------------------

def test_merged_and_closed_branches_are_fixable_by_pr_state():
    out = classify_local_branches(
        [{"name": "feat/done", "upstream_gone": True, "checked_out_at": None, "contained_in_master": True},
         {"name": "fix/closed", "upstream_gone": True, "checked_out_at": None, "contained_in_master": True}],
        PRS,
    )
    assert _kinds(out) == {("merged_local_branch", "feat/done", True),
                           ("merged_local_branch", "fix/closed", True)}


def test_open_pr_keeps_branch_even_after_an_older_closed_pr():
    out = classify_local_branches(
        [{"name": "feat/live", "upstream_gone": False, "checked_out_at": None},
         {"name": "feat/reopened", "upstream_gone": False, "checked_out_at": None}],
        PRS,
    )
    assert out == []


def test_checked_out_merged_branch_is_never_fixable():
    out = classify_local_branches(
        [{"name": "feat/done", "upstream_gone": True, "checked_out_at": "C:/wt/a"}], PRS)
    assert _kinds(out) == {("checked_out_elsewhere", "feat/done", False)}


def test_no_pr_branch_is_reported_not_fixed_and_master_is_ignored():
    out = classify_local_branches(
        [{"name": "wip/idea", "upstream_gone": False, "checked_out_at": None},
         {"name": "master", "upstream_gone": False, "checked_out_at": "C:/repo"}], PRS)
    assert _kinds(out) == {("no_pr_branch", "wip/idea", False)}


def test_gh_unavailable_makes_nothing_fixable():
    out = classify_local_branches(
        [{"name": "feat/done", "upstream_gone": True, "checked_out_at": None, "contained_in_master": True}], None)
    assert _kinds(out) == {("branch_unknown", "feat/done", False)}


def test_recreated_or_unknown_tip_cannot_be_deleted():
    for contained in (False, None):
        out = classify_local_branches([
            {"name": "feat/done", "contained_in_master": contained}], PRS)
        assert _kinds(out) == {("unmerged_branch", "feat/done", False)}


# --- worktrees ----------------------------------------------------------------

def _wt(**kw):
    base = {"path": "C:/wt/x", "is_main": False, "exists": True, "head": "abc",
            "branch": None, "clean": True, "last_activity_ts": NOW - 2 * DAY}
    base.update(kw)
    return base


def test_clean_old_worktree_on_merged_branch_is_stale():
    out = classify_worktrees([_wt(branch="feat/done")], PRS, {"abc"}, NOW)
    assert _kinds(out) == {("worktree_stale", "C:/wt/x", True)}


def test_old_worktree_with_new_unmerged_commit_is_preserved():
    out = classify_worktrees([_wt(branch="feat/done", head="new")], PRS, {"abc"}, NOW)
    assert _kinds(out) == {("worktree_active", "C:/wt/x", False)}
    assert "preserve for review" in out[0].detail


def test_recent_dirty_or_no_pr_worktrees_are_kept():
    out = classify_worktrees([
        _wt(path="recent", branch="feat/done", last_activity_ts=NOW - 3600),
        _wt(path="dirty", branch="feat/done", clean=False),
        _wt(path="nopr", branch="wip/idea"),
        _wt(path="open", branch="feat/live"),
    ], PRS, {"abc"}, NOW)
    assert {f.subject: f.fixable for f in out} == {
        "recent": False, "dirty": False, "nopr": False, "open": False}
    assert {f.kind for f in out} == {"worktree_recent", "worktree_dirty", "worktree_active"}


def test_detached_worktree_on_master_history_is_stale_only_when_reachable():
    out = classify_worktrees([_wt(path="onmaster", head="aaa"),
                              _wt(path="offmaster", head="bbb")], PRS, {"aaa"}, NOW)
    assert {f.subject: (f.kind, f.fixable) for f in out} == {
        "onmaster": ("worktree_stale", True), "offmaster": ("worktree_active", False)}


def test_missing_worktree_dir_is_pruned_and_main_is_skipped():
    out = classify_worktrees([_wt(path="main", is_main=True, clean=False),
                              _wt(path="gone", exists=False)], PRS, set(), NOW)
    assert _kinds(out) == {("worktree_missing", "gone", True)}


# --- refs / stashes / tree ----------------------------------------------------

def test_orphan_remote_tracking_ref_is_fixable_but_origin_is_not():
    out = classify_remote_refs(["origin/master", "scratch/pr299", "origin/HEAD"], ["origin"])
    assert _kinds(out) == {("orphan_remote_ref", "scratch/pr299", True)}


def test_stashes_are_reported_never_fixable():
    out = classify_stashes([{"ref": "stash@{0}", "ts": NOW - 5 * DAY, "message": "wip"}], NOW)
    assert _kinds(out) == {("stash_present", "stash@{0}", False)}
    assert "5d old" in out[0].detail


def test_working_tree_lines_classify_modified_staged_untracked():
    out = classify_working_tree([" M a.py", "M  b.py", "?? c/", "A  d.py"])
    assert {(f.kind, f.subject) for f in out} == {
        ("dirty_tracked", "a.py"), ("staged", "b.py"), ("untracked", "c/"), ("staged", "d.py")}


# --- stop gate ----------------------------------------------------------------

def _state(**kw):
    base = {"branch": "claude/x", "porcelain": [], "ahead": 0, "has_upstream": True,
            "ahead_of_master": 0, "stop_hook_active": False}
    base.update(kw)
    return base


def test_stop_blocks_on_dirty_tree_with_remedy():
    block, reason = classify_stop(_state(porcelain=[" M a.py", "?? new.py"]))
    assert block
    assert "modified: a.py" in reason and "untracked: new.py" in reason
    assert "git push -u origin HEAD" in reason


def test_stop_blocks_on_unpushed_commits_with_or_without_upstream():
    assert classify_stop(_state(ahead=2))[0]
    assert classify_stop(_state(has_upstream=False, ahead_of_master=1))[0]
    assert not classify_stop(_state(has_upstream=False, ahead_of_master=0))[0]


def test_stop_is_one_shot_and_allows_clean_or_detached():
    assert classify_stop(_state(porcelain=[" M a.py"], stop_hook_active=True)) == (False, "")
    assert classify_stop(_state()) == (False, "")
    assert classify_stop(_state(branch=None, porcelain=[" M a.py"])) == (False, "")


def test_stop_on_master_with_changes_says_create_a_branch():
    block, reason = classify_stop(_state(branch="master", porcelain=[" M a.py"]))
    assert block and "Create a branch" in reason


# --- wiring pins --------------------------------------------------------------

def test_claude_hooks_are_wired():
    settings = json.loads((_REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmds = {h["command"] for ev in ("SessionStart", "Stop") for grp in settings["hooks"][ev]
            for h in grp["hooks"]}
    assert "python3 tools/session_brief_hook.py --claude" in cmds
    assert "python3 tools/repo_hygiene.py stop-gate" in cmds


def test_ci_runs_these_tests():
    yml = (_REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    assert "tools/test_repo_hygiene.py" in yml and "tools/test_session_brief_hook.py" in yml
