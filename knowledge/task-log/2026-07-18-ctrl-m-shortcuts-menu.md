# 2026-07-18 — Ctrl+M shortcuts cheat-sheet peek/pin

- **Status:** completed
- **Agents:** parent
- **Domain:** hotkeys
- **Related:** `CHANGELOG.md` §2026-07-18 Ctrl+M shortcuts cheat-sheet

## Task

Add a global shortcut to view all bound Nova keyboard shortcuts.

## Goal

Ctrl+M shows a menu of current bindings; double Ctrl+M pins it so release does not dismiss.

## Why it mattered

Users need a fast reference without opening Settings → Hotkeys.

## What we changed

- Peek/pin state machine + live catalog (Automation six + enabled Nova Actions)
- Overlay wired into `HotkeyDispatchProvider` (same dispatcher)
- Constants + CSS + continuity note

## How it works now

Ctrl+M → peek (keyup M/Ctrl closes). Second Ctrl+M within 450ms → pinned until Esc, Ctrl+M, or backdrop click.

## Why this approach

**Same dispatcher** avoids double-fire / competing listeners. **Peek vs pin** matches the user’s hold-vs-double-tap request. Catalog is derived from live bindings, not a static help page.

## Verification

- Vitest `src/hotkeys` (35 passed) including menu state/catalog
- Playwright probe when Vite up

## Follow-ups

- Optional: list disabled Nova Actions in a muted section

## Keywords

Ctrl+M, shortcuts menu, peek, pin, HotkeyDispatchProvider
