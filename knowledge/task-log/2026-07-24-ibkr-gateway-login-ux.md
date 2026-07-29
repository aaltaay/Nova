# 2026-07-24 — Loud IB Gateway disconnected banner + reconnect warm-up empty state

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / ibkr UX
- **Related:** `CHANGELOG.md` § 2026-07-24 — Loud IB Gateway login banner + reconnect warm-up · `PROBLEM_LOG.md` § 2026-07-24 — Gateway offline looked like empty scanners

## Task

When IB Gateway was offline, Nova never showed a loud “log in” prompt; after reconnect, empty Gainers/Losers still looked like “no market activity.” Implement a global disconnected banner plus a bounded reconnect warm-up empty state.

## Goal

Operators cannot miss a Gateway login blocker, and a reconnect-in-progress empty table never reads as a quiet market.

## Why it mattered

Discovery is IBKR-only. An offline Gateway produces empty scanners that look identical to “no gaps/gainers,” which is exactly the failure mode `ibkr-gateway-login-warning.mdc` forbids agents from treating as market conditions — but the product UI itself was still quiet.

## What we changed

- Added `GatewayDisconnectedBanner` mounted above `TabNav` in `DashboardPage` (all scanner tabs).
- Added `useIbkrReconnectWarmup` + warm-up copy in `EmptyState` for Gainers/Losers (`context === 'market'`).
- Feature-local tunables in `ibkr/gatewayUxConstants.ts` (kept `market_ui.ts` at prior size).
- Banner/CTA styles in `styles/scanner-l2.css`; Vitest coverage for banner + hook.

## How it works now

While `discoveryProvider === 'ibkr'` and `ibkrConnected` is false, a non-dismissible red banner shows mode-aware login copy plus an **Open IB Gateway** button (`launchIbGateway`). After a false→true connect transition, empty Gainers/Losers show reconnect warm-up copy for `IBKR_RECONNECT_WARMUP_SEC` (45s), then fall back to the generic empty message.

## Why this approach

- **Rejected:** Only improving the header chip tooltip — still too easy to miss beside Integrity fail.
- **Rejected:** Folding Gateway-down into `HodMomoIntegrityBanner` — that banner is HOD-scope; mixing login blockers with surge/tick checks would muddy both.
- **Rejected:** Growing `market_ui.ts` further — it was already over the 400-line TS floor (480); feature-local `gatewayUxConstants.ts` matches centralized-constants “feature folders may own feature-only constants.”
- **Chose** client-side warm-up window over a backend “roster warming” flag — no new polling or scanner_stream coupling; ADR 008 resubscribe is already the slow path we need to cover.

## Verification

- Focused Vitest: banner + warm-up hook (7 passed); full frontend suite earlier 465 passed; ESLint clean on touched files; `npm run build` passed.
- Maintainer: no new FILE_SIZE findings from this work’s new modules; `market_ui.ts` unchanged vs HEAD.
- Browser: with Gateway connected LIVE, `[data-testid="gateway-disconnected-banner"]` absent (correct hide path). Disconnected/CTA path covered by unit tests.

## Follow-ups

- Optional: browser mock of `/api/ibkr/status` connected=false for a headed visual of the banner (unit tests already assert render + CTA).
- Pre-existing `market_ui.ts` over-limit remains debt unrelated to this change.

## Keywords

IB Gateway, disconnected banner, reconnect warm-up, EmptyState, launchIbGateway, ADR 008, ibkr-gateway-login-warning
