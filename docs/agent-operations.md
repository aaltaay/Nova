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
| Sync canvas snapshots (dry-run) | `py -3 tools/sync_agent_surfaces.py` |
| Sync canvas snapshots (write) | `py -3 tools/sync_agent_surfaces.py --write` |
| Scaffold a new agent (dry-run) | `py -3 tools/create_nova_agent.py --id <id> --title "…" --domain "…"` |
| Scaffold a new agent (write) | `py -3 tools/create_nova_agent.py --id <id> --title "…" --domain "…" --write` |
| Lifecycle hook (Cursor) | `.cursor/hooks.json` → `tools/subagent_lifecycle_hook.py` |

## Routing

See `.cursor/rules/specialist-routing.mdc`. Defaults:

- Product change verification → `tester`
- Maintainability / danger audit → `maintainer`
- Full-repo security posture → `security-sentinel`
- Docs / rules / prompts / canvases → `nova-agent`
- PR / diff security → Cursor built-in `security-review`

## Report Lifecycle line

Every specialist report must end with:

```text
**Lifecycle:** memory=unchanged|changed | promotion=none|<what> | dashboard=clean|refresh-required | handoff=none|<sibling|parent>
```

The `subagentStop` hook reminds once (fail-open, `loop_limit: 1`) if a Nova agent omits this line. It never edits files and never blocks completion.

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
