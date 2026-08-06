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
| Lifecycle hook (Cursor) | `.cursor/hooks.json` → `tools/subagent_lifecycle_hook.py` |
| Session-start fleet brief hook (Cursor) | `.cursor/hooks.json` → `tools/session_brief_hook.py` |
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
| `--pinecone` | dry-run unless `--write` | `tools/course_memory/ingest.py` (`--pinecone-full` drops `--limit`) |
| `--bridges` | `--write` | Claude Code `autoDreamEnabled` + `.cursor/agent-system/openclaw-MEMORY.md` export |
| `--commit` / `--push` | requires `--write` | Ship dream artifacts |

Shorthand: `py -3 tools/agent_dream.py --full-mission` (± `--write --commit --push`). Owner: `docs`. Vault: `knowledge/obsidian/00-System/Agent-Dreaming.md`.

## Fleet triage (zero-hop default + router + agent_fleet)

`tools/agent_fleet.py` unions signals that used to live in separate memories into one crack index: stale snapshots (`captured_at` >7 days old or self-reported `dashboard_freshness` not `clean`), open blockers, unowned/continuity-only domains and orphan skills (from `knowledge/obsidian/00-System/Agent-Fleet-Map.md`), unmanaged canvases on disk, and missing `AGENT_TITLES` entries. It is read-only — it never edits the fleet map, registry, or memories.

**Default is zero-hop:** the parent Auto session does classification and orchestration itself — no automatic `Task(...)` dispatch, including for "just get this done" or multi-domain work. Every subagent call is a full extra agent turn (new context, tools, Lifecycle report); routing to one automatically was found to be the most expensive, highest-frequency cost in the fleet. Prefer `py -3 tools/agent_fleet.py` for "who owns X / what's cracked?" — it's deterministic and has no LLM cost.

- **`router`** (dashboard `agent-router.canvas.tsx`) remains the pure classification / crack-index tool: given a task, it names the specialist(s)/skill(s) via a **Routing card** and hands off — it never implements product code. Invoke only when the user explicitly asks for a routing card; otherwise run `agent_fleet.py` directly.
- Every other specialist (ibkr-ops, market-feed, hod-momo, tester, maintainer, security, docs, warrior, widgets, execution, news, backtester, hotkeys) remains registered and invocable, but **opt-in only** — invoke by name when the user explicitly asks, never automatically.

When a domain/skill's ownership changes (a specialist is scaffolded, a domain starts/stops being maintained), update its row in `Agent-Fleet-Map.md` in the same commit — `agent_fleet.py` reads that file as the ownership source of truth and never rewrites it.

## Routing

See `.cursor/rules/specialist-routing.mdc`. Defaults (all opt-in unless noted):

- "Just get this done" / multi-domain work → the parent, in-session (no automatic dispatch)
- Classification / crack index only → `py -3 tools/agent_fleet.py` (default); `router` only on explicit ask
- Product change verification → `tester` (explicit ask) or run pytest/Vitest/build yourself
- Maintainability / danger audit → `maintainer`
- Full-repo security posture → `security`
- Docs / rules / prompts / canvases → `docs`
- Warrior Trading authenticated site / Day Trade Dash → `warrior`
- HOD Momo scanner data-quality / Warrior parity iteration → `hod-momo`
- Webull-to-Nova stock/day-trading widget parity → `widgets`
- Trading execution ADR 007 audit → `execution`
- IB Gateway login / IBC / port health → `ibkr-ops`
- General scanner L1 + quote/chart/L2/T&S coherence → `market-feed`
- News / catalyst pipeline → `news`
- Backtest product + VectorBT skills → `backtester`
- PR / diff security → Cursor built-in `security-review`

## Report Lifecycle line

Every specialist report must end with:

```text
**Lifecycle:** memory=unchanged|changed | promotion=none|<what> | dashboard=clean|refresh-required | handoff=none|<sibling|parent> | task_log=<path>|skipped|n/a | problem_log=<entry>|skipped|n/a
```

`problem_log=` is mandatory for **every** agent (rule: `.cursor/rules/problem-log.mdc`). After any bug fix or full diagnosis, prepend `PROBLEM_LOG.md` and set `problem_log=<YYYY-MM-DD title>`; otherwise `skipped` / `n/a`. Parent Auto sessions without a Lifecycle line still must write PROBLEM_LOG when they fix a bug.

The `subagentStop` hook reminds once (fail-open, `loop_limit: 1`) if a Nova agent omits this line. It never edits files and never blocks completion.

## Task log (reasoning archive)

After every completed material task, append a narrative under `knowledge/task-log/` so future agents keep the **why**, not only the diff.

| Piece | Path |
|-------|------|
| Rule (always apply) | `.cursor/rules/task-log.mdc` |
| Index | `knowledge/task-log/INDEX.md` |
| Template | `knowledge/task-log/_template.md` |
| Scaffold | `py -3 tools/task_log_new.py --slug <kebab> --title "…"` |

The parent writes one aggregate entry for multi-domain jobs done in-session. CHANGELOG / PROBLEM_LOG remain short; the task log holds tradeoffs and rejected alternatives.

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
