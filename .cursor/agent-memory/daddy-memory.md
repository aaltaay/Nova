# Daddy memory (living)

Living knowledge for the Nova `daddy` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/daddy.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-19T02:20:00Z
source_revision: 2048482
result: closed_orders_wid027_dispatch
metrics:
  specialists: [widgets, execution, tester]
  wid: WID-027
  isolation: closed_orders_feature_slice
  close_path: placeIbkrOrder_ORDERS_GATE
  cancel_path: CANCEL_GATE
  tester: pass_with_notes
dispatch_mode: direct
blockers: [reload_uvicorn_for_live_closed_orders]
dashboard_freshness: clean
```

Machine-readable block only. Update after material runs. Do not duplicate mutable truth that lives in canonical domain sources.

**dispatch_mode:** `direct` for nested Task. Order-status UI = widgets then tester; Close/Cancel SSOT = parallel `execution` (audit) with widgets. Use `plan` when security/maintainer must not ship product code.

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
