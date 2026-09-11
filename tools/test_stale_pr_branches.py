"""Classifier tests for leftover merged/closed PR head branches."""

from tools.stale_pr_branches import classify_stale_branches


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
