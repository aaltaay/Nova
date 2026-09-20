"""A squash-merged head must be deletable; anything else must prove itself.

Nova squash-merges, so a merged branch tip is never an ancestor of master --
its content lands under a new sha. Judged on ancestry alone every merged head
is refused and accumulates on origin forever, which is what happened to #396
and #400. These tests pin the two authorizations apart: the merge is proof for
the exact commit it carried, and containment in master is still required for
everything else (#369).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import branch_cleanup as bc

REPO = "aaltaay/Nova"
REF = "claude/clever-hamilton-cn5z3o"
MERGED_TIP = "05e2db0b099360683c00673748f07d56ff0ae1c2"
LATER_TIP = "f" * 40


def gh_for(*, prs, tip, compare=None, calls=None):
    """The gh surface delete_closed_head uses, recording every call."""
    def gh(args, check=False, stdin=None):
        args = list(args)
        if calls is not None:
            calls.append(args)
        if args[:2] == ["pr", "list"]:
            if "--state" in args and args[args.index("--state") + 1] == "open":
                return SimpleNamespace(returncode=0, stdout="[]", stderr="")
            return SimpleNamespace(returncode=0, stdout=json.dumps(prs), stderr="")
        if args[0] == "api" and "/git/ref/heads/" in args[1]:
            return SimpleNamespace(
                returncode=0, stdout=json.dumps({"object": {"sha": tip}}), stderr="")
        if args[0] == "api" and "/compare/" in args[1]:
            return SimpleNamespace(
                returncode=0, stdout=json.dumps(compare or {}), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return gh


def merged_pr(oid=MERGED_TIP):
    return {"state": "MERGED", "headRefName": REF, "headRefOid": oid,
            "headRepository": {"name": "Nova"},
            "headRepositoryOwner": {"login": "aaltaay"}}


def closed_pr(oid=MERGED_TIP):
    return {"state": "CLOSED", "headRefName": REF, "headRefOid": oid,
            "headRepository": {"name": "Nova"},
            "headRepositoryOwner": {"login": "aaltaay"}}


def patch_git(monkeypatch, pushes):
    def fake_run(args, **kw):
        args = list(args)
        if args[:2] == ["git", "push"]:
            pushes.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(bc.subprocess, "run", fake_run)


def test_a_squash_merged_head_is_deleted(monkeypatch):
    # The bug behind two orphaned branches: the merge ran, called the cleanup,
    # and the cleanup refused its own merge because a squash is never an
    # ancestor. Nothing reported it, because the merge job still exits 0.
    pushes, calls = [], []
    patch_git(monkeypatch, pushes)
    gh = gh_for(prs=[merged_pr()], tip=MERGED_TIP, calls=calls)
    assert bc.delete_closed_head(gh, REPO, REF, same_repo=True) == 0
    assert pushes, "the merged head must actually be deleted"
    assert f"--force-with-lease=refs/heads/{REF}:{MERGED_TIP}" in pushes[0], (
        "deletion still leases the verified sha, so a concurrent push survives"
    )


def test_a_merged_head_needs_no_ancestry_lookup(monkeypatch):
    # Ancestry is not merely redundant for a squash -- it is the wrong
    # question, and asking it is what produced the false refusal.
    pushes, calls = [], []
    patch_git(monkeypatch, pushes)
    gh = gh_for(prs=[merged_pr()], tip=MERGED_TIP, calls=calls)
    assert bc.delete_closed_head(gh, REPO, REF, same_repo=True) == 0
    assert not [c for c in calls if c[0] == "api" and "/compare/" in c[1]]


def test_a_push_after_the_merge_is_not_covered_by_it(monkeypatch, capsys):
    # The branch moved after GitHub merged it, so the extra commit exists
    # nowhere else and the merge says nothing about it.
    pushes = []
    patch_git(monkeypatch, pushes)
    gh = gh_for(prs=[merged_pr()], tip=LATER_TIP,
                compare={"status": "diverged",
                         "merge_base_commit": {"sha": "a" * 40}})
    assert bc.delete_closed_head(gh, REPO, REF, same_repo=True) == 1
    assert not pushes
    assert "REFUSE" in capsys.readouterr().err


def test_a_closed_unmerged_head_still_has_to_prove_containment(monkeypatch, capsys):
    # #369 unchanged: a PR closed without merging can hold the only copy.
    pushes = []
    patch_git(monkeypatch, pushes)
    gh = gh_for(prs=[closed_pr()], tip=MERGED_TIP,
                compare={"status": "diverged",
                         "merge_base_commit": {"sha": "a" * 40}})
    assert bc.delete_closed_head(gh, REPO, REF, same_repo=True) == 1
    assert not pushes
    assert "needs review" in capsys.readouterr().err


def test_a_closed_unmerged_head_contained_in_master_is_still_deleted(monkeypatch):
    pushes = []
    patch_git(monkeypatch, pushes)
    gh = gh_for(prs=[closed_pr()], tip=MERGED_TIP,
                compare={"status": "identical",
                         "merge_base_commit": {"sha": MERGED_TIP}})
    assert bc.delete_closed_head(gh, REPO, REF, same_repo=True) == 0
    assert pushes


def test_an_open_pr_head_is_never_deleted(monkeypatch):
    pushes = []
    patch_git(monkeypatch, pushes)
    prs = [dict(merged_pr(), state="OPEN")]
    gh = gh_for(prs=prs, tip=MERGED_TIP)
    assert bc.delete_closed_head(gh, REPO, REF, same_repo=True) == 0
    assert not pushes


def test_the_pr_query_asks_for_the_merged_commit():
    # headRefOid is the whole basis of the merged authorization; losing it
    # from the query would silently restore the refuse-everything behaviour.
    calls = []
    gh = gh_for(prs=[], tip=MERGED_TIP, calls=calls)
    bc.delete_closed_head(gh, REPO, REF, same_repo=True)
    listing = next(c for c in calls if c[:2] == ["pr", "list"])
    assert "headRefOid" in listing[listing.index("--json") + 1]
