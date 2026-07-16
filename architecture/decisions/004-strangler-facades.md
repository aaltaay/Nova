# ADR 004 — Strangler facades and compatibility barrels

**Status:** Accepted · **Date:** 2026-07-16

## Context

Call sites and tests import long-lived paths (`backend/constants.py`, `hod_momo.py`, `scan_runners.py`). Big-bang path rewrites mix risk with structural work.

## Decision

Use the **Strangler Facade** pattern:

1. Extract implementation to new modules.
2. Keep old path as a thin re-export / delegate.
3. Migrate callers opportunistically; remove facade when grep shows no remaining need.

Same for frontend `constants.ts` after domain splits (Phase 3).

## Consequences

- Each phase stays deployable and reversible.
- Facades must not accumulate logic.
- Every facade lists owner + removal criterion in the phase CHANGELOG or module docstring.

## Rejected alternatives

- Mass codemod of all imports in the same commit as the split
- Leaving god files as the permanent source of truth
