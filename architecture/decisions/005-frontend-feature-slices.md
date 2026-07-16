# ADR 005 — Frontend feature slices + workspace shell

**Status:** Accepted · **Date:** 2026-07-16

## Context

Nova already has `workspace/`, `hod_momo/`, `hotkeys/`, `ibkr/`, and thin `App.tsx`. Drift still places oversized components and root-level feature files.

## Decision

- **App / pages:** composition only.
- **Workspace:** selected symbol, layout registry, visibility — public contracts only.
- **Feature slices:** own UI, hooks, types, constants, tests, CSS.
- **Shared:** business-agnostic primitives and tokens.

Cross-feature coordination goes through workspace context, public feature barrels, or explicit events — never deep sibling imports.

## Consequences

- Phase 4–5 extractions land inside feature folders (`hotkeys/`, `hod_momo/`, `chart/`).
- Registry/plugin direction continues; avoid growing god-prop hosts.

## Rejected alternatives

- Full FSD rename of the entire `src/` tree in one phase
- New global event bus
