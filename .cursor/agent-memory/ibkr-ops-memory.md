# IBKR Ops memory (living)

Living knowledge for the Nova `ibkr-ops` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/ibkr-ops.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-20T19:32:00Z
source_revision: local
result: paper-md-entitlement-brief
metrics:
  ibkr_connected: true
  gateway_mode: paper
  spend_status: paper_armed
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

### 2026-07-20 — Paper delayed MD question (read-only)

- **Scope:** User asked if paper trading = delayed API feed because IBKR doesn't charge for paper.
- **Result:** It depends on market-data subscriptions on the Gateway login account, not Nova paper vs live. Nova uses the paper Gateway session (4002) for discovery/quotes when discovery=ibkr; no `reqMarketDataType(DELAYED)` in code. Status: connected paper / paper_armed. Error 10089 = subscription/entitlement gap.
- **Learning:** Promote fact: delayed vs realtime is IBKR Account Management entitlement on the logged-in user (paper username is separate); paper often free/delayed unless US equity API MD (and depth/OPRA if needed) subscribed or delayed enabled on that paper login.
- **Files updated:** `ibkr-ops-memory.md` only.

### 2026-07-18 — Agent install

- **Scope:** Meta — scaffold ibkr-ops via agent contract system.
- **Result:** install
- **Learning:** Follow docs/agent-operations.md remaining human steps.
- **Files updated:** `ibkr-ops.md`, `ibkr-ops-memory.md`, registry entry.

<!-- RUN_LOG_END -->
