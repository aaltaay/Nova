# Security sentinel memory (living)

Living knowledge for the Nova `security-sentinel` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/security-sentinel.md`
Canonical registry: `security/findings-registry.json` — open/accepted/fixed state lives **only** there.

---

## Current snapshot

```yaml
captured_at: 2026-07-16T00:50:00-04:00
source_revision: b8626e4
result: FINDINGS
metrics:
  open_findings: 6
  accepted_risks: 0
  highest_open_cvss: 9.8
  critical_open: 2
  high_open: 2
  medium_open: 2
blockers: []
dashboard_freshness: stale
notes: "Counts derived from security/findings-registry.json — re-read registry for truth."
```

---

## How to continue improving (for humans + agents)

Pick the next open item in **Backlog**, or after any significant change ask:

> Use the security-sentinel subagent to audit the repo.

Or specifically:

> Improve the security-sentinel agent — work the next backlog item in `.cursor/agent-memory/security-sentinel-memory.md`.

Durable facts (commands, severity rules, traps) get **promoted into `security-sentinel.md`**. Suppressions, run history, and open ideas stay **here**. Accepted-risk *IDs* are owned by the registry.

---

## Accepted risks (pointer)

Do **not** maintain a duplicate severity table here. Read `status: accepted` rows from `security/findings-registry.json`. Use this section only for run notes about acceptance decisions.

---

## Suppressions

False positives the deterministic scanner or greps keep hitting. Pattern + reason. Newest first.

_(empty)_

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [~] **CI gate** — `security-audit` job added to `deploy.yml` (warning-only, `continue-on-error: true`); runs `tools/security_audit.py`; gitleaks/osv-scanner/semgrep still missing from CI (tracked as SEC-005).
- [ ] **Semgrep rules** — add a `semgrep.yml` with Nova-specific rules: unauth executor routes, IBKR gate bypass patterns, CORS `allow_origins="*"` with credentials.
- [ ] **ZAP passive scan** — configure OWASP ZAP in passive (spider-only) mode against `127.0.0.1:8000` for a local session; document safe allowlist in memory.
- [ ] **Schemathesis allowlist expansion** — run `schemathesis run http://127.0.0.1:8000/openapi.json` against the local API; document which endpoints are safe to fuzz vs. skip (order/kill-switch routes must be skipped).
- [ ] **Dependency pinning sweep** — audit `backend/requirements.txt` for unpinned packages; propose pinned versions.
- [ ] **`.gitignore` completeness check** — verify `.env*`, `backend/.cache/`, `backend/logs/`, `*.db`, IBKR credential files are all covered.

### Completed

- [x] 2026-07-16 — Initial security-sentinel agent install (this file + `security-sentinel.md` + `security-continuity.mdc` created).

---

## Learned facts (pending promotion)

Facts discovered in a run that are **not yet** in `security-sentinel.md`. After promoting, delete the bullet here.

_(empty)_

---

## Run log

Newest first. Keep entries short. Skip boring all-clean runs unless a command/path was corrected.

<!-- RUN_LOG_START -->

### 2026-07-16 — Baseline enrichment (compensating controls + status ledger)

- **Scope:** Documentation pass — enrich registry compensating_controls for all 6 open findings; populate Security-Status.md; update verification ledger.
- **Result:** All 6 findings (SEC-001–SEC-006) now have compensating_controls in registry. Open findings table populated in Security-Status.md. Verification ledger row added. Findings remain **open/unfixed**.
- **Open findings:** SEC-001 (critical, credentials in GET /api/config), SEC-002 (critical, unauth executor POSTs), SEC-003 (high, CORS wildcard), SEC-004 (high, no API auth), SEC-005 (medium, CI missing security scanners), SEC-006 (medium, Dockerfile runs as root).
- **Memory update:** Compensating controls seeded; run-log updated. Accepted risks table still empty (controls documented but not formally accepted — that step requires explicit user sign-off per review_by date).
- **Files updated:** `security/findings-registry.json`, `knowledge/obsidian/03-Nova-Decisions/Security-Status.md`, `security-sentinel-memory.md`, `gemini.md`, `AGENTS.md`, `CHANGELOG.md`.

### 2026-07-16 — Agent install

- **Scope:** Meta — create security-sentinel agent, memory, rule, and registry scaffold.
- **Result:** n/a (protocol install)
- **Learning:** Accepted risks table seeded empty; backlog seeded with CI gate, Semgrep, ZAP, Schemathesis, dep pinning, .gitignore sweep.
- **Files updated:** `security-sentinel.md`, `security-sentinel-memory.md`, `.cursor/rules/security-continuity.mdc`, `security/findings-registry.json` (scaffold).

<!-- RUN_LOG_END -->
