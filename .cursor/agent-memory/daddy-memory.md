# Daddy memory (living)

Living knowledge for the Nova `daddy` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/daddy.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-23T23:00:00Z
source_revision: pre-commit
result: per_operation_latency_metrics
metrics:
  specialists: [execution, market-feed, widgets, tester, docs]
  dispatch_mode: direct
  orchestration: mixed
  backend_pytest: 961_pass
  frontend_vitest: 441_pass
blockers:
  - openai_embed_key_401_for_ask_recall_synthesis
  - include_whisper_allowlist_misses_grok_and_faster_whisper_labels
dashboard_freshness: clean
```

Machine-readable block only. Update after material runs. Do not duplicate mutable truth that lives in canonical domain sources.

**dispatch_mode:** `direct`. Vitest act-env: sequence implementer → tester; named fix from 2026-07-20 audit (`setupFiles` + `IS_REACT_ACT_ENVIRONMENT`); after flag, fix any real unwrapped-act tests uncovered (WorkspaceContext).

---

## How to continue improving

> Use the daddy subagent to dispatch this

Or:

> Improve the daddy agent — work the next backlog item in `.cursor/agent-memory/daddy-memory.md`.

Durable facts get **promoted into `daddy.md`**. Run history and open ideas stay **here**.

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] Keep roster in sync when new specialists are scaffolded.

### Completed

- [x] 2026-07-18 — First real invoke: recorded dispatch_mode=direct (security + maintainer parallel).
- [x] 2026-07-18 — Agent scaffolded via `tools/create_nova_agent.py`.

---

## Run log

Newest first. Keep entries short.

<!-- RUN_LOG_START -->

### 2026-07-23 — Per-operation latency metrics and lifecycle fixes

- **Scope:** End-to-end bounded latency metrics across execution, IBKR market data, HTTP/WS ingress, health attribution, and regression coverage.
- **Result:** sequence execution → market-feed → widgets → tester; parallelized two disjoint lint-only repairs and final read-only gates. Backend 961, frontend 441, lint/build/probe/endpoint verification passed; commit/push handled by parent.
- **Learning:** Cross-domain telemetry works best as owner-first sequence over one shared tree, with tester after all writers. `git add -A -- . ":(exclude)..."` can return nonzero on ignored Windows paths after staging the intended files; inspect the index, then use tracked-plus-explicit-untracked staging instead of retrying the same command.
- **Files updated:** daddy-memory.md; aggregate task log `2026-07-23-per-operation-latency-measurement.md`.

### 2026-07-22 — Vitest act() warnings — fix all (not ignore)

- **Scope:** User “fix all Vitest act(...) warnings”; apply 2026-07-20 audit fix + clear any uncovered real act bugs.
- **Result:** sequence generalPurpose → tester; setupFiles + `IS_REACT_ACT_ENVIRONMENT`; WorkspaceContext deferred config under `act`; tester PASS 99/422, zero act-env and zero unwrapped-act warnings. Pushed `ea85715` + `f09985a`.
- **Learning:** Audit-named one-liner first; expect real “not wrapped” warnings to appear once flag is on — treat those as follow-up test fixes in same dispatch, not as “still noisy.” No fleet specialist owns Vitest harness → nest `generalPurpose` then `tester`.
- **Files updated:** daddy-memory.md; task-log `2026-07-22-vitest-act-environment-fix.md` (Agents line).

### 2026-07-20 — Flatten dual-source position SSOT audit (plan expand)

- **Scope:** Plan-mode; Flatten NO_POSITION vs Positions SPY qty 1; full same-nature inventory; no product code.
- **Result:** parallel execution+maintainer; SSOT = `account.long_qty` on `ib.positions()` shared by validate + executor_flatten + `/positions` qty; reject draft validate→portfolio and UI `source=flatten`; CRITICAL sibling = OS flatten empty positions → skip sell + cancel legs.
- **Learning:** Align UI to gate truth (positions), not gate to UI (portfolio) — portfolio-as-primary can false-allow OVERSELL; positions-empty while portfolio-shows is the real class.
- **Files updated:** daddy-memory.md; aggregate task-log `2026-07-20-flatten-dual-source-daddy-audit.md` (execution also wrote sibling audit log).

### 2026-07-20 — Vitest act() environment warning audit

- **Scope:** Verify (not assume) root cause of `act()` env warning in `workingOrderCells.test.tsx`/`closedOrderCells.test.tsx`; scope + benign-or-not + fix name; audit only.
- **Result:** direct investigate, no specialist needed — confirmed `globalThis.IS_REACT_ACT_ENVIRONMENT` never set anywhere (no `setupFiles`, no RTL dependency at all); affects **24** manual-mount `*.test.tsx` files, not just 2 (653 warning instances / 386 tests, all passing); default Vitest reporter hides it on passing tests (only `--reporter=verbose`/failure show it) — that's why it looked occasional. Confirmed via React source it is **not purely cosmetic**: the same unset flag also disables React's real "update not wrapped in act" bug-catching warning in both directions. Named fix: `test.setupFiles` + tiny dedicated setup module setting the flag — not applied (audit-only ask).
- **Learning:** "Pre-existing noise, unrelated" claims are exactly what self-annealing should catch — verifying required reading React's own source (`isConcurrentActEnvironment`), not just grepping. A throwaway probe test + `--reporter=verbose` was the fastest way to get ground truth; default reporter output is not sufficient evidence for "nothing happens" claims on passing tests.
- **Files updated:** daddy-memory.md; `PROBLEM_LOG.md`; task-log `2026-07-20-vitest-act-environment-audit.md`.

### 2026-07-19 — Harvested materials vs AI decision wiring (current truth)

- **Scope:** Does Whisper harvest affect AI/trading decisions today?
- **Result:** direct investigate — Pinecone 2094 = slides + official captions; Whisper on disk unused; Obsidian keyword = official-only; decide/HOD/control_mode do not consume transcripts.
- **Learning:** Most harvest files are `groq-whisper-api` / `faster-whisper-local-cuda`, not `whisper-local-audio` — even `--include-whisper` would miss them until allowlist/retag.
- **Files updated:** daddy-memory.md; task-log `2026-07-19-harvested-materials-ai-decision-wiring.md`.

### 2026-07-19 — Alpaca usage inventory (ibkr ops)

- **Scope:** User declined frontend discovery default change; ask what Alpaca is still for.
- **Result:** direct explore inventory — under discovery=ibkr Alpaca still used for news, listing Assets, scanner RVOL daily bars, health/Settings; not for live prices/charts/WS/HOD/T&S/orders. No silent IBKR→Alpaca price fallback. HOD avg_vol = yfinance only.
- **Learning:** Investigate-only inventories → nested explore + spot-check gates; do not re-propose default flip after user declined.
- **Files updated:** daddy-memory.md; task-log `2026-07-19-alpaca-usage-inventory.md`.

### 2026-07-19 — Warrior transcripts → KB / AI plan

- **Scope:** How harvested LMS transcripts enter knowledge, automation, AI.
- **Result:** plan — reuse `tools/course_memory`; official→Pinecone first; Whisper curated; Obsidian/graphify = indexes only; dream `--pinecone-official`.
- **Learning:** Pipeline already exists (`--official-transcripts` / `--include-whisper`); harvest completion ≠ inventory + ingest, not a new RAG stack. Do not nest implementers for “how do we add this?” until input keys + Whisper scope decided.
- **Files updated:** daddy-memory.md; task-log `2026-07-19-warrior-transcript-kb-plan.md`.

### 2026-07-19 — Filled / active-trade field (“like filled”)

- **Scope:** User asked for field where you actively trade them (like filled); create if missing.
- **Result:** sequence widgets → tester; **already had** Filled/Remaining/Avg fill/Partially filled/Fill now; widgets tooltip polish only; tester PASS (42 Vitest + 12 pytest).
- **Learning:** “like filled” on Open/Closed ≠ WID-015 TurboTrader; verify columns first before inventing UI. Prefer-ask commit noted.
- **Files updated:** daddy-memory.md; aggregate task-log `2026-07-19-filled-active-trade-daddy-dispatch.md`.

### 2026-07-18 — Closed Orders WID-027 + Close SSOT

- **Scope:** Webull Closed Orders widget + flatten bells; isolation for hide/move/drag-drop.
- **Result:** parallel widgets+execution → tester; WID-027 partial shipped (`closed_orders/` + registry); Flatten = place/ORDERS_GATE; history read-only; tester PASS with notes (reload uvicorn).
- **Learning:** Closed/history ≠ Close button surface; Positions Flatten shares hotkeys exit path; ADR 005 slice before Stock View dock.
- **Files updated:** daddy-memory.md; aggregate task-log; specialists wrote own logs.

### 2026-07-18 — Cancel open-order SSOT audit

- **Scope:** Can we cancel pending/open orders; own gate; UML/SSOT.
- **Result:** parallel execution + hotkeys; **Yes** working cancel via `execute(cancel)` + `CANCEL_GATE`; panel ✕ ≠ hotkeys dispatcher; UML sequence missing.
- **Learning:** Cancel questions = audit pair execution+hotkeys; next = docs UML only unless product asks for ledger/client gate parity.
- **Files updated:** daddy-memory.md; aggregate task-log; specialists wrote own logs/memory.

### 2026-07-18 — Working Orders widget (Webull post-place)

- **Scope:** User wants a widget that opens after place, Webull columns/lifecycle.
- **Result:** sequence widgets → tester; WID-026 partial shipped (`WorkingOrdersPanel`); scoped gates green; paper place skipped (IBKR disconnected).
- **Learning:** Order-status UI = widgets owns map+UI; execution audit not needed for v1 column shell; tester after implement. Next gap WID-020 history/export.
- **Files updated:** daddy-memory.md; specialists wrote product/docs/task-log.

### 2026-07-18 — SEC-001–008 remediation Dispatch Plan

- **Scope:** User “fix them up” after vuln search — sequenced plan only (no product code from daddy/security).
- **Result:** plan — 5 implement chunks + tester after each + optional security re-audit; file hints from findings-registry.json.
- **Learning:** Remediations must use mode=plan (or parent generalPurpose), never ask security to ship fixes. Loopback+API-key first (SEC-002/004) before config mask / SSRF.
- **Files updated:** daddy-memory.md only.

### 2026-07-18 — Vulnerability search (security + maintainer)

- **Scope:** User “Search for vulnerabilities” — parallel audit dispatch.
- **Result:** FINDINGS — 8 open SEC (2 new: SSRF SEC-008, torch SEC-007); maintainer danger sniff clean on secrets / placeOrder.
- **Learning:** Nested Task works (dispatch_mode=direct). Parallel `security`+`maintainer` is the right shape for vuln searches.
- **Files updated:** daddy-memory.md only (specialists updated their own memories/registry).

### 2026-07-18 — Agent install

- **Scope:** Meta — scaffold daddy via agent contract system.
- **Result:** install
- **Learning:** Follow docs/agent-operations.md remaining human steps.
- **Files updated:** `daddy.md`, `daddy-memory.md`, registry entry.

<!-- RUN_LOG_END -->
