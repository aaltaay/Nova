# Nova Security Status

> **Canonical security posture ledger** for Nova.  
> **Agent dashboards:** `nova-home` (Nova Agent docs steward) · `agent-tester` · `agent-maintainer` · `agent-security`  
> **Tooling guide:** `security/tooling.md`  
> **CI job:** `.github/workflows/deploy.yml` → `security-audit` (warning-only, `continue-on-error: true`)  
> **Audit script:** `tools/security_audit.py --json`  
> **Roadmap-Status:** [[Nova-Roadmap-Status]] — Phase B remains product NEXT; `auto_live` NO-GO unchanged.

Checkbox legend: `[ ]` pending · `[~]` in progress · `[x]` complete / accepted

---

## Current position

- **State:** `[~]` Baseline captured — 6 open findings (SEC-001–SEC-006); compensating controls seeded; findings intentionally open (not yet fixed)
- **CI:** `security-audit` job added (warning-only; `continue-on-error: true`)  
- **Baseline:** captured 2026-07-16 — `tools/security_audit.py --json --write-registry` → 6 findings written to `security/findings-registry.json`
- **Blocking status:** no security gate blocks deploys yet (intentional; warning-first)
- **`auto_live`:** **NO-GO** — unchanged; no security work affects this gate
- **Last updated:** 2026-07-16

---

## Agent ownership

| Agent | Trigger | Scope | Output |
|-------|---------|-------|--------|
| `security-review` (Cursor) | "Review security of these changes" | Diff only — staged / branch changes | Inline comment / chat |
| `security-sentinel` (Nova) | "Run security sentinel" / full posture | Full repo: deps, secrets, patterns, CVSS triage | Report + `Security-Status.md` update |
| `llm-trading-agent-security` skill | Hardening alert→exec paths | Methodology reference (research only) | Guidance / patterns |
| CI `security-audit` job | Every PR + push | `pip-audit` + `cvss` scoring via `tools/security_audit.py` | JSON artifact uploaded |

**Rule:** `security-review` is for diff triage; `security-sentinel` is for scheduled / on-demand full-repo posture. Never conflate.

---

## Verification ledger

| Date | Action | Result | SHA / artifact |
|------|--------|--------|----------------|
| 2026-07-16 | First baseline audit — `tools/security_audit.py --json --write-registry` | 6 open findings (SEC-001 critical, SEC-002 critical, SEC-003 high, SEC-004 high, SEC-005 medium, SEC-006 medium); compensating controls seeded; findings open intentionally | registry: `security/findings-registry.json` |

---

## Open findings

> Populated 2026-07-16 from `tools/security_audit.py --json --write-registry`.  
> Findings are **recorded, not fixed**. Compensating controls documented in `security/findings-registry.json`.

| Finding ID | Severity | CVSS | Location | Status | Notes |
|------------|----------|------|----------|--------|-------|
| SEC-001 | critical | 7.5 | `backend/routes/health.py:85` | open | GET /api/config returns raw Alpaca API credentials; compensating: local-first, mask_secret pattern in alerts |
| SEC-002 | critical | 9.8 | `backend/routes/executor.py:51` | open | 9 POST executor routes unguarded; compensating: IBKR triple gate + FLATTEN confirm token + auto_live hard-rejected |
| SEC-003 | high | 5.4 | `backend/constants.py:34` | open | CORS wildcard default; compensating: allow_credentials=False, NOVA_CORS_ALLOWED_ORIGINS env override |
| SEC-004 | high | 9.1 | `backend/main.py:1` | open | No API auth middleware; compensating: same IBKR gates as SEC-002; Electron sidecar binds 127.0.0.1 |
| SEC-005 | medium | — | `.github/workflows/deploy.yml:1` | open | CI missing gitleaks/osv-scanner/semgrep; compensating: security-audit job runs tools/security_audit.py with continue-on-error; .env gitignored |
| SEC-006 | medium | — | `Dockerfile:1` | open | Container runs as root (no USER directive); compensating: Railway may remap UIDs; no --privileged flag; USER directive should be added |

---

## Baseline acceptance checklist

- [ ] Run `python tools/security_audit.py --json > .tmp/security-baseline.json`
- [ ] Review all CRITICAL and HIGH findings
- [ ] Triage: fix, accept-with-reason, or track in Open findings above
- [ ] Record baseline SHA and finding count in Verification ledger
- [ ] When baseline is clean / accepted: remove `continue-on-error: true` from CI job and add `--fail-on-findings` flag (or keep warning-only if preferred)
- [ ] Update this file: set Current position to `[x]` baseline accepted

---

## Tooling installed / available

| Tool | Install | Status | Purpose |
|------|---------|--------|---------|
| `pip-audit` | `requirements-dev.txt` | ✅ installed | Python CVE scan |
| `cvss` | `requirements-dev.txt` | ✅ installed | CVSS v4 scoring |
| Semgrep | `pip install semgrep` or `scoop install semgrep` | manual | SAST |
| Gitleaks | `scoop install gitleaks` | manual | Secret history scan |
| OSV-Scanner | GitHub releases binary | manual | OSV database cross-ref |
| Trivy | `scoop install trivy` | manual | Container + FS scan |
| OWASP ZAP | Docker `ghcr.io/zaproxy/zaproxy:stable` | manual | Passive API baseline only |

See `security/tooling.md` for commands and Windows setup.

---

## Invariants (never violate)

- ZAP **baseline passive only** — never active scan while IB Gateway is connected
- No scanner credentials / API keys committed to git
- Scanner JSON output goes to `.tmp/` (gitignored) — never committed
- `auto_live` remains NO-GO regardless of security posture
- Phase B (paper shadow) remains the product NEXT per [[Nova-Roadmap-Status]]

---

## History

| Date | Entry |
|------|-------|
| 2026-07-16 | Baseline audit completed: 6 findings (SEC-001–SEC-006) recorded in registry; compensating controls seeded for all findings; open findings section populated; verification ledger updated. Findings intentionally open — no product fixes applied. |
| 2026-07-16 | Security-Status ledger created; `security-audit` CI job added (warning-only); `tools/security_audit.py` created; `security/tooling.md` created; `cvss` added to `requirements-dev.txt` |
