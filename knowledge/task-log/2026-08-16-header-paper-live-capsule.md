# 2026-08-16 -- Header Paper | Live sliding capsule

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / ibkr-ops (UI chrome only)
- **Related:** `CHANGELOG.md` §2026-08-16 -- Header Paper | Live sliding capsule · `PROBLEM_LOG.md` n/a

## Task

Put a Paper | Live capsule in the global header, matching the API/Gateway chip family. Paper left and orange; Live right and green. The selected side is the one the capsule sits on.

## Goal

Operators can see and switch Gateway intent from the header without hunting Stock View, without a lone LIVE/PAPER word, and without arming live spend.

## Why it mattered

The header already answered "is Gateway up?" The leftover LIVE label answered "which money path?" as a static word. That looked like another status chip and was easy to miss. The switch already existed in Stock View; the header needed the same control in the place the operator looks first.

## What we changed

- Extracted `GatewayModeCapsule` as the shared Paper | Live control (confirm + `POST /api/ibkr/gateway-mode` + status refresh).
- Mounted it next to the Gateway chip in `HeaderConnectionStatus` (Scanner/Trader).
- Mounted it on the right of `GlobalAppBar` only when the scanner cluster is absent, so the capsule is never duplicated.
- Removed the old single-word `global-app-bar__mode` LIVE/PAPER label.
- Stock View `StockViewAccountModeCapsule` is now a thin wrapper around the same component.
- Sliding thumb CSS: left orange for paper, right green for live.

## How it works now

The capsule is intent, not truth. Clicking Live confirms, persists `IBKR_GATEWAY_MODE=live`, and reconnects to port 4001. It does not set `IBKR_LIVE_TRADING_CONFIRMED`. Canonical reality remains `/api/ibkr/status` (`mode`, `broker_account_kind`, listening port). One process, one `clientId`, one socket.

## Why this approach

A two-segment sliding capsule is the same control the user already knows from Stock View, just moved to the header and colored the way they asked (paper orange, live green). Rejected a second independent switch (would drift). Rejected a single colored LIVE/PAPER chip (not a left/right choice). Rejected auto-arming live spend on the Live click (ADR 007 / Invariant 7).

## Verification

- `npx vitest run src/components/HeaderConnectionStatus.test.tsx src/components/GlobalAppBar.test.tsx src/stock_view/StockViewTradingChrome.test.tsx src/stock_view/StockViewHeader.test.tsx` -- 28 passed
- `npx vitest run src/stock_view/stockViewTerminal.test.tsx` -- 12 passed
- `npm run build` -- first fail TS6133 unused `BACKEND_DIAG_FLAG_WEDGED`; after drop, `tsc -b && vite build` exit 0

## Follow-ups

Do not treat this capsule as a live-spend arm. Commit when asked.

## 2026-08-16 note -- Gateway chip no longer repeats mode

Operator asked to drop PAPER/LIVE from the Gateway chip now that the capsule owns the choice. Chip value is `up` / `delayed` / `offline` (plus launch states). Hover tooltip still names paper vs live. `status-chip--live` orange is no longer used for a connected live session.

## Keywords

header, capsule, paper, live, gateway-mode, orange, green, sliding toggle
