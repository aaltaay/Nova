# 2026-07-29 -- Shortcuts menu hold Ctrl+Alt popup

- **Status:** completed
- **Agents:** parent
- **Domain:** hotkeys
- **Related:** `CHANGELOG.md` §2026-07-29 -- Shortcuts menu opens on hold Ctrl+Alt

## Task

Hold-modifier shortcuts cheat-sheet; landed on **Ctrl+Alt** after Ctrl alone and Alt alone proved awkward. Listening must accept modifier-only chords (including Ctrl+Alt).

## Goal

Hold-Ctrl+Alt peek / release-to-close by default; Listening can bind Ctrl+Alt; works over focused inputs.

## Why it mattered

Ctrl+M felt like a toggle; bare Ctrl is used constantly; bare Alt fights browser chrome; TanStack cannot record modifier-only chords so Ctrl+Alt looked "broken" in Listening.

## What we changed

- Default `SHORTCUTS_MENU_BINDING` → `{ key: 'Alt', ctrl: true }`
- `eventMatchesModifierChord` + `bindingFromModifiers` for multi-modifier chords
- `bareModifierRecord` tracks a modifier *set* and emits on final keyup (fixes Ctrl+Alt Listening)
- Menu works over inputs; storage epoch clears stale overrides
- Playwright e2e for Ctrl+Alt

## How it works now

Menu opens when the Ctrl+Alt chord completes (either press order). Release either modifier to close peek. Rebind: TanStack for letter chords; `bareModifierRecord` for Alt / Ctrl+Alt / etc.

## Why this approach

Kept peek/pin state machine. Extended the parallel recorder instead of forking TanStack. Ctrl+Alt over bare Alt to avoid browser menu-bar theft while leaving Ctrl alone free for editing chords.

## Verification

Vitest hotkey suites + Playwright `e2e/shortcuts-menu-alt.spec.ts` (3 passed).

## Follow-ups

None.

## Keywords

shortcuts menu, Ctrl+Alt, Listening, bareModifierRecord, peek, SHORTCUTS_MENU_BINDING
