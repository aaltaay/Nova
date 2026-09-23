"""Ensure advisory CI still runs real tests and delivery has no verification wait."""

from pathlib import Path

import yaml

from tools import pr_delivery
from tools.master_branch_protection import apply_payload
from tools.security_lib.checks_infra import check_ci_missing_security_jobs

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return yaml.load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_advisory_jobs_keep_full_test_commands_and_scope_guards():
    ci = workflow("deploy.yml")
    for job_id, field, command in (
        ("backend-test", "backend", "pytest backend/ -x -q --tb=short"),
        ("frontend-build", "frontend", "npm test -- --run"),
        ("frontend-e2e", "e2e", "npm run test:e2e"),
    ):
        job = ci["jobs"][job_id]
        assert job["needs"] == ["changes"]
        assert job["if"] == "always()"
        guard, *steps = job["steps"]
        assert 'test "$SCOPE_RESULT" = success' in guard["run"]
        assert "exit 1" in guard["run"]
        assert all(step["if"] == f"needs.changes.outputs.{field} == 'true'" for step in steps)
        assert any(step.get("run") == command for step in steps)
    assert "paths" not in ci["on"]["pull_request"]
    assert ci["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"


def test_auto_merge_has_no_ci_dependency_or_desktop_wait():
    job = workflow("deploy.yml")["jobs"]["auto-merge"]
    assert "needs" not in job
    assert "--wait-desktop-minutes" not in str(job)
    assert pr_delivery.REQUIRED_CHECKS == pr_delivery.WAIT_IF_PRESENT == ()
    assert apply_payload()["required_status_checks"] is None


def test_desktop_only_uses_windows_for_application_changes():
    jobs = workflow("desktop-pack.yml")["jobs"]
    pack = jobs["desktop-pack"]
    assert "desktop == 'false' && 'ubuntu-latest' || 'windows-latest'" in pack["runs-on"]
    for step in pack["steps"][1:]:
        assert step["if"] == "needs.changes.outputs.desktop == 'true'"
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
