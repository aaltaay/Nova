# 2026-07-20 — Header Gateway shows PAPER vs LIVE; point Nova at live Gateway

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / widgets (header safety UX)
- **Related:** `CHANGELOG.md` §2026-07-20 Gateway PAPER/LIVE badge

## Task

Make the header Gateway chip show whether Nova is on paper or live IBKR, and attach Nova to the user's live Gateway session.

## Goal

Operators can never mistake a green "Gateway connected" for the wrong money path; Nova session mode matches the live Gateway they logged into.

## Why it mattered

Paper vs live is a serious safety signal. The UI only said "connected," while Nova stayed on paper port 4002 even after the user logged into a real-account Gateway on 4001. Empty gappers looked like "no market" instead of "wrong session / missing market-data entitlement."

## What we changed

- Header Gateway chip now shows `connected · PAPER` or `connected · LIVE` (LIVE uses a distinct orange chip tone).
- Wired `ibkrMode` / `ibkrGatewayMode` from `/api/ibkr/status` through Workspace → AppHeader → HeaderConnectionStatus.
- Local `.env` `IBKR_GATEWAY_MODE=live` + `/api/ibkr/reconnect` so Nova uses port 4001 (live). Spend remains `locked_live_unconfirmed` (`IBKR_LIVE_TRADING_CONFIRMED=false`).

## How it works now

Session `mode` from IBKR status drives the chip label. Configured `gateway_mode` is a fallback when disconnected. Live sessions get `status-chip--live` styling. Orders stay gated by existing spend flags even on live Gateway.

## Why this approach

- **Session mode over config-only:** Showing what Nova is actually attached to (`mode`) beats showing only the .env intent — that was the whole confusion.
- **Chip text, not a separate badge:** Keeps one Gateway signal; avoids another header control that can drift from connection state.
- **No auto paper→live heal:** Safety pin remains; user/ops must set `IBKR_GATEWAY_MODE=live` (done here explicitly).
- **Rejected:** Relying on Trading tab alone — the scanner header is where empty gappers are interpreted.

## Verification

- Vitest: `HeaderConnectionStatus.test.tsx`, `SampleDashboardPage.test.tsx`
- API: `GET /api/ibkr/status` → `connected=true`, `mode=live`, `gateway_mode=live`, `broker_account_kind=live`
- Note: gappers may still be empty until IB market-data Error 10089 entitlements are fixed on the live account

## Follow-ups

- Subscribe US equity API market data (or enable delayed) on the live IB account to clear Error 10089
- Optional: surface 10089 as a header warning when scanner symbols return but quotes fail

## Keywords

gateway, paper, live, IBKR_GATEWAY_MODE, header chip, 4001, 4002, Error 10089, spend_status
