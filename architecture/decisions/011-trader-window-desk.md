# ADR 011 -- Trader desk (extract and dock)

**Status:** Accepted · **Date:** 2026-08-17
**Builds on:** [[005-frontend-feature-slices]] · feed rule (Trader tabs / depth cap)
**Does not touch:** ADR 007 execution · `auto_live` · IBKR loop (ADR 010)

## Context

Trader View grew two one-way gestures, then a third operator request:

1. Default: a ticker click opens Trader in this window (`openStockView`).
2. Extract: `window.open` / Electron `BrowserWindow` + drop the tab here.
3. Scanner clicks used to replace the active tab (2026-08-17). Amended 2026-09-17 (#201): ticker click adds or activates; live L2 stays capped at 3.

There was no inverse. A popped-out window could only be closed. Session tab state lived in per-window `sessionStorage`, so windows could not agree on a move. `WorkspaceContext` was becoming the place every new windowing idea would get patched.

The operator needs Chrome-style docking: grab the ticker in the floated window and drop it back onto the other Nova window.

## Decision

1. **One desk, two roles.** Each OS window is a desk surface: `host` (no `?view=stock`, the scanner/app window) or `float` (extracted `?view=stock&symbol=`). Tabs still use the existing pure machine in `traderTabsState.ts`. The new module is `frontend/src/workspace/traderDesk/` -- protocol, bus, close policy -- not more branches in `App.tsx`.

2. **Extract and dock are inverse commands.**
   - Extract: open a float surface for symbol S, remove S from the source surface.
   - Dock: add S to the target surface, remove S from the source. If the source is a float and now empty, close that OS window. If the source is a host and now empty, return to the scanner (do not close the app).

3. **Scoped desk bus, not a product event bus.** Windows coordinate on `BroadcastChannel('nova.trader.desk')` plus a `localStorage` `storage` signal (`nova.trader.desk.bus`). Message types: `offer` / `offer-end` (drag highlight), `dock-request` (Dock control when there is no drop target; optional `targetWindowId` = last-known host), `tab-docked` (target accepted; source must give the tab up), `dock-reject` (host saw the request but refused it). This is not a cross-feature chat bus (ADR 005 / architecture README still forbid that). The storage signal is transport only -- tab strips stay per-window `sessionStorage`. Electron Pop out uses `new BrowserWindow`, which is a separate browsing-context group, so BroadcastChannel stays silent there; `storage` events still cross those windows. `window.open` copies sessionStorage, so a float must remint `nova.trader.windowId` or the host treats dock-request as a self-message and the tab vanishes (#199).

4. **HTML5 drag is the spatial gesture.** A tab carries `application/x-nova-trader-tab` plus a `text/plain` fallback. Drop is unambiguous: the window that receives `drop` is the target. Same-window drops are ignored (no silent reorder in this ADR). Drag-off-empty-space does **not** extract -- extract stays Pop out / double-click.

5. **Electron geometry is an adapter, not a second model.** Native title-bar window moves do not fire HTML5 DnD. A future `traderWindows.mjs` adapter may translate "floated BrowserWindow released over the host" into the same `dock-request` / `tab-docked` messages. Do not invent a parallel Electron-only dock path in the renderer.

6. **Live cap is `TRADER_MAX_LIVE_TABS` (3), not strip length (amended 2026-09-17, #201).** The target always accepts a docked name. Extra symbols stay on the strip gray / suspended (no L2). A new live name evicts the least-recently-focused live tab. Extract of a gray tab also releases the host's oldest live slot so the float can take it.

7. **Ticker click adds or activates; never silent-replace (amended 2026-09-17, #201).** `openStockView` calls `addTab`:
   - No Trader tab: create the first tab and show Trader.
   - New symbol: append a tab, make it live, evict the oldest live tab if needed.
   - Symbol already open: activate that tab. Do not duplicate. A gray tab is promoted; another live tab is suspended.
   - Draft active tab: commit the draft to the clicked symbol.
   - `+` / dock / drop also use `addTab` / `addDraftTab` and never hard-block a 4th name.
   - `Pop out` and **tab** double-click still extract. A scanner ticker double-click has no special action.
   - Drop target = dock home. Dock button without a drop uses last-known host, with a clear error if none. Not `window.opener`.

7a. **Row body vs ticker button is a spatial split, not click-vs-double-click (2026-08-26; add-or-activate 2026-09-17).** On tables that render a separate `SymbolSelectButton` (scanner tables, Catalysts, HOD Momo + Running Up, Watchlist, Signals), only the ticker opens Trader (`openStockView`). The row body calls `WorkspaceContext.selectRowSymbol`: on Scanner it only updates `selectedSymbol` (Quote Panel); while Trader is already showing it adds or activates, same as a ticker click. `SelectableTableRow`'s `openOnRowClick` prop (default `true`) keeps the old single-gesture behavior on tables with no ticker button (Positions, Working/Closed Orders, Journal, Executor, HOD debug) -- their row click still opens Trader directly. This does **not** reopen the temporal click-vs-double-click split rejected below; row and ticker are two different DOM elements clicked once, not one element clicked twice.

7b. **Sim scrubbing preserves desk selection (2026-09-19).** Moving the Sim session clock refreshes replay charts/tape without calling `openStockView`, activating a tab, or reopening a closed replay ticker. Replay selection and the active Trader tab are separate state. Only an explicit replay ticker pick opens/activates that ticker through the existing workspace command. Regression: IMCC active with SIM1 closed must remain that way when a clock response still names SIM1.

## Consequences

- Docking works in Vite/browser and in Electron with one protocol.
- `WorkspaceContext` stays a shell: it applies `addTab` / `activateTab` / `closeTab` and talks to the desk bus.
- A 4th name is allowed on the strip. Only 3 tabs are live L2; extras are gray until clicked or until they become the newest live name.
- Dragging the OS title bar (not the tab) does not dock until the Electron adapter exists.

## Rejected alternatives

- A "Dock" button only (no drag) -- hides the spatial model the operator asked for. The button stays as the same `dock-request` command for accessibility.
- `window.opener` after extract -- we already null `opener` so popup blockers and Electron IPC stay honest.
- Shared `localStorage` tab list as SoT -- races, and a host + float must not share one strip.
- dnd-kit -- same-document only; docking is cross-window.
- Auto-dock when two BrowserWindows overlap -- false docks while arranging monitors. Geometry may later *emit* the desk command after an explicit release rule, not replace it.
- A repo-wide event bus for other features.
- Reusing `addTab` for every scanner click was rejected in 2026-08-17 (it stacked names). Ahmed locked the opposite on 2026-09-16 (#201): stack names, gray the overflow. Silent replace is what felt broken.
- Delayed click-vs-double-click on ticker rows (Quote Panel first, Trader 280ms later) -- the second click had no special action, and the delay made Trader feel broken.

## Implementation map

| Piece | Path |
|-------|------|
| Add vs live/gray | `frontend/src/stock_view/traderTabsState.ts` (`addTab` / `activateTab` / `promoteLive`) |
| Open vs extract | `frontend/src/workspace/traderDesk/useTraderDeskBinding.ts` |
| Drag + message codec | `frontend/src/workspace/traderDesk/protocol.ts` |
| Role / close / claim | `frontend/src/workspace/traderDesk/commands.ts` |
| BroadcastChannel + localStorage signal | `frontend/src/workspace/traderDesk/bus.ts` |
| Overlay when the host is on the scanner | `TraderDockLayer.tsx` |
