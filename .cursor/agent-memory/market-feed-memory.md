# Market Feed memory (living)

Living knowledge for the Nova `market-feed` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/market-feed.md`

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

> Use the market-feed subagent to fix feed coherence

Or:

> Improve the market-feed agent — work the next backlog item in `.cursor/agent-memory/market-feed-memory.md`.

Durable facts get **promoted into `market-feed.md`**. Run history and open ideas stay **here**.

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] Coordinate with hod-momo before any scanner_l1 subscription-cap change.
- [ ] Document first symbol-gate regression reproduction path in memory.

### Completed

- [x] 2026-07-18 — Agent scaffolded via `tools/create_nova_agent.py`.

---

## Run log

Newest first. Keep entries short.

<!-- RUN_LOG_START -->

### 2026-07-18 — Agent install

- **Scope:** Meta — scaffold market-feed via agent contract system.
- **Result:** install
- **Learning:** Follow docs/agent-operations.md remaining human steps.
- **Files updated:** `market-feed.md`, `market-feed-memory.md`, registry entry.

<!-- RUN_LOG_END -->
