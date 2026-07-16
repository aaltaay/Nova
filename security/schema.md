# Security Finding Schema

All findings stored in `security/findings-registry.json` conform to this schema.

## Finding Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Stable, human-readable identifier: `SEC-NNN` (zero-padded to 3 digits minimum). Assigned on first encounter; never reused. |
| `fingerprint` | string | yes | SHA-256 hex of `"<source>\x00<kind>\x00<path>\x00<title>"`. Fingerprint stability guarantees that re-scans map to the same finding, even across renames of the source tool. |
| `status` | enum | yes | `open` — active finding, not yet addressed. `accepted` — risk accepted; requires `acceptance_rationale` + `review_by`. `resolved` — remediated; preserved for audit history. `false_positive` — confirmed not a real issue; requires `acceptance_rationale`. |
| `severity` | enum | yes | `critical` / `high` / `medium` / `low` |
| `cvss_vector` | string | no | CVSS 3.1 vector string, e.g. `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N`. |
| `cvss_score` | number | no | Base score 0.0–10.0 (numeric). |
| `cwe` | string | no | CWE identifier, e.g. `CWE-200`. |
| `asvs` | string | no | OWASP ASVS 5.0 requirement reference, e.g. `V2.1.1`. |
| `title` | string | yes | Short, human-readable summary of the finding. Max ~120 chars. |
| `detail` | string | yes | Full technical description: what is vulnerable, how it manifests, why it is risky. |
| `location` | string | yes | `file:line` format, e.g. `backend/routes/health.py:85`. For repository-wide or multi-file findings, use the most specific primary file. |
| `source` | string | yes | Name of the tool or check that produced this finding, e.g. `nova-builtin`, `semgrep`, `gitleaks`, `osv-scanner`, `trivy`, `pip_audit`. |
| `redacted_evidence` | string | no | Short verbatim snippet from source with any secret-looking values masked to `***REDACTED***`. Max 500 chars. |
| `first_seen` | string (ISO 8601) | yes | Date of first discovery, e.g. `2026-07-16`. |
| `last_seen` | string (ISO 8601) | yes | Date of most recent confirmation during a scan. Updated on every scan where the finding is still present. |
| `compensating_controls` | string | no | Describe any compensating controls that reduce the effective risk (e.g. "only accessible on localhost in dev; Railway env disables this route"). |
| `acceptance_rationale` | string | conditional | Required when `status` is `accepted` or `false_positive`. Explains why the risk is acceptable. |
| `review_by` | string | conditional | ISO 8601 date by which an accepted finding must be re-reviewed. Required for `accepted` findings. |
| `evidence_commit` | string | no | Git commit SHA at which the evidence was recorded. |

## Registry Envelope

```json
{
  "version": 1,
  "updated": "YYYY-MM-DD",
  "next_id": <integer>,
  "findings": [ /* array of Finding objects */ ],
  "scan_runs": [
    {
      "run_id": "UUID or timestamp",
      "date": "YYYY-MM-DD",
      "tools": ["nova-builtin", "semgrep", ...],
      "blocked_tools": ["gitleaks"],
      "new_findings": ["SEC-001"],
      "resolved_findings": [],
      "summary": "human-readable summary"
    }
  ]
}
```

## Status Transitions

```
open ──→ accepted  (human sets acceptance_rationale + review_by)
open ──→ resolved  (human confirms remediation)
open ──→ false_positive  (human confirms + rationale)
accepted ──→ open  (on re-review, re-open if risk increased)
resolved ──→ open  (auto: finding reappears in a future scan)
```

**Rule:** The scanner never auto-closes findings. It only:
- Creates new `open` findings for new fingerprints.
- Updates `last_seen` for matching fingerprints.
- Reports absent findings as "not seen this run" without changing their status.

## Severity Definitions

| Severity | CVSS Range | Meaning |
|----------|-----------|---------|
| `critical` | 9.0–10.0 | Exploitable without auth; full credential/secret exposure or RCE. Requires immediate remediation. |
| `high` | 7.0–8.9 | Significant security control missing (e.g. CORS wildcard, no auth middleware). |
| `medium` | 4.0–6.9 | Defense-in-depth gap (e.g. missing CI security scan). |
| `low` | 0.1–3.9 | Minor hardening opportunity. |

## Built-in Check Severities (Nova-Specific)

| Check | Severity | Rationale |
|-------|----------|-----------|
| `config_credentials_exposed` | `critical` | GET /api/config returns raw API key + secret to any caller |
| `executor_unauthenticated` | `critical` | POST executor routes (arm/kill-switch/flatten) have no auth Depends |
| `cors_wildcard` | `high` | CORS_ALLOWED_ORIGINS_DEFAULT = ["*"] allows any origin |
| `no_api_auth_middleware` | `high` | No bearer/API-key middleware registered in backend |
| `ci_missing_security_jobs` | `medium` | deploy.yml has no gitleaks/osv/semgrep job |
