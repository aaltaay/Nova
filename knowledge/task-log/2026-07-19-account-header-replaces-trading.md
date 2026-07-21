# 2026-07-19 — Account header replaces Trading tab

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / frontend
- **Related:** `CHANGELOG.md` §2026-07-19 Account header replaces Trading tab

## Task

Remove Trading’s Level 2 + Order Ticket, rename Trading → Account, put Account in the header next to Today (Live), and nest Reports under Account.

## Goal

Account is a header destination for balances, positions, orders, and habit reports — not a second order desk.

## Why it mattered

Duplicate L2/ticket competed with Trader; Trading as a scanner tab mixed execution UI with scanner workflow. Account belongs with Today (Live) as an ops/habits surface.

## What we changed

- Stripped DepthLadder + OrderTicket from `TradingTab`
- Registry: Account/Reports `showInTabNav: false`; title Account
- AppHeader Account button + Overview | Reports sections
- Reports rendered inside Account (not a top-level tab)
- CSS for single-column account layout + header button

## How it works now

Header **Account** → Overview (IBKR account tables) or **Reports**. Order entry remains on Trader (double-click). Internal tab ids stay `trading` / `reports`.

## Why this approach

Kept registry ids to avoid breaking visibility storage / scanAge / Modules toggles. Nested Reports as a section instead of a second header button so habits stay under one Account entry. Rejected deleting OrderTicket modules — still used by Trader rail.

## Verification

`npx tsc -b`; Vitest `registry.test.ts` (8); e2e baseline updated for header Account.

## Follow-ups

None required.

## Keywords

Account, Trading tab, Reports, AppHeader, Today (Live), OrderTicket, Level 2
