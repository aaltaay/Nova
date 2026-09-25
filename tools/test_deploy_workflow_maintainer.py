"""The maintainer gate must actually run in CI (#393).

Two independent gaps let `App.tsx` sit over its limit unreported: the test that
detects it was not in the enumerated tools-pytest list, and the checker that did
run was scoped to one kind, so `file_size_hard` was computed and discarded.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "deploy.yml"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _steps() -> list[dict]:
    return [step for job in _jobs().values() for step in (job.get("steps") or [])]


def _ruff_pin() -> str | None:
    sys.path.insert(0, str(WORKFLOW.parents[2] / "tools"))
    from maintainer_lib.lint import pinned_version

    return pinned_version(WORKFLOW.parents[2])


def _runs() -> list[str]:
    return [step["run"] for step in _steps() if isinstance(step.get("run"), str)]


def test_tools_pytest_step_includes_the_maintainer_tests():
    assert any("tools/test_maintainer_checks.py" in run for run in _runs()), (
        "tools/test_maintainer_checks.py must be in the enumerated tools pytest step, "
        "or a file-size breach is only visible to someone running the suite locally"
    )


def _gate_runs() -> list[str]:
    return [run for run in _runs() if "maintainer_checks.py" in run]


def test_tools_pytest_step_includes_the_policy_tests():
    assert any("tools/test_maintainer_policy.py" in run for run in _runs())


def test_maintainer_gate_fails_on_the_gate_kinds():
    """`--gate` reads tools/maintainer_lib/gate.py, so CI and a local run can
    never disagree about what blocks (file_size_hard was once computed and
    discarded, #393)."""
    import sys

    sys.path.insert(0, str(WORKFLOW.parents[2] / "tools"))
    from maintainer_lib.gate import GATE_KINDS

    gate = _gate_runs()
    assert gate, "deploy.yml must run tools/maintainer_checks.py"
    assert any("--gate" in run for run in gate), "the maintainer step must run --gate"
    for kind in ("file_size_hard", "ib_loop_sync_io", "file_size_growth", "swallowed_exception_money",
                 "ruff", "ruff_unavailable", "ruff_error"):
        assert kind in GATE_KINDS


def test_maintainer_gate_judges_growth_against_the_target_branch():
    steps = [step for step in _steps() if "maintainer_checks.py" in str(step.get("run", ""))]
    assert any('--base "$MAINTAINER_BASE"' in step["run"] for step in steps)
    assert any("github.base_ref" in str(step.get("env", {}).get("MAINTAINER_BASE", "")) for step in steps)


def test_backend_tests_run_even_when_ruff_fails():
    """A lint finding never hides the test results (AGENTS.md §6.7): five ruff findings
    once skipped pytest on every backend PR (#603). The job itself still fails on lint."""
    steps = _jobs()["backend-test"]["steps"]
    install = next(step for step in steps if step.get("id") == "install")
    ruff = next(step for step in steps if step.get("run") == "ruff check backend")
    tests = next(step for step in steps if str(step.get("run", "")).startswith("pytest backend/"))
    assert steps.index(install) < steps.index(ruff) < steps.index(tests)
    for part in ("!cancelled()", "needs.changes.outputs.backend == 'true'", "steps.install.outcome == 'success'"):
        assert part in tests["if"], tests["if"]
    assert "continue-on-error" not in ruff


def test_the_ci_gate_installs_the_pinned_ruff():
    """Without ruff where CI runs the gate, CI reads ruff_unavailable while a local run
    lints -- the gate must answer the same everywhere (maintainer_lib/lint.py)."""
    pin = _ruff_pin()
    assert pin, "backend/requirements-dev.txt must pin ruff=="
    gate_jobs = [job for job in _jobs().values()
                 if any("maintainer_checks.py --gate" in str(step.get("run", "")) for step in job.get("steps") or [])]
    assert gate_jobs
    for job in gate_jobs:
        assert any(f"ruff=={pin}" in str(step.get("run", "")) for step in job["steps"])


def test_every_agent_contract_check_reports_its_own_result():
    """A failing check never skips the ones after it (docs/ci.md): each runs once the tools
    installed, unless the run was cancelled -- so no step order can hide a result, the gate's
    included (it no longer has to stay last)."""
    steps = _jobs()["agent-contract"]["steps"]
    install = next(i for i, step in enumerate(steps) if step.get("id") == "tools")
    assert "pip install" in steps[install]["run"]
    checks = steps[install + 1:]
    assert any("maintainer_checks.py --gate" in str(step.get("run", "")) for step in checks)
    assert any(str(step.get("run", "")).startswith("pytest tools/") for step in checks)
    for step in checks:
        assert step.get("if") == "${{ !cancelled() && steps.tools.outcome == 'success' }}", step.get("name")


def test_every_ruff_pin_in_ci_is_the_requirements_pin():
    pins = re.findall(r"ruff==(\S+)", WORKFLOW.read_text(encoding="utf-8"))
    assert pins and set(pins) == {_ruff_pin()}
