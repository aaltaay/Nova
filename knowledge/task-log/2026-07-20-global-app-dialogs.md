# 2026-07-20 — Global pretty app dialogs replace native popups

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / frontend UX
- **Related:** `CHANGELOG.md` § "Global pretty app dialogs" · `PROBLEM_LOG.md` § "Native browser confirm/alert popups" · Intentional Paper↔Live Gateway switch

## Task

After the Live Gateway switch showed a native “localhost:5173 says” confirm, replace **all** browser popups app-wide with proper in-app UX.

## Goal

No product path uses `window.confirm` / `window.alert` / `window.prompt` / bare `alert()`. One styled dialog system covers confirm, alert, and typed-token prompt (flatten).

## Why it mattered

Native dialogs break immersion in the dark trading UI, look like errors, and can’t carry danger/warning tone or Nova labels. Operators clicking Live (or Flatten / Stop Automation) should see Nova chrome, not the browser chrome.

## What we changed

- New `frontend/src/ux/`: imperative `confirmApp` / `alertApp` / `promptApp`, `AppDialogHost` (shadcn AlertDialog + queue), `appDialog.css` tones.
- Mounted `AppDialogHost` at the root of `App.tsx` so Stock View, Dashboard, and sample shell all share it.
- `constantGroups/ux.ts` for shared labels.
- Migrated every former native popup call site (gateway switch, flatten, fill now, automate ladder, executor, HOD settings/clear, blocklist, alert channels, settings save error, Nova Actions).
- Left `PlaceOrderConfirmDialog` as-is (already custom with skip-next-time).

## How it works now

Any module awaits `confirmApp({ title, message, tone, confirmLabel })`. The host registers a handler on mount; requests queue if a dialog is already open. `promptApp({ expectedValue })` disables Confirm until the input matches (Nova OS flatten token). Danger actions use red primary; Live switch / paper switch use danger/warning tones.

## Why this approach

Imperative promise API (not only React state in each parent) was required so pure helpers (`runNovaAction`, `confirmAndFillWorkingOrder`) can confirm without mounting their own dialog trees. Reused existing shadcn AlertDialog primitives instead of inventing a third modal stack. Rejected keeping `window.confirm` as a test fallback — tests mock `confirmApp` instead so CI never depends on native dialogs.

## Verification

- `npx vitest run src/ux/AppDialogHost.test.tsx` + capsule/header/flatten tests
- Full frontend suite: 399 passed
- Grep: no remaining `window.confirm|alert|prompt` in product `frontend/src` (only comments / test helpers named `alert`)

## Follow-ups

None required. Optional later: animate queue transitions; wire Electron to the same host if a second window mounts without `App`.

## Keywords

confirmApp, alertApp, promptApp, AppDialogHost, window.confirm, native popup, global UX, shadcn AlertDialog
