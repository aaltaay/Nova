"""Regression tests for cross-batch file ownership (#367), without GitHub."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import backlog_claim_commands as cc
from tools import backlog_commands as commands
from tools.backlog_claims import active_claim, format_claim, format_release, parse_claim
from tools.backlog_footprints import (
    OVERLAP_REASON, UNKNOWN_FOOTPRINT, batch_touches, claim_conflicts,
    claim_touches, normalize_touches, overlapping_paths,
)
from tools.backlog_plan import load_packages, next_pr, pick_next
from tools.backlog_triage import build_parser

NOW = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


def package(slug, rank, issues, *footprints):
    return {
        "slug": slug, "rank": rank, "title": slug, "issues": issues,
        "readiness": "ready-now", "objective": slug, "done": [], "gate": "",
        "prs": [{"title": f"{slug}-{i}", "issues": [n], "note": "n", "gated": False,
                 "touches": paths} for i, (n, paths) in enumerate(zip(issues, footprints))],
    }


def plan():
    return [package("recorder", 1, [1], ["backend/capture/"]),
            package("state", 2, [2, 3], ["backend/capture/mode.py"], ["frontend/src/safe.ts"]),
            package("gateway", 3, [4], ["backend/ibkr/"])]


def holder(**kw):
    return {"agent": "worker-a", "batch": "recorder#0", "branch": "codex/recorder",
            "at": "2026-09-20T11:00:00Z", "stale": False, **kw}


@pytest.mark.parametrize("left,right,want", [
    (["backend/a.py"], ["backend/a.py"], ["backend/a.py"]),
    (["backend/capture/"], ["backend/capture/mode.py"], ["backend/capture/mode.py"]),
    (["backend/capture/mode.py"], ["backend/"], ["backend/capture/mode.py"]),
    (["backend/"], ["backend/capture/"], ["backend/capture/"]),
    (["backend/capture/"], ["backend/capture2/a.py"], []),
    (["backend/capture"], ["backend/capture/a.py"], []),
    (["a.py"], ["a.py.bak"], []),
    (["./Backend\\Capture\\"], ["backend/capture/A.py"], ["backend/capture/a.py"]),
])
def test_file_and_directory_overlap_boundaries(left, right, want):
    assert overlapping_paths(left, right) == want
    assert overlapping_paths(right, left) == want


@pytest.mark.parametrize("path", ["../a.py", "/a.py", "C:/a.py", "backend/*.py", "a//b", ""])
def test_invalid_footprints_are_rejected(path):
    with pytest.raises(ValueError):
        normalize_touches([path])


def test_claim_snapshots_round_trip_and_do_not_follow_later_plan_changes():
    body = format_claim(agent="worker-a", batch="recorder#0", branch="x", at=NOW,
                        touches=["Backend/Capture/", "backend/capture/"])
    fields = parse_claim(body)
    assert json.loads(fields["touches"]) == ["backend/capture/"]
    changed = plan()
    changed[0]["prs"][0]["touches"] = ["different/"]
    assert claim_touches(1, fields, changed) == ["backend/capture/"]


@pytest.mark.parametrize("extra", [{}, {"touches": "broken JSON"}, {"touches": "[]"},
                                   {"touches": '["../outside"]'}])
def test_legacy_or_malformed_snapshot_falls_back_to_authored_batch(extra):
    assert claim_touches(1, holder(**extra), plan()) == ["backend/capture/"]


def test_legacy_unknown_batch_uses_issue_membership():
    assert claim_touches(1, holder(batch="retired#9"), plan()) == ["backend/capture/"]


def test_batch_overrides_package_default():
    pkg = {"touches": ["backend/"]}
    assert batch_touches(pkg, {}) == ["backend/"]
    assert batch_touches(pkg, {"touches": ["frontend/"]}) == ["frontend/"]


def test_picker_reproduces_cross_package_overlap_and_selects_disjoint_later_batch():
    packages = plan()
    held = {1: holder()}
    pkg, skipped = pick_next(packages, {1, 2, 3, 4}, held)
    assert pkg["slug"] == "state"
    assert next_pr(pkg, {1, 2, 3, 4}, held, packages=packages)["issues"] == [3]
    assert "already claimed" in skipped[0]["_skip_reason"]


def test_picker_skips_whole_overlapping_package_with_explanation():
    packages = plan()
    pkg, skipped = pick_next(packages, {1, 2, 4}, {1: holder()})
    assert pkg["slug"] == "gateway"
    assert skipped[1]["_skip_reason"] == OVERLAP_REASON
    row = skipped[1]["_conflicts"][0]
    assert row["agent"] == "worker-a" and row["paths"] == ["backend/capture/mode.py"]


def test_duplicate_issue_claims_report_one_holder_with_all_issue_numbers():
    packages = plan()
    rows = claim_conflicts(packages[1], packages[1]["prs"][0],
                           {1: holder(), 9: holder()}, packages)
    assert len(rows) == 1 and rows[0]["issues"] == [1, 9]


def test_stale_and_released_claims_reserve_no_files():
    packages = plan()
    pkg, _ = pick_next(packages, {1, 2, 4}, {1: holder(stale=True)})
    assert pkg["slug"] == "recorder"
    comments = [{"body": format_claim(agent="a", batch="recorder#0", branch="x", at=NOW),
                 "createdAt": NOW.isoformat()},
                {"body": format_release(agent="a", batch="recorder#0"),
                 "createdAt": (NOW + timedelta(minutes=1)).isoformat()}]
    assert active_claim(comments, now=NOW + timedelta(minutes=2)) is None


def test_unknown_live_footprint_is_not_assumed_disjoint():
    packages = plan()
    pkg, skipped = pick_next(packages, {1, 2, 4}, {999: holder(batch="missing#0")})
    assert pkg is None
    assert skipped[0]["_conflicts"][0]["paths"] == [UNKNOWN_FOOTPRINT]


def test_closed_candidate_and_gated_batch_are_never_selected():
    packages = plan()
    packages[1]["prs"][1]["gated"] = True
    pkg, _ = pick_next(packages, {2, 3, 4}, {1: holder()})
    assert pkg["slug"] == "gateway"


def test_explicit_package_still_resolves_claims_against_full_plan(monkeypatch, capsys):
    packages = plan()
    monkeypatch.setattr(commands, "load_packages", lambda: packages)
    monkeypatch.setattr(commands, "fetch_issues", lambda: [{"number": n} for n in (1, 2, 4)])
    monkeypatch.setattr(commands, "live_claims", lambda *a, **kw: {1: holder()})
    assert commands.cmd_next(argparse.Namespace(package="state", json=True)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["pull_request"] is None
    assert result["skipped_gated"][0]["conflicts"][0]["batch"] == "recorder#0"


def test_claims_conflicts_view_explains_candidate_holder_and_path(monkeypatch, capsys):
    monkeypatch.setattr(cc, "load_packages", plan)
    monkeypatch.setattr(cc, "fetch_issues", lambda: [
        {"number": 1, "labels": [{"name": "claimed"}]}, {"number": 2}])
    monkeypatch.setattr(cc, "fetch_comments", lambda n: [])
    monkeypatch.setattr(cc, "active_claim", lambda *a, **kw: holder())
    assert cc.cmd_claims(build_parser().parse_args(["claims", "--conflicts"])) == 0
    output = capsys.readouterr().out
    assert "state#0 -- files overlap an in-flight claim" in output
    assert "worker-a on codex/recorder" in output and "backend/capture/mode.py" in output


def claim_args(**kw):
    return argparse.Namespace(package="state", batch=0, agent="worker-b",
                              branch="codex/state", force=False, **kw)


def setup_claim(monkeypatch, held):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(cc, "datetime", FrozenDatetime)
    monkeypatch.setattr(cc, "load_packages", plan)
    monkeypatch.setattr(cc, "fetch_issues", lambda: [{"number": 1}, {"number": 2}])
    monkeypatch.setattr(cc, "fetch_comments", lambda n: [])
    monkeypatch.setattr(cc, "active_claim", lambda *a, **kw: None)
    monkeypatch.setattr(cc, "live_claims", lambda *a, **kw: held)


def test_claim_rejects_overlap_before_writing_even_with_force(monkeypatch, capsys):
    setup_claim(monkeypatch, {1: holder()})
    writes = []
    monkeypatch.setattr(cc, "run_gh", lambda args, **kw: writes.append(args))
    args = claim_args()
    args.force = True
    assert cc.cmd_claim(args) == 1
    assert not writes
    assert OVERLAP_REASON in capsys.readouterr().err


def test_claim_records_authored_footprint(monkeypatch):
    setup_claim(monkeypatch, {})
    monkeypatch.setattr(cc, "run_gh", lambda *a, **kw: SimpleNamespace(returncode=0))
    observed = []
    original = cc.format_claim
    def record(**kw):
        observed.append(kw["touches"])
        return original(**kw)
    monkeypatch.setattr(cc, "format_claim", record)
    assert cc.cmd_claim(claim_args()) == 0
    assert observed == [["backend/capture/mode.py"]]


def test_claim_yields_when_other_batch_wins_file_race(monkeypatch, capsys):
    setup_claim(monkeypatch, {})
    snapshots = iter([{}, {1: holder()}])
    monkeypatch.setattr(cc, "live_claims", lambda *a, **kw: next(snapshots))
    writes = []
    def write(args, **kw):
        writes.append(args)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(cc, "run_gh", write)
    assert cc.cmd_claim(claim_args()) == 1
    assert "Race lost" in capsys.readouterr().err
    assert len([w for w in writes if w[:2] == ["issue", "comment"]]) == 2


def test_every_authored_batch_has_a_nonempty_normalizable_footprint():
    for pkg in load_packages():
        for batch in pkg["prs"]:
            assert batch_touches(pkg, batch), (pkg["slug"], batch["title"])


def test_real_recorder_claim_blocks_all_six_files_from_issue_367():
    packages = load_packages()
    held = claim_touches(314, holder(batch="recorder-safety#0"), packages)
    evidence = ["backend/capture/mode.py", "backend/capture/recorder.py",
                "backend/capture/routes.py", "backend/capture/sessions.py",
                "backend/sim/feed.py", "frontend/src/capture/sessionRecordStore.ts"]
    assert overlapping_paths(evidence, held) == normalize_touches(evidence)


def test_new_regressions_are_in_the_agent_ci_job():
    root = Path(__file__).resolve().parents[1]
    assert "tools/test_backlog_footprints.py" in (root / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
