# 2026-07-29 — Stock Quote unified widget (stats + L2 + T&S)

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / trader UI (continuity: hotkeys not involved)
- **Related:** `CHANGELOG.md` §2026-07-29 -- Stock Quote is one widget · `PROBLEM_LOG.md` §2026-07-29 -- Stock Quote looked outside Level 2

## Task

Make Trader View Stock Quote read as one widget that contains quote stats, Level 2, and Time & Sales -- not a title bar floating above separate L2/T&S cards.

## Goal

One bordered Stock Quote module in the right rail; L2 and T&S are inner panes; TRADE remains below the splitter without becoming a header-only sliver.

## Why it mattered

User annotated STOCK QUOTE as visually outside Level 2. Hierarchy was wrong for a trading desk mental model (quote owns depth + tape).

## What we changed

- Removed standalone `StockViewQuoteCard` from `StockViewRail`.
- `StockViewDepthTape` now renders one `StockViewModuleCard` titled Stock Quote with `StockViewQuoteStats` + L2|T&S columns.
- Extracted `StockViewQuoteStats` for reuse (rail + standalone quote card tests).
- Split key `nova.stockView.depthOrderSplitPct.v3`, default depth 45%, max 58%, TRADE min-height 360px.
- CSS: `.sv-quote-depth-card` owns the stack; L2/T&S keep inner pane chrome only.

## How it works now

Rail stack = Stock Quote (stats + depth/tape) | horizontal resize | TRADE. Module visibility still can hide L2 and/or tape; the outer card title stays Stock Quote.

## Why this approach

**Required.** Alternatives rejected: (1) restyle-only so the old quote card hugged L2 -- still two module borders/titles; (2) rename the depth card to Stock Quote while keeping a separate stats card -- same dual-card bug; (3) nest L2/T&S as true `StockViewModuleCard` children -- triple chrome. One outer card + inner section panes matches Webull-style quote blocks and keeps the existing depth/trade splitter.

## Verification

`npx vitest run src/stock_view/stockViewTerminal.test.tsx` -- 12 passed.

## Follow-ups

Hard-refresh Trader View so localStorage picks up split key `.v3`. Do not mix with unrelated hotkeys WIP.

## Keywords

Stock Quote, Level 2, Time & Sales, StockViewDepthTape, StockViewRail, unified widget, depthOrderSplitPct.v3
