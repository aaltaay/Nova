# ADR 011 -- Trader desk (extract and dock)

**Status:** Accepted · **Date:** 2026-08-17
**Builds on:** [[005-frontend-feature-slices]] · feed rule (Trader tabs / depth cap)
**Does not touch:** ADR 007 execution · `auto_live` · IBKR loop (ADR 010)

## Context

Trader View grew two one-way gestures, then a third operator request:

1. Default: a ticker click opens Trader in this window (`openStockView`).
2. Extract: `window.open` / Electron `BrowserWindow` + drop the tab here.
3. Scanner clicks must not stack extra tabs -- they replace the active tab. `+` remains the only in-window add.

There was no inverse. A popped-out window could only be closed. Session tab state lived in per-window `sessionStorage`, so windows could not agree on a move. `WorkspaceContext` was becoming the place every new windowing idea would get patched.

The operator needs Chrome-style docking: grab the ticker in the floated window and drop it back onto the other Nova window.

## Decision

1. **One desk, two roles.** Each OS window is a desk surface: `host` (no `?view=stock`, the scanner/app window) or `float` (extracted `?view=stock&symbol=`). Tabs still use the existing pure machine in `traderTabsState.ts`. The new module is `frontend/src/workspace/traderDesk/` -- protocol, bus, close policy -- not more branches in `App.tsx`.

2. **Extract and dock are inverse commands.**
   - Extract: open a float surface for symbol S, remove S from the source surface.
   - Dock: add S to the target surface, remove S from the source. If the source is a float and now empty, close that OS window. If the source is a host and now empty, return to the scanner (do not close the app).

3. **Scoped desk bus, not a product event bus.** Windows coordinate on `BroadcastChannel('nova.trader.desk')` plus a `localStorage` `storage` signal (`nova.trader.desk.bus`). Message types: `offer` / `offer-end` (drag highlight), `dock-request` (Dock control when there is no drop target), `tab-docked` (target accepted; source must give the tab up), `dock-reject` (host saw the request but could not take the tab -- usually at cap). This is not a cross-feature chat bus (ADR 005 / architecture README still forbid that). The storage signal is transport only -- tab strips stay per-window `sessionStorage`. Electron Pop out uses `new BrowserWindow`, which is a separate browsing-context group, so BroadcastChannel stays silent there; `storage` events still cross those windows.

4. **HTML5 drag is the spatial gesture.** A tab carries `application/x-nova-trader-tab` plus a `text/plain` fallback. Drop is unambiguous: the window that receives `drop` is the target. Same-window drops are ignored (no silent reorder in this ADR). Drag-off-empty-space does **not** extract -- extract stays Pop out / double-click.

5. **Electron geometry is an adapter, not a second model.** Native title-bar window moves do not fire HTML5 DnD. A future `traderWindows.mjs` adapter may translate "floated BrowserWindow released over the host" into the same `dock-request` / `tab-docked` messages. Do not invent a parallel Electron-only dock path in the renderer.

6. **Cap stays `TRADER_MAX_TABS` on the target.** If the target cannot take S, it does not publish `tab-docked` and the source stays put.

7. **Ticker click replaces the active tab; `+` adds; Pop out extracts.** `openStockView` calls `replaceActiveTab`, not `addTab`:
   - No Trader tab: create the first tab and show Trader.
   - Occupied active tab: replace that tab's symbol in place. Tab count does not change, so a click never burns a 4th L2 slot.
   - Symbol already open: activate that tab. Do not duplicate.
   - Draft active tab: commit the draft to the clicked symbol.
   - `+` / dock / drop still use `addTab` / `addDraftTab` and can hit the cap.
   - `Pop out` and **tab** double-click still extract. A scanner ticker double-click has no special action.

7a. **Row body vs ticker button is a spatial split, not click-vs-double-click (2026-08-26).** On tables that render a separate `SymbolSelectButton` (scanner tables, Catalysts, HOD Momo + Running Up, Watchlist, Signals), only the ticker opens Trader (`openStockView`). The row body calls `WorkspaceContext.selectRowSymbol`: on Scanner it only updates `selectedSymbol` (Quote Panel), leaving the operator on Scanner; while Trader is already showing (no Quote Panel to update) it falls through to `tryReplaceActive`, so a dock/roster row click there still switches the active tab. `SelectableTableRow`'s `openOnRowClick` prop (default `true`) keeps the old single-gesture behavior on tables with no ticker button (Positions, Working/Closed Orders, Journal, Executor, HOD debug) -- their row click still opens Trader directly. This does **not** reopen the temporal click-vs-double-click split rejected below; row and ticker are two different DOM elements clicked once, not one element clicked twice.

## Consequences

- Docking works in Vite/browser and in Electron with one protocol.
- `WorkspaceContext` stays a shell: it applies `replaceActiveTab` / `addTab` / `closeTab` and talks to the desk bus.
- A 4th live L2 symbol is still blocked on add/dock. Scanner clicks replace instead of adding, so they do not hit that cap.
- Dragging the OS title bar (not the tab) does not dock until the Electron adapter exists.

## Rejected alternatives

- A "Dock" button only (no drag) -- hides the spatial model the operator asked for. The button stays as the same `dock-request` command for accessibility.
- `window.opener` after extract -- we already null `opener` so popup blockers and Electron IPC stay honest.
- Shared `localStorage` tab list as SoT -- races, and a host + float must not share one strip.
- dnd-kit -- same-document only; docking is cross-window.
- Auto-dock when two BrowserWindows overlap -- false docks while arranging monitors. Geometry may later *emit* the desk command after an explicit release rule, not replace it.
- A repo-wide event bus for other features.
- Reusing `addTab` for an occupied active tab -- that stacked symbols on every scanner click.
- Delayed click-vs-double-click on ticker rows (Quote Panel first, Trader 280ms later) -- the second click had no special action, and the delay made Trader feel broken.

## Implementation map

| Piece | Path |
|-------|------|
| Replace vs add | `frontend/src/stock_view/traderTabsState.ts` (`replaceActiveTab` / `addTab`) |
| Open vs extract | `frontend/src/workspace/traderDesk/useTraderDeskBinding.ts` |
| Drag + message codec | `frontend/src/workspace/traderDesk/protocol.ts` |
| Role / close / claim | `frontend/src/workspace/traderDesk/commands.ts` |
| BroadcastChannel + localStorage signal | `frontend/src/workspace/traderDesk/bus.ts` |
| Overlay when the host is on the scanner | `TraderDockLayer.tsx` |
