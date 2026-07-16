"""Nova-specific built-in static security checks.

These checks always run without any external binary.  They scan the repo
source files directly using Python.  No subprocess calls here.

Side-effect-free: reads files, returns RawFinding list.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.security_lib.normalize import RawFinding
from tools.security_lib.redact import redact

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SOURCE = "nova-builtin"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _location(path: str, line: int | None) -> str:
    if line:
        return f"{path}:{line}"
    return path


def _line_of(text: str, match: re.Match[str]) -> int:
    return text.count("\n", 0, match.start()) + 1


# ---------------------------------------------------------------------------
# Check A: GET /api/config returns raw api_key / api_secret
# ---------------------------------------------------------------------------

_CONFIG_ROUTE_FILE = REPO_ROOT / "backend" / "routes" / "health.py"

_APIKEY_PATTERN = re.compile(
    r"""["']api_key["']\s*:\s*_env\s*\("""
    r"""|["']api_secret["']\s*:\s*_env\s*\(""",
    re.MULTILINE,
)


def check_config_credentials_exposed() -> list[RawFinding]:
    """Check that GET /api/config returns raw credentials."""
    path = _CONFIG_ROUTE_FILE
    rel = _rel(path)
    text = _read(path)
    if text is None:
        return []

    findings = []
    for m in _APIKEY_PATTERN.finditer(text):
        line = _line_of(text, m)
        snippet = text[max(0, m.start() - 40) : m.end() + 80].strip()
        findings.append(
            RawFinding(
                source=SOURCE,
                kind="config_credentials_exposed",
                path=rel,
                title="GET /api/config returns raw API credentials",
                detail=(
                    "The GET /api/config endpoint returns the plaintext APCA_API_KEY_ID "
                    "and APCA_API_SECRET_KEY values to any caller with network access. "
                    "This leaks broker credentials to any authenticated or unauthenticated "
                    "client that can reach the API port."
                ),
                severity="critical",
                location=_location(rel, line),
                redacted_evidence=redact(snippet),
                cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
                cvss_score=7.5,
                cwe="CWE-200",
                asvs="V2.10.1",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Check B: Unauthenticated executor POST routes
# ---------------------------------------------------------------------------

_EXECUTOR_ROUTE_FILE = REPO_ROOT / "backend" / "routes" / "executor.py"

_POST_ROUTE_PATTERN = re.compile(r"""@router\.post\s*\(""", re.MULTILINE)
_DEPENDS_PATTERN = re.compile(r"""Depends\s*\(""", re.MULTILINE)


def check_executor_unauthenticated() -> list[RawFinding]:
    """Check executor routes have no auth Depends."""
    path = _EXECUTOR_ROUTE_FILE
    rel = _rel(path)
    text = _read(path)
    if text is None:
        return []

    post_routes = list(_POST_ROUTE_PATTERN.finditer(text))
    has_depends = bool(_DEPENDS_PATTERN.search(text))

    if post_routes and not has_depends:
        first_line = _line_of(text, post_routes[0])
        snippet = f"{len(post_routes)} POST route(s); no Depends(...) auth guard found"
        return [
            RawFinding(
                source=SOURCE,
                kind="executor_unauthenticated",
                path=rel,
                title="Executor POST routes have no authentication guard",
                detail=(
                    f"{rel} exposes {len(post_routes)} POST routes including arm, "
                    "kill-switch, disarm, flatten, approve/reject staged tickets — "
                    "none of which use a FastAPI Depends() authentication guard. "
                    "Any network client can trigger executor state changes without credentials."
                ),
                severity="critical",
                location=_location(rel, first_line),
                redacted_evidence=snippet,
                cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                cvss_score=9.8,
                cwe="CWE-306",
                asvs="V4.1.1",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Check C: CORS wildcard default
# ---------------------------------------------------------------------------

_CONSTANTS_FILE = REPO_ROOT / "backend" / "constants.py"

_CORS_WILDCARD_PATTERN = re.compile(
    r"""CORS_ALLOWED_ORIGINS_DEFAULT\s*=\s*\[["']\*["']\]""",
    re.MULTILINE,
)


def check_cors_wildcard() -> list[RawFinding]:
    """Check for CORS_ALLOWED_ORIGINS_DEFAULT = ['*']."""
    path = _CONSTANTS_FILE
    rel = _rel(path)
    text = _read(path)
    if text is None:
        return []

    findings = []
    for m in _CORS_WILDCARD_PATTERN.finditer(text):
        line = _line_of(text, m)
        snippet = m.group(0)
        findings.append(
            RawFinding(
                source=SOURCE,
                kind="cors_wildcard",
                path=rel,
                title="CORS_ALLOWED_ORIGINS_DEFAULT is set to wildcard [\"*\"]",
                detail=(
                    "constants.py sets CORS_ALLOWED_ORIGINS_DEFAULT = [\"*\"], which allows "
                    "any web origin to make cross-origin requests to the API. This is acceptable "
                    "in pure local-dev, but becomes a high-risk misconfiguration if the API is "
                    "deployed to Railway without setting NOVA_CORS_ALLOWED_ORIGINS in the env."
                ),
                severity="high",
                location=_location(rel, line),
                redacted_evidence=snippet,
                cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N",
                cvss_score=5.4,
                cwe="CWE-942",
                asvs="V14.4.2",
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Check D: No API auth middleware in backend
# ---------------------------------------------------------------------------

_AUTH_MIDDLEWARE_PATTERNS = [
    re.compile(r"""APIKeyHeader|OAuth2|HTTPBearer|HTTPBasic""", re.MULTILINE),
    re.compile(r"""add_middleware.*[Aa]uth""", re.MULTILINE),
    re.compile(r"""Depends\s*\(\s*(?:get_current_user|verify_token|require_auth)""", re.MULTILINE),
]

_BACKEND_PYTHON_GLOB = "backend/**/*.py"


def check_no_api_auth_middleware() -> list[RawFinding]:
    """Check that no auth middleware or global Depends is present in backend."""
    backend_dir = REPO_ROOT / "backend"
    if not backend_dir.exists():
        return []

    found_any = False
    for py_file in backend_dir.rglob("*.py"):
        # Skip test files and __pycache__
        if "test" in py_file.name.lower() or "__pycache__" in str(py_file):
            continue
        text = _read(py_file)
        if text is None:
            continue
        for pat in _AUTH_MIDDLEWARE_PATTERNS:
            if pat.search(text):
                found_any = True
                break
        if found_any:
            break

    if not found_any:
        return [
            RawFinding(
                source=SOURCE,
                kind="no_api_auth_middleware",
                path="backend/",
                title="No API authentication middleware found in backend",
                detail=(
                    "No FastAPI auth patterns (APIKeyHeader, HTTPBearer, OAuth2, or a "
                    "global Depends with a known auth guard name) were found across the "
                    "backend Python files. All API routes are effectively unauthenticated, "
                    "including sensitive /api/config, /api/strategy/executor, and "
                    "/api/trading endpoints."
                ),
                severity="high",
                location="backend/main.py:1",
                redacted_evidence="No APIKeyHeader/HTTPBearer/OAuth2 found in backend/**/*.py",
                cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
                cvss_score=9.1,
                cwe="CWE-306",
                asvs="V4.1.1",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Check E: CI deploy.yml missing security jobs
# ---------------------------------------------------------------------------

_CI_FILE = REPO_ROOT / ".github" / "workflows" / "deploy.yml"

_SECURITY_JOB_PATTERNS = [
    re.compile(r"gitleaks", re.IGNORECASE),
    re.compile(r"osv.?scanner|osv-scan", re.IGNORECASE),
    re.compile(r"semgrep", re.IGNORECASE),
]


def check_ci_missing_security_jobs() -> list[RawFinding]:
    """Check that deploy.yml includes dedicated security scanners.

    A warning-only ``security-audit`` job that runs ``tools/security_audit.py``
    is progress but does not replace gitleaks / osv-scanner / semgrep coverage.
    """
    path = _CI_FILE
    rel = _rel(path)
    text = _read(path)
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
            path=rel,
            title=f"CI deploy.yml missing security scan jobs: {', '.join(missing)}",
            detail=(
                f"The GitHub Actions workflow at {rel} does not include jobs for: "
                f"{', '.join(missing)}. Secret leaks and known-vulnerable dependencies "
                f"can reach production undetected.{note}"
            ),
            severity="medium",
            location=_location(rel, 1),
            redacted_evidence=f"Missing: {', '.join(missing)}",
            asvs="V14.2.1",
        )
    ]


# ---------------------------------------------------------------------------
# Check F: Dockerfile runs as root (no USER directive)
# ---------------------------------------------------------------------------

_DOCKERFILE = REPO_ROOT / "Dockerfile"


def check_dockerfile_runs_as_root() -> list[RawFinding]:
    """Flag root Docker images with no USER directive."""
    path = _DOCKERFILE
    rel = _rel(path)
    text = _read(path)
    if text is None:
        return []
    if re.search(r"(?m)^\s*USER\s+\S+", text):
        return []
    return [
        RawFinding(
            source=SOURCE,
            kind="dockerfile_runs_as_root",
            path=rel,
            title="Dockerfile runs container process as root (no USER directive)",
            detail=(
                "Root Dockerfile has no USER directive, so uvicorn runs as UID 0. "
                "A container escape or path-traversal bug would yield root privileges. "
                "Add a non-root user before CMD."
            ),
            severity="medium",
            location=_location(rel, 1),
            redacted_evidence="No USER directive found before CMD",
            cwe="CWE-250",
            asvs="V14.1.3",
        )
    ]


# ---------------------------------------------------------------------------
# External tool availability detection
# ---------------------------------------------------------------------------

_EXTERNAL_TOOLS = {
    "semgrep": ["semgrep", "--version"],
    "gitleaks": ["gitleaks", "version"],
    "osv-scanner": ["osv-scanner", "--version"],
    "trivy": ["trivy", "--version"],
    "pip_audit": ["pip-audit", "--version"],
    "npm": ["npm", "--version"],
}


def detect_tools() -> tuple[list[str], list[str]]:
    """Return (available_tools, blocked_tools)."""
    available: list[str] = []
    blocked: list[str] = []
    for name, cmd in _EXTERNAL_TOOLS.items():
        if shutil.which(cmd[0]) is None:
            blocked.append(name)
            continue
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0 or result.returncode == 1:
                available.append(name)
            else:
                blocked.append(name)
        except (OSError, subprocess.TimeoutExpired):
            blocked.append(name)
    return available, blocked


# ---------------------------------------------------------------------------
# Main entry: run all built-in checks
# ---------------------------------------------------------------------------

def run_builtin_checks() -> list[RawFinding]:
    """Run all Nova-specific built-in checks and return findings."""
    findings: list[RawFinding] = []
    findings.extend(check_config_credentials_exposed())
    findings.extend(check_executor_unauthenticated())
    findings.extend(check_cors_wildcard())
    findings.extend(check_no_api_auth_middleware())
    findings.extend(check_ci_missing_security_jobs())
    findings.extend(check_dockerfile_runs_as_root())
    return findings
