# 2026-07-18 — Rebind shortcuts on the go via TanStack recorder

- **Status:** completed
- **Agents:** parent
- **Domain:** hotkeys
- **Related:** `CHANGELOG.md` §2026-07-18 Rebind shortcuts on the go

## Task

Allow changing shortcuts from the Ctrl+M menu by double-click, using a library for capture + conflict detection.

## Goal

On-the-go rebinding for Automation / Nova Actions / menu chord without a second dispatcher or hand-rolled recorder.

## Why it mattered

Users want to rebind while trading, not only in Settings; duplicates must be caught reliably.

## What we changed

- Added `@tanstack/react-hotkeys` (`useHotkeyRecorder`, `parseHotkey` / `normalizeHotkey`)
- Double-click row → capture session; TanStack-normalized conflict messages
- Profile schema v3: `automationBindings`, `shortcutsMenuKey`
- Dispatcher uses effective bindings; pauses while recording

## How it works now

Pin or peek menu → double-click a row → press new chord → saved to local profile. Duplicate chords rejected. Esc cancels capture.

## Why this approach

**TanStack recorder for capture/normalize** instead of inventing CaptureKey again. **Keep Nova’s single dispatcher** for execution (continuity). Rejected: replacing the dispatcher with TanStack `useHotkey` (would fight Automation/Nova Action gates).

## Verification

- Vitest hotkeys suite 51 passed; `tsc -b` PASS

## Follow-ups

- Settings table could share the same conflict helper for Automation overrides UI

## Keywords

rebind, TanStack, useHotkeyRecorder, conflict, Ctrl+M, automationBindings
