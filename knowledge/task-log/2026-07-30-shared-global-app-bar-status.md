# 2026-07-30 -- Shared GlobalAppBar status strip on Scanner and Trader

- **Status:** completed
- **Agents:** parent
- **Domain:** frontend / workspace shell
- **Related:** `CHANGELOG.md` §2026-07-30 Shared GlobalAppBar · `PROBLEM_LOG.md` §2026-07-30 Shared header status strip missing on Trader

## Task

Make Scanner and Trader use one shared global header (status chips, Sample, history, lookup) instead of a thin Trader-only bar.

## Goal

One `GlobalAppBar` status strip that stays published when switching Scanner ↔ Trader.

## Why it mattered

User expected a single source of truth. Trader looked like a different product chrome because the middle strip vanished.

## What we changed

- Added `GlobalBarStatusBridge` in AppShell (always-on `/mode` + history + IBKR chips).
- Simplified `scannerBarStore`: merge patches; never clear whole bar on route leave.
- Slimmed `ScannerBarBridge` to freshness + history sync only.
- Dashboard "Back to Live" clears shared history via `setGlobalBarHistoryDate`.

## How it works now

`GlobalAppBar` reads `useScannerBarProps()`. AppShell bridge publishes core status. Dashboard only patches `secondsAgo` / `pricesStale`. Leaving Scanner does not null the store.

## Why this approach

Rejected mounting a second header in Trader (duplicates SSOT). Rejected keeping publish inside Dashboard (unmount clears). AppShell ownership matches account cluster already living above both views. Freshness stays Scanner-only because Trader has no active scanner table SLA.

## Verification

`npx vitest run src/components/scannerBarStore.test.ts src/components/GlobalAppBar.test.tsx` (11 passed).

## Follow-ups

Hard-refresh UI after pull. Optional: stop dual `history/dates` fetch in `useScannerData` later (harmless).

## Keywords

GlobalAppBar, GlobalBarStatusBridge, scannerBarStore, Trader, Scanner, shared header
