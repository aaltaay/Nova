"""Tests for tools/bump_version.py (commit-count vNNN + electron semver)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUMP = REPO_ROOT / "tools" / "bump_version.py"


def _load_bump_version():
    spec = importlib.util.spec_from_file_location("bump_version", BUMP)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    merged = dict(**{k: str(v) for k, v in (env or {}).items()})
    return subprocess.run(
        [sys.executable, str(BUMP), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**dict(__import__("os").environ), **merged},
        check=False,
    )


def test_format_release_tag_pads_to_three_digits():
    bump = _load_bump_version()
    assert bump.format_release_tag(1) == "v001"
    assert bump.format_release_tag(42) == "v042"
    assert bump.format_release_tag(467) == "v467"
    assert bump.format_release_tag(1000) == "v1000"


def test_parse_release_tag_accepts_vnnn_and_legacy_semver():
    bump = _load_bump_version()
    assert bump.parse_release_count("v001") == 1
    assert bump.parse_release_count("v467") == 467
    assert bump.parse_release_count("v1000") == 1000
    assert bump.parse_release_count("0.1.418") == 418
    assert bump.parse_release_count("not-a-version") is None


def test_show_reports_tag_and_package_shape():
    proc = _run("--show")
    assert proc.returncode == 0
    assert "commits=" in proc.stdout
    assert "tag=v" in proc.stdout
    assert "package=0.1." in proc.stdout


def test_print_tag_is_vnnn_only():
    proc = _run("--print-tag")
    assert proc.returncode == 0
    tag = proc.stdout.strip()
    assert tag.startswith("v")
    assert tag[1:].isdigit()
    assert len(tag) >= 4


def test_sync_writes_tag_and_package(tmp_path: Path, monkeypatch):
    bump = _load_bump_version()
    vf = tmp_path / "VERSION"
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"name": "nova", "version": "0.1.0"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(bump, "VERSION_FILE", vf)
    monkeypatch.setattr(bump, "PACKAGE_JSON", pkg)
    monkeypatch.setattr(bump, "git_commit_count", lambda: 418)

    assert bump.run_sync() == 0
    assert vf.read_text(encoding="utf-8").strip() == "v418"
    data = json.loads(pkg.read_text(encoding="utf-8"))
    assert data["version"] == "0.1.418"


def test_pre_commit_targets_next_count(tmp_path: Path, monkeypatch):
    bump = _load_bump_version()
    vf = tmp_path / "VERSION"
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"name": "nova", "version": "0.1.0"}) + "\n", encoding="utf-8")
    vf.write_text("v001\n", encoding="utf-8")
    monkeypatch.setattr(bump, "VERSION_FILE", vf)
    monkeypatch.setattr(bump, "PACKAGE_JSON", pkg)
    monkeypatch.setattr(bump, "git_commit_count", lambda: 10)
    monkeypatch.setattr(bump, "is_amend_commit", lambda: False)
    staged: list[list[str]] = []
    monkeypatch.setattr(
        bump.subprocess,
        "run",
        lambda cmd, **kwargs: staged.append(cmd) or subprocess.CompletedProcess(cmd, 0),
    )

    assert bump.run_pre_commit() == 0
    assert vf.read_text(encoding="utf-8").strip() == "v011"
    assert json.loads(pkg.read_text(encoding="utf-8"))["version"] == "0.1.11"
    assert staged and "git" in staged[0]


def test_pre_push_fails_on_drift(tmp_path: Path, monkeypatch):
    bump = _load_bump_version()
    vf = tmp_path / "VERSION"
    pkg = tmp_path / "package.json"
    vf.write_text("v001\n", encoding="utf-8")
    pkg.write_text(json.dumps({"name": "nova", "version": "0.1.1"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(bump, "VERSION_FILE", vf)
    monkeypatch.setattr(bump, "PACKAGE_JSON", pkg)
    monkeypatch.setattr(bump, "git_commit_count", lambda: 99)

    assert bump.run_pre_push() == 1


def test_pre_push_ok_when_aligned(tmp_path: Path, monkeypatch):
    bump = _load_bump_version()
    vf = tmp_path / "VERSION"
    pkg = tmp_path / "package.json"
    vf.write_text("v099\n", encoding="utf-8")
    pkg.write_text(json.dumps({"name": "nova", "version": "0.1.99"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(bump, "VERSION_FILE", vf)
    monkeypatch.setattr(bump, "PACKAGE_JSON", pkg)
    monkeypatch.setattr(bump, "git_commit_count", lambda: 99)

    assert bump.run_pre_push() == 0


def test_ensure_tag_skips_when_present(tmp_path: Path, monkeypatch):
    bump = _load_bump_version()
    monkeypatch.setattr(bump, "git_commit_count", lambda: 12)
    monkeypatch.setattr(bump, "existing_tag_commit", lambda tag: "abc123")
    created: list[str] = []
    monkeypatch.setattr(bump, "create_lightweight_tag", lambda tag: created.append(tag))

    assert bump.run_ensure_tag(push=False) == 0
    assert created == []


def test_ensure_tag_creates_missing_tag(monkeypatch):
    bump = _load_bump_version()
    monkeypatch.setattr(bump, "git_commit_count", lambda: 12)
    monkeypatch.setattr(bump, "existing_tag_commit", lambda tag: None)
    created: list[str] = []
    monkeypatch.setattr(bump, "create_lightweight_tag", lambda tag: created.append(tag))

    assert bump.run_ensure_tag(push=False) == 0
    assert created == ["v012"]
