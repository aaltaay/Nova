# Nova agent operations

How Nova's custom Cursor agents are installed, validated, and kept in sync.

## Design principles

1. **Only real agent prompts** live in `.cursor/agents/`. Memory files live in `.cursor/agent-memory/`.
2. **Registry owns wiring** (`.cursor/agent-system/registry.json`): invoke phrases, dashboard, continuity rule/waiver, permissions, handoffs.
3. **Canvases are generated snapshots** — never sources of truth. Every snapshot states capture time, source revision, and freshness.
4. **Filesystem discovery is authoritative:** every `*.md` in `.cursor/agents/` must be a registered agent prompt.
5. **Every future agent** follows the same onboarding lifecycle (see contract).

## Lifecycle (mandatory for every agent)

1. Unique, non-overlapping domain.
2. Spec in `.cursor/agents/<id>.md`.
3. Memory in `.cursor/agent-memory/<id>-memory.md`.
4. Registry entry + exact invoke phrases.
5. Explicit permissions, prohibited actions, canonical inputs/outputs, sibling handoffs.
6. Continuity rule **or** documented waiver in the registry.
7. Dashboard assignment (`agent-*` canvas or explicit Nova Home section).
8. Deterministic checks before LLM judgment.
9. Standard report footer with **Lifecycle** line.
10. Contract validation + real smoke invoke before installation is complete.

## Day-to-day commands

| Task | Command |
|------|---------|
| Validate all agents | `py -3 tools/agent_contract.py` |
| Validate (CI mode, skip external canvas files) | `py -3 tools/agent_contract.py --ci` |
| Live-doc invariants (stale deploy/SoT claims) | `py -3 tools/doc_invariants.py` |
| Live-doc invariant unit tests | `py -3 -m pytest tools/test_doc_invariants.py -q` |
| Sync canvas snapshots (dry-run) | `py -3 tools/sync_agent_surfaces.py` |
| Sync canvas snapshots (write) | `py -3 tools/sync_agent_surfaces.py --write` |
| Scaffold a new agent (dry-run) | `py -3 tools/create_nova_agent.py --id <id> --title "…" --domain "…"` |
| Scaffold a new agent (write) | `py -3 tools/create_nova_agent.py --id <id> --title "…" --domain "…" --write` |
| Fleet crack index (human text) | `py -3 tools/agent_fleet.py` |
| Fleet crack index (JSON) | `py -3 tools/agent_fleet.py --json` |
| Session brief (top-3 cracks, used by hook) | `py -3 tools/agent_fleet.py --session-brief` |
| Deferred log (ranked open bugs/features) | `py -3 tools/deferred_log.py status` |
| Deferred log (same list; human "priorities" ask) | `py -3 tools/deferred_log.py priorities` |
| Lifecycle hook (Cursor) | `.cursor/hooks.json` → `tools/subagent_lifecycle_hook.py` |
| Session-start fleet brief hook (Cursor) | `.cursor/hooks.json` → `tools/session_brief_hook.py` |
| Session-start brief + Stop gate (Claude Code) | `.claude/settings.json` → `tools/session_brief_hook.py --claude`, `tools/repo_hygiene.py stop-gate` |
| Repo maintenance result | Task Scheduler `LastTaskResult`: 0 = verified clean, 1 = findings remain, 2 = fetch/inspection/action failure; `logs/repo-hygiene.log` records each run. Three retries at five-minute intervals; linked worktrees never install the task. |
| Repo hygiene (is this clone clean?) | `py -3 tools/repo_hygiene.py status` |
| Repo hygiene (safe fixes: merged branches, stale worktrees, orphan refs) | `py -3 tools/repo_hygiene.py fix [--dry-run]` (nightly task `NovaRepoHygiene`, `scripts/Ensure-NovaMaintenanceTask.ps1`; installed/verified automatically by API and source Desktop startup, and daily-task setup) |
| Agent dreaming (dry-run) | `py -3 tools/agent_dream.py` |
| Agent dreaming (apply) | `py -3 tools/agent_dream.py --write` |
| Agent dreaming (one agent) | `py -3 tools/agent_dream.py --agent <id> [--write]` |

## Dreaming (fleet memory consolidation)

Nova-native light → REM → deep over agent memory, plus optional Obsidian hygiene, Pinecone ingest, Claude/OpenClaw bridges, and git ship.

| Phase / flag | Writes? | Effect |
|--------------|---------|--------|
| Light | No | Stage pending facts, backlog counts, run-log size |
| REM | Diary | Heuristic themes + LLM diary when `OPENAI_API_KEY` set (`--no-llm-rem` to force heuristic) |
| Deep | `--write` | Promote pending facts; trim run logs to 30; stamp `last_dream_at` |
| `--obsidian` | `--write` | `_Agent-Dream-Hygiene.md` + strategy note footers (no Chosen-strategy rewrites) |
| `--bridges` | `--write` | Claude Code `autoDreamEnabled` + `.cursor/agent-system/openclaw-MEMORY.md` export |
| `--commit` / `--push` | requires `--write` | Ship dream artifacts |

Shorthand: `py -3 tools/agent_dream.py --full-mission` (± `--write --commit --push`). Owner: `docs`. Vault: `knowledge/obsidian/00-System/Agent-Dreaming.md`.

