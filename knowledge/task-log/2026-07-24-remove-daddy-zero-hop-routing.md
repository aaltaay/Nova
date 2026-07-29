# 2026-07-24 — Remove daddy dispatcher; zero-hop specialist routing

- **Status:** completed
- **Agents:** parent
- **Domain:** agent OS / fleet routing
- **Related:** `CHANGELOG.md` § 2026-07-24 — Remove daddy dispatcher; zero-hop specialist routing · `PROBLEM_LOG.md` § 2026-07-24 — `hotkeys` agent missing from contract test's expected set

## Task

User asked to remove the `daddy` top-of-fleet dispatcher agent because it was expensive and slow, after first investigating why. Mid-plan, the user asked to go further and avoid agent "hops" entirely, not just remove daddy's extra hop on top of specialist dispatch. Separately, the user asked for a reviewed (non-gaslit) opinion on adopting refactoring.guru's design-pattern catalog and the `keysersoose/loop-library` collection as maintenance principles, and on whether `yu-iskw/cursor-experiments` was useful.

## Goal

1. Remove `daddy` and everything that forces a hop through it.
2. Flip the fleet's default from "auto-dispatch a specialist" to zero-hop: the parent Auto session works in-session by default; every other specialist becomes opt-in-only (invoked only when the user explicitly names it).
3. Add a small, explicitly reviewed "pragmatic patterns & loops" principle to `engineering-standards.mdc` — adopting only what has a concrete match in this codebase, rejecting the rest with stated reasons.
4. Keep `py -3 tools/agent_contract.py` and the fleet tests green throughout.

## Why it mattered

Two subagent investigations (explore agents) confirmed `daddy` was live wiring, not just documentation: it was the registry's first entry, had the highest-priority parent routing rule (any message addressed to `daddy` forced an immediate `Task(subagent_type="daddy")` call), and its own preferred mode was nested `Task` calls to specialists. That means the single most common request shapes ("just get this done", casual `daddy, …`) were paying for at least one extra full agent turn — new context, tools, and a Lifecycle report — before any real work started, with no product-code dependency to justify it.

## What we changed

- Deleted `.cursor/agents/daddy.md`, `.cursor/agent-memory/daddy-memory.md`, and the `agent-daddy.canvas.tsx` dashboard.
- Removed the `daddy` entry from `.cursor/agent-system/registry.json` (14 agents remain, all opt-in).
- Rewrote `.cursor/rules/specialist-routing.mdc`: removed the daddy-shorthand priority rule; inverted the default from "prefer that subagent" to "the parent works in-session unless the user explicitly invokes a specialist"; "who owns X / what's cracked" now prefers the deterministic `py -3 tools/agent_fleet.py` over invoking `router`.
- Updated `.cursor/rules/task-log.mdc` and `.cursor/rules/problem-log.mdc` to move the "ensure one aggregate entry for multi-specialist work" duty from daddy to the parent.
- Updated `knowledge/obsidian/00-System/Agent-Fleet-Map.md`: "Fleet dispatch / orchestration" domain owner is now `parent`; the Orchestration section documents the zero-hop default and lists specialists as opt-in-only, not auto-dispatch targets.
- Updated `AGENTS.md`, `docs/agent-operations.md`, `.cursor/agents/router.md`, `.cursor/agents/hotkeys.md`, `.cursor/agent-system/agent-template.md` to remove daddy references and describe zero-hop routing.
- Updated `tools/sync_agent_surfaces.py` (removed `daddy` from `AGENT_TITLES`), `tools/session_brief_hook.py` (session-start message now says "work in-session by default" instead of "prefer daddy"), `tools/test_agent_contract.py` and `tools/test_agent_fleet.py` (expectations updated for daddy's removal and the fleet-map owner rename to `parent`).
- Regenerated all `AGENT_SNAPSHOT`-marked canvas blocks via `py -3 tools/sync_agent_surfaces.py --write`, then hand-edited the remaining hand-authored prose in `nova-home.canvas.tsx` and `agent-router.canvas.tsx` that referenced daddy outside the generated markers.
- Updated `knowledge/task-log/_template.md` and `knowledge/task-log/README.md` so future task-log entries stop citing `daddy` as an example agent.
- Added a "Pragmatic patterns & loops" section to `.cursor/rules/engineering-standards.mdc`: named five GoF-shaped patterns that already exist in Nova's code (Strategy, Chain of Responsibility, Facade, Observer, Adapter) as recognition-only vocabulary, explicitly rejected the rest of the GoF catalog (Singleton, Builder, Abstract Factory, Bridge, Composite, Decorator, Flyweight, Proxy, Command, Iterator, Mediator, Memento, State, Template Method, Visitor) as unneeded ceremony for a flat, functional Python/TS codebase, and recommended refactoring.guru's code-smell/refactoring catalog (Extract Function/Class, Move Function, Split Phase) as the more useful asset since it maps directly onto the existing `file-size-limits.mdc` enforcement. Reviewed `keysersoose/loop-library` (156 loops) and kept exactly one future-facing recommendation — a deterministic pre-commit test guard (no LLM cost) — rejecting the rest as domain-mismatched (marketing, SEO, mobile, ML retraining) or already covered by existing mandatory rules.
- Found and fixed an unrelated pre-existing test gap while in `tools/test_agent_contract.py`: `hotkeys` was never added to `test_discovery_finds_registered_agents`'s expected set when that agent was scaffolded (logged separately in `PROBLEM_LOG.md`).
- Reviewed `yu-iskw/cursor-experiments` (a toy multi-agent demo) and concluded it was not useful — it demonstrates the exact `Task`-nesting hierarchy this task removes, with no reusable code beyond three markdown agent specs and two bash scripts for a trip-planning toy problem.

## How it works now

Default behavior for any request — including "just get this done" and multi-domain work — is that the parent Auto session classifies and executes in the current session. No automatic `Task(subagent_type=...)` call happens unless the user explicitly names a specialist (e.g. "Use the ibkr-ops subagent to diagnose IB Gateway"). Fleet-health questions ("who owns X", "what's cracked") default to running `py -3 tools/agent_fleet.py` directly (no LLM hop); `router` is invoked only if the user explicitly asks for a routing card. Specialist agent specs, memories, and continuity rules remain on disk and readable — the parent should still follow the relevant domain's continuity rule (e.g. `single-market-data-feed.mdc`, `ibkr-gateway-login-warning.mdc`) even when working in-session rather than dispatching the owning specialist. Multi-domain work done in one parent session gets one aggregate task-log entry, same shape daddy used to produce for a dispatch.

## Why this approach

The user's stated goal was cost/speed ("all hops are expensive"), which ruled out the initially proposed middle ground (remove daddy but keep the parent auto-dispatching specialists) — that still paid for a hop on every multi-domain or ambiguous request. The chosen alternative, promoting `router` into a dispatcher, was rejected because it would spread orchestration responsibility into what is deliberately kept as a cheap, report-only classification tool (`router.md`'s hard constraint is "report-only... never a worker"); merging roles would make router itself more expensive to invoke and muddy its audit-only guarantee. Fully deleting the specialist fleet was also rejected: specialist specs encode hard-won domain knowledge (continuity rules, writable-path conflict tables, deterministic checks) that is still valuable as *reference*, and an explicit opt-in path preserves the option to isolate a genuinely large cross-cutting job into a fresh, narrowly-scoped context when that tradeoff is worth it. The chosen shape — parent-does-the-work by default, everything else opt-in — is the only option that removes the hop cost for the common case while keeping the escape hatch for the rare case that needs it.

