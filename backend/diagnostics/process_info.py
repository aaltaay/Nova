"""Facts about this API process: revision, repo root, cwd, env file (ADR 021).

Owner: this module. The git facts are read once at import (a hung git must
never stall a diagnostics read); the env-file facts are re-read on every call
because the operator may create the file while the API runs.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from constants_diagnostics import DIAG_GIT_TIMEOUT_SEC

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=DIAG_GIT_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        logger.debug("diagnostics: git %s unavailable", args, exc_info=True)
        return None
    if out.returncode != 0:
        return None
    text = (out.stdout or "").strip()
    return text or None


def _frozen_version_text() -> str | None:
    """A packaged desk carries VERSION beside the executable (bump_version.py --sync)."""
    candidate = Path(os.path.dirname(sys.executable)) / "VERSION"
    try:
        return candidate.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def tag_from_count(count: str | None) -> str | None:
    """``vNNN`` from ``git rev-list --count`` output; None when it is not a count."""
    return f"v{count}" if count and count.isdigit() else None


def read_checkout_tag(repo_root: Path = _REPO_ROOT) -> str | None:
    """The checkout's revision on disk now (``vNNN``); None when git cannot say. Waits on git."""
    return tag_from_count(_git(["rev-list", "--count", "HEAD"], repo_root))


def read_git_revision(repo_root: Path = _REPO_ROOT) -> dict[str, Any]:
    """``{release_tag, commit, branch, worktree, git_common_dir, source}``; never raises."""
    frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        tag = _frozen_version_text()
        return {
            "release_tag": tag,
            "commit": None,
            "branch": None,
            "worktree": False,
            "git_common_dir": None,
            "source": "version_file" if tag else "unavailable",
        }
    count = _git(["rev-list", "--count", "HEAD"], repo_root)
    commit = _git(["rev-parse", "--short", "HEAD"], repo_root)
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    common = _git(["rev-parse", "--git-common-dir"], repo_root)
    dot_git = repo_root / ".git"
    return {
        "release_tag": tag_from_count(count),
        "commit": commit,
        "branch": branch,
        # A linked worktree keeps ``.git`` as a file pointing at the main repo.
        "worktree": dot_git.is_file(),
        "git_common_dir": common,
        "source": "git" if count else "unavailable",
    }


REVISION: dict[str, Any] = read_git_revision()


def env_file_facts(path: Path | None = None) -> dict[str, Any]:
    """Where this process reads ``.env`` from and what it found there.

    Reports key *names* count only -- never a value, never a secret.
    """
    from paths import env_file_path

    target = path if path is not None else env_file_path()
    exists = target.is_file()
    keys: list[str] = []
    if exists:
        try:
            from dotenv import dotenv_values

            keys = [k for k in dotenv_values(str(target)).keys() if k]
        except Exception:
            logger.warning("diagnostics: could not parse %s", target, exc_info=True)
    return {
        "path": str(target),
        "exists": exists,
        "keys_loaded": len(keys),
        "keys": sorted(keys),
        "override": bool(os.environ.get("NOVA_ENV_PATH")),
    }


def process_facts(now: float | None = None) -> dict[str, Any]:
    """Everything the process rows are judged from: ``REVISION`` (what this process loaded),
    and ``checkout_tag``, its checkout's revision on disk now as last read."""
    import instance_identity
    from diagnostics.checkout_revision import checkout_tag

    ts = time.time() if now is None else float(now)
    return {
        "pid": instance_identity.PID,
        "parent_pid": instance_identity.PARENT_PID,
        "instance_id": instance_identity.INSTANCE_ID,
        "started_at": instance_identity.STARTED_AT,
        "uptime_sec": max(0.0, ts - float(instance_identity.STARTED_AT)),
        "reload": instance_identity.RELOAD_ENABLED,
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": platform.python_version(),
        "executable": sys.executable,
        "repo_root": str(_REPO_ROOT),
        "backend_dir": str(_BACKEND_DIR),
        "cwd": os.getcwd(),
        "argv0": sys.argv[0] if sys.argv else "",
        **REVISION,
        "checkout_tag": checkout_tag(),
        "env_file": env_file_facts(),
    }
