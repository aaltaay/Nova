# Nova Router memory (living)

Living knowledge for the Nova `nova-router` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/nova-router.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-18T05:52:42Z
source_revision: d1b1ccc
result: install
metrics: {}
blockers: []
dashboard_freshness: clean
```

**Known misroutes:** none yet.

**Fleet-brief cache:** none yet — run `py -3 tools/agent_fleet.py --json` fresh each session; do not trust a cached count older than the current session.

Machine-readable block only. Update after material runs. Do not duplicate mutable truth that lives in canonical domain sources.

---

## How to continue improving

> Use the nova-router subagent to triage this

Or:

> Improve the nova-router agent — work the next backlog item in `.cursor/agent-memory/nova-router-memory.md`.

Durable facts get **promoted into `nova-router.md`**. Run history and open ideas stay **here**.

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] Seed domain-specific backlog after first real run.

### Completed

- [x] 2026-07-18 — Agent scaffolded via `tools/create_nova_agent.py`.

---

## Run log

Newest first. Keep entries short.

<!-- RUN_LOG_START -->

### 2026-07-18 — Agent install

- **Scope:** Meta — scaffold nova-router via agent contract system.
- **Result:** install
- **Learning:** Follow docs/agent-operations.md remaining human steps.
- **Files updated:** `nova-router.md`, `nova-router-memory.md`, registry entry.

<!-- RUN_LOG_END -->
