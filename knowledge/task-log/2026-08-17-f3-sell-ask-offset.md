# 2026-08-17 -- Sell 1 at Ask+$0.05 (F5)

- **Status:** completed
- **Agents:** parent
- **Domain:** hotkeys
- **Related:** `CHANGELOG.md` §Sell Ask+$0.05 is F5, not F3 · F1/F2 desk pair same day

## Task

Add a 1-share sell limit at Ask + $0.05 (extended hours), same architecture as F1/F2.

## Goal

A typed Nova Action places SELL 1 LMT at L2 ask + $0.05 with EH.

## Why it mattered

F2 sells on the bid minus a nickel (more aggressive fill). The operator also wanted a sell sitting at the ask plus a nickel.

## What we changed

- New kind `sell_limit_ask_offset`.
- Default `nova-sell-ask` on F5 (was F3 same session), shares 1, +$0.05, `outsideRth`.
- Desk epoch bumped to `f1-f5-eh-2026-08-17` so existing local profiles get F5.

## How it works now

F1 buy Ask+$0.05, F2 sell Bid-$0.05, F5 sell Ask+$0.05 (was F3; rebound same session). All 1 share, EH, L2-only, confirm + PIN. Not flatten.

## Why this approach

New kind instead of overloading `sell_pos_pct_ask` (that sizes from position %). Same place helper as F1, just SELL at ask + offset.

## Verification

`npx vitest run src/hotkeys` -- 70 passed this turn.

## Follow-ups

Refresh the UI once so the new epoch applies.

## Keywords

F5, F3, sell_limit_ask_offset, Ask+0.05, nova-sell-ask
