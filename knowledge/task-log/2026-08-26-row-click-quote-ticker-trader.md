# 2026-08-26 — Scanner row click updates Quote Panel; ticker opens Trader

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / frontend workspace
- **Related:** `CHANGELOG.md` § 2026-08-26 "Scanner row click only updates Quote Panel; ticker click opens Trader" · `architecture/decisions/011-trader-window-desk.md` §7a

## Task

Operator asked to split the scanner click gesture: clicking anywhere in a row body should only update the Quote Panel and keep the operator on Scanner. Only clicking the blue ticker text should open Trader. If the operator is already in Trader (no Quote Panel visible), a row click should switch the active tab instead of doing nothing useful.

## Goal

- Row body click on tables with a ticker button -> `setSelectedSymbol` only, no Trader jump, stay on Scanner.
- Blue ticker click -> unchanged, opens Trader / replaces the active tab (ADR 011).
- Row body click while Trader is already showing -> switch the active tab in place (there is no Quote Panel to update, so falling back to a no-op would be worse than matching the ticker behavior).
- Tables with no ticker button (Positions, Working/Closed Orders, Journal, Executor, HOD debug) keep their existing single-click-opens-Trader behavior — they have no other way into Trader.

## Why it mattered

Every scanner row click was yanking the operator into Trader View, which made it impossible to quickly scan rows for a quote check without losing the scanner table. The ticker was already the "intentional" click target (styled as a button, own hover copy); the row body duplicating that action was an unnecessary second trigger for the same outcome.

## What we changed

- `frontend/src/components/SelectableTableRow.tsx`: new `openOnRowClick` prop (default `true`, preserves old behavior for ticker-less tables). When `false`, row click/Enter/Space only calls `onSelect`; row `title` swaps to the new `ROW_SELECT_QUOTE_TITLE` copy.
- Set `openOnRowClick={false}` at the five call sites that also render `SymbolSelectButton`: `ScannerTable.tsx` (Gappers/Gainers/Losers/AH/Large Cap), `CatalystsTable.tsx`, `hod_momo/HodMomoAlertRow.tsx` (HOD Momo + Running Up), `strategy/WatchlistTab.tsx`, `strategy/SignalsPanel.tsx`.
- `frontend/src/workspace/traderDesk/useTraderDeskBinding.ts`: new `selectRowSymbol(symbol)` — `setSelectedSymbol` when `traderViewActive` is false, `tryReplaceActive(symbol)` (same path as a ticker click) when it is true. Exposed on `WorkspaceContext`.
- `pages/DashboardPage.tsx`: `ScannerTabPanels`/`TabModuleHost`'s `onSelect` now wired to `selectRowSymbol` instead of `setSelectedSymbol` (DashboardPage only mounts on Scanner, so this is a no-op change there today but keeps the contract uniform).
- `hod_momo/HodMomoDock.tsx`: same swap for both roster and alert table `onSelect` — this component is also mounted inside the Trader slot in `App.tsx`, so this is what makes a dock/roster row click while in Trader switch tabs instead of silently updating an invisible Quote Panel. Sample shell's fixture `onOpenTrading` override keeps plain `setSelectedSymbol` so fixtures never touch live trader tab state.
- `constantGroups/trader_view.ts`: `ROW_SELECT_QUOTE_TITLE` constant.
- Removed stale "Click: side panel. Double-click: full trading view." copy in `WatchlistTab.tsx` and `SignalsPanel.tsx` (ADR 011 already rejected that temporal model; the copy had never been updated).
- Docs: `.cursor/rules/single-market-data-feed.mdc` rule 3 and ADR 011 §7a document the row-vs-ticker split explicitly as spatial, not temporal, to prevent a future agent from "fixing" it back into a double-click model.

## How it works now

`SelectableTableRow.openRow()` gates the `onOpenTrading` call behind `openOnRowClick`. The `SymbolSelectButton` inside the row is unaffected — it always calls both `onSelect` and `onOpenTrading` with `stopPropagation` so the row handler doesn't also fire. `WorkspaceContext.selectRowSymbol` is the single decision point for "what does a bare row click do right now": it reads `traderViewActive` from the same trader desk binding that owns `openStockView`, so the branch and the open path share one source of truth. No new trader-tab logic was added — `selectRowSymbol` just calls the existing `tryReplaceActive` when appropriate.

## Why this approach

Considered making the row body a no-op while in Trader (do nothing) instead of switching tabs. Rejected: the operator explicitly said "it will just switch the focus entirely" when already in Trader, i.e. a row click should still be useful there — reusing `tryReplaceActive` (the same function the ticker already uses) means there's no second tab-switching implementation to keep in sync with ADR 011's cap/dedupe rules.

Considered adding `openOnRowClick={false}` as the new default and flipping it on for ticker-less tables instead. Rejected: that would touch 6+ call sites (Positions, Working/Closed Orders, Journal, Executor, HOD debug tables) for zero behavior change there, versus 5 call sites for an actual behavior change — smaller, more surgical diff the other way.

Considered a `stopPropagation`-based approach on the row where the ticker button already stops propagation and the row keeps calling both `onSelect` + `onOpenTrading` unconditionally, then suppressing `onOpenTrading` for a subset of tables via a wrapper function at each call site. Rejected: that duplicates the same "if" in 5 places instead of once inside `SelectableTableRow`, and loses the single-title-source behavior (row hover copy needs to match which mode it's in).

## Verification

- New `frontend/src/components/SelectableTableRow.test.tsx` (4 tests: default row click opens Trader, `openOnRowClick=false` row click/Enter only selects, hover copy differs).
- Extended `frontend/src/workspace/traderOpen.test.tsx` with 2 cases: `selectRowSymbol` on Scanner only sets `selectedSymbol`; `selectRowSymbol` while Trader is open switches `traderTabs`/`activeTraderSymbol` without adding a tab.
- `npm test -- --run`: 166 files / 767 tests passed (fresh run this session, includes `HodMomoDock.test.tsx`, `SampleDashboardPage.test.tsx`, `GlobalAppBar.test.tsx`, `WorkspaceContext.test.tsx`).
- `npm run build`: `tsc -b && vite build` exit 0.

## Follow-ups

- `strategy/ExecutorTables.tsx` still has stale click/double-click-style copy from before ADR 011; left untouched since its behavior (row-click-opens-Trader, no ticker button) did not change in this task — flag for the next agent that touches that file.
- Browser click-path verification (Gappers row -> Quote Panel repaints, stays on Scanner; ticker -> Trader opens; in-Trader dock row click -> tab switches) was not captured with a screenshot in this session; Vitest DOM-event coverage plus the build stood in for it given no dev server was already running.

## Keywords

scanner row click, quote panel, ticker click, trader view, ADR 011, selectRowSymbol, openOnRowClick, SelectableTableRow, SymbolSelectButton
