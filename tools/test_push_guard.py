"""push_guard: commits added to a merged PR's branch are refused before the push (follow-up to PR #957).

The git cases run against a real throwaway repository; gh is replaced by a lookup function.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import push_guard  # noqa: E402
from tools.push_guard import (  # noqa: E402
    HOOK_MARKER,
    HOOK_SCRIPT,
    LatePush,
    check,
    install,
    merged_pr_for,
    parse_pre_push,
    refusal,
    run_pre_push,
)
from tools.repo_hygiene_lib import classify_stop  # noqa: E402

ZERO = "0" * 40


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
         *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"add {name}")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """master at A (also origin/master), branch feat at B = the merged PR's head."""
    _git(tmp_path, "init", "-q", "-b", "master")
    base = _commit(tmp_path, "a.txt")
    _git(tmp_path, "update-ref", "refs/remotes/origin/master", base)
    _git(tmp_path, "switch", "-q", "-c", "feat")
    _commit(tmp_path, "b.txt")
    return tmp_path


def _merged(repo: Path, head: str | None = None, number: int = 7):
    sha = head or _git(repo, "rev-parse", "feat")
    rows = [{"number": number, "state": "MERGED", "headRefOid": sha, "url": f"https://x/pull/{number}"}]
    return lambda _branch, _cwd: rows


# --- pure -----------------------------------------------------------------------

def test_merged_pr_for_prefers_open_then_newest_merged():
    assert merged_pr_for([{"number": 1, "state": "MERGED", "headRefOid": "a"},
                          {"number": 2, "state": "OPEN", "headRefOid": "b"}]) is None
    assert merged_pr_for([{"number": 1, "state": "MERGED", "headRefOid": "a"},
                          {"number": 3, "state": "MERGED", "headRefOid": "c"},
                          {"number": 2, "state": "CLOSED", "headRefOid": "b"}])["number"] == 3
    assert merged_pr_for([{"number": 2, "state": "CLOSED", "headRefOid": "b"}]) is None
    assert merged_pr_for([]) is None


def test_parse_pre_push_keeps_branch_pushes_only():
    stdin = "\n".join([
        f"refs/heads/feat {'1' * 40} refs/heads/feat {'2' * 40}",
        f"(delete) {ZERO} refs/heads/gone {'3' * 40}",
        f"refs/tags/v1 {'4' * 40} refs/tags/v1 {ZERO}",
        f"HEAD {'5' * 40} refs/heads/other {ZERO}",
        "garbage",
    ])
    assert parse_pre_push(stdin) == [("feat", "1" * 40), ("other", "5" * 40)]


def test_refusal_says_branch_from_master_cherry_pick_new_pr():
    late = LatePush(pr=868, url="https://x/pull/868", branch="fix/x", merged_head="a" * 40,
                    commits=[("b" * 40, "review fix"), ("c" * 40, "second fix")])
    text = refusal(late, pushed=False)
    assert "PR #868" in text and "already merged" in text and "Do not push" in text
    assert "origin/master" in text and f"git cherry-pick -x {'b' * 12} {'c' * 12}" in text
    assert "gh pr create" in text and "review fix" in text
    pushed = refusal(late, pushed=True)
    assert "recover/fix/x" in pushed and "Do not push" not in pushed


def test_refusal_caps_the_listed_commits_but_cherry_picks_all():
    commits = [(f"{i:040d}", f"c{i}") for i in range(14)]
    text = refusal(LatePush(1, "u", "b", "a" * 40, commits), pushed=False)
    assert "4 more" in text and f"{13:040d}"[:12] in text


# --- against real git -----------------------------------------------------------

def test_tip_at_the_merged_head_is_fine(repo: Path):
    assert check("feat", "HEAD", cwd=str(repo), lookup=_merged(repo)) == push_guard.Verdict()


def test_commit_after_the_merged_head_is_late(repo: Path):
    merged = _merged(repo)
    late_sha = _commit(repo, "c.txt")
    verdict = check("feat", "HEAD", cwd=str(repo), lookup=merged)
    assert verdict.late is not None and not verdict.unknown
    assert verdict.late.pr == 7 and verdict.late.commits == [(late_sha, "add c.txt")]


