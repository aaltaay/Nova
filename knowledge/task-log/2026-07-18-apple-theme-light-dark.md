# 2026-07-18 — Apple-inspired light/dark appearance tokens

- **Status:** completed
- **Agents:** parent
- **Domain:** frontend / theme
- **Related:** `CHANGELOG.md` §2026-07-18 Apple-inspired light/dark

## Task

Redesign Nova’s look via theme tokens only — Apple HIG vibe — while keeping light and dark.

## Goal

Dual `data-theme` palettes, system fonts, calm shell chrome, header toggle; no layout/infra changes.

## Why it mattered

User wanted brand feel without rewriting Stock View / hotkeys / execution.

## What we changed

- Dark + light token blocks in `tokens-shell.css` (system blue accents, stacked grays)
- System font stack; quieter header (no hero image / purple glow)
- `themePrefs` + `ThemeToggle` + FOUC script in `index.html`
- Softened logo to accent `currentColor`

## How it works now

`localStorage['nova.theme']` = `light`|`dark` → `html[data-theme]` → CSS variables. Components already on tokens pick up both modes.

## Why this approach

**Token dual-scope over a second stylesheet or component rewrite** — one variable surface, Tailwind already maps to `--nova-*`. Rejected: OS `prefers-color-scheme` as sole source (user asked for explicit light + dark). Rejected: ripping feature CSS hex in one pass.

## Verification

- Vitest `src/theme/themePrefs.test.ts` — 5 passed

## Follow-ups

- Spot-replace hard-coded colors in scanner/ibkr CSS that ignore tokens

## Keywords

theme, light, dark, Apple HIG, tokens-shell, data-theme
