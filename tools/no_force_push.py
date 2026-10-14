#!/usr/bin/env python3
"""Apply and verify the GitHub ruleset that refuses force-pushes on every branch.

Owner, 2026-10-14: "Force push, meaning we're deleting work. Everything needs to be merged properly."
AGENTS.md section 5.1 is the law; this is its server-side lock. Master's branch protection already blocks
force-push on master (``tools/master_branch_protection.py``); the ruleset covers every other branch, where the
PR-delivery bot's conflict comment used to tell agents to rebase and ``git push --force-with-lease``.

Policy: one repository ruleset, ``No force-push``, active, on every branch (``~ALL``), with the single rule
``non_fast_forward`` and no bypass actors -- admins and apps included. Creating a branch stays allowed, and so
does deleting one (cleanup's plain delete of a merged head after re-reading its tip, #369). The rule is proved
by reading it back (``check``), never by attempting a force-push.

Usage:
  python3 tools/no_force_push.py check
  python3 tools/no_force_push.py apply
  python3 tools/no_force_push.py dump-policy

``apply`` needs a token with Administration on the repo (the owner's ``gh``). ``check`` reads the ruleset
itself; when the token cannot read rulesets it reads the rules GitHub applies to a probe branch instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.master_branch_protection import (  # noqa: E402
    EXIT_BLOCKED,
    EXIT_OK,
    EXIT_UNPROTECTED,
    CheckResult,
    _gh_api,
    classify_http_error,
    repo_slug,
)

RULESET_NAME = "No force-push"
ALL_BRANCHES = "~ALL"
RULE = "non_fast_forward"
PROBE_BRANCH = "no-force-push-probe"      # any name: a ~ALL ruleset applies to it whether or not it exists


def policy() -> dict[str, Any]:
    """POST / PUT /repos/{repo}/rulesets body."""
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": [ALL_BRANCHES], "exclude": []}},
        "rules": [{"type": RULE}],
    }


def evaluate(ruleset: dict[str, Any] | None) -> CheckResult:
    """Whether one ruleset's detail (GET /rulesets/{id}) carries the policy."""
    if ruleset is None:
        return CheckResult(False, "missing", (f"No '{RULESET_NAME}' ruleset: branches other than master "
                                              "accept force-pushes.",), EXIT_UNPROTECTED)
    reasons: list[str] = []
    if ruleset.get("enforcement") != "active":
        reasons.append(f"The ruleset is '{ruleset.get('enforcement')}', not active.")
    if ruleset.get("target") != "branch":
        reasons.append(f"The ruleset targets '{ruleset.get('target')}', not branches.")
    ref = ((ruleset.get("conditions") or {}).get("ref_name") or {})
    if ALL_BRANCHES not in (ref.get("include") or []):
        reasons.append("The ruleset does not cover every branch (~ALL).")
    if ref.get("exclude"):
        reasons.append("The ruleset excludes branches: " + ", ".join(map(str, ref["exclude"])))
    if RULE not in {str((r or {}).get("type")) for r in ruleset.get("rules") or []}:
        reasons.append("The ruleset has no 'non_fast_forward' rule (it does not block force-push).")
    if ruleset.get("bypass_actors"):
        reasons.append("Someone can bypass it: " + ", ".join(
            f"{a.get('actor_type')} {a.get('actor_id')}" for a in ruleset["bypass_actors"]))
    if reasons:
        return CheckResult(False, "policy_mismatch", tuple(reasons), EXIT_UNPROTECTED)
    if "bypass_actors" not in ruleset:
        # GitHub sends the bypass list only to a caller that can write rulesets: absent is not empty.
        return CheckResult(False, "unverified", ("The rule is there, but this token cannot see who may bypass "
                                                 "it; check with the owner's token.",), EXIT_BLOCKED)
    return CheckResult(True, "ok", (), EXIT_OK)


