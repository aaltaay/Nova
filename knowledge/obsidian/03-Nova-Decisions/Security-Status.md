# Nova Security Status

> **Canonical security posture ledger** for Nova.  
> **Agent dashboards:** `nova-home` (Docs docs steward) · `agent-tester` · `agent-maintainer` · `agent-security`  
> **Tooling guide:** `security/tooling.md`  
> **CI job:** `.github/workflows/deploy.yml` → `security-audit` (warning-only, `continue-on-error: true`)  
> **Audit script:** `tools/security_audit.py --json`  
> **Roadmap-Status:** [[Nova-Roadmap-Status]] — Phase B WAIVED (2026-07-28); Phase K short entry is product NEXT; `auto_live` NO-GO unchanged.

Checkbox legend: `[ ]` pending · `[~]` in progress · `[x]` complete / accepted

---

## Current position

- **State:** `[x]` SEC-001–SEC-011 remediated (SEC-009–011 on 2026-10-09) — registry statuses `fixed`
- **GitHub alerts:** CodeQL and Dependabot alerts live on the repo's Security tab, not here. 2026-10-09: all 70 open alerts triaged — 13 CodeQL and 2 Dependabot fixed in one PR, the rest dismissed on GitHub with a written reason (46 error-text alerts: the desk shows the reason on screen by design and the API is loopback-only)
- **CI:** `security-audit` + `gitleaks` + `osv-scanner` + `semgrep` jobs (warning-only; `continue-on-error: true`)
- **Baseline:** first captured 2026-07-16; remediations 2026-07-18
- **Blocking status:** no security gate blocks deploys yet (intentional; warning-first)
- **`auto_live`:** **NO-GO** — unchanged; no security work affects this gate
- **Last updated:** 2026-10-09
- **Visibility:** public source home is `aaltaay/Nova`. `aaltaay/Nova-public` is a private archive.
- **Master branch:** `[x]` Protected 2026-09-11 (issue #63 / D-041). Force-push and deletion blocked, including admins. Required checks: `Backend tests`, `Frontend build`, `Frontend E2E`, `Agent contract`. No required reviews. Cloud Agent `check` reads the public branch summary when GET `/protection` is 403.

---

## Agent ownership

| Agent | Trigger | Scope | Output |
|-------|---------|-------|--------|
| `security-review` (Cursor) | "Review security of these changes" | Diff only — staged / branch changes | Inline comment / chat |
| `security` (Nova) | "Run security sentinel" / full posture | Full repo: deps, secrets, patterns, CVSS triage | Report + `Security-Status.md` update |
| `llm-trading-agent-security` skill | Hardening alert→exec paths | Methodology reference (research only) | Guidance / patterns |
| CI `security-audit` job | Every PR + push | `pip-audit` + `cvss` scoring via `tools/security_audit.py` | JSON artifact uploaded |

**Rule:** `security-review` is for diff triage; `security` is for scheduled / on-demand full-repo posture. Never conflate.

---

## Verification ledger

| Date | Action | Result | SHA / artifact |
|------|--------|--------|----------------|
| 2026-10-09 | Triage all 70 GitHub alerts; fix SEC-009–011 | Host allowlist + socket Origin check (`backend/request_guard/`); shared capture path guard (`capture.storage.session_path`); shell-quote 1.12.0, source-map-js 1.2.2; full backend suite 6254 passed; packaged-desk socket origin measured (`file://`, Electron 41.10.6) | registry scan_run `github-alerts-triage-2026-10-09` |
| 2026-07-18 | Re-audit verify (security subagent) | `run_builtin_checks()=[]`; audit `open_finding_count: 0`; SEC-001–008 stay `fixed`; spot-checks pass; IBKR/`auto_live` gates intact | registry scan_run `reaudit-verify-2026-07-18` · tip `3287641` |
| 2026-07-18 | Remediate SEC-001–SEC-008 | Builtin checks clean; API key middleware; config mask; webhook SSRF validator; torch optional; CORS localhost; Docker USER; CI scanners | `security/findings-registry.json` statuses → fixed |
| 2026-07-16 | First baseline audit — `tools/security_audit.py --json --write-registry` | 6 open findings (SEC-001 critical, SEC-002 critical, SEC-003 high, SEC-004 high, SEC-005 medium, SEC-006 medium); compensating controls seeded; findings open intentionally | registry: `security/findings-registry.json` |

---

## Open findings

> None open as of 2026-10-09. Historical rows kept for audit trail (status = fixed).

| Finding ID | Severity | CVSS | Location | Status | Notes |
|------------|----------|------|----------|--------|-------|
| SEC-001 | critical | 7.5 | `backend/routes/health.py` | fixed | Masked secrets via `mask_secret`; `*_set` flags |
| SEC-002 | critical | 9.8 | `backend/routes/executor.py` | fixed | `Depends(require_auth)` on POSTs |
| SEC-003 | high | 5.4 | `backend/constants_scanner.py` | fixed | Localhost Vite origins default |
| SEC-004 | high | 9.1 | `backend/auth.py` | fixed | `APIKeyHeader` + mutating middleware |
| SEC-005 | medium | — | `.github/workflows/deploy.yml` | fixed | gitleaks / osv-scanner / semgrep jobs |
| SEC-006 | medium | — | `Dockerfile` | fixed | `USER nova` (UID 10001) |
| SEC-007 | medium | 5.3 | `backend/requirements.txt` | fixed | torch moved to optional `requirements-ml.txt` |
| SEC-008 | high | 7.2 | `backend/alerts/webhook_url.py` | fixed | https + private-IP / metadata block |
| SEC-009 | high | 5.3 | `backend/request_guard/` | fixed | Any Host answered (DNS rebinding); now 400 `HOST_NOT_ALLOWED` |
| SEC-010 | high | 4.3 | `backend/request_guard/` | fixed | Sockets took any Origin; now CORS list + `file://` only |
| SEC-011 | high | 4.0 | `backend/capture/storage.py` | fixed | Replay/backtest date+symbol reached file paths; format + root check |

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
- Phase B paper shadow was WAIVED (2026-07-28); Phase K is product NEXT per [[Nova-Roadmap-Status]]

---

## History

| Date | Entry |
|------|-------|
| 2026-10-09 | GitHub Security tab had 70 open alerts while this ledger said clean. Triaged all; fixed the real ones (SEC-009–011 + 13 CodeQL + 2 Dependabot), dismissed the rest with reasons. GitHub alerts are tracked on the Security tab from now on. |
| 2026-09-11 | Master protection live. Owner applied via `gh api` as aaltaay. #63 / D-041 closed. `check` now uses the public branch summary so App tokens stop reporting `integration_forbidden`. |
| 2026-09-11 | Source published as `aaltaay/Nova`. Historical Alpaca `.env` keys revoked. `Nova-public` archived private. Master protection still needs `apply` (#63). |
| 2026-09-11 | GitHub Security "master isn't protected." Live `protected: false`. Tool + policy shipped; apply blocked on Administration token + GitHub Pro. Issue #63. |
| 2026-07-18 | Security subagent re-audit verified SEC-001–SEC-008 remain fixed; builtin empty; dashboard refreshed to CLEAN. |
| 2026-07-16 | Baseline audit completed: 6 findings (SEC-001–SEC-006) recorded in registry; compensating controls seeded for all findings; open findings section populated; verification ledger updated. Findings intentionally open — no product fixes applied. |
| 2026-07-16 | Security-Status ledger created; `security-audit` CI job added (warning-only); `tools/security_audit.py` created; `security/tooling.md` created; `cvss` added to `requirements-dev.txt` |
