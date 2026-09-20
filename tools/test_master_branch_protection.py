"""Policy tests for master branch protection (no live GitHub writes)."""

from __future__ import annotations

import sys
from pathlib import Path

# pytest puts this file's directory on sys.path, so `import tools` fails
# unless the repo root is also present (CI agent-contract job).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.master_branch_protection import (
    EXIT_BLOCKED,
    EXIT_OK,
    EXIT_UNPROTECTED,
    REQUIRED_CONTEXTS,
    apply_payload,
    classify_http_error,
    evaluate,
    required_contexts,
)


def _ok_protection() -> dict:
    return {
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "enforce_admins": {"enabled": True},
        "required_status_checks": {
            "strict": False,
            "contexts": list(REQUIRED_CONTEXTS),
            "checks": [{"context": name} for name in REQUIRED_CONTEXTS],
        },
    }


def test_apply_payload_blocks_force_push_and_delete():
    body = apply_payload()
    assert body["allow_force_pushes"] is False
    assert body["allow_deletions"] is False
    assert body["enforce_admins"] is True
    assert body["required_pull_request_reviews"] is None
    assert body["restrictions"] is None
    names = required_contexts(body)
    assert set(REQUIRED_CONTEXTS) <= names


def test_apply_payload_does_not_require_reviews():
    """Solo repo: required reviews would deadlock merges."""
    assert apply_payload()["required_pull_request_reviews"] is None


def test_apply_payload_omits_warning_only_checks():
    names = required_contexts(apply_payload())
    assert "Semgrep" not in names
    assert "Gitleaks" not in names
    assert "OSV Scanner" not in names
    assert "Security audit (warning-only)" not in names


def test_evaluate_ok_when_policy_matches():
    result = evaluate(branch_protected=True, protection=_ok_protection(), error=None)
    assert result.ok is True
    assert result.status == "ok"
    assert result.exit_code == EXIT_OK


def test_evaluate_unprotected_when_flag_false():
    result = evaluate(branch_protected=False, protection=None, error=None)
    assert result.ok is False
    assert result.status == "unprotected"
    assert result.exit_code == EXIT_UNPROTECTED


def test_evaluate_unprotected_when_protection_404():
    result = evaluate(branch_protected=False, protection=None, error="not_found")
    assert result.status == "unprotected"
    assert result.exit_code == EXIT_UNPROTECTED


def test_evaluate_mismatch_when_force_push_allowed():
    prot = _ok_protection()
    prot["allow_force_pushes"] = {"enabled": True}
    result = evaluate(branch_protected=True, protection=prot, error=None)
    assert result.status == "policy_mismatch"
    assert result.exit_code == EXIT_UNPROTECTED
    assert any("force" in r.lower() for r in result.reasons)


def test_evaluate_mismatch_when_admins_can_bypass():
    prot = _ok_protection()
    prot["enforce_admins"] = {"enabled": False}
    result = evaluate(branch_protected=True, protection=prot, error=None)
    assert result.status == "policy_mismatch"
    assert any("admin" in r.lower() for r in result.reasons)


def test_evaluate_mismatch_when_check_is_required():
    prot = _ok_protection()
    prot["required_status_checks"]["contexts"] = ["Backend tests"]
    prot["required_status_checks"]["checks"] = [{"context": "Backend tests"}]
    result = evaluate(branch_protected=True, protection=prot, error=None)
    assert result.status == "policy_mismatch"
    assert any("Backend tests" in r for r in result.reasons)


def test_evaluate_rejects_extra_required_checks():
    prot = _ok_protection()
    prot["required_status_checks"]["contexts"].append("Extra check")
    result = evaluate(branch_protected=True, protection=prot, error=None)
    assert result.ok is False


def test_classify_plan_required():
    assert (
        classify_http_error(
            403,
            "Upgrade to GitHub Pro or make this repository public to enable this feature.",
        )
        == "plan_required"
    )


def test_classify_integration_forbidden():
    assert (
        classify_http_error(403, "Resource not accessible by integration")
        == "integration_forbidden"
    )


def test_evaluate_plan_required_is_blocked():
    result = evaluate(branch_protected=None, protection=None, error="plan_required")
    assert result.status == "plan_required"
    assert result.exit_code == EXIT_BLOCKED
    joined = " ".join(result.reasons).lower()
    assert "do not make nova public" not in joined
    assert "public nova unlocks" in joined


def test_evaluate_integration_forbidden_is_blocked():
    result = evaluate(
        branch_protected=None,
        protection=None,
        error="integration_forbidden",
    )
    assert result.status == "integration_forbidden"
    assert result.exit_code == EXIT_BLOCKED


def _public_summary() -> dict:
    return {
        "enabled": True,
        "required_status_checks": {
            "enforcement_level": "everyone",
            "contexts": list(REQUIRED_CONTEXTS),
            "checks": [{"context": name, "app_id": 15368} for name in REQUIRED_CONTEXTS],
        },
    }


def test_evaluate_ok_on_public_branch_summary():
    """App tokens cannot GET /protection; GET /branches/master still has this."""
    result = evaluate(
        branch_protected=True,
        protection=_public_summary(),
        error=None,
    )
    assert result.ok is True
    assert result.exit_code == EXIT_OK


def test_evaluate_mismatch_when_public_summary_not_everyone():
    prot = _public_summary()
    prot["required_status_checks"]["enforcement_level"] = "non_admins"
    result = evaluate(branch_protected=True, protection=prot, error=None)
    assert result.status == "policy_mismatch"
    assert any("admin" in r.lower() for r in result.reasons)


def test_evaluate_rejects_public_summary_required_check():
    prot = _public_summary()
    prot["required_status_checks"]["contexts"] = ["Backend tests"]
    prot["required_status_checks"]["checks"] = [{"context": "Backend tests"}]
    result = evaluate(branch_protected=True, protection=prot, error=None)
    assert result.status == "policy_mismatch"
    assert any("Backend tests" in r for r in result.reasons)


def test_evaluate_unprotected_when_public_summary_disabled():
    prot = _public_summary()
    prot["enabled"] = False
    result = evaluate(branch_protected=True, protection=prot, error=None)
    assert result.status == "unprotected"
    assert result.exit_code == EXIT_UNPROTECTED
