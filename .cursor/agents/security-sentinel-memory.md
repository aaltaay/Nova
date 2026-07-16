# Security sentinel memory (living)

Living knowledge for the Nova `security-sentinel` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/security-sentinel.md`
Canonical registry: `security/findings-registry.json`

---

## How to continue improving (for humans + agents)

Pick the next open item in **Backlog**, or after any significant change ask:

> Use the security-sentinel subagent to audit the repo.

Or specifically:

> Improve the security-sentinel agent — work the next backlog item in `.cursor/agents/security-sentinel-memory.md`.

Durable facts (commands, severity rules, traps) get **promoted into `security-sentinel.md`**. Accepted risks, suppressions, run history, and open ideas stay **here**.

---

## Accepted risks

Known findings the team has consciously accepted. Must NOT be re-reported as new CRITICAL unless `review_by` has expired or evidence materially changed. Maintain this table in parallel with `security/findings-registry.json`.

| ID | Finding | Severity | Accepted date | Review by | Rationale | Compensating control |
|----|---------|----------|---------------|-----------|-----------|----------------------|
| — | — | — | — | — | — | — |

_(empty — no accepted risks yet)_

---

## Suppressions

False positives the deterministic scanner or greps keep hitting. Pattern + reason. Newest first.

_(empty)_

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] **CI gate** — add GitHub Actions job running `tools/security_audit.py --json` + `pip_audit` + `npm audit`; fail on CRITICAL/HIGH (warning-only initially).
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

### 2026-07-16 — Agent install

- **Scope:** Meta — create security-sentinel agent, memory, rule, and registry scaffold.
- **Result:** n/a (protocol install)
- **Learning:** Accepted risks table seeded empty; backlog seeded with CI gate, Semgrep, ZAP, Schemathesis, dep pinning, .gitignore sweep.
- **Files updated:** `security-sentinel.md`, `security-sentinel-memory.md`, `.cursor/rules/security-continuity.mdc`, `security/findings-registry.json` (scaffold).

<!-- RUN_LOG_END -->
