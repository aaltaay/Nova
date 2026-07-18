# IBKR Ops memory (living)

Living knowledge for the Nova `ibkr-ops` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/ibkr-ops.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-18T06:20:43Z
source_revision: cdf87d5
result: install
metrics: {}
blockers: []
dashboard_freshness: clean
```

Machine-readable block only. Update after material runs. Do not duplicate mutable truth that lives in canonical domain sources.

---

## How to continue improving

> Use the ibkr-ops subagent to diagnose IB Gateway

Or:

> Improve the ibkr-ops agent — work the next backlog item in `.cursor/agent-memory/ibkr-ops-memory.md`.

Durable facts get **promoted into `ibkr-ops.md`**. Run history and open ideas stay **here**.

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] Verify docs/ibc-gateway-setup.md matches local IBC paths on this machine.
- [ ] Smoke: /api/ibkr/status connected:true after Gateway login.

### Completed

- [x] 2026-07-18 — Agent scaffolded via `tools/create_nova_agent.py`.

---

## Run log

Newest first. Keep entries short.

<!-- RUN_LOG_START -->

### 2026-07-18 — Agent install

- **Scope:** Meta — scaffold ibkr-ops via agent contract system.
- **Result:** install
- **Learning:** Follow docs/agent-operations.md remaining human steps.
- **Files updated:** `ibkr-ops.md`, `ibkr-ops-memory.md`, registry entry.

<!-- RUN_LOG_END -->
