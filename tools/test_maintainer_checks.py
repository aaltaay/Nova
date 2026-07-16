"""Unit tests for tools/maintainer_checks.py (deterministic scanner)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "maintainer_checks.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("maintainer_checks", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve annotations under PEP 563.
    sys.modules["maintainer_checks"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mc():
    return _load_module()


def test_count_lines_handles_trailing_newline(mc, tmp_path: Path):
    p = tmp_path / "a.py"
    p.write_text("a\nb\n", encoding="utf-8")
    assert mc.count_lines(p) == 2
    p.write_text("a\nb", encoding="utf-8")
    assert mc.count_lines(p) == 2


def test_hard_limit_main_py_flagged_when_over(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    backend = fake_root / "backend"
    backend.mkdir(parents=True)
    main = backend / "main.py"
    main.write_text("\n".join(f"x = {i}" for i in range(205)) + "\n", encoding="utf-8")

    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    monkeypatch.setattr(mc, "HARD_LIMIT_FILES", {"backend/main.py": 200})
    monkeypatch.setattr(mc, "BASELINE_OVER_LIMIT", {})

    findings = mc.check_file_sizes([main])
    assert len(findings) == 1
    assert findings[0].kind == "file_size_hard"
    assert findings[0].baseline is False


def test_baseline_over_limit_marked_baseline(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    backend = fake_root / "backend"
    backend.mkdir(parents=True)
    target = backend / "hod_momo.py"
    target.write_text("\n".join(f"x = {i}" for i in range(450)) + "\n", encoding="utf-8")

    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    monkeypatch.setattr(mc, "HARD_LIMIT_FILES", {})
    monkeypatch.setattr(mc, "BASELINE_OVER_LIMIT", {"backend/hod_momo.py": 400})

    findings = mc.check_file_sizes([target])
    assert len(findings) == 1
    assert findings[0].baseline is True
    assert findings[0].kind == "file_size_baseline"


def test_secret_pattern_redacts_value(mc, tmp_path: Path):
    p = tmp_path / "leak.py"
    p.write_text('api_key = "abcdefghijklmnopqrstuvwxyz12"\n', encoding="utf-8")
    findings = mc.check_secrets([p])
    assert findings
    assert "abcdefghijklmnopqrstuvwxyz12" not in findings[0].detail
    assert "redacted" in findings[0].detail


def test_swallowed_except_pass_detected(mc, tmp_path: Path):
    p = tmp_path / "bad.py"
    p.write_text("try:\n    1/0\nexcept Exception:\n    pass\n", encoding="utf-8")
    findings = mc.check_swallowed_errors([p])
    assert any(f.kind == "swallowed_exception" for f in findings)


def test_run_checks_on_real_repo_includes_baselines(mc):
    """Smoke: real Nova tree should mark hod_momo / executor as baseline, not hard."""
    report = mc.run_checks()
    assert report["files_scanned"] > 50
    baseline_paths = {
        f["path"] for f in report["findings"] if f["kind"] == "file_size_baseline"
    }
    assert "backend/hod_momo.py" in baseline_paths
    hard = [f for f in report["findings"] if f["kind"] == "file_size_hard"]
    assert hard == [], f"unexpected hard file-size findings: {hard}"
