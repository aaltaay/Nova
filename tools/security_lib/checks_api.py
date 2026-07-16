"""API and backend auth security checks (ADR 004 strangler split)."""
from __future__ import annotations

import re

from tools.security_lib.checks_helpers import REPO_ROOT, SOURCE, line_of, location, read, rel
from tools.security_lib.normalize import RawFinding
from tools.security_lib.redact import redact

_CONFIG_ROUTE_FILE = REPO_ROOT / "backend" / "routes" / "health.py"

_APIKEY_PATTERN = re.compile(
    r"""["']api_key["']\s*:\s*_env\s*\("""
    r"""|["']api_secret["']\s*:\s*_env\s*\(""",
    re.MULTILINE,
)

_EXECUTOR_ROUTE_FILE = REPO_ROOT / "backend" / "routes" / "executor.py"

_POST_ROUTE_PATTERN = re.compile(r"""@router\.post\s*\(""", re.MULTILINE)
_DEPENDS_PATTERN = re.compile(r"""Depends\s*\(""", re.MULTILINE)

_CORS_WILDCARD_PATTERN = re.compile(
    r"""CORS_ALLOWED_ORIGINS_DEFAULT\s*=\s*\[["']\*["']\]""",
    re.MULTILINE,
)

_CORS_CONSTANTS_FILES = (
    REPO_ROOT / "backend" / "constants.py",
    REPO_ROOT / "backend" / "constants_scanner.py",
)

_AUTH_MIDDLEWARE_PATTERNS = [
    re.compile(r"""APIKeyHeader|OAuth2|HTTPBearer|HTTPBasic""", re.MULTILINE),
    re.compile(r"""add_middleware.*[Aa]uth""", re.MULTILINE),
    re.compile(r"""Depends\s*\(\s*(?:get_current_user|verify_token|require_auth)""", re.MULTILINE),
]


def check_config_credentials_exposed() -> list[RawFinding]:
    """Check that GET /api/config returns raw credentials."""
    path = _CONFIG_ROUTE_FILE
    rel_path = rel(path)
    text = read(path)
    if text is None:
        return []

    findings = []
    for m in _APIKEY_PATTERN.finditer(text):
        line = line_of(text, m)
        snippet = text[max(0, m.start() - 40) : m.end() + 80].strip()
        findings.append(
            RawFinding(
                source=SOURCE,
                kind="config_credentials_exposed",
                path=rel_path,
                title="GET /api/config returns raw API credentials",
                detail=(
                    "The GET /api/config endpoint returns the plaintext APCA_API_KEY_ID "
                    "and APCA_API_SECRET_KEY values to any caller with network access. "
                    "This leaks broker credentials to any authenticated or unauthenticated "
                    "client that can reach the API port."
                ),
                severity="critical",
                location=location(rel_path, line),
                redacted_evidence=redact(snippet),
                cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
                cvss_score=7.5,
                cwe="CWE-200",
                asvs="V2.10.1",
            )
        )
    return findings


def check_executor_unauthenticated() -> list[RawFinding]:
    """Check executor routes have no auth Depends."""
    path = _EXECUTOR_ROUTE_FILE
    rel_path = rel(path)
    text = read(path)
    if text is None:
        return []

    post_routes = list(_POST_ROUTE_PATTERN.finditer(text))
    has_depends = bool(_DEPENDS_PATTERN.search(text))

    if post_routes and not has_depends:
        first_line = line_of(text, post_routes[0])
        snippet = f"{len(post_routes)} POST route(s); no Depends(...) auth guard found"
        return [
            RawFinding(
                source=SOURCE,
                kind="executor_unauthenticated",
                path=rel_path,
                title="Executor POST routes have no authentication guard",
                detail=(
                    f"{rel_path} exposes {len(post_routes)} POST routes including arm, "
                    "kill-switch, disarm, flatten, approve/reject staged tickets — "
                    "none of which use a FastAPI Depends() authentication guard. "
                    "Any network client can trigger executor state changes without credentials."
                ),
                severity="critical",
                location=location(rel_path, first_line),
                redacted_evidence=snippet,
                cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                cvss_score=9.8,
                cwe="CWE-306",
                asvs="V4.1.1",
            )
        ]
    return []


def check_cors_wildcard() -> list[RawFinding]:
    """Check for CORS_ALLOWED_ORIGINS_DEFAULT = ['*']."""
    findings = []
    for path in _CORS_CONSTANTS_FILES:
        rel_path = rel(path)
        text = read(path)
        if text is None:
            continue
        for m in _CORS_WILDCARD_PATTERN.finditer(text):
            line = line_of(text, m)
            snippet = m.group(0)
            findings.append(
                RawFinding(
                    source=SOURCE,
                    kind="cors_wildcard",
                    path=rel_path,
                    title="CORS_ALLOWED_ORIGINS_DEFAULT is set to wildcard [\"*\"]",
                    detail=(
                        f"{rel_path} sets CORS_ALLOWED_ORIGINS_DEFAULT = [\"*\"], which allows "
                        "any web origin to make cross-origin requests to the API. This is acceptable "
                        "in pure local-dev, but becomes a high-risk misconfiguration if the API is "
                        "deployed to Railway without setting NOVA_CORS_ALLOWED_ORIGINS in the env."
                    ),
                    severity="high",
                    location=location(rel_path, line),
                    redacted_evidence=snippet,
                    cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N",
                    cvss_score=5.4,
                    cwe="CWE-942",
                    asvs="V14.4.2",
                )
            )
    return findings


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
        text = read(py_file)
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
