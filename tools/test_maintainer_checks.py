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


def test_bare_css_selector_detected(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    styles = fake_root / "frontend" / "src" / "styles"
    styles.mkdir(parents=True)
    css = styles / "leaky.css"
    css.write_text("button {\n  color: red;\n}\n", encoding="utf-8")
    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    findings = mc.check_css_design_contract([css])
    assert any(f.kind == "bare_css_selector" for f in findings)


def test_color_muted_as_text_detected(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    styles = fake_root / "frontend" / "src" / "styles"
    styles.mkdir(parents=True)
    css = styles / "tape.css"
    css.write_text(".title { color: var(--color-muted); }\n", encoding="utf-8")
    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    findings = mc.check_css_design_contract([css])
    assert any(f.kind == "css_token_collision" for f in findings)


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


def test_swallowed_tuple_except_pass_detected(mc, tmp_path: Path):
    p = tmp_path / "ws.py"
    p.write_text(
        "try:\n    await ws.receive()\n"
        "except (WebSocketDisconnect, Exception):\n    pass\n",
        encoding="utf-8",
    )
    findings = mc.check_swallowed_errors([p])
    assert any(f.kind == "swallowed_exception" for f in findings)


def test_except_return_empty_detected(mc, tmp_path: Path):
    p = tmp_path / "scan.py"
    p.write_text(
        "try:\n    x()\nexcept Exception:\n    return []\n",
        encoding="utf-8",
    )
    findings = mc.check_swallowed_errors([p])
    assert any(f.kind == "except_return_empty" for f in findings)


def test_empty_promise_catch_detected(mc, tmp_path: Path):
    p = tmp_path / "a.ts"
    p.write_text("fetch('/x').catch(() => {});\n", encoding="utf-8")
    findings = mc.check_swallowed_errors([p])
    assert any(f.kind == "empty_promise_catch" for f in findings)


def test_tools_scripts_exempt_from_swallow_checks(mc, tmp_path: Path, monkeypatch):
    """tools/ one-off scripts are not the product read-paths this heuristic
    protects — see fail-loud remainder plan bucket B."""
    fake_root = tmp_path / "repo"
    tools = fake_root / "tools"
    tools.mkdir(parents=True)
    p = tools / "script.py"
    p.write_text("try:\n    x()\nexcept Exception:\n    return []\n", encoding="utf-8")
    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    assert mc.check_swallowed_errors([p]) == []


def test_test_files_exempt_from_swallow_checks(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    tests = fake_root / "backend" / "tests"
    tests.mkdir(parents=True)
    p = tests / "test_x.py"
    p.write_text("try:\n    x()\nexcept Exception:\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    assert mc.check_swallowed_errors([p]) == []


def test_except_return_empty_allowlist_path_skipped(mc, tmp_path: Path, monkeypatch):
    """channels_store.py / journal/tags.py / ibkr/client.py / scanner.py
    already handle their empty-on-error case deliberately (logged disk load
    or fail-closed account classification) — not a silent market lie."""
    fake_root = tmp_path / "repo"
    alerts = fake_root / "backend" / "alerts"
    alerts.mkdir(parents=True)
    p = alerts / "channels_store.py"
    p.write_text("try:\n    x()\nexcept Exception:\n    return []\n", encoding="utf-8")
    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    assert mc.check_swallowed_errors([p]) == []


def test_swallowed_exception_allowlist_path_skipped(mc, tmp_path: Path, monkeypatch):
    """ibkr/ticks.py + ibkr/order_times.py: idempotent cleanup / parse-then-
    fall-through, already triaged as intentional — not a silent failure."""
    fake_root = tmp_path / "repo"
    ibkr = fake_root / "backend" / "ibkr"
    ibkr.mkdir(parents=True)
    p = ibkr / "ticks.py"
    p.write_text("try:\n    x()\nexcept ValueError:\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    assert mc.check_swallowed_errors([p]) == []


def test_non_allowlisted_backend_module_still_flagged(mc, tmp_path: Path, monkeypatch):
    """Guard against the allowlist swallowing everything — an unlisted
    product module must still be flagged."""
    fake_root = tmp_path / "repo"
    ibkr = fake_root / "backend" / "ibkr"
    ibkr.mkdir(parents=True)
    p = ibkr / "some_new_module.py"
    p.write_text("try:\n    x()\nexcept Exception:\n    return []\n", encoding="utf-8")
    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    findings = mc.check_swallowed_errors([p])
    assert any(f.kind == "except_return_empty" for f in findings)


def test_run_checks_on_real_repo_swallow_noise_excludes_tools_and_tests(mc):
    """Documents the bucket-B policy on the live repo: tools/ + tests never
    contribute swallow-heuristic noise."""
    report = mc.run_checks()
    noisy_kinds = {"swallowed_exception", "bare_except", "except_return_empty"}
    for f in report["findings"]:
        if f["kind"] not in noisy_kinds:
            continue
        posix = f["path"].replace("\\", "/")
        assert not posix.startswith("tools/"), f
        assert "/tests/" not in posix, f
        assert not posix.startswith("tests/"), f


def test_import_main_detected_non_baseline_until_fingerprinted(mc, tmp_path: Path):
    from maintainer_lib.baselines import apply_baseline_fingerprints, fingerprint
    from maintainer_lib.deps import check_import_main

    p = tmp_path / "scan_runners.py"
    p.write_text("def f():\n    import main as _main\n    return _main\n", encoding="utf-8")
    findings = check_import_main([p], lambda x: "backend/scan_runners.py", mc.Finding)
    assert findings
    assert findings[0].kind == "import_main"
    assert findings[0].baseline is False
    fp = fingerprint(
        findings[0].kind, findings[0].path, findings[0].line, findings[0].detail
    )
    apply_baseline_fingerprints(findings, {fp})
    assert findings[0].baseline is True


def test_cross_feature_new_violation_not_baselined(mc, tmp_path: Path):
    from maintainer_lib.baselines import apply_baseline_fingerprints
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
    apply_baseline_fingerprints(findings, set())
    assert findings[0].baseline is False


def test_artifacts_ignored_are_informational(mc, tmp_path: Path):
    from maintainer_lib.artifacts import check_artifacts

    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    (fake_root / ".env").write_text("X=1\n", encoding="utf-8")
    findings = check_artifacts(
        fake_root, mc.Finding, paths=(".env",), tracked_fn=lambda: set()
    )
    assert len(findings) == 1
    assert findings[0].kind == "artifact_present"
    assert findings[0].baseline is True


def test_artifacts_tracked_are_non_baseline(mc, tmp_path: Path):
    from maintainer_lib.artifacts import check_artifacts

    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    (fake_root / ".env").write_text("X=1\n", encoding="utf-8")
    findings = check_artifacts(
        fake_root, mc.Finding, paths=(".env",), tracked_fn=lambda: {".env"}
    )
    assert len(findings) == 1
    assert findings[0].kind == "artifact_tracked"
    assert findings[0].baseline is False


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
    # No accepted oversize baselines currently (executor + hod_momo facades under limit).
    assert "backend/strategy/executor.py" not in baseline_paths
    assert "backend/hod_momo.py" not in baseline_paths
    hard_app = [
        f
        for f in report["findings"]
        if f["kind"] == "file_size_hard"
        and f["path"] in {"backend/main.py", "frontend/src/App.tsx"}
    ]
    assert hard_app == [], f"unexpected hard app findings: {hard_app}"
    json.dumps(report)
