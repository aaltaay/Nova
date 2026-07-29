# 2026-07-28 -- Trader View unclickable (flex host chain)

- **Status:** completed
- **Agents:** parent
- **Domain:** frontend / Stock View
- **Related:** `CHANGELOG.md` §2026-07-28 -- Fix Trader View click-through · `PROBLEM_LOG.md` §2026-07-28 -- Trader View unclickable

## Task

User reported Trader View not working after Phase K / sample shortability work.

## Goal

Restore clickable Stock View (sample + live): Short toggle, L2, order ticket receive real pointer events.

## Why it mattered

Painted UI with dead clicks looks like a total Trader outage and blocked Phase K UI verification without force-click hacks.

## What we changed

- `AppErrorBoundary` remount wrapper: `className="app-shell-host"`.
- `stock-view.css`: flex-fill rules for `#root .app-shell-host` when ticker-detail shell is present.
- Unit test asserting the host class wraps healthy children.

## How it works now

Stock View locks the viewport via `body` / `#root` flex column. Nested error-boundary hosts must also be flex columns with `flex: 1 1 0` and `min-height: 0`, or the shell collapses while children paint outside the hit-test box.

## Why this approach

- **Chosen:** CSS flex-fill on a named host class -- keeps remount `key` behavior, one-line component change, scoped to ticker-detail.
- **Rejected:** Removing the boundary wrapper `<div>` (breaks remount via `key`); wrapping only Stock View in a special layout div (duplicates hosts already present); `pointer-events` hacks on `#root` (masks layout breakage).

## Verification

- Sample: pageH~896, railH~819, `elementFromPoint` -> BUTTON; normal Short click sets `aria-pressed=true`.
- Live AAPL Stock View: pageH~896, hit BUTTON.
- `npx vitest run src/components/AppErrorBoundary.test.tsx`
- `npx playwright test e2e/sample-shortability.spec.ts`

## Follow-ups

None required for click-through. Commit/push when user asks (working tree may include unrelated prior edits).

## Keywords

Trader View, Stock View, AppErrorBoundary, app-shell-host, flex collapse, unclickable
