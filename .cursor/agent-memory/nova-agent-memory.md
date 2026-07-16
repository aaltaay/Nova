# Nova Agent memory (living)

Living knowledge for the Nova `nova-agent` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/nova-agent.md`  
Dashboard: `nova-home.canvas.tsx` (no separate Nova Agent canvas)

---

## Current snapshot

```yaml
captured_at: 2026-07-16T01:00:00-04:00
source_revision: b8626e4
result: install
metrics:
  preferred_canvases: 4
  unmanaged_canvases: 0
blockers: []
dashboard_freshness: stale
notes: "Current classification comes from tools/nova_docs_inventory.py; history table below is durable."
```

---

## How to continue improving

Pick the next open item in **Backlog**, or ask:

> Use the Nova Agent to review documentation.

Or:

> Improve the Nova Agent — work the next backlog item in `.cursor/agent-memory/nova-agent-memory.md`.

Durable facts (commands, canvas policy, traps) get **promoted into `nova-agent.md`**. Run history and open ideas stay **here**. Current canvas classification is owned by `nova_docs_inventory`.

---

## Suppressions

False positives from markdownlint / Vale / Lychee. Pattern + reason. Newest first.

_(empty)_

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] **CI warning-first** — GitHub Actions job for markdownlint-cli2 + Vale + Lychee (continue-on-error initially).
- [ ] **Diátaxis map** — classify `docs/` + key vault notes into tutorial / how-to / reference / explanation; fix misplaced files only with evidence.
- [ ] **CHANGELOG/PROBLEM_LOG template drift** — detect entries missing required fields.
- [ ] **Broken internal links** — Lychee pass focused on `file://` / relative markdown links in `docs/` and `knowledge/obsidian/`.
- [ ] **Promote top traps** — after 2+ identical doc mistakes, add Known traps to `nova-agent.md`.

### Completed

- [x] 2026-07-16 — Initial Nova Agent install (agent + memory + docs-continuity + inventory + standards pins).
- [x] 2026-07-16 — Canvas hygiene: merge `nova-security-audit` → `agent-security`; preferred naming policy on Nova Home.

---

## Learned facts (pending promotion)

Facts discovered in a run that are **not yet** in `nova-agent.md`. After promoting, delete the bullet here.

_(empty)_

---

## Canvas inventory (last known)

Update after each canvas-hygiene run.

| Date | Preferred | System | Unmanaged | Action |
|------|-----------|--------|-----------|--------|
| 2026-07-16 | nova-home, agent-tester, agent-maintainer, agent-security | context-usage-* | (none after merge) | Merged nova-security-audit into agent-security |

---

## Run log

Newest first. Keep entries short.

<!-- RUN_LOG_START -->

### 2026-07-16 — Agent install

- **Scope:** Meta — create nova-agent, memory, docs-continuity, SOURCE-PINS, markdownlint/Vale config, inventory tool, canvas hygiene, Nova Home section.
- **Result:** n/a (protocol install)
- **Learning:** Dashboard is Nova Home only; unmanaged canvases need evidence before delete.
- **Files updated:** `nova-agent.md`, `nova-agent-memory.md`, `docs-continuity.mdc`, standards configs, `tools/nova_docs_inventory.py`.

<!-- RUN_LOG_END -->
