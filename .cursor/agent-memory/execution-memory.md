# Execution Auditor memory (living)

Living knowledge for the Nova `execution` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/execution.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-18T06:20:27Z
source_revision: cdf87d5
result: install
metrics: {}
blockers: []
dashboard_freshness: clean
```

Machine-readable block only. Update after material runs. Do not duplicate mutable truth that lives in canonical domain sources.

---

## How to continue improving

> Use the execution subagent to audit trading execution

Or:

> Improve the execution agent — work the next backlog item in `.cursor/agent-memory/execution-memory.md`.

Durable facts get **promoted into `execution.md`**. Run history and open ideas stay **here**.

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [x] Continuity rule created (execution-continuity.mdc).
- [ ] First real audit run: pytest + synthetic latency probe; refresh validation canvas numbers if SLA claims change.
- [ ] Confirm paper Gateway probe still deferred and documented as such.

### Completed

- [x] 2026-07-18 — Agent scaffolded via `tools/create_nova_agent.py`.

---

## Run log

Newest first. Keep entries short.

<!-- RUN_LOG_START -->

### 2026-07-18 — Agent install

- **Scope:** Meta — scaffold execution via agent contract system.
- **Result:** install
- **Learning:** Follow docs/agent-operations.md remaining human steps.
- **Files updated:** `execution.md`, `execution-memory.md`, registry entry.

<!-- RUN_LOG_END -->
