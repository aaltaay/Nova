"""The backend installs its own packages at start (package_sync/sync.py, operator report 2026-10-21)."""
from __future__ import annotations

import json

from package_sync.sync import STAMP_SCHEMA_VERSION, requirements_hash, sync_packages


def _setup(tmp_path, text="fastapi==1.0\n"):
    req = tmp_path / "requirements.txt"
    req.write_text(text, encoding="utf-8")
    return req, tmp_path / ".cache" / "requirements-installed.json"


def _run(req, stamp, installs, ok=True, **kw):
    def install(path, python):
        installs.append((path, python))
        return ok, "Successfully installed fastapi-1.0" if ok else "ERROR: no network"

    kw.setdefault("frozen", False)
    kw.setdefault("env", {})
    return sync_packages(requirements=req, stamp=stamp, python="py.exe", install=install, say=lambda _t: None, **kw)


def test_installs_once_then_only_when_the_file_changes(tmp_path):
    req, stamp = _setup(tmp_path)
    installs = []
    assert _run(req, stamp, installs) == "installed"
    body = json.loads(stamp.read_text(encoding="utf-8"))
    assert body == {"schema_version": STAMP_SCHEMA_VERSION, "sha256": requirements_hash(req), "python": "py.exe"}
    assert _run(req, stamp, installs) == "current"
    assert len(installs) == 1
    req.write_text("fastapi==1.1\n", encoding="utf-8")
    assert _run(req, stamp, installs) == "installed"
    assert len(installs) == 2


def test_another_interpreter_installs_again(tmp_path):
    req, stamp = _setup(tmp_path)
    installs = []
    _run(req, stamp, installs)
    stamp.write_text(json.dumps({"schema_version": 1, "sha256": requirements_hash(req), "python": "other.exe"}), encoding="utf-8")
    assert _run(req, stamp, installs) == "installed"


def test_a_failed_install_keeps_the_old_stamp_so_the_next_start_tries_again(tmp_path):
    req, stamp = _setup(tmp_path)
    installs = []
    assert _run(req, stamp, installs, ok=False) == "failed"
    assert not stamp.exists()
    assert _run(req, stamp, installs) == "installed"


def test_an_unreadable_or_other_version_stamp_reads_as_never_installed(tmp_path):
    req, stamp = _setup(tmp_path)
    stamp.parent.mkdir(parents=True)
    stamp.write_text("{not json", encoding="utf-8")
    installs = []
    assert _run(req, stamp, installs) == "installed"
    stamp.write_text(json.dumps({"schema_version": 99, "sha256": requirements_hash(req), "python": "py.exe"}), encoding="utf-8")
    assert _run(req, stamp, installs) == "installed"


def test_frozen_skip_and_missing_file_never_run_pip(tmp_path):
    req, stamp = _setup(tmp_path)
    installs = []
    assert _run(req, stamp, installs, frozen=True) == "frozen"
    assert _run(req, stamp, installs, env={"NOVA_SKIP_PACKAGE_SYNC": "1"}) == "skipped"
    assert _run(tmp_path / "missing.txt", stamp, installs) == "unreadable"
    assert installs == []
