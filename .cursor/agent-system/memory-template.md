# {{AGENT_TITLE}} memory (living)

Living knowledge for the Nova `{{AGENT_ID}}` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/{{AGENT_ID}}.md`

---

## Current snapshot

```yaml
captured_at: {{CAPTURED_AT}}
source_revision: {{SOURCE_REVISION}}
result: install
metrics: {}
blockers: []
dashboard_freshness: unknown
```

Machine-readable block only. Update after material runs. Do not duplicate mutable truth that lives in canonical domain sources.

---

## How to continue improving

> {{PRIMARY_INVOKE}}

Or:

> Improve the {{AGENT_ID}} agent — work the next backlog item in `.cursor/agent-memory/{{AGENT_ID}}-memory.md`.

Durable facts get **promoted into `{{AGENT_ID}}.md`**. Run history and open ideas stay **here**.

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] Seed domain-specific backlog after first real run.

### Completed

- [x] {{CAPTURED_AT_DATE}} — Agent scaffolded via `tools/create_nova_agent.py`.

---

## Run log

Newest first. Keep entries short.

<!-- RUN_LOG_START -->

### {{CAPTURED_AT_DATE}} — Agent install

- **Scope:** Meta — scaffold {{AGENT_ID}} via agent contract system.
- **Result:** install
- **Learning:** Follow docs/agent-operations.md remaining human steps.
- **Files updated:** `{{AGENT_ID}}.md`, `{{AGENT_ID}}-memory.md`, registry entry.

<!-- RUN_LOG_END -->
