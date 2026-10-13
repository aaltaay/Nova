"""Ensure change-aware CI still runs real tests and delivery merges only green PRs."""

from pathlib import Path

import yaml

from tools import pr_delivery
from tools.master_branch_protection import apply_payload
from tools.security_lib.checks_infra import check_ci_missing_security_jobs

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def reports_alone(field: str, setup: str = "install") -> str:
    """A check that runs even when an earlier check failed, once ``setup`` succeeded -- still
    only when its job is selected (docs/ci.md)."""
    return f"${{{{ !cancelled() && needs.changes.outputs.{field} == 'true' && steps.{setup}.outcome == 'success' }}}}"


def test_advisory_jobs_keep_full_test_commands_and_scope_guards():
    ci = workflow("deploy.yml")
    for job_id, field, command, checks_after_install in (
        ("backend-test", "backend", "pytest backend/ -x -q --tb=short", True),
        ("frontend-build", "frontend", "npm test -- --run", True),
        ("frontend-e2e", "e2e", "npm run test:e2e", False),  # one check: nothing for it to hide
    ):
        job = ci["jobs"][job_id]
        assert job["needs"] == ["changes"]
        assert job["if"] == "always()"
        guard, *steps = job["steps"]
        assert 'test "$SCOPE_RESULT" = success' in guard["run"]
        assert "exit 1" in guard["run"]
        install = next((i for i, step in enumerate(steps) if step.get("id") == "install"), None)
        assert (install is not None) == checks_after_install, job_id
        for i, step in enumerate(steps):
            if checks_after_install and i > install:
                assert step["if"] == reports_alone(field), step
            else:
                assert step["if"] == f"needs.changes.outputs.{field} == 'true'", step
        assert any(step.get("run") == command for step in steps)
    assert "paths" not in ci["on"]["pull_request"]
    assert ci["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"


def test_auto_merge_decides_only_once_the_four_checks_finished():
    """Green only (operator decision 2026-10-13, "Merge only green PRs too").

    Auto-merge `needs` exactly the four jobs the gate reads, so it decides with
    their results in hand and a re-run of a failed one re-runs it; it never
    judges a PR with the PR's own copy of the gate. Branch protection keeps no
    required status checks: the merge job is the gate, and status-only master
    pushes stay possible.
    """
    from tools.release_gate import REQUIRED_CHECKS

    ci = workflow("deploy.yml")
    job = ci["jobs"]["auto-merge"]
    assert job["needs"] == ["backend-test", "frontend-build", "frontend-e2e", "agent-contract"]
    assert {ci["jobs"][need]["name"] for need in job["needs"]} == set(REQUIRED_CHECKS)
    # Scope never skips one at GitHub's level: each runs and reports "Unaffected" as success.
    assert all(ci["jobs"][need]["if"] == "always()" for need in job["needs"])
    assert job["if"].strip().startswith("!cancelled() &&"), "a superseded run must decide nothing"
    assert "always()" not in job["if"]
    assert job["steps"][0]["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert "--wait-desktop-minutes" not in str(job)
    assert pr_delivery.REQUIRED_CHECKS == REQUIRED_CHECKS
    assert apply_payload()["required_status_checks"] is None


def test_desktop_only_uses_windows_for_application_changes():
    jobs = workflow("desktop-pack.yml")["jobs"]
    pack = jobs["desktop-pack"]
    assert "desktop == 'false' && 'ubuntu-latest' || 'windows-latest'" in pack["runs-on"]
    *steps, maintenance = pack["steps"][1:]
    for step in steps:
        assert step["if"] == "needs.changes.outputs.desktop == 'true'"
    # The Windows maintenance tests do not need the pack: they run last, even after a failed pack,
    # so neither hides the other; a failure still fails the job, and so still holds the release.
    assert "tools/test_windows_maintenance.py" in maintenance["run"]
    assert any(step.get("id") == "python" for step in steps)
    assert maintenance["if"] == reports_alone("desktop", setup="python")
    # The release gate holds a Release whose pack (or any required check) is not green.
    gate = next(s for s in jobs["publish-release"]["steps"] if s.get("name") == "Release only a green build")
    assert gate["env"]["PACK_RESULT"] == "${{ needs.desktop-pack.result }}"
    assert "needs.changes.outputs.desktop == 'true'" in jobs["publish-release"]["if"]
    assert any(step.get("run") == "npm run electron:pack" for step in pack["steps"])


def test_housekeeping_is_scheduled_and_security_coverage_remains():
    ci = workflow("deploy.yml")
    agent = str(ci["jobs"]["agent-contract"])
    assert "python tools/stale_pr_branches.py" not in agent
    assert "python tools/master_branch_protection.py check" not in agent
    assert "maintainer_checks.py --gate" in agent
    assert "if" not in ci["jobs"]["gitleaks"]
    for name in ("security-scans.yml", "repository-maintenance.yml"):
        wf = workflow(name)
        assert wf["on"]["schedule"]
        assert all("timeout-minutes" in job for job in wf["jobs"].values())
    assert check_ci_missing_security_jobs() == []


def test_scope_workflow_is_shared_and_fetches_full_history():
    for name in ("deploy.yml", "desktop-pack.yml"):
        assert workflow(name)["jobs"]["changes"]["uses"] == "./.github/workflows/ci-scope.yml"
    scope = workflow("ci-scope.yml")
    assert scope["jobs"]["select"]["steps"][0]["with"]["fetch-depth"] == "0"
