"""A claim must name a branch that exists (#344), without touching GitHub.

The old claim recorded an intended branch name; nothing proved it. These tests
pin the replacement: a successful claim leaves a ref on origin, every failure
path leaves neither a claim nor an orphan branch, and a release takes back only
a branch that carries no work.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

from tools import backlog_branches as bb
from tools import backlog_claim_commands as cc
from tools import backlog_claims as bc
from tools.backlog_claims import (
    CLAIM_TTL_HOURS,
    active_claim,
    format_claim,
    format_release,
    live_claims,
    resolve_claim,
)

NOW = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
REPO = "aaltaay/Nova"
TIP = "a" * 40


def package(slug, rank, issues, *footprints):
    return {
        "slug": slug, "rank": rank, "title": slug, "issues": issues,
        "readiness": "ready-now", "objective": slug, "done": [], "gate": "",
        "prs": [{"title": slug, "issues": list(issues), "note": "n", "gated": False,
                 "touches": list(footprints[0]) if footprints else []}],
    }


def plan():
    return [package("state", 1, [2, 3], ["backend/capture/mode.py"])]


class FakeGh:
    """The gh surface `backlog_branches` uses. Records every call, so a test can
    assert what was *not* done -- an orphan branch is silent otherwise."""

    def __init__(self, *, refs=None, linked=None, prs=(), compare=None, deny=False):
        self.refs = dict(refs or {})
        self.linked = {int(k): set(v) for k, v in (linked or {}).items()}
        self.prs = list(prs)
        self.compare = compare
        self.deny = deny
        self.calls: list[list[str]] = []

    def _ok(self, stdout=""):
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    def _fail(self, stderr):
        return SimpleNamespace(returncode=1, stdout="", stderr=stderr)

    @property
    def creates(self):
        return [c for c in self.calls if c[:2] == ["issue", "develop"] and "--name" in c]

    def __call__(self, args, **kw):
        args = list(args)
        self.calls.append(args)
        if args[0] == "api":
            path = args[1]
            if "/git/ref/heads/" in path:
                # gh receives the ref percent-encoded, as the real API needs.
                ref = unquote(path.split("/git/ref/heads/", 1)[1])
                if ref not in self.refs:
                    return self._fail("gh: Not Found (HTTP 404)")
                return self._ok(json.dumps({"object": {"sha": self.refs[ref]}}))
            if "/compare/" in path:
                return self._ok(json.dumps(self.compare or {}))
            if "/branches/" in path:
                if unquote(path.split("/branches/", 1)[1]) not in self.refs:
                    return self._fail("gh: Not Found (HTTP 404)")
                return self._ok(json.dumps(
                    {"commit": {"commit": {"committer": {"date": "2026-09-20T11:50:00Z"}}}}))
        if args[:2] == ["issue", "develop"]:
            issue = int(args[2])
            if "--list" in args:
                return self._ok("\n".join(f"{b}\turl" for b in sorted(self.linked.get(issue, ()))))
            if self.deny:
                return self._fail("HTTP 403: Resource not accessible by integration")
            name = args[args.index("--name") + 1]
            self.refs.setdefault(name, TIP)
            self.linked.setdefault(issue, set()).add(name)
            return self._ok()
        if args[:2] == ["pr", "list"]:
            return self._ok(json.dumps(self.prs))
        return self._ok()


# --------------------------------------------------------------------------
# ensure_linked_branch


def test_a_claim_without_a_branch_cuts_one_and_links_the_anchor():
    gh = FakeGh()
    link = bb.ensure_linked_branch(gh, REPO, anchor=2, branch="agent/state-0", extra_issues=(3,))
    assert link.ok and link.created and link.tip == TIP
    assert 2 in link.linked, "the anchor issue must carry the Development link"


def test_an_existing_branch_is_never_recut():
    # A re-claim or --force must not touch a branch that already holds work.
    gh = FakeGh(refs={"agent/state-0": "b" * 40}, linked={2: ["agent/state-0"]})
    link = bb.ensure_linked_branch(gh, REPO, anchor=2, branch="agent/state-0")
    assert link.ok and not link.created and link.tip == "b" * 40
    assert not gh.creates, "an existing linked branch needs no mutation at all"


def test_a_second_issue_failing_to_link_does_not_fail_the_claim():
    # Whether GitHub links an existing ref to a second issue is unverified, so
    # the batch's extras are best-effort; the ref is what the claim promises.
    class OneLinkOnly(FakeGh):
        def __call__(self, args, **kw):
            if list(args)[:2] == ["issue", "develop"] and "--name" in list(args) \
                    and int(list(args)[2]) != 2:
                self.calls.append(list(args))
                return self._fail("reference already exists")
            return super().__call__(args, **kw)

    gh = OneLinkOnly()
    link = bb.ensure_linked_branch(gh, REPO, anchor=2, branch="agent/state-0", extra_issues=(3,))
    assert link.ok and link.linked == (2,)


def test_a_token_that_cannot_write_branches_is_reported_not_guessed():
    gh = FakeGh(deny=True)
    link = bb.ensure_linked_branch(gh, REPO, anchor=2, branch="agent/state-0")
    assert not link.ok and link.denied


def test_an_unreadable_ref_lookup_is_not_read_as_absence():
    # "I could not look" must never become "it is not there", or a re-claim
    # would cut over a branch that already carries someone's work.
    gh = FakeGh()
    gh.refs = {}
    def boom(args, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="gh: server error (HTTP 500)")
    with pytest.raises(bb.BranchLookupError):
        bb.branch_tip(boom, REPO, "agent/state-0")


# --------------------------------------------------------------------------
# cmd_claim


def claim_args(**kw):
    return argparse.Namespace(package="state", batch=0, agent="worker-b",
                              branch="agent/state-0", force=False, **kw)


def setup_claim(monkeypatch, gh, held=None):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(cc, "datetime", FrozenDatetime)
    monkeypatch.setattr(cc, "load_packages", plan)
    monkeypatch.setattr(cc, "fetch_issues", lambda: [{"number": 2}, {"number": 3}])
    monkeypatch.setattr(cc, "fetch_comments", lambda n: [])
    monkeypatch.setattr(cc, "active_claim", lambda *a, **kw: None)
    monkeypatch.setattr(cc, "live_claims", lambda *a, **kw: held or {})
    monkeypatch.setattr(cc, "run_gh", gh)


def releases(gh):
    return [c for c in gh.calls if c[:2] == ["issue", "comment"]]


def test_a_successful_claim_leaves_the_branch_on_origin(monkeypatch, capsys):
    gh = FakeGh()
    setup_claim(monkeypatch, gh)
    assert cc.cmd_claim(claim_args()) == 0
    assert "agent/state-0" in gh.refs
    out = capsys.readouterr().out
    assert "on origin at" in out and "git checkout agent/state-0" in out


def test_a_claim_that_cannot_cut_its_branch_is_withdrawn(monkeypatch, capsys):
    # The invariant this whole change exists for: `claimed` must never outlive
    # a branch nobody can fetch.
    gh = FakeGh(deny=True)
    setup_claim(monkeypatch, gh)
    assert cc.cmd_claim(claim_args()) == 2
    assert len(releases(gh)) == 4, "two claim comments, then two withdrawals"
    err = capsys.readouterr().err
    assert "Claim withdrawn" in err and "cannot write branches" in err


def test_losing_the_race_cuts_no_branch(monkeypatch, capsys):
    gh = FakeGh()
    snapshots = iter([{}, {2: {"agent": "worker-a", "batch": "other#0",
                              "branch": "codex/other", "at": "2026-09-20T10:00:00Z"}}])
    setup_claim(monkeypatch, gh)
    monkeypatch.setattr(cc, "live_claims", lambda *a, **kw: next(snapshots))
    assert cc.cmd_claim(claim_args()) == 1
    assert not gh.creates, "a yielding agent must not leave an orphan ref"
    assert "agent/state-0" not in gh.refs


# --------------------------------------------------------------------------
# cmd_release


def release_args(**kw):
    fields = {"package": "state", "batch": 0, "agent": "worker-b",
              "branch": None, "keep_branch": False}
    return argparse.Namespace(**{**fields, **kw})


def setup_release(monkeypatch, gh, claim_branch="agent/state-0"):
    monkeypatch.setattr(cc, "load_packages", plan)
    monkeypatch.setattr(cc, "fetch_issues", lambda: [{"number": 2}, {"number": 3}])
    monkeypatch.setattr(cc, "fetch_comments", lambda n: [])
    # R5: release looks up its OWN claim, not whoever is elected.
    monkeypatch.setattr(cc, "claim_for",
                        lambda *a, **kw: {"branch": claim_branch})
    monkeypatch.setattr(cc, "run_gh", gh)
    monkeypatch.setattr(bb.subprocess, "run",
                        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="", stderr=""))


def test_release_takes_back_a_branch_that_never_carried_work(monkeypatch, capsys):
    gh = FakeGh(refs={"agent/state-0": TIP},
                compare={"status": "identical", "merge_base_commit": {"sha": TIP}})
    setup_release(monkeypatch, gh)
    assert cc.cmd_release(release_args()) == 0
    assert "deleted unused branch agent/state-0" in capsys.readouterr().out


def test_release_keeps_a_branch_that_carries_commits(monkeypatch, capsys):
    # #369: the release clears the claim, never someone's unmerged work.
    gh = FakeGh(refs={"agent/state-0": TIP},
                compare={"status": "ahead", "merge_base_commit": {"sha": "c" * 40}})
    setup_release(monkeypatch, gh)
    assert cc.cmd_release(release_args()) == 0
    assert "RETAIN agent/state-0" in capsys.readouterr().err


def test_release_keeps_a_branch_that_has_a_pull_request(monkeypatch, capsys):
    gh = FakeGh(refs={"agent/state-0": TIP}, prs=[{"number": 9, "state": "OPEN"}])
    setup_release(monkeypatch, gh)
    assert cc.cmd_release(release_args()) == 0
    assert "it has a pull request" in capsys.readouterr().out


def test_keep_branch_releases_the_claim_and_nothing_else(monkeypatch):
    gh = FakeGh(refs={"agent/state-0": TIP})
    setup_release(monkeypatch, gh)
    assert cc.cmd_release(release_args(keep_branch=True)) == 0
    assert not [c for c in gh.calls if c[:2] == ["pr", "list"]]


# --------------------------------------------------------------------------
# staleness


def claim_comment(hours_ago, branch="agent/state-0"):
    at = NOW - timedelta(hours=hours_ago)
    return [{"body": format_claim(agent="worker-b", batch="state#0", branch=branch, at=at),
             "createdAt": at.strftime("%Y-%m-%dT%H:%M:%SZ")}]


def test_a_working_agent_is_not_stale_just_because_the_comment_aged():
    # The gap the old code had: an agent six hours into real work and one that
    # died at minute two both read as stale off the comment alone.
    comments = claim_comment(CLAIM_TTL_HOURS + 2)
    assert active_claim(comments, now=NOW)["stale"] is True
    fresh = active_claim(comments, now=NOW,
                         branch_activity_for=lambda ref: NOW - timedelta(minutes=30))
    assert fresh["stale"] is False and fresh["age_hours"] == 0.5


def test_an_abandoned_branch_still_goes_stale():
    comments = claim_comment(CLAIM_TTL_HOURS + 2)
    old = active_claim(
        comments, now=NOW,
        branch_activity_for=lambda ref: NOW - timedelta(hours=CLAIM_TTL_HOURS + 1))
    assert old["stale"] is True


def test_the_claim_comment_describes_the_staleness_rule_it_actually_uses():
    body = format_claim(agent="worker-b", batch="state#0", branch="agent/state-0", at=NOW)
    assert "last commit" in body, "the comment must not promise what the code cannot do"


# --------------------------------------------------------------------------
# the enforcement path agrees with the display (P1)


def labelled(*numbers):
    return [{"number": n, "labels": [{"name": "claimed"}]} for n in numbers]


def test_next_keeps_a_batch_whose_holder_is_still_committing(monkeypatch):
    # The bug: `claims` consulted the branch and `next` did not, so a holder
    # past the TTL but actively committing read as held on the display and
    # stale to the picker -- which handed the same batch to a second agent.
    monkeypatch.setattr(bc, "fetch_comments",
                        lambda n: claim_comment(CLAIM_TTL_HOURS + 2))
    assert live_claims(labelled(2), now=NOW) == {}, "comment age alone calls it stale"
    held = live_claims(labelled(2), now=NOW,
                       branch_activity_for=lambda ref: NOW - timedelta(minutes=5))
    assert set(held) == {2}, "a branch committed 5 minutes ago is not an abandoned claim"


def test_next_still_reclaims_a_batch_whose_branch_was_abandoned(monkeypatch):
    monkeypatch.setattr(bc, "fetch_comments",
                        lambda n: claim_comment(CLAIM_TTL_HOURS + 2))
    held = live_claims(labelled(2), now=NOW,
                       branch_activity_for=lambda ref: NOW - timedelta(days=2))
    assert held == {}, "an old claim on an untouched branch must still expire"


def test_a_live_claim_costs_no_branch_lookup(monkeypatch):
    # Branch activity can only revive a claim, never expire one, so a holder
    # that is live on comment age never pays for the call. This is what keeps
    # `next` cheap now that it resolves the same way `claims` does.
    monkeypatch.setattr(bc, "fetch_comments", lambda n: claim_comment(1))
    looked_up = []
    held = live_claims(labelled(2), now=NOW,
                       branch_activity_for=lambda ref: looked_up.append(ref))
    assert set(held) == {2} and looked_up == []


def test_resolve_claim_without_a_resolver_is_the_old_answer():
    comments = claim_comment(CLAIM_TTL_HOURS + 2)
    assert resolve_claim(comments, now=NOW) == active_claim(comments, now=NOW)


def test_every_enforcement_path_resolves_the_same_way(monkeypatch):
    # A regression guard with teeth: if a future edit reintroduces a bare
    # active_claim in cmd_claim, `claims` and `next` silently disagree again.
    source = Path(cc.__file__)
    text = source.read_text(encoding="utf-8")
    body = text.split("def cmd_claim(", 1)[1].split("def cmd_release(", 1)[0]
    assert "active_claim(" not in body, (
        "cmd_claim must resolve claims through resolve_claim so the picker and "
        "the claims view share one definition of stale"
    )


# --------------------------------------------------------------------------
# a withdrawn claim leaves no label behind (P2)


def test_a_withdrawn_claim_drops_the_label_it_added(monkeypatch, capsys):
    # `claimed` is half the claim: live_claims uses it as its cheap filter, so
    # a label with nothing behind it makes the backlog look held.
    gh = FakeGh(deny=True)
    setup_claim(monkeypatch, gh)
    assert cc.cmd_claim(claim_args()) == 2
    removed = [c for c in gh.calls if "--remove-label" in c]
    assert {int(c[2]) for c in removed} == {2, 3}


def markers(*bodies):
    return [{"body": b, "createdAt": f"2026-09-20T11:5{i}:00Z"}
            for i, b in enumerate(bodies)]


def winner_claim(agent="worker-a"):
    return format_claim(agent=agent, batch="state#0", branch=f"{agent}/x",
                        at=NOW - timedelta(minutes=10))


def test_a_withdrawal_never_strips_a_concurrent_winners_label(monkeypatch):
    # Drives the real active_claim on real markers. The earlier version of
    # this test monkeypatched active_claim to return a winner -- which is the
    # exact function whose behaviour was the bug -- so it asserted the
    # intention and passed while the code deleted the winner's label.
    gh = FakeGh()
    monkeypatch.setattr(cc, "run_gh", gh)
    monkeypatch.setattr(cc, "fetch_comments", lambda n: markers(
        winner_claim(),
        format_release(agent="worker-b", batch="state#0"),
    ))
    cc.post_release([2, 3], agent="worker-b", batch="state#0")
    assert not [c for c in gh.calls if "--remove-label" in c], (
        "a losing agent's release speaks only for itself; the label is the "
        "winner's advertisement and live_claims filters on it"
    )


def test_a_withdrawal_drops_the_label_when_no_claim_survives(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(cc, "run_gh", gh)
    monkeypatch.setattr(cc, "fetch_comments", lambda n: markers(
        winner_claim(agent="worker-b"),
        format_release(agent="worker-b", batch="state#0"),
    ))
    cc.post_release([2, 3], agent="worker-b", batch="state#0")
    assert {int(c[2]) for c in gh.calls if "--remove-label" in c} == {2, 3}


def test_a_release_names_the_agent_it_speaks_for():
    # Identity is the whole basis of the rule above; an anonymous release
    # silently restores the behaviour that dropped live claims.
    assert "agent: worker-b" in format_release(agent="worker-b", batch="state#0")


def test_a_loser_yielding_leaves_the_winner_visible_to_next():
    # The same defect one level up: live_claims filters on the label, but
    # active_claim also has to still report the holder.
    held = active_claim(markers(
        winner_claim(),
        format_claim(agent="worker-b", batch="state#0", branch="b/x", at=NOW),
        format_release(agent="worker-b", batch="state#0"),
    ), now=NOW)
    assert held and held["agent"] == "worker-a"


def test_a_legacy_anonymous_release_still_clears_the_issue():
    # Releases written before they carried an agent keep their old meaning,
    # so historical comments resolve exactly as they always did.
    held = active_claim(markers(
        winner_claim(),
        "<!-- nova-claim-release -->\nReleased by `worker-b` (batch `state#0`).",
    ), now=NOW)
    assert held is None


def test_release_clears_the_label_through_the_same_path(monkeypatch):
    gh = FakeGh(refs={"agent/state-0": TIP},
                compare={"status": "identical", "merge_base_commit": {"sha": TIP}})
    setup_release(monkeypatch, gh)
    monkeypatch.setattr(cc, "active_claim", lambda *a, **kw: None)
    assert cc.cmd_release(release_args()) == 0
    removed = [c for c in gh.calls if "--remove-label" in c]
    assert {int(c[2]) for c in removed} == {2, 3}
