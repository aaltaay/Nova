"""The backend lint as maintainer findings -- ``ruff check backend``, the check CI's Backend tests runs.

AGENTS.md §6.7. CI runs Ruff before pytest; here the same command joins ``--gate``, so an agent
meets a lint finding before the push instead of on the PR. The rules are ``backend/ruff.toml``;
the version is the ``ruff==`` pin in ``backend/requirements-dev.txt`` (CI installs that pin, and
``tools/test_deploy_workflow_maintainer.py`` holds every ``ruff==`` in the workflow to it).

An unrun lint is never a pass: ruff missing from this interpreter is ``ruff_unavailable`` and a
run that could not finish is ``ruff_error``, both gate kinds. A ruff other than the pinned version
is ``ruff_version`` -- reported, not blocking, since its findings may differ from CI's.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

LINT_TARGET = "backend"
PIN_FILE = "backend/requirements-dev.txt"
RUFF_TIMEOUT_SEC = 120
_PIN = re.compile(r"^ruff==(\S+)\s*$", re.MULTILINE)


def pinned_version(repo_root: Path) -> str | None:
    """The ruff version ``backend/requirements-dev.txt`` pins, or None when it pins none."""
    try:
        text = (repo_root / PIN_FILE).read_text(encoding="utf-8")
    except OSError:
        return None
    match = _PIN.search(text)
    return match.group(1) if match else None


def installed_version() -> str | None:
    """This interpreter's ruff version; None when ``python -m ruff`` cannot run here."""
    if importlib.util.find_spec("ruff") is None:
        return None
    try:
        return importlib.metadata.version("ruff")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _rel(repo_root: Path, filename: str) -> str:
    try:
        return Path(filename).resolve().relative_to(repo_root.resolve()).as_posix()
    except (OSError, ValueError):
        return filename.replace("\\", "/")


def _first_line(text: str | None) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[0][:200] if lines else "no output"


def check_ruff(
    repo_root: Path,
    finding_cls: type,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    installed_fn: Callable[[], str | None] = installed_version,
) -> list:
    """Every ruff finding in ``backend/`` as a ``ruff`` finding, or why the lint did not run."""
    if not (repo_root / LINT_TARGET).is_dir():
        return []
    pin = pinned_version(repo_root)
    fix = f"py -3 -m pip install ruff=={pin}" if pin else f"py -3 -m pip install -r {PIN_FILE}"
    here = installed_fn()
    if here is None:
        return [finding_cls(
            kind="ruff_unavailable", path=PIN_FILE,
            detail=f"ruff is not installed for {sys.executable}, so the backend lint did not run -- {fix}",
        )]
    findings = []
    if pin and here != pin:
        findings.append(finding_cls(
            kind="ruff_version", path=PIN_FILE,
            detail=f"ruff {here} here, CI pins {pin}: its findings may differ -- {fix}",
        ))
    cmd = [sys.executable, "-m", "ruff", "check", LINT_TARGET, "--output-format", "json", "--no-cache"]
    try:
        proc = run(cmd, cwd=repo_root, capture_output=True, encoding="utf-8", errors="replace",
                   timeout=RUFF_TIMEOUT_SEC, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return findings + [finding_cls(
            kind="ruff_error", path=LINT_TARGET,
            detail=f"ruff did not finish ({type(exc).__name__}: {exc})",
        )]
    try:
        rows = json.loads(proc.stdout) if proc.returncode in (0, 1) else None
    except json.JSONDecodeError:
        rows = None
    # Exit 1 means "found something"; an empty or unreadable list then is no answer, not a pass.
    if not isinstance(rows, list) or (proc.returncode == 1 and not rows):
        return findings + [finding_cls(
            kind="ruff_error", path=LINT_TARGET,
            detail=f"ruff exited {proc.returncode} without a readable answer: {_first_line(proc.stderr)}",
        )]
    for row in rows:
        loc = row.get("location") or {}
        findings.append(finding_cls(
            kind="ruff", path=_rel(repo_root, str(row.get("filename") or "")), line=loc.get("row"),
            detail=f"{row.get('code') or 'syntax'} {row.get('message') or ''}".strip(),
        ))
    return findings
