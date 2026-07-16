"""CI and infrastructure security checks (ADR 004 strangler split)."""
from __future__ import annotations

import re

from tools.security_lib.checks_helpers import REPO_ROOT, SOURCE, location, read, rel
from tools.security_lib.normalize import RawFinding

_CI_FILE = REPO_ROOT / ".github" / "workflows" / "deploy.yml"

_SECURITY_JOB_PATTERNS = [
    re.compile(r"gitleaks", re.IGNORECASE),
    re.compile(r"osv.?scanner|osv-scan", re.IGNORECASE),
    re.compile(r"semgrep", re.IGNORECASE),
]

_DOCKERFILE = REPO_ROOT / "Dockerfile"


def check_ci_missing_security_jobs() -> list[RawFinding]:
    """Check that deploy.yml includes dedicated security scanners.

    A warning-only ``security-audit`` job that runs ``tools/security_audit.py``
    is progress but does not replace gitleaks / osv-scanner / semgrep coverage.
    """
    path = _CI_FILE
    rel_path = rel(path)
    text = read(path)
    if text is None:
        return [
            RawFinding(
                source=SOURCE,
                kind="ci_missing_security_jobs",
                path=".github/workflows/deploy.yml",
                title="CI workflow file not found — security jobs cannot be verified",
                detail=(
                    ".github/workflows/deploy.yml does not exist. No CI security "
                    "scanning (gitleaks, osv-scanner, semgrep) can be confirmed."
                ),
                severity="medium",
                location=".github/workflows/deploy.yml:0",
                redacted_evidence="File not found",
            )
        ]

    missing = [
        name
        for name, pat in zip(["gitleaks", "osv-scanner", "semgrep"], _SECURITY_JOB_PATTERNS)
        if not pat.search(text)
    ]
    if not missing:
        return []

    has_sentinel_job = bool(
        re.search(r"security-audit|security_audit\.py", text, re.IGNORECASE)
    )
    note = (
        " A warning-only security-audit job already runs tools/security_audit.py;"
        " add dedicated scanner steps next."
        if has_sentinel_job
        else " Add gitleaks, osv-scanner, and semgrep steps before the deploy job."
    )
    return [
        RawFinding(
            source=SOURCE,
            kind="ci_missing_security_jobs",
            path=rel_path,
            title=f"CI deploy.yml missing security scan jobs: {', '.join(missing)}",
            detail=(
                f"The GitHub Actions workflow at {rel_path} does not include jobs for: "
                f"{', '.join(missing)}. Secret leaks and known-vulnerable dependencies "
                f"can reach production undetected.{note}"
            ),
            severity="medium",
            location=location(rel_path, 1),
            redacted_evidence=f"Missing: {', '.join(missing)}",
            asvs="V14.2.1",
        )
    ]


def check_dockerfile_runs_as_root() -> list[RawFinding]:
    """Flag root Docker images with no USER directive."""
    path = _DOCKERFILE
    rel_path = rel(path)
    text = read(path)
    if text is None:
        return []
    if re.search(r"(?m)^\s*USER\s+\S+", text):
        return []
    return [
        RawFinding(
            source=SOURCE,
            kind="dockerfile_runs_as_root",
            path=rel_path,
            title="Dockerfile runs container process as root (no USER directive)",
            detail=(
                "Root Dockerfile has no USER directive, so uvicorn runs as UID 0. "
                "A container escape or path-traversal bug would yield root privileges. "
                "Add a non-root user before CMD."
            ),
            severity="medium",
            location=location(rel_path, 1),
            redacted_evidence="No USER directive found before CMD",
            cwe="CWE-250",
            asvs="V14.1.3",
        )
    ]
