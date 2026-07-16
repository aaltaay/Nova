# Maintainer memory (living)

Living knowledge for the Nova `maintainer` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/maintainer.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-16T14:20:00-04:00
source_revision: phase-13-close
result: FINDINGS
metrics:
  findings_total: 19
  findings_non_baseline: 3
  files_scanned: 540
  index_css_lines: 18
  main_py_lines: 18
  app_tsx_lines: 83
  hod_momo_lines: 137
  executor_lines: 494
  swallowed_exception: 0
blockers: []
dashboard_freshness: refresh-required
notes: "Pattern-Driven Architecture Phases 0–13 closed. Only accepted oversize baseline is executor.py. Artifacts .env/dist/.cache are local."
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

_(empty)_

---

## Backlog

- [ ] **Weekly automation** — optional Cursor Automation or scheduled CI job for `tools/maintainer_checks.py --json`
- [ ] **CI gate** — GitHub Actions job for maintainer scanner + ruff (warning-first)
- [ ] **Feed-mixing heuristics** — AST/grep for IBKR→Alpaca silent fallbacks
- [ ] **Cross-feature import cleanup** — migrate baseline-warned frontend deep imports to public barrels
- [ ] **Executor shared-state extract** — only after Phase 12 entry gate + security review

### Completed

- [x] 2026-07-16 — Pattern-Driven Architecture Phases 0–13 (CSS split, constants barrels, component/chart splits, runtime_state, scanner/ticker/depth/HOD facades, error visibility, executor deferral).
- [x] 2026-07-16 — Phase 1 gates: CSS hard limit, baseline growth, import_main + cross-feature warnings.
- [x] 2026-07-15 — Initial maintainer agent, memory, and deterministic scanner.

---

## Run log

<!-- RUN_LOG_START -->

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