def test_master_merged_into_the_branch_is_not_counted(repo: Path):
    merged = _merged(repo)
    _git(repo, "switch", "-q", "master")
    upstream = _commit(repo, "m.txt")
    _git(repo, "update-ref", "refs/remotes/origin/master", upstream)
    _git(repo, "switch", "-q", "feat")
    _git(repo, "merge", "-q", "--no-edit", "master")
    assert check("feat", "HEAD", cwd=str(repo), lookup=merged).late is None


def test_a_hand_resolved_merge_is_late_work(repo: Path):
    """The resolution lives only in the merge commit, so it is not in the merged head or master."""
    (repo / "a.txt").write_text("branch's a", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "branch edits a")
    merged = _merged(repo)  # the PR merged with this edit as its head
    _git(repo, "switch", "-q", "master")
    (repo / "a.txt").write_text("master's a", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "master edits a")
    _git(repo, "update-ref", "refs/remotes/origin/master", _git(repo, "rev-parse", "HEAD"))
    _git(repo, "switch", "-q", "feat")
    assert subprocess.run(["git", "merge", "-q", "master"], cwd=repo, capture_output=True).returncode
    (repo / "a.txt").write_text("resolved by hand", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "--no-edit")
    late = check("feat", "HEAD", cwd=str(repo), lookup=merged).late
    assert late is not None and late.commits[0][1].startswith(push_guard.MERGE_TAG)
    assert "-m 1" in refusal(late, pushed=False)


def test_open_pr_or_no_pr_or_master_never_refuses(repo: Path):
    _commit(repo, "c.txt")
    sha = _git(repo, "rev-parse", "feat")
    reopened = [{"number": 7, "state": "MERGED", "headRefOid": sha, "url": "u"},
                {"number": 9, "state": "OPEN", "headRefOid": sha, "url": "u"}]
    assert check("feat", "HEAD", cwd=str(repo), lookup=lambda b, c: reopened).late is None
    assert check("feat", "HEAD", cwd=str(repo), lookup=lambda b, c: []).late is None
    assert check("master", "HEAD", cwd=str(repo), lookup=_merged(repo)) == push_guard.Verdict()


def test_no_gh_fails_open_and_says_so(repo: Path):
    _commit(repo, "c.txt")
    verdict = check("feat", "HEAD", cwd=str(repo), lookup=lambda b, c: None)
    assert verdict.late is None and "gh" in verdict.unknown


def test_unfetchable_merged_head_fails_open(repo: Path):
    verdict = check("feat", "HEAD", cwd=str(repo), lookup=_merged(repo, head="f" * 40))
    assert verdict.late is None and "could not be fetched" in verdict.unknown


def test_pre_push_refuses_late_and_lets_unknown_through(repo: Path):
    merged = _merged(repo)
    sha = _commit(repo, "c.txt")
    said: list[str] = []
    line = f"refs/heads/feat {sha} refs/heads/feat {ZERO}"
    assert run_pre_push(line, cwd=str(repo), lookup=merged, err=said.append) == 1
    assert "refused" in said[0] and "cherry-pick -x" in said[0]
    said.clear()
    assert run_pre_push(line, cwd=str(repo), lookup=lambda b, c: None, err=said.append) == 0
    assert "pushing anyway" in said[0]


# --- the stop gate --------------------------------------------------------------

def _state(**kw):
    base = {"branch": "claude/x", "porcelain": [], "ahead": 0, "has_upstream": True,
            "ahead_of_master": 3, "stop_hook_active": False, "late_push": ""}
    base.update(kw)
    return base


def test_stop_refuses_late_commits_even_on_a_clean_pushed_branch():
    block, reason = classify_stop(_state(late_push="PR #868 (u) is already merged."))
    assert block and "PR #868" in reason and "git push -u origin HEAD" not in reason


