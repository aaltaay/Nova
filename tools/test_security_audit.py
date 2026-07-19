"""Pytest suite for the Nova security audit tool stack.

Run from repo root:
    py -3 -m pytest tools/test_security_audit.py -q
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure repo root is importable.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.security_lib.normalize import fingerprint, format_id, RawFinding, raw_to_registry_entry
from tools.security_lib.redact import redact
from tools.security_lib.registry import load_registry, merge_findings, save_registry
from tools.security_lib.checks import (
    check_config_credentials_exposed,
    check_cors_wildcard,
    check_executor_unauthenticated,
    check_no_api_auth_middleware,
    check_ci_missing_security_jobs,
    run_builtin_checks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw(
    source: str = "test-tool",
    kind: str = "test-kind",
    path: str = "backend/foo.py",
    title: str = "Test finding",
    severity: str = "high",
) -> RawFinding:
    return RawFinding(
        source=source,
        kind=kind,
        path=path,
        title=title,
        detail="Some detail",
        severity=severity,
        location=f"{path}:1",
    )


def _empty_registry() -> dict:
    return {
        "version": 1,
        "updated": "2026-01-01",
        "next_id": 1,
        "findings": [],
        "scan_runs": [],
    }


# ---------------------------------------------------------------------------
# 1. Fingerprint stability
# ---------------------------------------------------------------------------

class TestFingerprintStability:
    def test_same_inputs_same_fingerprint(self):
        fp1 = fingerprint("semgrep", "hardcoded-secret", "backend/foo.py", "Hardcoded API key")
        fp2 = fingerprint("semgrep", "hardcoded-secret", "backend/foo.py", "Hardcoded API key")
        assert fp1 == fp2

    def test_case_insensitive_source_and_kind(self):
        fp1 = fingerprint("Semgrep", "Hardcoded-Secret", "backend/foo.py", "Hardcoded API key")
        fp2 = fingerprint("semgrep", "hardcoded-secret", "backend/foo.py", "Hardcoded API key")
        assert fp1 == fp2

    def test_different_path_different_fingerprint(self):
        fp1 = fingerprint("semgrep", "kind", "backend/a.py", "title")
        fp2 = fingerprint("semgrep", "kind", "backend/b.py", "title")
        assert fp1 != fp2

    def test_different_title_different_fingerprint(self):
        fp1 = fingerprint("tool", "kind", "path.py", "Title A")
        fp2 = fingerprint("tool", "kind", "path.py", "Title B")
        assert fp1 != fp2

    def test_fingerprint_is_hex_string(self):
        fp = fingerprint("tool", "kind", "path", "title")
        assert len(fp) == 64
        int(fp, 16)  # should not raise

    def test_raw_finding_fp_matches_function(self):
        raw = _make_raw(source="s", kind="k", path="p.py", title="T")
        assert raw.fp == fingerprint("s", "k", "p.py", "T")


# ---------------------------------------------------------------------------
# 2. Merge preserves accepted status
# ---------------------------------------------------------------------------

class TestMergePreservesAcceptedStatus:
    def _registry_with_accepted(self) -> dict:
        reg = _empty_registry()
        raw = _make_raw()
        entry = raw_to_registry_entry(raw, "SEC-001", "2026-01-01", "2026-01-01")
        entry["status"] = "accepted"
        entry["acceptance_rationale"] = "Accepted for now"
        entry["review_by"] = "2027-01-01"
        reg["findings"] = [entry]
        reg["next_id"] = 2
        return reg

    def test_re_scan_does_not_change_accepted_status(self):
        reg = self._registry_with_accepted()
        raw = _make_raw()
        updated_reg, new_ids, updated_ids = merge_findings(
            raw_findings=[raw],
            registry=reg,
            tools_run=["test-tool"],
            blocked_tools=[],
            write=False,
        )
        findings = updated_reg["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == "accepted"
        assert findings[0]["acceptance_rationale"] == "Accepted for now"

    def test_re_scan_updates_last_seen(self):
        reg = self._registry_with_accepted()
        raw = _make_raw()
        updated_reg, _, _ = merge_findings(
            raw_findings=[raw],
            registry=reg,
            tools_run=["test-tool"],
            blocked_tools=[],
            write=False,
        )
        from tools.security_lib.normalize import today_iso
        assert updated_reg["findings"][0]["last_seen"] == today_iso()

    def test_absent_finding_not_auto_closed(self):
        reg = self._registry_with_accepted()
        # merge with empty raw findings — accepted should remain
        updated_reg, _, _ = merge_findings(
            raw_findings=[],
            registry=reg,
            tools_run=["test-tool"],
            blocked_tools=[],
            write=False,
        )
        assert len(updated_reg["findings"]) == 1
        assert updated_reg["findings"][0]["status"] == "accepted"

    def test_new_finding_gets_next_id(self):
        reg = self._registry_with_accepted()
        raw2 = _make_raw(kind="different-kind", title="Another finding")
        updated_reg, new_ids, _ = merge_findings(
            raw_findings=[raw2],
            registry=reg,
            tools_run=["test-tool"],
            blocked_tools=[],
            write=False,
        )
        assert len(new_ids) == 1
        assert new_ids[0] == "SEC-002"
        assert updated_reg["next_id"] == 3


# ---------------------------------------------------------------------------
# 3. Redaction masks secrets
# ---------------------------------------------------------------------------

class TestRedaction:
    def test_masks_api_key_assignment(self):
        text = 'api_key = "AKIAIOSFODNN7EXAMPLE"'
        result = redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "***REDACTED***" in result

    def test_masks_aws_access_key(self):
        text = "key: AKIAIOSFODNN7EXAMPLE rest"
        result = redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_masks_stripe_key(self):
        text = "token = 'sk_live_abcdefghijklmnop123456'"
        result = redact(text)
        assert "sk_live_abcdefghijklmnop123456" not in result
        assert "***REDACTED***" in result

    def test_empty_string_unchanged(self):
        assert redact("") == ""

    def test_plain_text_unchanged(self):
        result = redact("hello world 123")
        # short non-secret strings should pass through (no match)
        assert "***REDACTED***" not in result

    def test_truncated_to_max_chars(self):
        long_text = "x" * 1000
        assert len(redact(long_text)) <= 500


# ---------------------------------------------------------------------------
# 4. Built-in checks find known issues in repo
# ---------------------------------------------------------------------------

class TestBuiltinChecks:
    """Builtin checks are regression guards — they must stay clean after SEC remediations."""

    def test_check_a_config_credentials_remediated(self):
        findings = check_config_credentials_exposed()
        assert findings == [], "GET /api/config must not return plaintext Alpaca secrets"

    def test_check_b_executor_auth_remediated(self):
        findings = check_executor_unauthenticated()
        assert findings == [], "executor POSTs must use Depends(require_auth)"

    def test_check_c_cors_wildcard_remediated(self):
        findings = check_cors_wildcard()
        assert findings == [], "CORS default must not be wildcard *"

    def test_check_d_api_auth_present(self):
        findings = check_no_api_auth_middleware()
        assert findings == [], "backend must expose APIKeyHeader / require_auth"

    def test_check_e_ci_security_jobs_present(self):
        findings = check_ci_missing_security_jobs()
        assert findings == [], "deploy.yml must reference gitleaks, osv-scanner, and semgrep"

    def test_check_dockerfile_non_root(self):
        from tools.security_lib.checks_infra import check_dockerfile_runs_as_root

        assert check_dockerfile_runs_as_root() == []

    def test_run_builtin_checks_clean(self):
        findings = run_builtin_checks()
        assert findings == [], f"unexpected builtin findings: {[f.kind for f in findings]}"


# ---------------------------------------------------------------------------
# 5. Registry next_id increments correctly
# ---------------------------------------------------------------------------

class TestRegistryNextId:
    def test_first_finding_gets_sec_001(self):
        reg = _empty_registry()
        raw = _make_raw()
        updated, new_ids, _ = merge_findings(
            raw_findings=[raw],
            registry=reg,
            tools_run=["test"],
            blocked_tools=[],
            write=False,
        )
        assert new_ids == ["SEC-001"]
        assert updated["next_id"] == 2

    def test_second_finding_gets_sec_002(self):
        reg = _empty_registry()
        raws = [
            _make_raw(kind="kind1", title="T1"),
            _make_raw(kind="kind2", title="T2"),
        ]
        updated, new_ids, _ = merge_findings(
            raw_findings=raws,
            registry=reg,
            tools_run=["test"],
            blocked_tools=[],
            write=False,
        )
        assert "SEC-001" in new_ids
        assert "SEC-002" in new_ids
        assert updated["next_id"] == 3

    def test_duplicate_finding_does_not_increment(self):
        reg = _empty_registry()
        raw = _make_raw()
        reg, new_ids1, _ = merge_findings(
            raw_findings=[raw],
            registry=reg,
            tools_run=["test"],
            blocked_tools=[],
            write=False,
        )
        reg2, new_ids2, _ = merge_findings(
            raw_findings=[raw],
            registry=reg,
            tools_run=["test"],
            blocked_tools=[],
            write=False,
        )
        assert new_ids2 == []
        assert reg2["next_id"] == 2  # still 2, not 3

    def test_format_id_pads_to_three_digits(self):
        assert format_id(1) == "SEC-001"
        assert format_id(42) == "SEC-042"
        assert format_id(999) == "SEC-999"
        assert format_id(1000) == "SEC-1000"

    def test_registry_write_and_reload(self, tmp_path: Path):
        reg = _empty_registry()
        raw = _make_raw()
        reg_path = tmp_path / "findings-registry.json"
        updated, _, _ = merge_findings(
            raw_findings=[raw],
            registry=reg,
            tools_run=["test"],
            blocked_tools=[],
            write=True,
            path=reg_path,
        )
        reloaded = load_registry(reg_path)
        assert reloaded["next_id"] == 2
        assert len(reloaded["findings"]) == 1
        assert reloaded["findings"][0]["id"] == "SEC-001"
