# 2026-07-20 — Paper Place CTA + hot banner

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / trading UI
- **Related:** `CHANGELOG.md` §2026-07-20 — Paper trading CTA + hot banner

## Task

Make paper mode unmistakable: orange **Place Paper order** CTA and a top hot banner when Gateway mode is paper.

## Goal

Operators cannot confuse paper Place with live Place by label or color alone.

## Why it mattered

Paper Gateway + paper_armed is safe, but a blue generic “Place an order” still reads like production.

## What we changed

- Constants: `TICKER_TRADE_PLACE_PAPER_ORDER_LABEL`, `PAPER_TRADING_BANNER_TEXT`
- `ManualOrderTicket` paper label + `manual-order-submit--paper` orange style
- `PaperTradingBanner` on Stock View header and Trading tab (paper only)
- Vitest coverage for banner + CTA

## How it works now

Both cues key off `IbkrMode === 'paper'` from IBKR status. Live/disconnected: blue “Place an order”, no banner.

## Why this approach

Mode-gated UI (not spend_status) matches the paper pin mental model. Shared banner component avoids Stock View vs Trading drift. Rejected always-orange Place (would scare live) and banner-only without CTA rename (easy to miss).

## Verification

`npx vitest run src/ibkr/ManualOrderTicket.paperLabel.test.tsx src/stock_view/StockViewHeader.test.tsx` — 6 passed.

## Follow-ups

None.

## Keywords

paper trading, Place Paper order, banner, ManualOrderTicket, IBKR mode