For the refactoring.guru and loop-library review: the honest, non-gaslighting answer given the "maintain as cheaply as possible" goal was to adopt almost nothing from either catalog. Nova's backend/frontend are flat, functional codebases already governed by strict anti-monolith rules (`file-size-limits.mdc`, `backend-modularity.mdc`, `karpathy-guidelines.mdc`'s "no abstractions for single-use code"). Importing the full 23-pattern GoF vocabulary — designed for class-hierarchy-heavy OOP — would add indirection with no matching problem, directly increasing maintenance cost. The five patterns kept are pure vocabulary for shapes that already exist in the code (no new code written), which costs nothing and helps future agents recognize the shape instead of reinventing it. Similarly, 154 of ~156 loop-library loops target domains Nova doesn't have (marketing, SEO, mobile builds, ML retraining, red-teaming); adopting a loop-runner framework or nightly agent would be a new process to maintain for no matching gap. The one kept idea (pre-commit test guard) is a plain deterministic shell hook with zero LLM cost, closing a real gap (`commit-push-deploy.mdc` currently only *asks* agents to remember to test, without mechanical enforcement) — it was recorded as a reviewed recommendation in `engineering-standards.mdc`, not implemented as a hook in this pass, since the user's request was to update principles, not ship new tooling.

## Verification

```text
py -3 tools/agent_contract.py                                        # PASS (14 agents)
py -3 -m pytest tools/test_agent_contract.py tools/test_agent_fleet.py -q   # 19 passed
py -3 tools/agent_fleet.py --session-brief                           # no daddy reference; pre-existing unrelated cracks only
py -3 tools/sync_agent_surfaces.py --write                           # regenerated 15 canvas snapshot blocks
```

Manually re-grepped the repo and canvases folder for `daddy` after all edits; remaining hits are historical `CHANGELOG.md` / `knowledge/task-log/*` narratives (left alone per task-log anti-pattern "don't rewrite history") and the explanatory sentence in `nova-home.canvas.tsx` describing why daddy was removed.

## Follow-ups

- The pre-commit test guard recommended in `engineering-standards.mdc` was not implemented in this pass — worth adding when next touching git tooling.
- The `hotkeys` domain is still missing from `tools/sync_agent_surfaces.py`'s `AGENT_TITLES` dict (a separate, pre-existing structural crack visible in the session brief) — out of scope here since it predates and is unrelated to the daddy removal.
- Do not reopen this by re-adding an auto-dispatch default without a new, explicit user decision — the zero-hop default is the point of this change.

## Keywords

daddy, zero-hop, specialist routing, agent dispatch, Task nesting, subagent hop cost, specialist-routing.mdc, Agent-Fleet-Map.md, refactoring.guru, GoF design patterns, loop-library, pre-commit test guard, karpathy-guidelines
