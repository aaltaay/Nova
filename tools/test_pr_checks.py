"""Actions merges a PR only when its four required checks are green (operator decision 2026-10-13)."""

from __future__ import annotations

import json
import subprocess

import pytest

from tools import pr_checks, pr_delivery
from tools.pr_delivery import ACTION_BLOCK, ACTION_MERGE, ACTION_SKIP, ACTION_WAIT, decide
from tools.release_gate import REQUIRED_CHECKS

SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture(autouse=True)
def _no_job_summary(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


def run(name: str, conclusion: str | None = "success", *, status: str = "completed",
        run_id: int = 1, app: str = "github-actions") -> dict:
    return {"id": run_id, "name": name, "status": status, "conclusion": conclusion,
            "app": {"slug": app}}


def green(start: int = 10) -> list[dict]:
    return [run(name, run_id=start + i) for i, name in enumerate(REQUIRED_CHECKS)]


def without(runs: list[dict], name: str) -> list[dict]:
    return [r for r in runs if r["name"] != name]


def _decide(checks: list[dict], **overrides):
    args = dict(draft=False, state="OPEN", mergeable_state="clean", labels=[],
                head_ref="feature/x", same_repo=True, checks=checks)
    args.update(overrides)
    return decide(**args)


def test_green_merges():
    assert pr_checks.merge_verdict(green()) == ([], [])
    assert _decide(green()).action == ACTION_MERGE


def test_a_scope_skipped_check_is_green_because_ci_reports_it_green():
    """A docs-only PR: each of the four still runs (`if: always()`), says "Unaffected" and
    concludes success, so the PR merges. Other apps and warning-only scanners never count."""
    runs = green() + [run("Semgrep", "failure", run_id=90), run("Desktop pack", None, status="in_progress")]
    assert _decide(runs).action == ACTION_MERGE


@pytest.mark.parametrize("conclusion, words", [
    ("failure", "failed"), ("cancelled", "was cancelled"), ("timed_out", "timed out"),
    ("skipped", "was skipped"), ("startup_failure", "failed to start"),
])
def test_a_red_check_holds_with_its_name(conclusion, words):
    runs = without(green(), "Frontend E2E") + [run("Frontend E2E", conclusion, run_id=99)]
    result = _decide(runs)
    assert result.action == ACTION_BLOCK
    assert result.reason == f"checks_red: Frontend E2E {words}"


def test_a_running_or_missing_check_waits():
    runs = without(green(), "Backend tests") + [run("Backend tests", None, status="in_progress", run_id=99)]
    assert _decide(runs).reason == "checks_pending: Backend tests is still in_progress"
    assert _decide(without(green(), "Agent contract")).reason == "checks_pending: Agent contract has not reported"
    assert _decide([]).action == ACTION_WAIT


def test_red_wins_over_pending_so_the_hold_names_it():
    runs = [run("Backend tests", "failure", run_id=1), run("Frontend build", None, status="queued", run_id=2)]
    assert _decide(runs).action == ACTION_BLOCK


def test_a_green_rerun_merges_and_a_newer_red_holds_again():
    runs = without(green(), "Backend tests") + [run("Backend tests", "failure", run_id=50)]
    assert _decide(runs).action == ACTION_BLOCK
    runs.append(run("Backend tests", "success", run_id=51))
    assert _decide(runs).action == ACTION_MERGE
    runs.append(run("Backend tests", "cancelled", run_id=52))
    assert _decide(runs).reason == "checks_red: Backend tests was cancelled"


def test_a_same_named_check_from_another_app_never_stands_in(monkeypatch):
    impostor = [run(name, run_id=200 + i, app="someone-else") for i, name in enumerate(REQUIRED_CHECKS)]
    page = {"total_count": 4, "check_runs": impostor}

    def gh(args, check=True, stdin=None):
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(page), stderr="")

    assert pr_checks.fetch_head_checks(gh, "aaltaay/Nova", SHA) == []


def test_drafts_and_do_not_merge_still_hold_first():
    red = [run(name, "failure", run_id=i) for i, name in enumerate(REQUIRED_CHECKS)]
    assert _decide(red, draft=True).reason == "draft"
    assert _decide(green(), labels=[{"name": "do-not-merge"}]).action == ACTION_SKIP
    assert _decide(red, labels=["do-not-merge"]).reason == "do-not-merge"


def test_fetch_reads_every_page_of_every_attempt():
    calls: list[list[str]] = []
    runs = green()
    pages = "".join(json.dumps({"total_count": 4, "check_runs": chunk}) for chunk in (runs[:2], runs[2:]))

    def gh(args, check=True, stdin=None):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout=pages, stderr="")

    assert pr_checks.fetch_head_checks(gh, "aaltaay/Nova", SHA) == runs
    assert calls == [["api", "--paginate", f"repos/aaltaay/Nova/commits/{SHA}/check-runs?filter=all&per_page=100"]]


