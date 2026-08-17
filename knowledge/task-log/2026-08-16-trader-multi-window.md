# 2026-08-16 -- Three Trader windows, one symbol each

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / market-feed
- **Related:** `CHANGELOG.md` §2026-08-16 -- Three Trader windows · `PROBLEM_LOG.md` n/a

## Task

Operator wants up to three Trader windows, one symbol per window, parked on different screens.

## Goal

SPY, QQQ, and IWM can each own an OS window. A fourth live symbol is blocked. Same symbol focuses the existing window.

## Why it mattered

`window.open(..., 'nova-trader')` reused one window. Electron also spawned unbounded untitled children with no display placement. The depth plan already allowed 3 live L2 symbols; the windowing model did not.

## What we changed

- Per-symbol window names (`nova-trader-SPY`)
- Electron registry: reuse / cap 3 / place on the Nth display
- Detached hydrate is that URL symbol only (shared sessionStorage is the cap registry, not this window's tab strip)
- Always try a detached window first; in-app tabs only if popup is blocked
- Detached `+` commits open another window
- Closing a detached window releases its registry slot

## How it works now

Cap = `TRADER_MAX_TABS` = 3 L2 streams. Prefer one window per monitor; if you have fewer monitors than windows, extras cascade on the last display. Browser cannot assign monitors -- drag the popups. Electron can.

## Why this approach

Rejected keeping one window with three tabs (cannot sit on three screens). Rejected a hard "one window per monitor" refuse (one monitor would lock you to one symbol). Rejected opening all three indexes at once (user picks). Shared tab strip in every window was rejected -- it would show SPY+QQQ+IWM in each popup and double-bind L2.

## Verification

- `npx vitest run src/utils/stockViewNav.test.ts src/utils/traderWindowBounds.test.ts src/workspace/WorkspaceContext.test.tsx src/components/GlobalAppBar.test.tsx src/stock_view/StockViewTabStrip.test.tsx` -- 5 files, 23 passed
- `npm run build` -- tsc + vite exit 0

## Follow-ups

Desktop must be restarted to pick up `electron/main.mjs`. Browser: allow popups for localhost. Commit when asked.

## Keywords

trader, multi-window, per-monitor, Level 2 cap, nova-trader-SPY, Electron
