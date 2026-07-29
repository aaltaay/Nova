# 2026-07-29 -- Global single-row app header (Webull-style)

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / frontend shell (continuity-only; no specialist hop)
- **Related:** `CHANGELOG.md` §2026-07-29 -- Global single-row app header

## Task

Add a common Webull-style single-row header shared by the homepage (Scanner) and Trader View so every future live page inherits it automatically.

## Goal

One slim top row with brand, Scanner/Trader nav, and live account cluster (Day P&L, Net Liq, BP, Working) plus Paper/Live status; existing page headers remain as secondary rows.

## Why it mattered

Scanner and Trader each owned different chrome (`AppHeader` vs `StockViewHeader`), so account essentials only showed in Trader and new pages would not inherit a shared status strip.

## What we changed

- Mounted `IbkrAccountProvider` + `GlobalAppBar` once in `App.tsx` for all live branches (sample route stays isolated).
- Lifted the 5s account/positions/orders poll into shared context; `useIbkrAccount` became a thin consumer (sample fixtures unchanged).
- Added `GlobalAppBar`, `GlobalAccountCard`, `NovaLogo` extraction, `constantGroups/global_bar.ts`, and `styles/global-app-bar.css`.
- Left `AppHeader` / `StockViewHeader` in place as secondary rows per product choice.

## How it works now

Live `AppShell` always renders the global bar above `NovaOsAttentionStrip`, then either Dashboard or Trader tabs. The bar reads `useWorkspace()` for nav/mode and `useIbkrAccountContext()` for money/orders. Hover or click the account cluster opens a detail card. Narrow widths hide BP then Day P&L so the row never wraps.

## Why this approach

**Required.** Mounting in `AppShell` (not per-page) is the only way new pages get the bar for free without React Router. A shared account provider was chosen over a second poller so Scanner, Trader, and Account tab do not triple-hit IBKR. Keep-secondary avoided a risky big-bang delete of page chrome; dedupe can land later if the double Net Liq/BP feels noisy. Account-id / "Roth" label deferred because `/api/ibkr/account` does not ship managed account ids today.

## Verification

- `npx vitest run` on `globalBarMoney`, `GlobalAppBar`, `IbkrAccountContext`, plus related Stock View tests (25 passed).
- `npm run build` (tsc + vite) green.
- Browser on `http://localhost:5173/`: `[data-testid="global-app-bar"]` present with live Day P&L / Net Liq / BP / Working / Live chip.

## Follow-ups

- Slim duplicated Net Liq/BP from `StockViewHeader` if desired.
- Optional masked account-id in the bar once backend exposes managed account ids.
- Later: move search/settings/theme into the global row only if secondary headers are retired.

## Keywords

global app bar, Webull header, NetLiquidation, BuyingPower, Day P&L, IbkrAccountProvider, AppShell, Scanner Trader nav
