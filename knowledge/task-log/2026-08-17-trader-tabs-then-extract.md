# 2026-08-17 -- Trader tabs stay here; extract is opt-in

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / market-feed
- **Related:** `CHANGELOG.md` §2026-08-17 -- Trader tabs stay in this window · `PROBLEM_LOG.md` n/a

## Task

New symbols must open as tabs in the same window. A new OS window only when the operator extracts (Pop out or double-click), with that path visible.

## Goal

SPY + IPST can sit as two tabs in one window. Pop out / double-click moves one symbol to its own window.

## Why it mattered

Yesterday's multi-window work made every new symbol a popup. The `+` next to SPY opened IPST in a second Edge window. The operator still wants multi-monitor extract, just not as the default.

## What we changed

- `openStockView` adds/focuses a tab in this window (no `window.open`)
- `extractTraderTab` opens `nova-trader-SYMBOL` and removes the tab here
- Tab strip: Pop out button, double-click extract, hint "Double-click a tab to pop out"
- Detached `+` / rename no longer spawn another window
- Feed MDC: default in-app tabs; extract is explicit

## How it works now

`+` then type Enter = another tab here. Click a tab to view it. Double-click or Pop out = new window. 4th live symbol still blocked.

## Why this approach

Rejected keeping "always pop out" (that was the complaint). Rejected removing windows entirely (multi-monitor extract is still useful). Double-click used to edit the ticker; edit is now the `+` draft / type-in-tab flow so double-click can mean extract, which matches the operator's ask.

## Verification

`npx vitest run` on 6 files: 36 passed. Build in the same turn.

## Follow-ups

Restart Electron to pick up nothing in main.mjs (no main process change). Browser: allow popups only when extracting.

## Keywords

trader, tabs, extract, pop out, double-click, openStockView
