# 2026-07-29 -- Trader tabs + slim Quote Panel

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed | widgets (UI layout)
- **Related:** `CHANGELOG.md` §2026-07-29 -- Trader tabs · `PROBLEM_LOG.md` §Quote Panel could not scroll

## Task

User could not see the full chart / Time & Sales in the Quote Panel (no scroll). Proposed separating scanner browsing from trading: L2 + T&S only in Trader View, with up to N editable ticker tabs.

## Goal

Quote Panel scrolls and stays L1-only; Trader View holds max 3 live L2/T&S tabs (matching IBKR depth plan cap) with editable chips and a clear block when full.

## Why it mattered

Depth is the scarcest IBKR resource (hard cap 3). Mounting L2 on every scanner click wasted slots and crushed the sidebar layout. Trading needs lightning-fast multi-ticker switches without 16s tape resubscribe churn.

## What we changed

- Removed Quote Panel `DepthTapePanel`; panel body scrolls; chart height raised.
- Added pure `traderTabsState` + `TRADER_MAX_TABS=3`; `WorkspaceContext` owns tabs / block notice / sessionStorage.
- `StockViewTabs` + `StockViewTabStrip`: inactive panes stay mounted; shared `nova-trader` window name.
- Updated `single-market-data-feed.mdc` ownership (Quote = L1; Trader tabs = L2/T&S).

## How it works now

Click row → Quote Panel (quote, chart, fundamentals, news). Double-click → add/focus a Trader tab (detached window preferred). At 3 tabs, further opens show a banner; user closes or renames a tab. All open tabs keep WS depth/tape subscriptions hot while hidden.

## Why this approach

- **Tab cap = depth cap (3), not 5:** raising tabs above plan entitlement would thrash eviction or fail with IBKR errors; keep logic simple until the plan upgrades.
- **All tabs keep L2 live (not focused-only):** with max 3 = exact plan fill, focused-only pause adds complexity without freeing slots for a 4th.
- **Editable tabs over silent LRU eviction:** never drop a live book while the user is trading; block + rename is the escape hatch.
- **Reject leaving L2 in Quote Panel with scroll-only fix:** would still burn depth on browse; scroll alone does not fix the resource model.

## Verification

- `npm run test -- --run` (498 passed)
- `npm run build` (tsc + vite green)
- Unit: `traderTabsState.test.ts`, `StockViewTabStrip.test.tsx`, updated nav/composition/wiring mocks

## Follow-ups

- Live browser pass: Quote Panel scroll; open 3 tabs; 4th banner; rename/close.
- If IBKR depth entitlement grows, raise `TRADER_MAX_TABS` and `IBKR_MAX_DEPTH_SYMBOLS` together.

## Keywords

Trader tabs, Quote Panel, Level 2, Time & Sales, IBKR_MAX_DEPTH_SYMBOLS, scroll, StockViewTabs, TRADER_MAX_TABS
