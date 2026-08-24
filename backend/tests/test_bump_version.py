"""Tests for tools/bump_version.py (commit-count semver)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_show_reports_semver_shape():
    proc = _run("--show")
    assert proc.returncode == 0
    assert "commits=" in proc.stdout
    assert "head=0.1." in proc.stdout


def test_sync_writes_matching_version(tmp_path: Path, monkeypatch):
    bump_version = _load_bump_version()
    vf = tmp_path / "VERSION"
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"name": "nova", "version": "0.1.0"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(bump_version, "VERSION_FILE", vf)
    monkeypatch.setattr(bump_version, "PACKAGE_JSON", pkg)
    monkeypatch.setattr(bump_version, "git_commit_count", lambda: 418)

    assert bump_version.run_sync() == 0
    assert vf.read_text(encoding="utf-8").strip() == "0.1.418"
    data = json.loads(pkg.read_text(encoding="utf-8"))
    assert data["version"] == "0.1.418"


def test_pre_commit_targets_next_count(tmp_path: Path, monkeypatch):
    bump_version = _load_bump_version()
    vf = tmp_path / "VERSION"
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"name": "nova", "version": "0.1.0"}) + "\n", encoding="utf-8")
    vf.write_text("0.1.0\n", encoding="utf-8")
    monkeypatch.setattr(bump_version, "VERSION_FILE", vf)
    monkeypatch.setattr(bump_version, "PACKAGE_JSON", pkg)
    monkeypatch.setattr(bump_version, "git_commit_count", lambda: 10)
    monkeypatch.setattr(bump_version, "is_amend_commit", lambda: False)
    staged: list[list[str]] = []
    monkeypatch.setattr(
        bump_version.subprocess,
        "run",
        lambda cmd, **kwargs: staged.append(cmd) or subprocess.CompletedProcess(cmd, 0),
    )

    assert bump_version.run_pre_commit() == 0
    assert vf.read_text(encoding="utf-8").strip() == "0.1.11"
    assert staged and "git" in staged[0]


def test_pre_push_fails_on_drift(tmp_path: Path, monkeypatch):
    bump_version = _load_bump_version()
    vf = tmp_path / "VERSION"
    pkg = tmp_path / "package.json"
    vf.write_text("0.1.1\n", encoding="utf-8")
    pkg.write_text(json.dumps({"name": "nova", "version": "0.1.1"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(bump_version, "VERSION_FILE", vf)
    monkeypatch.setattr(bump_version, "PACKAGE_JSON", pkg)
    monkeypatch.setattr(bump_version, "git_commit_count", lambda: 99)

    assert bump_version.run_pre_push() == 1


def test_pre_push_ok_when_aligned(tmp_path: Path, monkeypatch):
    bump_version = _load_bump_version()
    vf = tmp_path / "VERSION"
    pkg = tmp_path / "package.json"
    vf.write_text("0.1.99\n", encoding="utf-8")
    pkg.write_text(json.dumps({"name": "nova", "version": "0.1.99"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(bump_version, "VERSION_FILE", vf)
    monkeypatch.setattr(bump_version, "PACKAGE_JSON", pkg)
    monkeypatch.setattr(bump_version, "git_commit_count", lambda: 99)

    assert bump_version.run_pre_push() == 0
