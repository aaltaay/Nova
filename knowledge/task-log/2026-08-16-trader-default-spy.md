# 2026-08-16 -- Trader opens SPY when no symbol is selected

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / market-feed (header chrome)
- **Related:** `CHANGELOG.md` §2026-08-16 -- Trader opens SPY when no symbol is selected · `PROBLEM_LOG.md` n/a

## Task

Trader was disabled with no selected symbol. Operator wanted a popular default (S&P 500) so the capsule is always usable.

## Goal

Clicking Trader always opens Trader View. Empty selection opens SPY. A selected symbol still wins.

## Why it mattered

Market-closed empty Gappers made Trader look broken. The gate was intentional (Trader is per-symbol L2 + tape) but the empty state had no way in.

## What we changed

- `TRADER_DEFAULT_SYMBOL = 'SPY'` in `trader_view.ts`
- `GlobalAppBar` always enables Trader and calls `openStockView(selected || SPY)`
- Replaced the "disabled when empty" test with an open-SPY test

## How it works now

Trader View still needs a symbol. The default supplies one. One tab only -- not SPY+QQQ+IWM -- so we do not spend the 3-tab Level 2 cap on a blank click.

## Why this approach

SPY is the liquid S&P 500 proxy IBKR can stream. Rejected opening a basket of popular names (burns all depth slots). Rejected an empty Trader desk (L2/tape have nothing to bind). Rejected keeping the disable gate (operator already hit it).

## Verification

- `npx vitest run src/components/GlobalAppBar.test.tsx` -- default-symbol case plus existing suite
- `npm run build`

## Follow-ups

Commit when asked.

## 2026-08-16 note -- QQQ and IWM as pickable defaults

Chevron next to Trader lists SPY / QQQ / IWM. One pick = one tab. Rejected opening all three (burns the Level 2 cap).

## Keywords

trader, SPY, default symbol, GlobalAppBar, Level 2 cap
