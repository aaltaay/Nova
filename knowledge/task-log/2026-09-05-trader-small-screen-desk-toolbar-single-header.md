# 2026-09-05 -- Trader small-screen overhaul: one desk toolbar, proportional MACD, single header row

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets (Trader layout) | frontend
- **Related:** `CHANGELOG.md` 2026-09-05 -- Trader small screens; `DEFERRED_LOG.md` D-005 (hit during verification, not changed)

## Task

On a large monitor Nova looked fine; on a ~1024-wide window the Trader charts "almost disappeared", MACD took most of a pane and could barely be dragged or minimized, every pane repeated the drawing toolbar, and the app header used three rows. The user pointed at Webull's grid (one toolbar above four charts) and asked for a solid overhaul, not a patch, including "combine that entire 3 rows into a single bar".

## Goal

At 1024x600 and 1366x720: one header row, one draw/indicator toolbar for the grid, each chart body gets real height, RSI/MACD sub-panes are proportional and closable, and nothing the operator relies on (tab strip, desk chip, Paper|Live capsule, Account/Settings) leaves the header.

## Why it mattered

Vertical budget on a laptop is the whole product for a chart-first desk. Three header rows (~110px) + four per-pane toolbars (~4x28px) + a fixed 120px oscillator per pane + a `min-height: 220px !important` on grid bodies left the actual candles a few pixels tall. Four identical toolbars were also a duplicate-code smell in the UI itself.

## What we changed

- `components/ChartGridToolbar.tsx` (new): single toolbar above the 2x2 grid; reuses `ChartToolbarControls` (extracted from `TickerChartControls`). Shows the focused pane's name as the indicator target and hosts the Show/Hide 10-Second toggle.
- `components/ChartGrid.tsx`: owns `activeTool`, `focusedPaneId`, `indicatorsByPane`; passes controlled props to every `TickerChart`; "Clear all" calls `clearDrawings(drawingsKey(symbol))` once. Hidden 10-Second pane cannot stay the focus target.
- `chart/TickerChart.tsx`: accepts controlled `indicators` / `activeTool`, `compactChrome`, `focused`, `onFocusPane`; oscillator area is `useResizableHeight` (percent of card, drag handle, localStorage key) instead of fixed px.
- `chart/useChartDrawingManager.ts`: controlled `activeTool` + `onActiveToolChange` (falls back to local state when uncontrolled).
- `components/TickerChartControls.tsx`: `compact` prop -> one header line, maximize in the header, no toolbar; a maximized compact pane gets its toolbar back.
- `components/TickerChartOscillatorPanes.tsx`: `onClose` x per sub-pane.
- `components/GlobalAppBar.tsx` + `components/globalBarSlots.ts` (new): middle column is `context | status`; context is the Trader tab-strip slot while `traderViewActive`, scanner controls otherwise. Slot element published through a `useSyncExternalStore` store.
- `stock_view/StockViewTabs.tsx`: `createPortal(tabStrip, headerSlot)` when a slot exists and Trader is showing; inline otherwise.
- CSS: `global-app-bar.css` (center/context/status, tab chips in the bar), `global-app-bar-responsive.css` (one-row contract down to 820px; ordered chip hides), `stock-view.css` (desk toolbar, compact header, nowrap title, removed 220px floor), `tickerChart.css` (oscillator close button).
- Tests: `ChartGrid.test.tsx` (desk toolbar, shared tool, focused-pane toggle, clear-all, focus fallback), `TickerChartControls.test.tsx` (compact / maximized), `GlobalAppBar.test.tsx` (slot registration), `StockViewTabs.test.tsx` (new; portal / inline / hidden Trader).

## How it works now

- Draw tools are shared: pick a tool once, click any pane, the line lands there. Drawings are still stored per symbol, so every pane shows the same set.
- Indicator toggles are per pane: the focused pane (thin accent ring, name shown in the toolbar) is the target. Click a chart to focus it.
- The header is one CSS grid row. Chips leave in a fixed order as the window narrows; nothing wraps to a second row until 820px.
- The tab strip is React-owned by `StockViewTabs` (state + handlers); the header only offers a DOM slot. No slot (detached window, tests) means the strip renders where it used to.

## Why this approach

- **Lift state, not the manager.** Each `useChartDrawingManager` still owns its `DrawingManager`; only `activeTool` became controllable. Rebuilding a cross-pane manager would have been a bigger, riskier change for the same visible result.
- **Focused-pane indicators instead of "apply to all".** Timeframes want different overlays (EMAs on 1m/5m, none on 10s). A global toggle would fight the per-timeframe defaults in `CHART_GRID_PANE_INDICATORS`.
- **Portal slot instead of moving tab state into the header.** `GlobalAppBar` would otherwise need every Trader tab handler (drag/drop, rename, extract, dock). A DOM slot keeps ownership where it is and degrades to inline rendering when the header is absent.
- **Hide chips, do not wrap.** The prior `@media (max-width: 1679px)` rule gave the scanner its own row, which is exactly the third row the user saw at 125% zoom. Hiding in priority order keeps the bar one row and keeps the desk chip + capsule always visible.
- **Fix the cascade-layer bug instead of `!important`.** `.header-symbol-search { display: flex }` lived in the `features` layer, so the `components`-layer container-query hide never won and the input got clipped. Moving the base rule to the header sheet fixes it in the right layer.
- **Rejected:** collapsing MACD to a fixed "mini" height (still not draggable); a fourth breakpoint that moves Account/Settings into a menu (not needed above 820px).

## Verification

- `npx tsc -p tsconfig.app.json --noEmit` clean.
- `npx vitest run`: 178 files, 870 tests pass.
- `npm run build` OK; ESLint clean on touched files.
- Headless Chromium (Playwright, temp script outside repo) at 1024x600 and 1366x720 against the dev server + local API: header `grid-template-rows` one row; tab strip inside `global-bar-trader-slot`; 1 desk toolbar, 0 per-pane toolbars, 4 compact headers; chart bodies 122/183/140/90 px at 1024 (previously ~0-70); "10-Second" title no longer wraps; symbol lookup shown at 1366, hidden at 1024 (Quote Panel still has one).
- During verification port 8000 had no listener while a `run_api.py` orphan held `api-instance.lock` and the IB socket -- D-005 exactly. Recovered per its Evidence (stop the orphan, start once); `/api/health` connected, `/api/ibkr/status` connected live.

## Follow-ups

- Trader rail width (`--ticker-trade-side-width`, ~350px at 1024) and the quote-loading spinner stealing grid height are untouched.
- Headless page showed "Desk offline" with `ERR_ABORTED` fetches right after the API restart (IB warm-up); the user's own live screenshot showed Desk up. Not a UI regression; watch on next cold start.

## Keywords

trader, chart grid, desk toolbar, MACD, RSI, oscillator, resizable, compact header, GlobalAppBar, single row, tab strip portal, globalBarSlots, responsive, 1024, cascade layers, container query
