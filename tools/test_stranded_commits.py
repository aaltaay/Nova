"""Commits pushed after a PR merged are carried to master, never lost (operator report 2026-10-14)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import stranded_commits as sc

PR = sc.Merged(951, "fix(followed-traders): say when the feed reads the stream's past", "fix/following", "a" * 40)
LATE, LATER = "b" * 40, "c" * 40
# History: merged head a -> b (pushed after the merge) -> c (pushed after that).
HISTORY = {("a" * 40, LATE), ("a" * 40, LATER), (LATE, LATER)}


def ancestor(a: str, b: str) -> bool:
    return a == b or (a, b) in HISTORY


def decide(tip: str, **kw) -> sc.Plan:
    args = {"open_pr": False, "open_recovery": False, "carried": set(), "is_ancestor": ancestor} | kw
    return sc.plan(PR, tip, **args)


def test_a_commit_pushed_after_the_merge_is_landed_from_the_merged_head():
    assert decide(LATE) == sc.Plan("land", "commits after the merge", PR.head)


def test_nothing_after_the_merge_or_an_open_pr_is_left_alone():
    assert decide(PR.head).action == "skip"
    assert decide(LATE, open_pr=True).reason == "an open PR carries the branch"


def test_a_tip_already_carried_is_never_carried_twice():
    assert decide(LATE, carried={LATE}).reason == "this tip is already carried"


def test_a_later_push_extends_the_open_recovery_from_the_last_carried_tip():
    assert decide(LATER, carried={LATE}, open_recovery=True) == sc.Plan("extend", "commits after the merge", LATE)


def test_a_branch_rewritten_past_its_merged_head_opens_an_issue():
    assert decide("d" * 40).action == "issue"


def test_the_tip_marker_is_read_back_from_pr_and_issue_bodies():
    body = sc._body.__doc__ or ""  # bodies are built with the marker; read one back as a sweep would
    text = f"lands them\n<!-- {sc.TIP_MARKER} {LATE} -->\n"
    assert sc.recorded_tips([body, text, "no marker"]) == {LATE}


def test_the_recovery_pr_keeps_the_original_kind_and_names_the_pr():
    assert sc.recovery_title(PR) == "fix(followed-traders): land the commits pushed after #951 merged"
    assert sc.recovery_title(sc.Merged(1, "Some title", "b", "h")).startswith("fix: land")
    assert sc.recovery_branch("fix/following") == "recover/fix/following"


def test_merged_prs_skip_forks_protected_and_recovery_heads():
    rows = ('[{"number":1,"title":"t","headRefName":"fix/a","headRefOid":"x","isCrossRepository":false},'
            '{"number":2,"title":"t","headRefName":"fix/b","headRefOid":"x","isCrossRepository":true},'
            '{"number":3,"title":"t","headRefName":"recover/fix/a","headRefOid":"x","isCrossRepository":false}]')
    assert [m.number for m in sc.merged_prs(lambda args: rows, 3)] == [1]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _git(tmp_path, "init", "-q", "-b", "master")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / "f.txt").write_text("one\n")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _commit(repo: Path, name: str, text: str, msg: str) -> str:
    (repo / name).write_text(text)
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def test_pick_drops_a_commit_master_already_has_and_carries_the_rest(repo: Path):
    _git(repo, "checkout", "-q", "-b", "side")
    same = _commit(repo, "g.txt", "same\n", "redone later")
    new = _commit(repo, "h.txt", "new\n", "the stranded fix")
    _git(repo, "checkout", "-q", "master")
    _commit(repo, "g.txt", "same\n", "a later PR did the same work")
    assert sc.pick([same, new]) == ""
    assert (repo / "h.txt").read_text() == "new\n"
    assert _git(repo, "log", "-1", "--format=%s") == "the stranded fix"


def test_pick_stops_at_a_conflict_and_leaves_the_tree_clean(repo: Path):
    _git(repo, "checkout", "-q", "-b", "side")
    clash = _commit(repo, "f.txt", "theirs\n", "conflicts with master")
    _git(repo, "checkout", "-q", "master")
    _commit(repo, "f.txt", "ours\n", "master moved on")
    assert sc.pick([clash]) == clash
    assert _git(repo, "status", "--porcelain") == ""


def test_a_branch_run_finds_its_merged_pr_however_old_and_a_broad_scan_keeps_the_window():
    """PR #957 review: a push to a branch whose PR merged a week ago must still be carried."""
    seen: list[list[str]] = []

    def runner(args: list[str]) -> str:
        seen.append(args)
        return "[]"

    sc.merged_prs(runner, 3, "fix/old")
    sc.merged_prs(runner, 3)
    branch_run, broad = seen
    assert "--search" not in branch_run and branch_run[branch_run.index("--head") + 1] == "fix/old"
    assert broad[broad.index("--search") + 1].startswith("merged:>=")


