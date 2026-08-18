# 2026-08-17 -- F1 buy Ask+$0.05 / F2 sell Bid-$0.05

- **Status:** completed
- **Agents:** parent
- **Domain:** hotkeys
- **Related:** `CHANGELOG.md` §2026-08-17 -- F1 buy Ask+$0.05 / F2 sell Bid-$0.05 · Phase G3 Nova Actions

## Task

Give the desk F1 = buy 1 share at Ask + $0.05 with extended hours, and F2 = sell 1 share at Bid - $0.05, using the existing hotkey profile (localStorage), not a new database.

## Goal

Those two chords fire the existing typed Nova Actions on the open symbol, qty 1, EH always on.

## Why it mattered

The Ask+/Bid- actions already existed but were bound to Ctrl+Shift+B / Alt+Shift+S at 100 shares, and EH only followed the clock. The operator trades 1 share either way and wanted fat-finger F-keys.

## What we changed

- Default `nova-buy-ask` / `nova-sell-bid` to F1 / F2, shares 1, offset $0.05, `outsideRth: true`.
- Added `outsideRth` on Nova Action params and an Extended hours checkbox in Settings.
- One-time epoch rewrite so an older `nova.hotkeys.profile.v1` picks up F1/F2.
- Symbol chip no longer uses F2 to rename (Enter / double-click still do).

## How it works now

F1/F2 are System 2 Nova Actions: L2 top-of-book only, then `placeIbkrOrder` LMT with `outside_rth`. Confirm + PIN + spend gates still apply. SELL is 1 share, not flatten. Flat + F2 is still rejected by the short-entry gate unless you add a separate short action. `IBKR_FORCE_ONE_SHARE` still caps qty at 1.

## Why this approach

Reused `buy_limit_ask_offset` / `sell_limit_bid_offset` instead of a new kind or SQLite table. Merge-by-id would have left old chords in place, so a one-time epoch rewrite was required. Did not silently price off last trade (hotkeys continuity: L2 only).

## Verification

`npx vitest run src/hotkeys src/hooks/useHotkeys.test.ts src/settings/prefsBundle.test.ts` -- 71 passed. SettingsWorkspace 3 passed.

## Follow-ups

Needs a browser refresh so `loadProfile` applies the epoch. F1/F2 need Trader L2 on the selected symbol.

## Keywords

F1, F2, Ask+0.05, Bid-0.05, outsideRth, nova-buy-ask, nova-sell-bid, desk-ask-bid-epoch
