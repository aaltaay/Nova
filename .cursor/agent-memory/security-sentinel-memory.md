# Security sentinel memory (living)

Living knowledge for the Nova `security-sentinel` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/security-sentinel.md`
Canonical registry: `security/findings-registry.json` — open/accepted/fixed state lives **only** there.

---

## Current snapshot

```yaml
captured_at: 2026-07-16T23:25:00-04:00
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
dashboard_freshness: clean
notes: "Counts derived from security/findings-registry.json — re-read registry for truth. SEC-007 candidate (2026-07-16) was a dedup, not a new finding — see run log; registry now accurately reflects 6 open findings with no duplicates."
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

- **Location-drift duplicate after constants-module split** (2026-07-16) — `tools/security_lib/normalize.fingerprint()` hashes `(source, kind, path, title)`. When a constant's authoritative definition moves file (e.g. Phase 3 `backend/constants.py` → domain module split), the same logical finding gets a new fingerprint and looks like a new SEC-NNN even though nothing new was introduced. Before accepting a "new" finding whose `title`/`cvss_score` exactly match an existing open finding, `grep` the old and new location to confirm whether the value is genuinely re-declared (real duplicate — new SEC-NNN) or the old location is now a barrel/no-op (dedup — fold into the existing ID's `location`/`fingerprint`, do not open a new ID). Confirmed case: SEC-003 (`CORS_ALLOWED_ORIGINS_DEFAULT`) — `backend/constants.py` is a 19-line Phase-3 barrel (`from constants_scanner import *`), no line 34 definition remains there; the literal lives only in `backend/constants_scanner.py:34`. Folded the new fingerprint into SEC-003 rather than creating SEC-007.

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [~] **CI gate** — `security-audit` job added to `deploy.yml` (warning-only, `continue-on-error: true`); runs `tools/security_audit.py`; gitleaks/osv-scanner/semgrep still missing from CI (tracked as SEC-005).
- [ ] **Semgrep rules** — add a `semgrep.yml` with Nova-specific rules: unauth executor routes, IBKR gate bypass patterns, CORS `allow_origins="*"` with credentials.
- [ ] **ZAP passive scan** — configure OWASP ZAP in passive (spider-only) mode against `127.0.0.1:8000` for a local session; document safe allowlist in memory.
- [ ] **Schemathesis allowlist expansion** — run `schemathesis run http://127.0.0.1:8000/openapi.json` against the local API; document which endpoints are safe to fuzz vs. skip (order/kill-switch routes must be skipped).
- [ ] **Dependency pinning sweep** — audit `backend/requirements.txt` for unpinned packages; propose pinned versions.
- [ ] **`.gitignore` completeness check** — verify `.env*`, `backend/.cache/`, `backend/logs/`, `*.db`, IBKR credential files are all covered.
- [ ] **Fingerprint dedup across file moves** — `normalize.fingerprint()` includes `path`, so any constants-module split/rename (see Suppressions above, SEC-003) manufactures a spurious "new" SEC-NNN candidate for the exact same logical finding. Consider a secondary dedup pass in `merge_findings()` that flags (not auto-merges) a candidate whose `(source, kind, title, severity)` matches an existing open finding with a different `path`, so the sentinel gets a "possible relocation of SEC-NNN" hint instead of a silent new ID. Out of scope for this subagent to implement directly (tool code, not registry/memory) — hand to parent/maintainer if picked up.

### Completed

- [x] 2026-07-16 — Initial security-sentinel agent install (this file + `security-sentinel.md` + `security-continuity.mdc` created).

---

## Learned facts (pending promotion)

Facts discovered in a run that are **not yet** in `security-sentinel.md`. After promoting, delete the bullet here.

**(empty)**

---

## Run log

Newest first. Keep entries short. Skip boring all-clean runs unless a command/path was corrected.

<!-- RUN_LOG_START -->

### 2026-07-16 — SEC-007 candidate triaged as dedup, not a new finding

- **Scope:** Parent flagged a fresh dry-run (`py -3 tools/security_audit.py --json`, registry not written) surfacing SEC-007 — `CORS_ALLOWED_ORIGINS_DEFAULT` wildcard at `backend/constants_scanner.py:34`, same title/CVSS as SEC-003 (`backend/constants.py:34`). Asked to verify genuine duplicate definition vs. tool dedup gap, and to reconcile the registry.
- **Verification:** `grep -n CORS_ALLOWED_ORIGINS_DEFAULT backend` → only one literal definition, `backend/constants_scanner.py:34`. Read `backend/constants.py` (19 lines) — it is the Phase 3 compatibility barrel, `from constants_scanner import *`; no independent redeclaration. **Not** a centralized-constants violation — the barrel-import pattern is exactly what that policy requires ("import, don't re-declare").
- **Root cause of the false "new" finding:** `tools/security_lib/normalize.fingerprint()` hashes `(source, kind, path, title)`. The constants Phase-3 split moved the physical definition out of `constants.py` into `constants_scanner.py`, changing `path` → new fingerprint → looked like a second independent finding even though SEC-003's old location no longer contains the code at all.
- **Resolution:** Did not run `--write-registry` (its `merge_findings()` only dedupes on exact fingerprint match; it would have added SEC-007 as a second open finding). Manually updated SEC-003 in place: `location` → `backend/constants_scanner.py:34`, `fingerprint` → the new value, `detail` clarified re: barrel, `compensating_controls` records the superseded old fingerprint for traceability, `last_seen` bumped. Appended a `scan_runs` entry documenting the manual dedup (0 new, SEC-003 updated). Re-ran the dry-run afterward — confirms `new_finding_ids: []`, `open_finding_count: 6`, SEC-003 now matches on the new fingerprint going forward.
- **Result:** Open findings still 6 (SEC-001–SEC-006); no SEC-007 created. Highest open CVSS unchanged at 9.8 (SEC-002). No genuine second CORS-wildcard definition exists — flagged to parent as informational only (not a product bug), since the barrel pattern is correct as-is.
- **Memory update:** Suppression added (location-drift dedup rule); backlog item added (fingerprint dedup gap, hand to maintainer/tool owner — out of sentinel's edit scope); Current snapshot refreshed, `dashboard_freshness: clean`.
- **Files updated:** `security/findings-registry.json` (SEC-003 merge, scan_runs entry), `security-sentinel-memory.md`.

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
