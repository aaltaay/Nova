# 2026-07-30 -- Hot Keys Webull-style Settings shell (landing + manager + create)

- **Status:** completed
- **Agents:** parent
- **Domain:** hotkeys
- **Related:** `CHANGELOG.md` §2026-07-30 Hot Keys Webull-style Settings shell

## Task

Reshape Settings → Hot Keys into a Webull-like three-window UX: landing, Hotkeys Settings manager, and Create a Customized Button -- using existing typed Nova Action kinds only.

## Goal

Users can open Hotkeys Settings, edit bindings in a master-detail pane, create new typed actions via `+`, and still reach DAS `.htk` import under Advanced -- without inventing Buy/Sell Market kinds that Nova cannot execute yet.

## Why it mattered

The old Hot Keys panel was a dense DAS + Nova Actions stack that did not match the mental model from Webull screenshots. Operators need a clear landing list and a dedicated editor before we invest in new order kinds.

## What we changed

- Landing (`HotkeyManager`): Trade/General/Paper/Chart tabs, subtitle, Hotkeys Settings CTA, summary list, Reset, Advanced DAS, Automation shortcuts strip.
- Manager (`HotkeysSettingsDialog` + `HotkeysSettingsDetail`): list + detail + Done/Reset; Escape closes manager.
- Create (`CreateCustomButtonDialog`): name / Stock / Buy|Sell / honest kind picker → appends typed `NovaActionRecord`.
- Shared helpers: `KeyCapture`, `novaActionConflict`, `novaActionFormat`, `createBlankNovaAction`.
- CSS under `settings-workspace.css`; Vitest coverage for CTA/escape/create/DAS advanced/conflicts.

## How it works now

Settings → Hot Keys is a landing page. **Hotkeys Settings** opens a modal master-detail editor over localStorage profile `nova.hotkeys.profile.v1`. `+` opens Create, which only offers kinds Nova already executes. DAS import stays collapsed under Advanced and still never auto-runs raw scripts. Non-Trade tabs show Coming soon.

## Why this approach

UI shell first, honest labels only -- rejected faking Webull Market rows because those kinds do not exist in the dispatcher. Kept DAS under Advanced so power users retain Map-to-Nova without cluttering the primary path. Persistence stayed on the existing profile hook (no new sync layer). Pass 2 can add Market/Stop kinds behind the same Create dialog without reshaping the shell again.

## Verification

`npx vitest run src/hotkeys` -- 12 files, 49 tests passed.

## Follow-ups

Pass 2: Buy/Sell Market (and similar) kinds + Paper/Chart tab content + TurboTrader grid (WID-015) if productized.

## Keywords

hotkeys, Webull, Hotkeys Settings, Create Customized Button, Nova Action, DAS, landing
