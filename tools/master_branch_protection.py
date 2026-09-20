#!/usr/bin/env python3
"""Apply and verify GitHub protection on Nova's default branch.

Closes the Security Overview hole: "Your master branch isn't protected."

Policy (solo public repo):
- Block force-push and deletion, including for admins.
- Require gating CI checks before a PR can merge.
- Do not require pull-request reviews (would deadlock a solo merge).
- Do not require a PR to push (status-only master commits).

Usage:
  python3 tools/master_branch_protection.py check
  python3 tools/master_branch_protection.py apply
  python3 tools/master_branch_protection.py dump-policy

`apply` needs a token with Administration on aaltaay/Nova. Cloud Agent
integrations return 403 on PUT and on GET /protection. `check` still
works: GET /branches/master includes a public `protection` summary
(required checks + `enforcement_level`). Public repos unlock branch
protection on GitHub Free. A private personal repo still needs GitHub Pro.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

DEFAULT_REPO = "aaltaay/Nova"
DEFAULT_BRANCH = "master"

# Job `name:` values from `.github/workflows/deploy.yml`. Do not require
# warning-only scanners (Semgrep has been red on master).
REQUIRED_CONTEXTS: tuple[str, ...] = (
    "Backend tests",
    "Frontend build",
    "Frontend E2E",
    "Agent contract",
)

EXIT_OK = 0
EXIT_UNPROTECTED = 1
EXIT_BLOCKED = 2
EXIT_USAGE = 3


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    status: str
    reasons: tuple[str, ...]
    exit_code: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "reasons": list(self.reasons),
            "exit_code": self.exit_code,
        }


def repo_slug() -> str:
    return (os.environ.get("NOVA_GITHUB_REPO") or DEFAULT_REPO).strip()


def apply_payload() -> dict[str, Any]:
    """PUT /branches/{branch}/protection body."""
    checks = [{"context": name} for name in REQUIRED_CONTEXTS]
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": list(REQUIRED_CONTEXTS),
            "checks": checks,
        },
        "enforce_admins": True,
        "required_pull_request_reviews": None,
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_conversation_resolution": False,
        "lock_branch": False,
    }


def required_contexts(protection: dict[str, Any]) -> set[str]:
    block = protection.get("required_status_checks") or {}
    names: set[str] = set()
    for item in block.get("contexts") or []:
        if item:
            names.add(str(item))
    for item in block.get("checks") or []:
        if isinstance(item, dict) and item.get("context"):
            names.add(str(item["context"]))
        elif isinstance(item, str) and item:
            names.add(item)
    return names


def classify_http_error(status: int, message: str) -> str:
    text = (message or "").lower()
    if status == 404:
        return "not_found"
    if status == 403:
        if "upgrade to github pro" in text or "make this repository public" in text:
            return "plan_required"
        if "not accessible by integration" in text:
            return "integration_forbidden"
        return "forbidden"
    return "http"


def _flag_enabled(block: Any, default: bool | None = None) -> bool | None:
    if block is None:
        return default
    if isinstance(block, bool):
        return block
    if isinstance(block, dict) and "enabled" in block:
        return bool(block["enabled"])
    return default


def _is_public_summary(protection: dict[str, Any]) -> bool:
    """Branch payload `protection` omits admin-only force-push / deletion flags."""
    return (
        "allow_force_pushes" not in protection
        and "allow_deletions" not in protection
        and "enforce_admins" not in protection
    )


def evaluate(
    *,
    branch_protected: bool | None,
    protection: dict[str, Any] | None,
    error: str | None,
) -> CheckResult:
    if error == "integration_forbidden":
        return CheckResult(
            False,
            "integration_forbidden",
            ("GitHub App token lacks Administration; cannot read or set protection.",),
            EXIT_BLOCKED,
        )
    if error == "plan_required":
        return CheckResult(
            False,
            "plan_required",
            (
                "Private repo branch protection needs GitHub Pro. "
                "Public Nova unlocks this setting on GitHub Free.",
            ),
            EXIT_BLOCKED,
        )
    if error == "forbidden":
        return CheckResult(
            False,
            "integration_forbidden",
            ("GitHub returned 403; token cannot administer branch protection.",),
            EXIT_BLOCKED,
        )
    if error == "not_found" or not branch_protected or protection is None:
        return CheckResult(
            False,
            "unprotected",
            ("master is not protected (force-push and deletion are open).",),
            EXIT_UNPROTECTED,
        )
    if protection.get("enabled") is False:
        return CheckResult(
            False,
            "unprotected",
            ("master is not protected (force-push and deletion are open).",),
            EXIT_UNPROTECTED,
        )

    reasons: list[str] = []
    if _is_public_summary(protection):
        level = (protection.get("required_status_checks") or {}).get(
            "enforcement_level"
        )
        if level != "everyone":
            reasons.append(
                "Admins can bypass protection (enforcement_level is not everyone)."
            )
    else:
        if _flag_enabled(protection.get("allow_force_pushes"), default=True):
            reasons.append("Force-push is still allowed.")
        if _flag_enabled(protection.get("allow_deletions"), default=True):
            reasons.append("Branch deletion is still allowed.")
        if _flag_enabled(protection.get("enforce_admins"), default=False) is False:
            reasons.append("Admins can bypass protection (owner force-push hole).")

    have = required_contexts(protection)
    missing = [name for name in REQUIRED_CONTEXTS if name not in have]
    if missing:
        reasons.append("Missing required status checks: " + ", ".join(missing))

    if reasons:
        return CheckResult(False, "policy_mismatch", tuple(reasons), EXIT_UNPROTECTED)
    return CheckResult(True, "ok", (), EXIT_OK)


def _gh_api(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> tuple[int, int, dict[str, Any] | None, str]:
    cmd = ["gh", "api", "-i", "--method", method, path]
    proc = subprocess.run(
        cmd,
        input=json.dumps(body) if body is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    raw = proc.stdout
    header_blob, _, rest = raw.partition("\r\n\r\n")
    if rest == "" and "\n\n" in raw:
        header_blob, _, rest = raw.partition("\n\n")
    http_status = 0
    for line in header_blob.splitlines():
        if line.upper().startswith("HTTP/"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                http_status = int(parts[1])
    payload: dict[str, Any] | None = None
    text = (rest or proc.stderr or "").strip()
    if text:
        try:
            loaded = json.loads(text)
            if isinstance(loaded, dict):
                payload = loaded
        except json.JSONDecodeError:
            payload = None
    message = ""
    if payload and payload.get("message"):
        message = str(payload["message"])
    elif text:
        message = text[:400]
    return proc.returncode, http_status, payload, message


def _branch_path(branch: str) -> str:
    return f"repos/{repo_slug()}/branches/{branch}"


def check_live(branch: str = DEFAULT_BRANCH) -> CheckResult:
    code, status, payload, message = _gh_api(_branch_path(branch))
    if payload is None and (status in (401, 403) or code != 0):
        err = classify_http_error(status or 403, message)
        return evaluate(branch_protected=None, protection=None, error=err)

    protected = bool(payload.get("protected")) if payload else False
    summary = payload.get("protection") if payload else None
    if not isinstance(summary, dict):
        summary = None
    if not protected:
        return evaluate(branch_protected=False, protection=None, error=None)

    p_code, p_status, protection, p_message = _gh_api(
        f"{_branch_path(branch)}/protection"
    )
    if p_status < 400 and protection:
        return evaluate(branch_protected=True, protection=protection, error=None)
    if summary:
        return evaluate(branch_protected=True, protection=summary, error=None)
    err = classify_http_error(p_status or 403, p_message)
    if err == "not_found":
        return evaluate(branch_protected=False, protection=None, error="not_found")
    return evaluate(branch_protected=protected, protection=None, error=err)


def apply_live(branch: str = DEFAULT_BRANCH) -> CheckResult:
    code, status, payload, message = _gh_api(
        f"{_branch_path(branch)}/protection",
        method="PUT",
        body=apply_payload(),
    )
    if status >= 400 or code != 0:
        err = classify_http_error(status or 403, message)
        result = evaluate(branch_protected=None, protection=None, error=err)
        if result.status == "unprotected":
            return CheckResult(
                False,
                err,
                (message or "PUT branch protection failed.",),
                EXIT_BLOCKED if err in {"plan_required", "integration_forbidden", "forbidden"} else EXIT_UNPROTECTED,
            )
        extra = (message,) if message and message not in result.reasons else ()
        return CheckResult(
            False,
            result.status,
            result.reasons + extra,
            result.exit_code,
        )
    return check_live(branch)


def _print_result(result: CheckResult, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result.as_dict(), indent=2))
        return result.exit_code
    label = "OK" if result.ok else result.status.upper().replace("_", " ")
    print(f"{label}: {repo_slug()}@{DEFAULT_BRANCH}")
    for reason in result.reasons:
        print(f"- {reason}")
    if not result.ok:
        print(
            "Apply with a human admin token: "
            "python3 tools/master_branch_protection.py apply"
        )
        print("UI: https://github.com/aaltaay/Nova/settings/branches")
    return result.exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("check", "apply", "dump-policy"),
        help="check current protection, apply the Nova policy, or print the PUT body",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    args = parser.parse_args(argv)

    if args.command == "dump-policy":
        print(json.dumps(apply_payload(), indent=2))
        return EXIT_OK
    if args.command == "check":
        return _print_result(check_live(args.branch), as_json=args.json)
    if args.command == "apply":
        return _print_result(apply_live(args.branch), as_json=args.json)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
