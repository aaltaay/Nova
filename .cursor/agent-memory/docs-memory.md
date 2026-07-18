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
| 2026-07-17 | all 7 preferred (nova-home + agent-tester/maintainer/security/warrior/hod-momo/widgets) | context-usage-* | (none) | Full refresh, no reorder needed — registry order (quality/ops trio → docs steward → domain specialists) already coherent; content updated in place |

---

## Run log

Newest first. Keep entries short.

<!-- RUN_LOG_START -->

### 2026-07-17 — Full canvas refresh + documentation audit

- **Scope:** User asked for a canvas summary/cleanup ("update all canvases and shuffle them around, do not delete") plus a documentation audit.
- **Canvas refresh:** Confirmed inventory unchanged (7 preferred, 0 unmanaged). `tester` and `security` dashboards were genuinely stale (not just old-looking) — dispatched both subagents to re-run their real deterministic gates; `tester` came back **FAIL** (2 confirmed non-flaky regressions in untracked `frontend/src/stock_view/` WIP, not fixed here — handed off), `security` confirmed 6 open findings unchanged (SEC-007 candidate correctly triaged as a fingerprint-dedup, not a new finding). `maintainer`'s snapshot was also flagged `dashboard_freshness: refresh-required` with suspicious metrics (`main_py_lines: 18` looked wrong) — dispatched that subagent too; root cause was a **manual data-entry error** in a prior snapshot (`index_css_lines: 18` was a copy-paste of the adjacent `main_py_lines` field, not a fresh recount — real value 48), not a tool bug; findings dropped 19→10 as the codebase had moved on. Ran `tools/sync_agent_surfaces.py --write` (final pass: 0 writes = fully consistent). Also hand-fixed stale hardcoded prose _outside_ the generated snapshot blocks in `nova-home`, `agent-tester`, and `agent-security` canvases (these don't auto-refresh via the sync tool). No canvas content deleted — only figures/text updated in place, matching the house rule.
- **Shuffle:** Checked registry/roster order (tester → maintainer → security → docs → warrior → hod-momo → widgets) — already a coherent grouping (quality/ops trio → docs steward → domain specialists). Did not force a reorder with no real benefit (Karpathy: no gold-plating).
- **Docs audit:** `markdownlint-cli2` repo-wide: 453→176 errors. Fully cleaned the highest-value docs: `gemini.md`/`AGENTS.md` (constitution, re-synced to match, BOM preserved out of `gemini.md` originally so bytes now identical), `CHANGELOG.md`, `PROBLEM_LOG.md`, `security/SOURCE-PINS.md`, all 4 active `.cursor/agents/*.md` specs, all `.cursor/rules/*.mdc`, and legacy `findings.md`/`progress.md`. Remaining 176 errors are vendored skill copies (`.cursor/skills`, `.claude/skills`, `.agents/skills` — 3x mirrors of graphify/vectorbt-expert/karpathy-guidelines, pinned per SOURCE-PINS) and `knowledge/obsidian/` vault notes — left untouched, logged as backlog.
- **Bug found + fixed:** `markdownlint-cli2 --fix` silently corrupted bare Python identifiers in prose (MD037/MD050 mis-detecting `_session_date`, `__init__.py` etc. as broken emphasis/strong markup and mangling them, e.g. `__init__.py` → `**init**.py`). Caught via `git diff` review before committing, hand-reverted every instance, disabled both rules in `.markdownlint-cli2.jsonc`, logged in `PROBLEM_LOG.md` per self-annealing protocol. Also fixed `**/graphify-out/**` ignore (was only matching root-level) and added `**/.tmp/**` + `**/test-results/**`.
- **Learning:** Never trust `--fix` blindly on a codebase whose prose contains bare code identifiers (underscores/dunders/globs) without backticks — review the diff for MD037/MD050/MD049 damage before committing. Dashboard `dashboard_freshness` flags (`refresh-required`) are a reliable signal to dispatch the owning subagent rather than hand-editing another agent's domain data.
- **Files updated:** 7 canvases (all), `docs-memory.md` (this), `.markdownlint-cli2.jsonc`, `PROBLEM_LOG.md`, `gemini.md`, `AGENTS.md`, `CHANGELOG.md`, `security/SOURCE-PINS.md`, 4 `.cursor/agents/*.md`, `.cursor/rules/*.mdc` (3 files), `findings.md`, `progress.md`, `security/tooling.md`, plus `tester-memory.md`/`security-memory.md`/`maintainer-memory.md` (via their own subagents).

### 2026-07-16 — Agent install

- **Scope:** Meta — create docs, memory, docs-continuity, SOURCE-PINS, markdownlint/Vale config, inventory tool, canvas hygiene, Nova Home section.
- **Result:** n/a (protocol install)
- **Learning:** Dashboard is Nova Home only; unmanaged canvases need evidence before delete.
- **Files updated:** `docs.md`, `docs-memory.md`, `docs-continuity.mdc`, standards configs, `tools/nova_docs_inventory.py`.

<!-- RUN_LOG_END -->
