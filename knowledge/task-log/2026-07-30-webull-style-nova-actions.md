# 2026-07-30 -- Webull-style Nova Actions (Buy 1 / Cancel All / long-only percent exits)

- **Status:** completed
- **Agents:** parent
- **Domain:** hotkeys / execution (System 2)
- **Related:** `CHANGELOG.md` §2026-07-30 Webull-style Nova Actions · plan `webull-style_nova_hotkeys`

## Task

Add Webull-like shortcuts: Buy 1 MKT, Cancel All stocks, long-only % sells at Ask / Bid-$0.03, with full confirm + audit, no shorts, whole shares, paper and live same path.

## Goal

Seven `nova-wb-*` defaults wired through typed Nova Actions; account-wide cancel; id-only profile merge; tests green.

## Why it mattered

User needs fast 1-share smoke tests and rapid long reduction without silent orders or accidental short opens while on live Gateway.

## What we changed

- Kinds: `buy_market`, `cancel_all_orders`, `sell_pos_pct_ask`, `sell_pos_pct_bid_offset`
- `buildLongExitPercent` / `buildBuyMarketShares`
- `DELETE /api/ibkr/orders?all_symbols=true`
- Confirm dialogs include PAPER|LIVE; Cancel All needs no open symbol
- `mergeMissingDefaultNovaActions` is id-only

## How it works now

Same `runNovaAction` → ADR 007 path for paper and live. Spend/Gateway gates differ by env. Long-% sells never set `short_entry` and refuse non-long books; backend OVERSELL/NO_POSITION remain backup.

## Why this approach

Rejected Webull-style skipped confirmations (user required visibility). Rejected reusing `exit_pos_pct` MKT for Ask/Bid (different fill semantics). Rejected kind-gated profile merge (would drop duplicate Ask % rows). Account-wide cancel mirrors symbol cancel orchestration (per-order execute) instead of a broker SDK bypass.

## Verification

- `npx vitest run src/hotkeys src/hooks/useHotkeys.test.ts src/components/SettingsWorkspace.test.tsx` -- 70 passed
- `pytest tests/test_trading_cancel_all.py` -- 5 passed

## Follow-ups

Paper Gateway script before live reliance. Quantity Settings $/% panel from Webull screenshot remains out of scope.

## Keywords

Nova Actions, buy_market, cancel_all_orders, sell_pos_pct_ask, long-only, Webull, Ctrl+1, ADR 007, ADR 009
