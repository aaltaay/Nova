# ADR 006 — ITCSS-inspired CSS + native cascade layers

**Status:** Accepted · **Date:** 2026-07-16

## Context

`frontend/src/index.css` is ~6168 lines. Tailwind may arrive incrementally but is not a prerequisite for removing the monolith.

## Decision

1. Mechanically split styles into shared `frontend/src/styles/` + feature-colocated CSS, preserving selectors and relative cascade order.
2. Make `index.css` an **import-only** entry (≤50 lines).
3. Adopt native `@layer` order: reset → tokens → base → layout → components → features → utilities → overrides.
4. Prefer feature-prefixed / BEM-style names for **new** selectors only; no mass rename during the split.

## Consequences

- Phase 2 is mechanical + visual verification only (no redesign).
- Domain stylesheets &lt;1000 lines (prefer &lt;700).
- Stock View viewport-lock regressions must be retested (see PROBLEM_LOG).

## Rejected alternatives

- Big-bang CSS Modules or styled-components migration
- Mandatory Tailwind install as the architecture
