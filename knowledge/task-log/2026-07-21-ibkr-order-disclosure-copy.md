# 2026-07-21 — Drop misleading paper-by-default from IBKR order disclosure

- **Status:** completed
- **Agents:** parent
- **Domain:** hotkeys / IBKR trading UI copy
- **Related:** `CHANGELOG.md` §2026-07-21 — Drop misleading "paper by default" from IBKR order disclosure

## Task

User saw Flatten confirm on a live position still say orders go through IBKR "(paper by default)" and asked whether that was accurate or stale copy.

## Goal

Remove the contradictory parenthetical so live flatten dialogs do not look like they silently route to paper.

## Why it mattered

On live, the static disclaimer sat above a correct "on the LIVE account?" line and could make an operator hesitate or distrust the confirmation at the moment they are about to flatten real shares.

## What we changed

- Reworded `TICKER_TRADE_ORDER_DISCLOSURE` in `frontend/src/constantGroups/chart_api.ts` to drop "(paper by default)".
- Call sites unchanged (`ClosePositionButton`, `TickerTradeActionBar`, `PlaceOrderConfirmDialog`) — they already import the constant and compose mode dynamically.

## How it works now

Disclosure always states: IBKR-only + Alpaca read-only. Actual paper vs live for the order comes from the dynamic `${mode.toUpperCase()} account` line and the header Live/Paper badge. Backend spend gates (`IBKR_ORDERS_ENABLED`, `IBKR_LIVE_TRADING_CONFIRMED`) are unchanged.

## Why this approach

- **Chose:** one constant string edit — the disclosure was never mode-aware; mode is already shown elsewhere in the same dialog.
- **Rejected:** mode-conditioned disclosure text — would duplicate the existing `mode.toUpperCase()` line and add more surface area for drift.
- **Rejected:** leaving the parenthetical as "system default posture" — accurate in the abstract, but misleading next to a live confirm.

## Verification

- Repo grep: no remaining "paper by default".
- Constant readback shows the new string.
- Callers still reference `TICKER_TRADE_ORDER_DISCLOSURE`.

## Follow-ups

None. Soft-reload the UI if Vite HMR did not pick up the constant.

## Keywords

IBKR, flatten, disclosure, paper by default, TICKER_TRADE_ORDER_DISCLOSURE, live account
