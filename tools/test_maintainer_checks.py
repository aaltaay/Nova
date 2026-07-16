"""Unit tests for tools/maintainer_checks.py (deterministic scanner)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "maintainer_checks.py"


def _load_module():
    tools_dir = str(REPO_ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    spec = importlib.util.spec_from_file_location("maintainer_checks", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
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
    monkeypatch.setattr(mc, "BASELINE_ACCEPTED_LINES", {})

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
    monkeypatch.setattr(mc, "BASELINE_ACCEPTED_LINES", {"backend/hod_momo.py": 1079})

    findings = mc.check_file_sizes([target])
    assert len(findings) == 1
    assert findings[0].baseline is True
    assert findings[0].kind == "file_size_baseline"


def test_baseline_growth_flagged_when_past_accepted(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    backend = fake_root / "backend"
    backend.mkdir(parents=True)
    target = backend / "hod_momo.py"
    target.write_text("\n".join(f"x = {i}" for i in range(1100)) + "\n", encoding="utf-8")

    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    monkeypatch.setattr(mc, "HARD_LIMIT_FILES", {})
    monkeypatch.setattr(mc, "BASELINE_OVER_LIMIT", {"backend/hod_momo.py": 400})
    monkeypatch.setattr(mc, "BASELINE_ACCEPTED_LINES", {"backend/hod_momo.py": 1079})

    findings = mc.check_file_sizes([target])
    assert any(f.kind == "baseline_growth" and not f.baseline for f in findings)


def test_index_css_hard_limit(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    css_dir = fake_root / "frontend" / "src"
    css_dir.mkdir(parents=True)
    css = css_dir / "index.css"
    css.write_text("\n".join(f"/* {i} */" for i in range(1005)) + "\n", encoding="utf-8")

    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    monkeypatch.setattr(mc, "HARD_LIMIT_FILES", {"frontend/src/index.css": 1000})
    monkeypatch.setattr(mc, "BASELINE_OVER_LIMIT", {})

    findings = mc.check_file_sizes([css])
    assert len(findings) == 1
    assert findings[0].kind == "file_size_hard"
    assert "1005" in findings[0].detail


def test_domain_css_over_limit(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    styles = fake_root / "frontend" / "src" / "styles"
    styles.mkdir(parents=True)
    css = styles / "shell.css"
    css.write_text("\n".join(f".x{i} {{}}" for i in range(1001)) + "\n", encoding="utf-8")

    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    monkeypatch.setattr(mc, "HARD_LIMIT_FILES", {})
    monkeypatch.setattr(mc, "BASELINE_OVER_LIMIT", {})

    findings = mc.check_file_sizes([css])
    assert any(f.kind == "file_size" and "CSS" in f.detail for f in findings)


def test_test_files_exempt_from_size(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    tests = fake_root / "backend" / "tests"
    tests.mkdir(parents=True)
    big = tests / "test_huge.py"
    big.write_text("\n".join(f"x = {i}" for i in range(500)) + "\n", encoding="utf-8")

    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    monkeypatch.setattr(mc, "HARD_LIMIT_FILES", {})
    monkeypatch.setattr(mc, "BASELINE_OVER_LIMIT", {})

    assert mc.check_file_sizes([big]) == []


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


def test_import_main_detected_as_baseline_warning(mc, tmp_path: Path):
    from maintainer_lib.deps import check_import_main

    p = tmp_path / "scan_runners.py"
    p.write_text("def f():\n    import main as _main\n    return _main\n", encoding="utf-8")
    findings = check_import_main([p], lambda x: "backend/scan_runners.py", mc.Finding)
    assert findings
    assert findings[0].kind == "import_main"
    assert findings[0].baseline is True


def test_cross_feature_import_detected(mc, tmp_path: Path):
    from maintainer_lib.deps import check_cross_feature_imports

    feat = tmp_path / "frontend" / "src" / "hotkeys"
    feat.mkdir(parents=True)
    p = feat / "X.tsx"
    p.write_text("import { y } from '../hod_momo/secret'\n", encoding="utf-8")
    findings = check_cross_feature_imports(
        [p], lambda x: "frontend/src/hotkeys/X.tsx", mc.Finding
    )
    assert findings
    assert findings[0].kind == "cross_feature_import"


def test_run_checks_on_real_repo_reports_index_css(mc):
    report = mc.run_checks()
    assert report["files_scanned"] > 50
    css = report.get("css_line_counts") or {}
    assert "frontend/src/index.css" in css
    assert css["frontend/src/index.css"] <= 50, "index.css must stay import-only"
    assert "frontend/src/hod_momo/hodMomo.css" in css
    hard_css = [
        f
        for f in report["findings"]
        if f["kind"] == "file_size_hard" and f["path"] == "frontend/src/index.css"
    ]
    assert hard_css == [], f"index.css should be within import-only limit: {hard_css}"
    baseline_paths = {
        f["path"] for f in report["findings"] if f["kind"] == "file_size_baseline"
    }
    assert "backend/hod_momo.py" in baseline_paths
    hard_app = [
        f
        for f in report["findings"]
        if f["kind"] == "file_size_hard"
        and f["path"] in {"backend/main.py", "frontend/src/App.tsx"}
    ]
    assert hard_app == [], f"unexpected hard app findings: {hard_app}"
    json.dumps(report)
