# ADR 006 — ITCSS-inspired CSS + native cascade layers + shadcn New York

**Status:** Accepted · **Date:** 2026-07-16 · **Updated:** 2026-07-16

## Context

`frontend/src/index.css` was a monolith; Tailwind arrived incrementally. A token collision (`--color-muted` as Tailwind background vs Time & Sales text) proved that domain CSS must not consume shadcn semantic color variables. Bare `form` / `label` / `input` / `button` / `header` selectors in feature sheets leaked into Stock View.

## Decision

1. **Canonical UI system:** [shadcn/ui New York](https://ui.shadcn.com) + Radix + Tailwind v4 (theme + utilities only; **no preflight**). Do not introduce Blueprint, Carbon, or a second component library.
2. **Nova tokens are source of truth.** Canonical `--nova-*` (and legacy `--bg-color` / `--text-*`) live in `:root`. Tailwind `@theme` in `styles/tailwind-theme.css` is a **one-way adapter** into `--color-*`. Domain/feature CSS must use `--nova-*` / `--text-*` / `--panel-bg` — never `--color-muted` for text.
3. **`index.css` is import-only** (≤50 lines). Layer order: reset → tokens → base → layout → components → features → utilities → overrides.
4. **Layer ownership:**
   - `tokens` — variables + Tailwind theme adapter
   - `base` — approved global element rules only (prefer none in feature sheets)
   - `layout` — app shell geometry
   - `components` — reusable primitives including `ibkr/marketData.css` (L2 + Time & Sales)
   - `features` — feature composition / density (e.g. Stock View rail)
   - `overrides` — empty by default
5. **Official shadcn recipes first:** `Button`, `Dialog` / `AlertDialog`, `InputOTP`, `ToggleGroup`, `Select`, `Tooltip`, `Badge`, `Separator`, `Table`, `ScrollArea`. Custom code is reserved for TradingView charts, L2 size bars, tape aggressor coloring, and live-feed / IBKR safety gates.
6. **Feature CSS must be scoped** (BEM / feature prefix). Bare `form`, `label`, `input`, `button`, `table`, `th`, `td`, `header` selectors are forbidden outside the base layer.

## Consequences

- Stock View L2/T&S skin is owned by `frontend/src/ibkr/marketData.css`.
- Maintainer checks reject bare feature selectors and `--color-muted` text usage outside the Tailwind adapter.
- Domain stylesheets &lt;1000 lines (prefer &lt;700).

## Rejected alternatives

- Big-bang CSS Modules or styled-components migration
- Competing design systems (Blueprint, Carbon)
- Treating Tailwind `--color-*` as the domain token namespace
