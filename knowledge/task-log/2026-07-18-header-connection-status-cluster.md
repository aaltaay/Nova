# 2026-07-18 — Header connection status cluster (API / Gateway / Prices)

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed (UI honesty)
- **Related:** `CHANGELOG.md` §2026-07-18 Header connection status cluster · single-market-data-feed

## Task

Make the header status indicators coherent so “Connected” is not confused with IB Gateway / live prices.

## Goal

One labeled cluster: API health, Gateway (or Alpaca feed), and price freshness — each explained on hover.

## Why it mattered

Users saw a green “Connected” while Gateway was offline and prices were hours stale. That looked like a lie; it was three different signals sharing one ambiguous word.

## What we changed

- Added `HeaderConnectionStatus` chips: **API** / **Gateway|Feed** / **Prices**
- Wired `ibkrConnected` from workspace into `AppHeader` / `DashboardPage`
- Humanized age via `formatScanAge` (`59915s` → `16h ago`)
- Styles in `tokens-shell.css`; Vitest coverage for age + chip labeling

## How it works now

- **API** = local Nova `/api/health` (backend process). Label is `up`/`down`, never bare “Connected”.
- **Gateway** (discovery=ibkr) = `useIbkrStatus().connected`. Offline is a red chip with the IB login remediation tooltip.
- **Feed** (discovery=alpaca) = Alpaca IEX/SIP (+ fallback warn).
- **Prices** = age of last successful table price tick; stale uses warn tone.

## Why this approach

Kept three distinct chips instead of collapsing into one “overall status” — a single rollup would hide the exact failure mode again (API up + Gateway down is the common IBKR case). Rejected renaming only “Connected” → “API connected” without a Gateway chip: the chart already shouted Gateway, but the header still implied everything was fine.

## Verification

- `npm test -- --run src/utils/formatScanAge.test.ts src/components/HeaderConnectionStatus.test.tsx` (5 passed)
- Browser: header shows `API up · …ms`, `Gateway offline`, `Prices … ago` with distinct tones

## Follow-ups

- Optional: when Gateway offline + discovery=ibkr, force Prices chip to warn even if a residual timestamp looks “fresh”
- Commit/push when user requests (not done in this session per commit preference)

## Keywords

header, connection status, IB Gateway, API health, prices stale, UX honesty
