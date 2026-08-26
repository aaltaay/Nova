# 2026-08-25 — Nova Action Key, Edit, and guarded delete

- **Status:** completed
- **Agents:** parent
- **Domain:** hotkeys (Nova Actions / shortcuts menu)
- **Related:** `CHANGELOG.md` 2026-08-25 "Nova Action hotkeys gain edit/delete..." · commit `e9fc955` (feature) · commit `d5c3f41` (follow-up dispatch-timing fix)

## Task

Each Nova Action row in the shortcuts cheat-sheet only supported rebinding its trigger key. Add the ability to edit the action itself and to delete a Nova Action, without a deleted default action silently reappearing on the next load.

## Goal

A row's Key button still rebinds the trigger. A new Edit button opens `NovaActionEditor` to change the action's parameters. A guarded two-click delete (`ConfirmDeleteIconButton`) removes the row -- first click arms it, a second click within the arm window confirms -- and the deletion survives a reload even for a default (built-in) Nova Action.

## Why it mattered

Rebind-only meant a user who wanted a *different* action on a key, or wanted to remove one entirely, had no path except editing the hotkeys JSON by hand. `mergeMissingDefaultNovaActions` re-adding any default action missing from the profile (its whole point, so a fresh profile always has the built-ins) meant a naive delete would just come back on the next load unless the deletion itself was remembered.

## What we changed

- `frontend/src/hotkeys/hotkeyStorage.ts`: `HotkeyProfile` gains `removedNovaActionIds`; `mergeMissingDefaultNovaActions(existing, removedIds)` now skips ids in that set; new `deleteNovaActionFromProfile` / `upsertNovaActionInProfile` mutation helpers.
- `frontend/src/hotkeys/HotkeyDispatchContext.tsx`: new `editDraft`/`editError` state, `onEditAction`/`onDeleteAction`/`saveEditAction` handlers, conflict check via `novaActionConflictMessage` before saving an edit.
- `frontend/src/hotkeys/ShortcutsMenuRowActions.tsx` (new): extracts the per-row Key/Edit/delete button cluster out of `ShortcutsMenuOverlay`.
- `frontend/src/hotkeys/ConfirmDeleteIconButton.tsx` (new): arm-then-confirm delete button, `SHORTCUTS_MENU_DELETE_ARM_MS` (4s) window.
- `frontend/src/constantGroups/features.ts`: `SHORTCUTS_MENU_KEY_BTN` / `SHORTCUTS_MENU_ACTION_BTN` / `SHORTCUTS_MENU_DELETE_CONFIRM` / `SHORTCUTS_MENU_DELETE_ARM_MS`; updated peek/pinned hint copy to mention Edit and the delete's second-click requirement.
- `frontend/src/styles/shortcuts-menu.css` (new): rules extracted out of `settings-workspace.css` for the row action cluster and edit/delete affordances.
- Follow-up (commit `d5c3f41`): `useHotkeyProfile.ts`'s `resetProfile`/`setNovaActions`/`restoreNovaDefaults`/`deleteNovaAction` called `dispatch?.reloadNovaActions()` synchronously from inside a `setProfile` functional updater. New `syncDispatch()` defers it via `setTimeout(0)` so the dispatch call happens after React's render/commit, not during it.

## How it works now

Editing calls `onEditAction(id)`, which loads the existing record into `editDraft` and pins the menu open; saving runs `novaActionConflictMessage` against the draft first (same conflict check rebinding already used) and only commits via `upsertNovaActionInProfile` if clean. Deleting calls `deleteNovaActionFromProfile`, which both removes the row from `novaActions` and adds its id to `removedNovaActionIds` -- so the next `mergeMissingDefaultNovaActions` pass (which runs on every profile load to backfill any default action a user has never touched) explicitly skips ids in that removed set instead of only checking "is this id currently present."

## Why this approach

Storing the removal as an explicit id set (rather than, say, a boolean flag per action, or just trusting "absent from `novaActions`" to mean "user deleted it on purpose") is the only way to distinguish "user deleted this default action" from "this is a newer default that didn't exist in an old saved profile yet" -- both look identical as "missing from `novaActions`" without the extra list. The two-click arm-then-confirm delete (rather than a native `confirm()` dialog or immediate delete) matches the existing rebind-conflict UX pattern in this same menu (inline feedback, no browser-native modal breaking the pinned-menu flow) and needs no extra state beyond a timestamp.

## Verification

Full frontend suite (163 files / 739 tests passed, including updated `HotkeyManager.test.tsx`, `ShortcutsMenuOverlay.test.tsx`, `hotkeyStorage.merge.test.ts`, `shortcutsCatalog.test.ts`, `useHotkeyProfile.test.tsx`); `npm run build` clean. Hotkeys-scoped Vitest rerun (65 passed) after the `d5c3f41` dispatch-timing follow-up.

## Follow-ups

None known.

## Keywords

Nova Action, hotkeys, shortcuts menu, edit action, delete action, removedNovaActionIds, ConfirmDeleteIconButton, ShortcutsMenuRowActions, arm then confirm, ARM_MS, syncDispatch
