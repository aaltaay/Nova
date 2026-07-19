# Maintainer memory (living)

Living knowledge for the Nova `maintainer` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/maintainer.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-18T02:46:00-04:00
source_revision: working-tree
result: FINDINGS
metrics:
  findings_total: 13
  findings_non_baseline: 10
  files_scanned: 645
  secret_pattern: 0
  swallowed_exception: 4
  ib_placeOrder_sites: 1
  # file-size / CSS counts deferred this run (danger-sniff scope)
blockers: []
dashboard_freshness: refresh-required
notes: "Danger-sniff only (parallel with security). Tracked-source secret_pattern=0; .env gitignored+untracked (local keys present — do not commit). Swallows: scanner_l1.py:181 Exception:pass (HOD L1 blocklist import — real WARNING), ticks.py:63 ValueError remove (benign), ticks.py:332 float(dh) (benign), test_hod_momo_former.py:26 (test). ib.placeOrder only in ibkr/orders.py (safety-gated). Ruff TRY203 clean; BLE001≈104 (logged Exception catches, not silent pass); S105×3 false positives (env-name / FLATTEN confirm / test). File-size noise present but out of scope."
```

Accepted-baseline *rationale* stays below; current measured line counts come from `maintainer_checks`.

---

## How to continue improving (for humans + agents)

Pick the next open item in **Backlog**, or after any significant change ask:

> Use the maintainer subagent to audit the repo.

---

## Accepted baselines

| Path | Limit | Baseline lines (accepted) | Why accepted |
|------|-------|---------------------------|--------------|
| `backend/strategy/executor.py` | 400 | 494 | Placement gate chain kept intact; Phase 12 deferred — see `architecture/phase-12-executor-deferral.md` |

Hard limits:

| Path | Limit |
|------|-------|
| `backend/main.py` | 200 |
| `frontend/src/App.tsx` | 150 |
| `frontend/src/index.css` | 50 |

`hod_momo.py` is no longer baselined (Phase 10 facade ≤400).

---

## Suppressions

**(empty)**

---

## Backlog

- [ ] **Weekly automation** — optional Cursor Automation or scheduled CI job for `tools/maintainer_checks.py --json`
- [ ] **CI gate** — GitHub Actions job for maintainer scanner + ruff (warning-first)
- [ ] **Feed-mixing heuristics** — AST/grep for IBKR→Alpaca silent fallbacks
- [ ] **Cross-feature import cleanup** — migrate baseline-warned frontend deep imports to public barrels
- [ ] **Executor shared-state extract** — only after Phase 12 entry gate + security review
- [ ] **Emit key-file line counts from the tool** — `maintainer_checks.py` doesn't emit `main_py_lines`/`index_css_lines`/`app_tsx_lines`/`hod_momo_lines`/`executor_lines` as a JSON field; every memory snapshot update hand-transcribes them from separate ad hoc counts, which is how `index_css_lines: 18` drifted (copy-paste from `main_py_lines`) in the 2026-07-16 phase-13-close snapshot. Adding a `key_file_lines` dict to the JSON report would remove the manual step.

### Completed

- [x] 2026-07-16 — Pattern-Driven Architecture Phases 0–13 (CSS split, constants barrels, component/chart splits, runtime_state, scanner/ticker/depth/HOD facades, error visibility, executor deferral).
- [x] 2026-07-16 — Phase 1 gates: CSS hard limit, baseline growth, import_main + cross-feature warnings.
- [x] 2026-07-15 — Initial maintainer agent, memory, and deterministic scanner.

---

## Run log

<!-- RUN_LOG_START -->

### 2026-07-18 — Danger sniff (secrets / swallow / order path)

- **Scope:** Secrets + danger only (Daddy parallel with security vulnerability audit). Skipped file-size triage, pip_audit, npm audit.
- **Commands:** `py -3 tools/maintainer_checks.py --json` (exit 0); `check_secrets`/`check_swallowed_errors` direct; `ruff --select BLE,TRY203,S105,S106,S107`; complementary greps for placeOrder / key assigns; `git check-ignore .env`.
- **Result:** FINDINGS (danger) — 0 `secret_pattern` in scanned source; 4 `swallowed_exception` (1 production-relevant: `scanner_l1.py:181`); order send confined to `ibkr/orders.py` via safety gate; `.env` ignored/untracked.
- **Learning:** Maintainer secret scanner does not read `.env` (correct — gitignored artifact). Local `.env` still holds live-shaped keys; hygiene note for humans only, never echo values. `scanner_l1` silent `except Exception: pass` around optional `hod_momo_active` import is a new swallow vs 2026-07-16 snapshot (was 1 → now 4).
- **Files updated:** this memory (Current snapshot + this entry). No product code. Dashboard not refreshed (parent/security parallel).

### 2026-07-16 — Dashboard reconciliation (post phase-13, HEAD 13e530f)

- **Scope:** Re-ran deterministic scan against current working tree (HEAD `13e530f`) to reconcile a stale/suspicious Current-snapshot capture (`captured_at 2026-07-16T14:20:00-04:00`, `source_revision phase-13-close`, `dashboard_freshness refresh-required`).
- **Result:** FINDINGS — 10 total / 6 non-baseline: `backend/hod_momo_active.py` 436>400, `frontend/src/constantGroups/chart_api.ts` 413>400, `frontend/src/constantGroups/market_ui.ts` 401>400, `frontend/src/ibkr/ManualOrderTicket.tsx` 331>300, `tools/sync_agent_surfaces.py` 401>400, 1 swallowed exception (`backend/ibkr/ticks.py:59`, benign `list.remove` `ValueError` swallow). `executor.py` baseline stable at 494. `hod_momo.py` (133 lines) and `main.py` (18 lines) well under limit.
- **Root cause of the wrong metrics:** No bug in `tools/maintainer_checks.py` — verified its `count_lines()` against direct measurement for `main.py`, `index.css`, `App.tsx`, `hod_momo.py`, `executor.py` and all matched. The prior snapshot's `index_css_lines: 18` was a manual data-entry error (duplicate of the adjacent `main_py_lines: 18` value, not a fresh recount) — `index.css` is actually 48 lines. `main_py_lines: 18` itself was coincidentally already correct: `main.py` had been refactored further than the last snapshot's author expected, down to an 18-line composition root delegating to `app_lifespan.py` / `app_routers.py`. Systemic cause: the tool doesn't emit these five convenience metrics itself, so every memory update requires hand-transcription — logged as a backlog item instead of editing the tool (outside this read-only auditor's remit).
- **Files updated:** this memory (Current snapshot + backlog + this entry), `agent-maintainer.canvas.tsx` (hand-written pill/stat/table figures reconciled to fresh scan; generated `AGENT_SNAPSHOT_MAINTAINER` block refreshed via `sync_agent_surfaces.py --write`). No product code touched; no PROBLEM_LOG entry added (no actual code/tool defect found, per self-annealing step 3 — root cause was a documentation data-entry error, not a build/runtime/logic failure).

### 2026-07-16 — Phase 13 program close

- **Scope:** Full maintainer + pytest 669 + Vitest 178 + build + Playwright 14.
- **Result:** FINDINGS — 3 non-baseline artifacts only (after sync_agent_surfaces trim); 0 swallowed exceptions; executor baseline intact.
- **Learning:** Windows console must stay ASCII in human reports; hod_momo baseline removed after Phase 10 facade.
- **Files updated:** this memory, `architecture/program-close-metrics.md`, roadmap status.

### 2026-07-16 — Phase 1 gates

- **Scope:** CSS hard limit, baseline growth, dependency warnings.
- **Result:** FINDINGS — index.css hard-fail until Phase 2.
- **Files updated:** `tools/maintainer_checks.py`, `tools/maintainer_lib/deps.py`.

<!-- RUN_LOG_END -->
