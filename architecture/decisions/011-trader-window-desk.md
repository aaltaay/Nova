# ADR 011 -- Trader desk (extract and dock)

**Status:** Accepted · **Date:** 2026-08-17
**Builds on:** [[005-frontend-feature-slices]] · feed rule (Trader tabs / depth cap)
**Does not touch:** ADR 007 execution · `auto_live` · IBKR loop (ADR 010)

## Context

Trader View grew two one-way gestures:

1. Default: add a tab in this window (`openStockView`).
2. Extract: `window.open` / Electron `BrowserWindow` + drop the tab here.

There was no inverse. A popped-out window could only be closed. Session tab state lived in per-window `sessionStorage`, so windows could not agree on a move. `WorkspaceContext` was becoming the place every new windowing idea would get patched.

The operator needs Chrome-style docking: grab the ticker in the floated window and drop it back onto the other Nova window.

## Decision

1. **One desk, two roles.** Each OS window is a desk surface: `host` (no `?view=stock`, the scanner/app window) or `float` (extracted `?view=stock&symbol=`). Tabs still use the existing pure machine in `traderTabsState.ts`. The new module is `frontend/src/workspace/traderDesk/` -- protocol, bus, close policy -- not more branches in `App.tsx`.

2. **Extract and dock are inverse commands.**
   - Extract: open a float surface for symbol S, remove S from the source surface.
   - Dock: add S to the target surface, remove S from the source. If the source is a float and now empty, close that OS window. If the source is a host and now empty, return to the scanner (do not close the app).

3. **Scoped desk bus, not a product event bus.** Windows coordinate on `BroadcastChannel('nova.trader.desk')` only. Message types: `offer` / `offer-end` (drag highlight), `dock-request` (Dock control when there is no drop target), `tab-docked` (target accepted; source must give the tab up), `dock-reject` (host saw the request but could not take the tab -- usually at cap). This is not a cross-feature chat bus (ADR 005 / architecture README still forbid that).

4. **HTML5 drag is the spatial gesture.** A tab carries `application/x-nova-trader-tab` plus a `text/plain` fallback. Drop is unambiguous: the window that receives `drop` is the target. Same-window drops are ignored (no silent reorder in this ADR). Drag-off-empty-space does **not** extract -- extract stays Pop out / double-click.

5. **Electron geometry is an adapter, not a second model.** Native title-bar window moves do not fire HTML5 DnD. A future `traderWindows.mjs` adapter may translate "floated BrowserWindow released over the host" into the same `dock-request` / `tab-docked` messages. Do not invent a parallel Electron-only dock path in the renderer.

6. **Cap stays `TRADER_MAX_TABS` on the target.** If the target cannot take S, it does not publish `tab-docked` and the source stays put.

## Consequences

- Docking works in Vite/browser and in Electron with one protocol.
- `WorkspaceContext` stays a shell: it applies `addTab` / `closeTab` and talks to the desk bus.
- A 4th live L2 symbol is still blocked on the receiving strip.
- Dragging the OS title bar (not the tab) does not dock until the Electron adapter exists.

## Rejected alternatives

- A "Dock" button only (no drag) -- hides the spatial model the operator asked for. The button stays as the same `dock-request` command for accessibility.
- `window.opener` after extract -- we already null `opener` so popup blockers and Electron IPC stay honest.
- Shared `localStorage` tab list as SoT -- races, and a host + float must not share one strip.
- dnd-kit -- same-document only; docking is cross-window.
- Auto-dock when two BrowserWindows overlap -- false docks while arranging monitors. Geometry may later *emit* the desk command after an explicit release rule, not replace it.
- A repo-wide event bus for other features.

## Implementation map

| Piece | Path |
|-------|------|
| Drag + message codec | `frontend/src/workspace/traderDesk/protocol.ts` |
| Role / close / claim | `frontend/src/workspace/traderDesk/commands.ts` |
| BroadcastChannel | `frontend/src/workspace/traderDesk/bus.ts` |
| Overlay when the host is on the scanner | `TraderDockLayer.tsx` |
