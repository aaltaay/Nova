# Docs memory (living)

Living knowledge for the Nova `docs` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/docs.md`  
Dashboard: `nova-home.canvas.tsx` (no separate Docs canvas)

---

## Current snapshot

```yaml
captured_at: 2026-07-17T00:03:00-04:00
source_revision: 13e530f
result: clean
metrics:
  preferred_canvases: 7
  unmanaged_canvases: 0
  canvases_refreshed: 7
  markdownlint_errors_before: 453
  markdownlint_errors_after: 176
blockers: []
dashboard_freshness: clean
notes: "Full refresh pass: dispatched tester + security + maintainer subagents to re-run their own deterministic checks and reconcile stale dashboards (all 3 were genuinely stale, not just cosmetically old); ran sync_agent_surfaces.py --write (0 writes on the final pass = fully consistent); fixed hand-written stale prose in nova-home + agent-tester + agent-security canvases outside the generated snapshot blocks. Docs audit: gemini.md/AGENTS.md re-synced + fully markdownlint-clean; found and fixed a real `--fix` corruption bug (MD037/MD050 mangling bare Python identifiers like __init__.py); remaining 176 lint errors are vendored skill copies + Obsidian vault notes, left untouched (out of scope / not ours to edit)."
```

---

## How to continue improving

Pick the next open item in **Backlog**, or ask:

> Use the docs subagent to review documentation.

Or:

> Improve the docs agent — work the next backlog item in `.cursor/agent-memory/docs-memory.md`.

Durable facts (commands, canvas policy, traps) get **promoted into `docs.md`**. Run history and open ideas stay **here**. Current canvas classification is owned by `nova_docs_inventory`.

---

## Suppressions

False positives from markdownlint / Vale / Lychee. Pattern + reason. Newest first.

**(empty)**

---

## Backlog

Open improvements. Newest first. Mark `[x]` when done and move a one-line note to **Completed**.

- [ ] **Vendored skill lint debt** — 176 remaining markdownlint errors are all in `.cursor/skills/*` (+ `.claude/skills`, `.agents/skills` mirrors) and `knowledge/obsidian/`. Vendored copies are pinned per `docs/SOURCE-PINS.md` — don't hand-edit without checking whether upstream already fixed it; Obsidian vault needs its own pass (lower priority, high volume).
- [ ] **CI warning-first** — GitHub Actions job for markdownlint-cli2 + Vale + Lychee (continue-on-error initially).
- [ ] **Diátaxis map** — classify `docs/` + key vault notes into tutorial / how-to / reference / explanation; fix misplaced files only with evidence.
- [ ] **CHANGELOG/PROBLEM_LOG template drift** — detect entries missing required fields.
- [ ] **Broken internal links** — Lychee pass focused on `file://` / relative markdown links in `docs/` and `knowledge/obsidian/`.
- [ ] **Promote top traps** — after 2+ identical doc mistakes, add Known traps to `docs.md`.

### Completed

- [x] 2026-07-16 — Initial Docs install (agent + memory + docs-continuity + inventory + standards pins).
- [x] 2026-07-16 — Canvas hygiene: merge `nova-security-audit` → `agent-security`; preferred naming policy on Nova Home.
- [x] 2026-07-16/17 — Full canvas + docs refresh: dispatched tester/security/maintainer to reconcile stale dashboards; markdownlint errors 453→176; fixed `--fix` MD037/MD050 corruption bug (see PROBLEM_LOG); gemini.md/AGENTS.md re-synced and fully clean.

---

## Learned facts (pending promotion)

Facts discovered in a run that are **not yet** in `docs.md`. After promoting, delete the bullet here.

**(empty)**

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

### 2026-07-17 — Full canvas refresh + documentation audit



### 2026-07-16 — Agent install

- **Scope:** Meta — create docs, memory, docs-continuity, SOURCE-PINS, markdownlint/Vale config, inventory tool, canvas hygiene, Nova Home section.
- **Result:** n/a (protocol install)
- **Learning:** Dashboard is Nova Home only; unmanaged canvases need evidence before delete.
- **Files updated:** `docs.md`, `docs-memory.md`, `docs-continuity.mdc`, standards configs, `tools/nova_docs_inventory.py`.

<!-- RUN_LOG_END -->
