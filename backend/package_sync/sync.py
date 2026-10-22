"""Install ``requirements.txt`` into this interpreter when it changed since the last install.

Runs from ``run_api.main`` before the app is imported, so no package it upgrades is loaded yet
(Windows refuses to replace a loaded ``.pyd``). A stamp in ``backend/.cache`` remembers the
requirements' hash per interpreter, so an unchanged file costs one hash and no pip run. A frozen
engine carries its packages inside it and is never touched. A pip that fails is logged and the
start goes on: the stamp stays old, so the next start tries again. Logging is not configured yet
this early, so every line goes to stderr, which the launchers write to the API console log.

Starts can overlap (the localhost watchdog retries a start that has not answered in 25 s), so one
install runs at a time: an OS lock beside the stamp is held across reading the stamp again and
installing, and a start that finds a backend already running (it holds the API instance guard,
api_lock_handle.py) never touches the packages under it -- the next start installs.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = BACKEND_DIR / "requirements.txt"
STAMP_FILE = BACKEND_DIR / ".cache" / "requirements-installed.json"
STAMP_SCHEMA_VERSION = 1
PIP_TIMEOUT_S = 900
# Set to "1" to start without looking at the packages (a machine with no network, say).
SKIP_ENV = "NOVA_SKIP_PACKAGE_SYNC"
INSTALL_LOCK_FILE = BACKEND_DIR / ".cache" / "requirements-install.lock"
# Another start's install can take as long as pip may; a little more, then this start goes on.
INSTALL_LOCK_WAIT_S = PIP_TIMEOUT_S + 60
INSTALL_LOCK_POLL_S = 1.0


def _say(text: str) -> None:
    print(f"[package sync] {text}", file=sys.stderr, flush=True)


@contextmanager
def install_lock(path: Path = INSTALL_LOCK_FILE, wait_s: float = INSTALL_LOCK_WAIT_S):
    """Hold the one-install-at-a-time lock: yields True when held, False when waiting ran out."""
    from api_lock_handle import try_lock

    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait_s
    handle = try_lock(path)
    while handle is None and time.monotonic() < deadline:
        time.sleep(INSTALL_LOCK_POLL_S)
        handle = try_lock(path)
    try:
        yield handle is not None
    finally:
        if handle is not None:
            handle.close()


def backend_running() -> bool:
    """True while another backend holds the API instance guard (api_lock_handle.py)."""
    from api_lock_handle import guard_path, try_lock

    path = guard_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = try_lock(path)
    if handle is None:
        return True
    handle.close()
    return False


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
    lock=install_lock,
    running=backend_running,
) -> str:
    """Bring this interpreter to ``requirements``; returns what happened (``frozen``, ``skipped``,
    ``current``, ``unreadable``, ``busy``, ``installed`` or ``failed``). Never raises."""
    try:
        return _sync(requirements, stamp, python, frozen, env, install, say, lock, running)
    except Exception as exc:  # the start goes on: the next one tries again
        say(f"could not check the packages ({exc}); the backend starts on the packages it has")
        return "failed"


def _sync(requirements, stamp, python, frozen, env, install, say, lock, running) -> str:
    if frozen if frozen is not None else getattr(sys, "frozen", False):
        return "frozen"
    if (env if env is not None else os.environ).get(SKIP_ENV) == "1":
        return "skipped"
    python = python or sys.executable
    digest = requirements_hash(requirements)
    if digest is None:
        say(f"cannot read {requirements}")
        return "unreadable"
    if _stamped(stamp, digest, python):
        return "current"
    with lock() as held:
        if not held:
            say("another start is still installing; this one starts on the packages it has")
            return "busy"
        # Read again under the lock: the start that held it may have installed this very file.
        if _stamped(stamp, digest, python):
            return "current"
        if running():
            say("another backend is running; its packages are left alone until the next start")
            return "busy"
        say(f"{requirements.name} changed since the last install; installing into {python}")
        ok, line = install(requirements, python)
        if not ok:
            say(f"pip install failed ({line}); the backend starts on the packages it has")
            return "failed"
        write_stamp(digest, python, stamp)
    say(f"installed {requirements.name} ({line})")
    return "installed"


def _stamped(stamp: Path, digest: str, python: str) -> bool:
    last = read_stamp(stamp)
    return bool(last and last.get("sha256") == digest and last.get("python") == python)
