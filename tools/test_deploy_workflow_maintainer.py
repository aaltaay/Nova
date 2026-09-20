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


def test_maintainer_gate_fails_on_hard_file_size():
    gate = [run for run in _runs() if "maintainer_checks.py" in run]
    assert gate, "deploy.yml must run tools/maintainer_checks.py"
    assert any("--fail-on-kind file_size_hard" in run for run in gate), (
        "the maintainer gate must fail on file_size_hard, not merely compute it"
    )


def test_maintainer_gate_keeps_the_ib_loop_purity_kind():
    gate = [run for run in _runs() if "maintainer_checks.py" in run]
    assert any("--fail-on-kind ib_loop_sync_io" in run for run in gate)