## Fleet triage (zero-hop default + router + agent_fleet)

`tools/agent_fleet.py` unions signals that used to live in separate memories into one crack index: stale snapshots (`captured_at` >7 days old or self-reported `dashboard_freshness` not `clean`), open blockers, unowned/continuity-only domains and orphan skills (from `knowledge/obsidian/00-System/Agent-Fleet-Map.md`), unmanaged canvases on disk, and missing `AGENT_TITLES` entries. It is read-only — it never edits the fleet map, registry, or memories.

**Default is zero-hop:** the parent Auto session does classification and orchestration itself — no automatic `Task(...)` dispatch, including for "just get this done" or multi-domain work. Every subagent call is a full extra agent turn (new context, tools, Lifecycle report); routing to one automatically was found to be the most expensive, highest-frequency cost in the fleet. Prefer `py -3 tools/agent_fleet.py` for "who owns X / what's cracked?" — it's deterministic and has no LLM cost.



When a domain/skill's ownership changes (a specialist is scaffolded, a domain starts/stops being maintained), update its row in `Agent-Fleet-Map.md` in the same commit — `agent_fleet.py` reads that file as the ownership source of truth and never rewrites it.

## Routing

See `.cursor/rules/specialist-routing.mdc`. Defaults (all opt-in unless noted):



## Report Lifecycle line

Every specialist report must end with:

```text
**Lifecycle:** memory=unchanged|changed | promotion=none|<what> | dashboard=clean|refresh-required | handoff=none|<sibling|parent> | task_log=<PR URL>|<path>|skipped|n/a | problem_log=<entry>|skipped|n/a | deferred_log=<id>|none|skipped|n/a
```

`problem_log=` is mandatory for **every** agent (rule: `.cursor/rules/problem-log.mdc`). After any bug fix or full diagnosis, prepend `PROBLEM_LOG.md` and set `problem_log=<YYYY-MM-DD title>`; otherwise `skipped` / `n/a`. Parent Auto sessions without a Lifecycle line still must write PROBLEM_LOG when they fix a bug.

`deferred_log=` is mandatory for **every** agent (rule: `.cursor/rules/deferred-log.mdc`). After parking a known bug or a feature you will not build this session, open or update a GitHub Issue labeled `deferred` and set `deferred_log=#NNN` (its GitHub number); otherwise `none` / `skipped` / `n/a`. Agent-memory Backlog is not the SSOT. Parent Auto sessions without a Lifecycle line still must open the issue when they park work.

The `subagentStop` hook reminds once (fail-open, `loop_limit: 1`) if a Nova agent omits this line. It never edits files and never blocks completion.

## Task narrative (reasoning archive)

After every completed material task, write the narrative so future agents keep the **why**, not only the diff. Default home is the **PR body**; the `knowledge/task-log/` folder covers work that ships without a PR.

| Piece | Path |
|-------|------|
| Rule (always apply) | `.cursor/rules/task-log.mdc` |
| PR template (default home) | `.github/pull_request_template.md` |
| Index (no-PR entries) | `knowledge/task-log/INDEX.md` |
| Template | `knowledge/task-log/_template.md` |
| Scaffold | `py -3 tools/task_log_new.py --slug <kebab> --title "…"` |

The parent writes one aggregate narrative for multi-domain jobs done in-session, and never both a PR body and a task-log file for the same job. CHANGELOG / PROBLEM_LOG / deferred Issues remain short; the narrative holds tradeoffs and rejected alternatives.

## Deferred tracker (known bugs + parked features)

Parked work that is **not** a closed fix lives as GitHub Issues labeled `deferred` -- same respect as `PROBLEM_LOG.md`. Open P0/P1 items also appear in the session-start fleet brief. `DEFERRED_LOG.md` is the how-to, not the list.

**Before any fix:** run `py -3 tools/deferred_log.py status` (alias `priorities`) and search open issues. If an existing issue already covers the ask, work from that issue (`parked` means do not start it). When the human asks "what's on the to-do / what's missing / priorities," that command is the answer -- do not invent a second tracker.

| Piece | Path |
|-------|------|
| SSOT | GitHub Issues labeled `deferred` |
| How-to | `DEFERRED_LOG.md` |
| Rule (always apply) | `.cursor/rules/deferred-log.mdc` |
| Ranked list | `py -3 tools/deferred_log.py status` (alias `priorities`) |

## Adding a future agent

1. Dry-run `create_nova_agent.py` with a unique `--id` and non-overlapping invoke phrases.
2. `--write` when ready; fill domain checks / permissions the scaffolder leaves blank.
3. Add continuity rule **or** set `continuity_waiver` in the registry.
4. Run `agent_contract.py` (must pass).
5. Run `sync_agent_surfaces.py --write`.
6. Smoke-invoke with the registered phrase.
7. Only then treat the agent as installed.

## Canvas freshness

Generated blocks are marked:

```tsx
{/* AGENT_SNAPSHOT_START: <agent-id> */}
…
{/* AGENT_SNAPSHOT_END: <agent-id> */}
```

Stale = memory `dashboard_freshness` is `stale`/`unknown`, or snapshot `captured_at` is older than the sync policy threshold. Sync tool labels this explicitly — never pretend point-in-time data is live.
