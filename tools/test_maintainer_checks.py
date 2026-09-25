"""Unit tests for tools/maintainer_checks.py (deterministic scanner)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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

    findings = mc.check_file_sizes([main])
    assert len(findings) == 1
    assert findings[0].kind == "file_size_hard"
    assert findings[0].baseline is False


def test_oversize_file_is_advisory_until_it_states_a_reason(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    backend = fake_root / "backend"
    backend.mkdir(parents=True)
    target = backend / "hod_momo.py"
    target.write_text("\n".join(f"x = {i}" for i in range(450)) + "\n", encoding="utf-8")

    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    monkeypatch.setattr(mc, "HARD_LIMIT_FILES", {})

    findings = mc.check_file_sizes([target])
    assert [f.kind for f in findings] == ["file_size"]
    assert "soft limit 400" in findings[0].detail

    target.write_text(
        '"""Engine.\n\nmaintainer: one-concern the alert state machine shares one lock\n"""\n'
        + "\n".join(f"x = {i}" for i in range(450)) + "\n",
        encoding="utf-8",
    )
    assert mc.check_file_sizes([target]) == []


def test_index_css_hard_limit(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    css_dir = fake_root / "frontend" / "src"
    css_dir.mkdir(parents=True)
    css = css_dir / "index.css"
    css.write_text("\n".join(f"/* {i} */" for i in range(1005)) + "\n", encoding="utf-8")

    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    monkeypatch.setattr(mc, "HARD_LIMIT_FILES", {"frontend/src/index.css": 1000})

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


def test_swallowed_exception_with_a_site_reason_is_skipped(mc, tmp_path: Path, monkeypatch):
    """ibkr/ticks.py: an idempotent list.remove says why at the site. The old
    file-wide allowlist hid every future site in the file as well."""
    fake_root = tmp_path / "repo"
    ibkr = fake_root / "backend" / "ibkr"
    ibkr.mkdir(parents=True)
    p = ibkr / "ticks.py"
    p.write_text(
        "try:\n    x()\n"
        "except ValueError:  # maintainer: allow-swallow removing twice is a no-op\n    pass\n",
        encoding="utf-8",
    )
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
    assert any(f.kind == "except_return_empty_money" for f in findings)


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


def test_import_main_detected_non_baseline_until_frozen(mc, tmp_path: Path):
    from maintainer_lib.baselines import apply_baseline_counts, build_counts
    from maintainer_lib.deps import check_import_main

    p = tmp_path / "scan_runners.py"
    p.write_text("def f():\n    import main as _main\n    return _main\n", encoding="utf-8")
    findings = check_import_main([p], lambda x: "backend/scan_runners.py", mc.Finding)
    assert findings
    assert findings[0].kind == "import_main"
    assert findings[0].baseline is False
    apply_baseline_counts(findings, build_counts(findings))
    assert findings[0].baseline is True


def test_cross_feature_new_violation_not_baselined(mc, tmp_path: Path):
    from maintainer_lib.baselines import apply_baseline_counts
    from maintainer_lib.deps import check_cross_feature_imports

    feat = tmp_path / "frontend" / "src" / "hotkeys"
    feat.mkdir(parents=True)
    p = feat / "X.tsx"
    p.write_text("import { y } from '../hod_momo/secret'\n", encoding="utf-8")
    findings = check_cross_feature_imports(
        [p], lambda x: "frontend/src/hotkeys/X.tsx", mc.Finding, ("hod_momo", "hotkeys")
    )
    assert findings
    assert findings[0].kind == "cross_feature_import"
    apply_baseline_counts(findings, {})
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
    hard_app = [
        f
        for f in report["findings"]
        if f["kind"] == "file_size_hard"
        and f["path"] in {"backend/main.py", "frontend/src/App.tsx"}
    ]
    assert hard_app == [], f"unexpected hard app findings: {hard_app}"
    json.dumps(report)


def test_fail_on_kind_exits_one_only_for_that_kind(mc):
    class Args:
        json = True
        fail_on_findings = False
        fail_on_kind = ["ib_loop_sync_io"]

    # Wrapper: parse_args is used in main; call the kind filter logic via main argv.
    rc = mc.main(["--fail-on-kind", "ib_loop_sync_io", "--json"])
    assert rc == 0


def test_ib_loop_purity_flags_sqlite3(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    target = fake_root / "backend" / "ibkr" / "tape_stream.py"
    target.parent.mkdir(parents=True)
    target.write_text("import sqlite3\nconn = sqlite3.connect('x')\n", encoding="utf-8")
    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    findings = mc.check_ib_loop_purity([target])
    assert len(findings) == 1
    assert findings[0].kind == "ib_loop_sync_io"
    assert "sqlite3." in findings[0].detail


def test_ib_loop_purity_skips_comment_and_unlisted_file(mc, tmp_path: Path, monkeypatch):
    fake_root = tmp_path / "repo"
    listed = fake_root / "backend" / "ibkr" / "ticks.py"
    other = fake_root / "backend" / "cache.py"
    listed.parent.mkdir(parents=True)
    listed.write_text("# sqlite3.connect is forbidden here\nprint('ok')\n", encoding="utf-8")
    other.write_text("import sqlite3\nsqlite3.connect('x')\n", encoding="utf-8")
    monkeypatch.setattr(mc, "REPO_ROOT", fake_root)
    findings = mc.check_ib_loop_purity([listed, other])
    assert findings == []


# --- #393: entry points are capped on wiring, not on imports and comments ----


def _app_tsx(imports: int, logic: int) -> str:
    head = "/**\n * Root layout.\n */\n"
    lines = [f"import {{ X{i} }} from './x{i}';" for i in range(imports)]
    lines += ["", "// a comment", ""]
    lines += [f"const value{i} = {i};" for i in range(logic)]
    return head + "\n".join(lines) + "\n"


def test_entry_point_counts_logical_lines_not_imports(mc, tmp_path: Path):
    from maintainer_lib.sizes import count_logical_lines

    wiring = tmp_path / "App.tsx"
    wiring.write_text(_app_tsx(imports=100, logic=100), encoding="utf-8")
    assert mc.count_lines(wiring) > 200
    assert count_logical_lines(wiring) == 100


def test_entry_point_over_the_logical_limit_is_a_hard_finding(mc, tmp_path: Path, monkeypatch):
    path = tmp_path / "App.tsx"
    path.write_text(_app_tsx(imports=10, logic=160), encoding="utf-8")
    monkeypatch.setattr(mc, "_rel", lambda p: "frontend/src/App.tsx")
    findings = [f for f in mc.check_file_sizes([path]) if f.kind == "file_size_hard"]
    assert len(findings) == 1
    assert "160 logical lines > entry-point limit 150" in findings[0].detail
    assert "raw)" in findings[0].detail


def test_entry_point_under_the_logical_limit_is_clean(mc, tmp_path: Path, monkeypatch):
    path = tmp_path / "App.tsx"
    path.write_text(_app_tsx(imports=80, logic=100), encoding="utf-8")
    monkeypatch.setattr(mc, "_rel", lambda p: "frontend/src/App.tsx")
    assert [f for f in mc.check_file_sizes([path]) if f.kind == "file_size_hard"] == []


def test_python_docstrings_and_comments_are_not_logic(tmp_path: Path):
    from maintainer_lib.sizes import count_logical_lines

    path = tmp_path / "main.py"
    path.write_text(
        '"""Module docstring\nspanning lines\n"""\n'
        "import os\n"
        "from x import y\n"
        "\n"
        "# a comment\n"
        "app = 1\n"
        "value = 2\n",
        encoding="utf-8",
    )
    assert count_logical_lines(path) == 2


def test_real_entry_points_are_within_the_logical_limit(mc):
    report = mc.run_checks()
    counts = report["logical_line_counts"]
    assert set(counts) == {"backend/main.py", "frontend/src/App.tsx"}
    for rel, count in counts.items():
        assert count <= mc.HARD_LIMIT_FILES[rel], f"{rel} holds {count} logical lines"
    assert [f for f in report["findings"] if f["kind"] == "file_size_hard"] == []


def test_single_quoted_docstring_does_not_swallow_the_file():
    """A `'''` docstring closed by `'''`, not by `\"\"\"` (Codex review on #415)."""
    from maintainer_lib.sizes import count_logical_lines
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "main.py"
        path.write_text(
            "'''Module docstring\nspanning lines\n'''\n"
            + "".join(f"value{i} = {i}\n" for i in range(250)),
            encoding="utf-8",
        )
        assert count_logical_lines(path) == 250


def test_multiline_named_imports_are_not_logic(tmp_path: Path):
    from maintainer_lib.sizes import count_logical_lines

    tsx = tmp_path / "App.tsx"
    tsx.write_text(
        "import {\n  AlphaProvider,\n  BetaProvider,\n  GammaProvider,\n} from './providers';\n"
        "import { Solo } from './solo';\n"
        "const wiring = 1;\n",
        encoding="utf-8",
    )
    assert count_logical_lines(tsx) == 1

    py = tmp_path / "main.py"
    py.write_text(
        "from x import (\n    alpha,\n    beta,\n)\n"
        "import os\n"
        "app = 1\n",
        encoding="utf-8",
    )
    assert count_logical_lines(py) == 1


# --- the backend lint, ruff (AGENTS.md §6.7) -------------------------------------------------------

def _lint_root(tmp_path: Path, pin: str | None = "0.15.21") -> Path:
    root = tmp_path / "repo"
    (root / "backend").mkdir(parents=True)
    if pin:
        (root / "backend" / "requirements-dev.txt").write_text(f"pytest\nruff=={pin}\npip-audit\n", encoding="utf-8")
    return root


def _ran(stdout: str, returncode: int = 1, stderr: str = ""):
    def run(cmd, **_kwargs):
        assert cmd[1:5] == ["-m", "ruff", "check", "backend"] and "--no-cache" in cmd
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    return run


def _never(*_args, **_kwargs):
    raise AssertionError("ruff must not run here")


def test_a_ruff_finding_is_a_gate_finding_at_its_line(mc, tmp_path: Path):
    from maintainer_lib import lint

    root = _lint_root(tmp_path)
    row = {"code": "B905", "message": "`zip()` without an explicit `strict=` parameter",
           "filename": str(root / "backend" / "issue_report" / "scrub.py"), "location": {"row": 98, "column": 31}}
    findings = lint.check_ruff(root, mc.Finding, run=_ran(json.dumps([row])), installed_fn=lambda: "0.15.21")
    assert [(f.kind, f.path, f.line) for f in findings] == [("ruff", "backend/issue_report/scrub.py", 98)]
    assert findings[0].detail.startswith("B905 `zip()`")
    assert "ruff" in mc.GATE_KINDS


def test_a_clean_lint_is_no_finding(mc, tmp_path: Path):
    from maintainer_lib import lint

    root = _lint_root(tmp_path)
    assert lint.check_ruff(root, mc.Finding, run=_ran("[]", returncode=0), installed_fn=lambda: "0.15.21") == []


def test_no_ruff_here_fails_the_gate_with_the_install_command(mc, tmp_path: Path):
    from maintainer_lib import lint

    [finding] = lint.check_ruff(_lint_root(tmp_path), mc.Finding, run=_never, installed_fn=lambda: None)
    assert finding.kind == "ruff_unavailable" and "ruff_unavailable" in mc.GATE_KINDS
    assert "pip install ruff==0.15.21" in finding.detail


@pytest.mark.parametrize("outcome", ["exit_2", "no_output", "not_json", "found_but_listed_nothing", "timeout"])
def test_a_lint_that_gives_no_answer_is_an_error_never_a_pass(mc, tmp_path: Path, outcome):
    from maintainer_lib import lint

    def timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    run = {
        "exit_2": _ran("", 2, "ruff failed\n  Cause: Failed to parse backend/ruff.toml"),
        "no_output": _ran("", 1, "FileNotFoundError: the ruff binary is missing"),
        "not_json": _ran("backend/x.py:1:1: F401", 1),
        "found_but_listed_nothing": _ran("[]", 1),
        "timeout": timeout,
    }[outcome]
    findings = lint.check_ruff(_lint_root(tmp_path), mc.Finding, run=run, installed_fn=lambda: "0.15.21")
    assert [f.kind for f in findings] == ["ruff_error"]
    assert "ruff_error" in mc.GATE_KINDS


def test_another_ruff_version_is_reported_not_blocking(mc, tmp_path: Path):
    from maintainer_lib import lint

    findings = lint.check_ruff(_lint_root(tmp_path), mc.Finding, run=_ran("[]", 0), installed_fn=lambda: "0.16.0")
    assert [f.kind for f in findings] == ["ruff_version"]
    assert "ruff_version" not in mc.GATE_KINDS
    assert "0.16.0" in findings[0].detail and "ruff==0.15.21" in findings[0].detail


def test_no_backend_folder_is_nothing_to_lint(mc, tmp_path: Path):
    from maintainer_lib import lint

    assert lint.check_ruff(tmp_path, mc.Finding, run=_never, installed_fn=lambda: "0.15.21") == []


def test_the_installed_ruff_reports_a_real_finding(mc, tmp_path: Path):
    """End to end through the installed ruff: its JSON, the path and the line are the contract."""
    pytest.importorskip("ruff")
    from maintainer_lib import lint

    root = _lint_root(tmp_path, pin=None)
    (root / "backend" / "ruff.toml").write_text('[lint]\nselect = ["F"]\n', encoding="utf-8")
    (root / "backend" / "probe.py").write_text('"""Probe."""\n\nimport os\n', encoding="utf-8")
    findings = lint.check_ruff(root, mc.Finding)
    assert [(f.kind, f.path, f.line) for f in findings] == [("ruff", "backend/probe.py", 3)]
    assert findings[0].detail.startswith("F401 ")


def test_the_lint_runs_on_this_repo(mc):
    pytest.importorskip("ruff")
    from maintainer_lib import lint

    kinds = {f.kind for f in lint.check_ruff(REPO_ROOT, mc.Finding)}
    assert not kinds & {"ruff_error", "ruff_unavailable"}, kinds


def test_the_gate_collects_the_lint(mc, monkeypatch):
    finding = mc.Finding(kind="ruff", path="backend/x.py", detail="F401 `os` imported but unused", line=1)
    monkeypatch.setattr(mc, "check_ruff", lambda root, finding_cls: [finding])
    assert finding in mc._collect([], None)