def evaluate_branch_rules(rules: list[dict[str, Any]]) -> CheckResult:
    """The fallback: the rules GitHub applies to a probe branch (GET /rules/branches/{branch}). It can show a
    missing rule, never a sound one: who may bypass it is not in this answer, so a rule found is unverified."""
    if any((r or {}).get("type") == RULE for r in rules):
        return CheckResult(False, "unverified", ("A non_fast_forward rule applies to a new branch, but this token "
                                                 "cannot see who may bypass it; check with the owner's token.",),
                           EXIT_BLOCKED)
    return CheckResult(False, "missing", ("No non_fast_forward rule applies to a new branch: force-pushes are "
                                          "accepted.",), EXIT_UNPROTECTED)


def _find_ruleset() -> tuple[dict[str, Any] | None, str | None]:
    """Our ruleset's detail, or (None, None) when there is none, or (None, error) when it cannot be read."""
    code, status, _payload, message = _gh_api(f"repos/{repo_slug()}/rulesets?includes_parents=false")
    if status >= 400 or code != 0:
        return None, classify_http_error(status or 403, message)
    listing = _gh_list(f"repos/{repo_slug()}/rulesets?includes_parents=false")
    for item in listing:
        if item.get("name") == RULESET_NAME:
            d_code, d_status, detail, d_message = _gh_api(f"repos/{repo_slug()}/rulesets/{item['id']}")
            if d_status >= 400 or d_code != 0 or detail is None:
                return None, classify_http_error(d_status or 403, d_message)
            return detail, None
    return None, None


def _gh_list(path: str) -> list[dict[str, Any]]:
    import subprocess

    proc = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=False)
    try:
        loaded = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [x for x in loaded if isinstance(x, dict)] if isinstance(loaded, list) else []


def check_live() -> CheckResult:
    ruleset, error = _find_ruleset()
    if error is None:
        return evaluate(ruleset)
    rules = _gh_list(f"repos/{repo_slug()}/rules/branches/{PROBE_BRANCH}")
    result = evaluate_branch_rules(rules)
    return CheckResult(False, result.status, (f"Cannot read rulesets ({error}). {result.reasons[0]}",),
                       EXIT_BLOCKED if result.status == "unverified" else EXIT_UNPROTECTED)


def apply_live() -> CheckResult:
    ruleset, error = _find_ruleset()
    if error is not None:
        return CheckResult(False, error, ("Cannot read rulesets; apply needs the owner's admin token.",),
                           EXIT_BLOCKED)
    if ruleset is None:
        path, method = f"repos/{repo_slug()}/rulesets", "POST"
    else:
        path, method = f"repos/{repo_slug()}/rulesets/{ruleset['id']}", "PUT"
    code, status, _payload, message = _gh_api(path, method=method, body=policy())
    if status >= 400 or code != 0:
        err = classify_http_error(status or 403, message)
        return CheckResult(False, err, (message or f"{method} {path} failed.",), EXIT_BLOCKED)
    return check_live()


def _print(result: CheckResult, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result.as_dict(), indent=2))
        return result.exit_code
    label = "OK" if result.ok else result.status.upper().replace("_", " ")
    print(f"{label}: {repo_slug()} every branch refuses force-push ('{RULESET_NAME}')" if result.ok
          else f"{label}: {repo_slug()} '{RULESET_NAME}'")
    for reason in result.reasons:
        print(f"- {reason}")
    if not result.ok:
        print("Apply with the owner's admin token: python3 tools/no_force_push.py apply")
        print(f"UI: https://github.com/{repo_slug()}/settings/rules")
    return result.exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "apply", "dump-policy"))
    parser.add_argument("--json", action="store_true", help="machine-readable result")
    args = parser.parse_args(argv)
    if args.command == "dump-policy":
        print(json.dumps(policy(), indent=2))
        return EXIT_OK
    return _print(apply_live() if args.command == "apply" else check_live(), as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
