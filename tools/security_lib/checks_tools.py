"""External security tool detection (ADR 004 strangler split)."""
from __future__ import annotations

import shutil
import subprocess

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
