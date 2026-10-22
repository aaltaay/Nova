"""Install ``requirements.txt`` into this interpreter when it changed since the last install.

Runs from ``run_api.main`` before the app is imported, so no package it upgrades is loaded yet
(Windows refuses to replace a loaded ``.pyd``). A stamp in ``backend/.cache`` remembers the
requirements' hash per interpreter, so an unchanged file costs one hash and no pip run. A frozen
engine carries its packages inside it and is never touched. A pip that fails is logged and the
start goes on: the stamp stays old, so the next start tries again. Logging is not configured yet
this early, so every line goes to stderr, which the launchers write to the API console log.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path



def _say(text: str) -> None:
    print(f"[package sync] {text}", file=sys.stderr, flush=True)

BACKEND_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = BACKEND_DIR / "requirements.txt"
STAMP_FILE = BACKEND_DIR / ".cache" / "requirements-installed.json"
STAMP_SCHEMA_VERSION = 1
PIP_TIMEOUT_S = 900
# Set to "1" to start without looking at the packages (a machine with no network, say).
SKIP_ENV = "NOVA_SKIP_PACKAGE_SYNC"


def requirements_hash(path: Path = REQUIREMENTS_FILE) -> str | None:
    """sha256 of the requirements file; None when it cannot be read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def read_stamp(path: Path = STAMP_FILE) -> dict | None:
    """The last install's ``{schema_version, sha256, python}``; None when missing or unreadable."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict) or body.get("schema_version") != STAMP_SCHEMA_VERSION:
        return None
    return body


def write_stamp(digest: str, python: str, path: Path = STAMP_FILE) -> None:
    body = {"schema_version": STAMP_SCHEMA_VERSION, "sha256": digest, "python": python}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    except OSError:
        _say(f"could not write {path}; the next start installs again")


def pip_install(requirements: Path, python: str, run=subprocess.run) -> tuple[bool, str]:
    """``python -m pip install -r requirements``: ``(ok, last line of its output)``."""
    try:
        out = run(
            [python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-r", str(requirements)],
            cwd=str(requirements.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PIP_TIMEOUT_S,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    lines = [line.strip() for line in f"{out.stdout}\n{out.stderr}".splitlines() if line.strip()]
    return out.returncode == 0, lines[-1] if lines else f"exit code {out.returncode}"


def sync_packages(
    *,
    requirements: Path = REQUIREMENTS_FILE,
    stamp: Path = STAMP_FILE,
    python: str | None = None,
    frozen: bool | None = None,
    env: dict | None = None,
    install=pip_install,
    say=_say,
) -> str:
    """Bring this interpreter to ``requirements``; returns what happened (``frozen``, ``skipped``,
    ``current``, ``unreadable``, ``installed`` or ``failed``). Never raises."""
    if frozen if frozen is not None else getattr(sys, "frozen", False):
        return "frozen"
    if (env if env is not None else os.environ).get(SKIP_ENV) == "1":
        return "skipped"
    python = python or sys.executable
    digest = requirements_hash(requirements)
    if digest is None:
        say(f"cannot read {requirements}")
        return "unreadable"
    last = read_stamp(stamp)
    if last and last.get("sha256") == digest and last.get("python") == python:
        return "current"
    say(f"{requirements.name} changed since the last install; installing into {python}")
    ok, line = install(requirements, python)
    if not ok:
        say(f"pip install failed ({line}); the backend starts on the packages it has")
        return "failed"
    write_stamp(digest, python, stamp)
    say(f"installed {requirements.name} ({line})")
    return "installed"