def test_a_recovery_issue_goes_on_the_delivery_board():
    """PR #957 review: a GITHUB_TOKEN issue starts no board workflow, so the sweep boards it itself."""
    calls: list[list[str]] = []

    def runner(args: list[str]) -> str:
        calls.append(args)
        return "https://github.com/aaltaay/Nova/issues/999\n" if args[:2] == ["issue", "create"] else ""

    boarded: list[str] = []
    done = sc.report_issue(PR, LATE, [], "rewritten", runner=runner, boarder=boarded.append)
    assert boarded == ["https://github.com/aaltaay/Nova/issues/999"] and done.endswith("issues/999")
    create = next(c for c in calls if c[:2] == ["issue", "create"])
    assert "P1" in create and create[create.index("--milestone") + 1] == "00 - Untriaged"


def test_a_refused_recovery_pr_becomes_an_issue_naming_the_pushed_branch(repo: Path, tmp_path_factory):
    """2026-10-14: the repository did not allow Actions to open PRs; the refusal must reach a person, not a red run."""
    origin = tmp_path_factory.mktemp("origin")
    _git(origin, "init", "-q", "--bare")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "origin", "master")
    _git(repo, "checkout", "-q", "-b", "fix/late")
    head = _git(repo, "rev-parse", "HEAD")
    late = _commit(repo, "late.txt", "fix\n", "the review fix pushed after the merge")
    _git(repo, "checkout", "-q", "master")
    _git(repo, "fetch", "-q", "origin")
    calls: list[list[str]] = []

    def runner(args: list[str]) -> str:
        calls.append(args)
        if args[:2] == ["pr", "create"]:
            raise subprocess.CalledProcessError(1, args, stderr="GitHub Actions is not permitted to create pull requests")
        return "https://github.com/aaltaay/Nova/issues/998\n" if args[:2] == ["issue", "create"] else ""

    boarded: list[str] = []
    pr = sc.Merged(957, "fix(delivery): x", "fix/late", head)
    done = sc.land(pr, late, sc.Plan("land", "", head), runner=runner, dry_run=False, boarder=boarded.append)
    assert done.endswith("issues/998") and boarded == ["https://github.com/aaltaay/Nova/issues/998"]
    assert _git(origin, "rev-parse", "recover/fix/late") != head  # the commits are on the branch the issue names
    body = next(c for c in calls if c[:2] == ["issue", "create"])
    text = body[body.index("--body") + 1]
    assert "compare/master...recover/fix/late" in text and "not permitted" in text and late in text
    assert not any(c[:2] == ["workflow", "run"] for c in calls)


def test_a_tip_an_issue_only_reported_never_moves_the_base():
    """PR #960 review: a refused PR's issue named LATE, but LATE landed nowhere. A later push must carry
    LATE's commits too, from the merged head, not only the newest delta."""
    assert decide(LATER, reported=frozenset({LATE})) == sc.Plan("land", "commits after the merge", PR.head)
    assert decide(LATE, reported=frozenset({LATE})).reason == "an issue already names this tip"
