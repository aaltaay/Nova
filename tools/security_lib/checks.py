"""Nova-specific built-in static security checks.

Strangler facade (ADR 004). Implementation lives in:
  checks_helpers, checks_api, checks_infra, checks_tools.

These checks always run without any external binary.  They scan the repo
source files directly using Python.  No subprocess calls here.

Side-effect-free: reads files, returns RawFinding list.

Facade owner: security agent tooling.
Removal criterion: no production/tool caller imports this barrel for a
single check that lives in ``checks_*``; prefer focused modules.
"""

from __future__ import annotations

from tools.security_lib.checks_api import (
    check_config_credentials_exposed,
    check_cors_wildcard,
    check_executor_unauthenticated,
    check_no_api_auth_middleware,
)
from tools.security_lib.checks_helpers import REPO_ROOT, SOURCE
from tools.security_lib.checks_infra import (
    check_ci_missing_security_jobs,
    check_dockerfile_runs_as_root,
)
from tools.security_lib.checks_tools import detect_tools
from tools.security_lib.normalize import RawFinding

__all__ = [
    "REPO_ROOT",
    "SOURCE",
    "check_ci_missing_security_jobs",
    "check_config_credentials_exposed",
    "check_cors_wildcard",
    "check_dockerfile_runs_as_root",
    "check_executor_unauthenticated",
    "check_no_api_auth_middleware",
    "detect_tools",
    "run_builtin_checks",
]


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
