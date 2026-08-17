# 2026-08-17 -- Trader desk: drag a popped-out tab back in

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets
- **Related:** `CHANGELOG.md` §2026-08-17 -- Trader desk · ADR 011 · `PROBLEM_LOG.md` n/a

## Task

After extract, press-and-drag the popped-out ticker back into the original window. Do it as architecture, not a patch.

## Goal

Extract and dock are inverse commands on one desk protocol. Chrome-style: grab the tab, drop it on the other Nova window, the float closes.

## Why it mattered

Yesterday's extract was one-way. A second special-case button would have made the next windowing ask another patch on `WorkspaceContext`.

## What we changed

- ADR 011: host vs float surfaces, scoped `BroadcastChannel`, HTML5 drag as the spatial gesture, Electron geometry as a future adapter only.
- `frontend/src/workspace/traderDesk/`: protocol, commands, bus, session storage, desk hook, binding hook, scanner drop overlay.
- Tab chips are draggable. Float windows also get a Dock control that emits the same `dock-request`.
- `WorkspaceContext` stays a shell.

## How it works now

1. Pop out / double-click still extracts (opens `?view=stock&symbol=`).
2. Drag that tab onto the main Nova window (trader strip, trader body, or scanner). The target `addTab`s; the source hears `tab-docked` and closes if it is an empty float.
3. Dock on a float asks any host via the bus. Cap still blocks a 4th live L2 symbol (`dock-reject`).

## Why this approach

Rejected a Dock-only button (hides the spatial ask). Rejected `window.opener` (we null it). Rejected a shared `localStorage` tab list (host and float must not share one strip). Rejected dnd-kit (same-document only). Rejected auto-dock when two BrowserWindows overlap (false docks while arranging monitors). Title-bar drags still do not dock -- that needs an Electron adapter that emits the same messages, not a second model.

## Verification

`npx vitest run` on `src/workspace/traderDesk`, `traderOpen.test.tsx`, `StockViewTabStrip.test.tsx`, `WorkspaceContext.test.tsx`, `GlobalAppBar.test.tsx`, `workspaceWiring.test.ts` -- 32 passed.

## Follow-ups

Electron: optional `moved`/release adapter in `traderWindows.mjs` that publishes `dock-request`. Global live-symbol registry across windows (cap is still per strip today).

## Keywords

trader, dock, extract, BroadcastChannel, ADR 011, HTML5 drag
