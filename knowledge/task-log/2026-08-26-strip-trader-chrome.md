# 2026-08-26 -- Strip duplicate Trader chrome

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / market-feed (Trader shell chrome)
- **Related:** `CHANGELOG.md` §2026-08-26 Strip duplicate Trader chrome · `deferred_log=none`

## Task

Remove the extra Trader bars the operator boxed: HOD Live/Clear/Configure, and the Paper/Live + Net Liq + BP + Manual/Normal/Fully Automated strip.

## Goal

Trader is a trading terminal. Account/mode controls exist once, on the global top bar. HOD dock stays on Scanner.

## Why it mattered

Those controls duplicated GlobalAppBar (Day P&L / Net Liq / BP / Paper-Live) and added a fake operator-mode capsule that could not be used (`auto_live` is NO-GO). The HOD dock on Trader stole vertical space above L2/T&S.

## What we changed

- Stopped mounting `HodMomoDock` in the live Trader slot (`App.tsx`) and sample Trader (`SampleShell.tsx`). `HodMomoProvider` stays so the HOD websocket survives the view switch.
- Slimmed `StockViewHeader` to brand, symbol chip, ET clock, disconnect warn, paper banner.
- Deleted `StockViewTradingChrome.tsx` (wrapper + unused Manual/Normal/Fully Automated capsule). Gateway switch tests now live next to `GatewayModeCapsule`.
- Dropped operator-mode constants. Paper/Live labels stay for the global capsule.

## How it works now

Scanner still has the HOD/roster dock (Live/Clear/Configure belong there). Trader shows Stock View only. Paper/Live is the Desk-cluster `GatewayModeCapsule` on GlobalAppBar. Net Liq / BP / Working stay in the global account cluster.

## Why this approach

**Keep the provider, drop the second UI.** Unmounting the dock from Trader without keeping `HodMomoProvider` would tear down the HOD websocket again (the 2026-07-29 reason the dock was copied onto Trader). Putting Paper/Live only on Stock View was already obsolete once GlobalAppBar shipped.

Rejected: hiding the dock when collapsed (still a Live/Clear/Configure strip). Rejected: keeping the fake mode capsule as "documentation" of future Manual/auto_live.

## Verification

- `npx vitest run` (`frontend/`) -- 171 files / 821 tests passed
- `npm run build` -- `tsc -b && vite build` exit 0
- Playwright on `http://127.0.0.1:5173/?view=sample&symbol=AAPL`: dock=0, no Paper/Live/Net Liq/Fully Automated on the Stock View header; symbol chip + clock still there. Sample Scanner (`?view=sample`) still shows the HOD dock.

## Follow-ups

None. Do not remount HOD dock on Trader unless the operator asks for alerts-while-trading.

## Keywords

Trader chrome, StockViewHeader, HodMomoDock, Paper Live, Fully Automated, GlobalAppBar duplicate
