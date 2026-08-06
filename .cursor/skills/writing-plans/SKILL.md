---
name: writing-plans
description: >-
  Writes bite-sized implementation plans with exact files, interfaces, and
  red/green verification steps. Use in Plan mode, for multi-file features, or
  when the user asks for a plan/spec before coding. Not for one-line fixes.
---

# Writing plans (Nova)

Lineage: [obra/superpowers](https://github.com/obra/superpowers) `writing-plans`, adapted for Nova.

**Announce:** "Using writing-plans to create the implementation plan."

## When to use

- Plan mode, or user asks for a plan/spec
- Multi-file or multi-module work
- Behavior that needs an explicit test strategy

## When NOT to use

- One-line / mechanical fixes
- Pure docs or constants with no behavior change
- Live IBKR ops / Gateway login (use ibkr-ops continuity, not a feature plan)

## Hard constraints (Nova)

- Do not plan `auto_live`, silent Alpaca price fallback, or orders outside `backend/ibkr/` + ADR 007.
- Prefer parent-session execution (zero-hop). Do **not** require subagent-per-task.
- Save plans under `docs/plans/YYYY-MM-DD-<feature>.md` (create `docs/plans/` if needed) unless the user names another path.
- Keep tasks small enough that each ends with an independently testable deliverable.

## Plan header (required)

```markdown
# [Feature] Implementation Plan

**Goal:** …
**Architecture:** …
**Tech stack:** …
**Nova constraints:** single IBKR feed | execution gates | modularity | file limits | no auto_live

## Global constraints
- …
```

## Task shape

For each task:

- **Files:** Create / Modify / Test with exact paths
- **Interfaces:** Consumes / Produces (names + types)
- Checkbox steps: failing test → run (must fail) → minimal impl → run (pass) → docs/logs if needed
- **Verify:** exact command

Assume the implementer has weak taste and little Nova context -- be explicit.

## After the plan

1. Ask the user to approve (or revise) before coding unless they already said "implement the plan."
2. On approval, implement in the parent session unless the user explicitly names a specialist.
3. Before claiming done: follow `verification-before-completion`.

## Related

- `.cursor/rules/engineering-methodology.mdc`
- Soft TDD in that rule