def test_stop_late_reason_carries_the_dirty_tree_too_and_stays_one_shot():
    block, reason = classify_stop(_state(late_push="merged.", porcelain=[" M a.py"], ahead=1))
    assert block and "modified: a.py" in reason and "1 commit(s) not on origin" in reason
    assert classify_stop(_state(late_push="merged.", stop_hook_active=True)) == (False, "")


# --- install --------------------------------------------------------------------

def test_install_is_idempotent_refuses_a_foreign_hook_and_uninstalls(repo: Path):
    code, message = install(str(repo))
    hook = repo / ".git" / "hooks" / "pre-push"
    assert code == 0 and hook.is_file() and HOOK_MARKER in hook.read_text(encoding="utf-8")
    assert install(str(repo))[0] == 0
    assert install(str(repo), uninstall=True)[0] == 0 and not hook.exists()
    hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    code, message = install(str(repo))
    assert code == 2 and "not touched" in message
    assert install(str(repo), uninstall=True)[0] == 0 and hook.exists()


def test_a_hook_with_anything_else_in_it_is_never_touched(repo: Path):
    install(str(repo))
    hook = repo / ".git" / "hooks" / "pre-push"
    hook.write_text(HOOK_SCRIPT + "\necho another tool\n", encoding="utf-8")
    code, message = install(str(repo))
    assert code == 2 and "not touched" in message
    install(str(repo), uninstall=True)
    assert "another tool" in hook.read_text(encoding="utf-8")


def test_relative_hooks_path_installs_in_every_worktree(repo: Path, tmp_path: Path):
    """git resolves a relative core.hooksPath in the worktree that runs the hook."""
    _git(repo, "config", "core.hooksPath", "custom-hooks")
    other = tmp_path / "second-worktree"
    _git(repo, "worktree", "add", "-q", "-b", "second", str(other))
    code, message = install(str(other))
    assert code == 0
    assert (repo / "custom-hooks" / "pre-push").is_file() and (other / "custom-hooks" / "pre-push").is_file()
    assert "again after adding a worktree" in message
    install(str(repo), uninstall=True)
    assert not (repo / "custom-hooks" / "pre-push").exists() and not (other / "custom-hooks" / "pre-push").exists()


def test_hook_script_blocks_only_on_the_guards_refusal():
    assert "1) printf" in HOOK_SCRIPT and "exit 1 ;;" in HOOK_SCRIPT and HOOK_SCRIPT.rstrip().endswith("exit 0")
    assert "push-guard" in HOOK_SCRIPT and "exec " not in HOOK_SCRIPT
    sh = shutil.which("sh")
    if sh:
        assert subprocess.run([sh, "-n"], input=HOOK_SCRIPT, text=True).returncode == 0


def test_ci_runs_these_tests():
    yml = (_REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    assert "tools/test_push_guard.py" in yml


def _stub(root: Path, code: int, said: str) -> None:
    (root / "tools").mkdir(exist_ok=True)
    (root / "tools" / "repo_hygiene.py").write_text(
        f"import sys\nsys.stdin.read()\nprint({said!r}, file=sys.stderr)\nsys.exit({code})\n", encoding="utf-8")


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh")
def test_installed_hook_falls_back_to_the_main_checkout_and_blocks_only_on_1(repo: Path, tmp_path: Path):
    """A branch cut before the guard answers 2 (usage error); the main checkout's copy decides."""
    old = tmp_path / "old-branch"
    _git(repo, "worktree", "add", "-q", "-b", "old", str(old))
    _stub(old, 2, "usage: no push-guard here")
    hook = install(str(repo))[0] == 0 and (repo / ".git" / "hooks" / "pre-push")

    def push(main_code: int) -> subprocess.CompletedProcess:
        _stub(repo, main_code, f"main says {main_code}")
        return subprocess.run([shutil.which("sh"), str(hook), "origin", "url"], cwd=old, text=True,
                              input=f"refs/heads/old {'1' * 40} refs/heads/old {ZERO}\n", capture_output=True)

    refused = push(1)
    assert refused.returncode == 1 and "main says 1" in refused.stderr and "usage" not in refused.stderr
    assert push(0).returncode == 0
    assert push(3).returncode == 0  # a broken guard never blocks