def test_unreadable_checks_are_not_green(monkeypatch, capsys):
    def gh(args, check=True, stdin=None):
        if args[:2] == ["pr", "view"]:
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"number": 7, "headRefOid": SHA}), stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="HTTP 502")

    monkeypatch.setattr(pr_delivery, "_gh", gh)
    pr, checks = pr_delivery._fetch_pr(7)
    assert checks == []
    assert "#7 checks unreadable: HTTP 502" in capsys.readouterr().err
    with pytest.raises(ValueError):
        pr_checks.fetch_head_checks(gh, "aaltaay/Nova", "")


def _comment_gh(existing: list[str], posted: list[str]):
    def gh(args, check=True, stdin=None):
        if args[:2] == ["api", "--paginate"] and "/comments" in args[2]:
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps([{"body": b} for b in existing]), stderr="")
        if args[:2] == ["pr", "comment"]:
            posted.append(args[args.index("--body") + 1])
            existing.append(posted[-1])
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        raise AssertionError(args)
    return gh


def test_a_hold_is_said_once_per_head_and_verdict():
    existing: list[str] = []
    posted: list[str] = []
    gh = _comment_gh(existing, posted)
    red = [("Backend tests", "failed")]
    pr_checks.signal_checks_held(gh, "aaltaay/Nova", 7, SHA, red)
    pr_checks.signal_checks_held(gh, "aaltaay/Nova", 7, SHA, red)
    assert len(posted) == 1
    assert posted[0].startswith("**Not merged: Backend tests failed** on `0123456`.")
    assert "Backend tests, Frontend build, Frontend E2E and Agent contract" in posted[0]
    assert pr_checks.HELD_COMMENT_MARKER in posted[0]
    pr_checks.signal_checks_held(gh, "aaltaay/Nova", 7, "f" * 40, red)
    assert len(posted) == 2, "a new head that is red again says so again"


def _pr(number: int = 7) -> dict:
    return {"number": number, "title": "t", "body": "", "isDraft": False, "state": "OPEN",
            "mergeStateStatus": "CLEAN", "labels": [], "headRefName": "feature/x", "headRefOid": SHA,
            "headRepository": {"name": "Nova"}, "headRepositoryOwner": {"login": "aaltaay"}}


@pytest.mark.parametrize("command", ["merge", "sweep"])
def test_a_red_pr_is_held_out_loud_and_never_merged(monkeypatch, tmp_path, command):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    red = without(green(), "Backend tests") + [run("Backend tests", "failure", run_id=99)]
    held: list[tuple] = []
    merged: list[int] = []
    monkeypatch.setattr(pr_delivery, "_fetch_pr", lambda n: (_pr(n), red))
    monkeypatch.setattr(pr_delivery, "_merge_pr", lambda pr: merged.append(pr["number"]) or 0)
    monkeypatch.setattr(pr_checks, "signal_checks_held", lambda gh, repo, n, sha, r: held.append((n, sha, r)))
    monkeypatch.setattr(pr_delivery, "_gh", lambda args, check=True, stdin=None: subprocess.CompletedProcess(
        args, 0, stdout=json.dumps([{"number": 7}]), stderr=""))
    if command == "merge":
        assert pr_delivery.cmd_merge(7, wait_desktop_minutes=0, min_age_seconds=0) == 1
    else:
        assert pr_delivery.cmd_sweep(min_age_seconds=0) == 0, "one red PR is not a failed sweep"
    assert merged == []
    assert held == [(7, SHA, [("Backend tests", "failed")])]
    assert "#7 (head `0123456`): **block** -- checks_red: Backend tests failed" in summary.read_text(encoding="utf-8")


def test_the_rerun_that_turns_green_merges_from_the_merge_job(monkeypatch):
    """Re-running a failed check re-runs Auto-merge (it `needs` the four), which then merges."""
    rerun = without(green(), "Backend tests") + [run("Backend tests", "failure", run_id=50),
                                                 run("Backend tests", "success", run_id=51)]
    merged: list[int] = []
    monkeypatch.setattr(pr_delivery, "_fetch_pr", lambda n: (_pr(n), rerun))
    monkeypatch.setattr(pr_delivery, "_merge_pr", lambda pr: merged.append(pr["number"]) or 0)
    assert pr_delivery.cmd_merge(7, wait_desktop_minutes=0, min_age_seconds=0) == 0
    assert merged == [7]
