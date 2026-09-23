"""The maintainer gate must actually run in CI (#393).

Two independent gaps let `App.tsx` sit over its limit unreported: the test that
detects it was not in the enumerated tools-pytest list, and the checker that did
run was scoped to one kind, so `file_size_hard` was computed and discarded.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "deploy.yml"


def _steps() -> list[dict]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [step for job in data["jobs"].values() for step in (job.get("steps") or [])]


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
    for kind in ("file_size_hard", "ib_loop_sync_io", "file_size_growth", "swallowed_exception_money"):
        assert kind in GATE_KINDS


def test_maintainer_gate_judges_growth_against_the_target_branch():
    steps = [step for step in _steps() if "maintainer_checks.py" in str(step.get("run", ""))]
    assert any('--base "$MAINTAINER_BASE"' in step["run"] for step in steps)
    assert any("github.base_ref" in str(step.get("env", {}).get("MAINTAINER_BASE", "")) for step in steps)
