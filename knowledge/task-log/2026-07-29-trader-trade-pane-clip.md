# 2026-07-29 -- Trader TRADE pane no longer clipped

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / trader view
- **Related:** `CHANGELOG.md` §2026-07-29 -- Trader TRADE pane · `PROBLEM_LOG.md` §2026-07-29 -- Trader TRADE widget clipped

## Task

Stop the Trader View TRADE ticket from being cut off at the bottom (Trading Hours unreachable).

## Goal

Full order ticket reachable: either enough height by default, or scroll inside the TRADE card without clipping.

## Why it mattered

Users cannot place/adjust orders if Trading Hours and submit controls are off-screen with no scroll.

## What we changed

- Depth pane: `flex: 0 0 pct` → shrinkable `flex: 1 1 pct`
- TRADE card: hard min-height 320px, `flex-shrink: 0`; body `overflow-y: auto`
- Default depth split 52% (was 72%); max 68%; storage key `.v2` resets stale localStorage

## How it works now

Trade stack still splits via the drag handle. When space is tight, L2/T&S shrink first; TRADE never goes below 320px and scrolls internally so Trading Hours stays reachable. Whole rail still scrolls as a last-resort tiny-viewport fallback.

## Why this approach

**Required.** Making depth never-shrink was the root bug -- fixing shrink + a real order min-height matches the flex model. Resetting the storage key is required because persisted 72–86% splits would leave users broken after a CSS-only fix. Rejected “always scroll the whole rail” as primary -- that hid L2 while dragging; local TRADE scroll keeps depth visible.

## Verification

- `npx vitest run src/stock_view/stockViewTerminal.test.tsx` (12 passed)
- Layout reviewed against prior Quote Panel overflow PROBLEM_LOG pattern

## Follow-ups

- Optional: remember split only when user explicitly drags (already does via v2 key)
- If 320px still feels short on some tickets, raise `STOCK_VIEW_ORDER_PANE_MIN_PX`

## Keywords

Trader View, TRADE clipped, Trading Hours, flex-shrink, depthOrderSplitPct, sv-open-card
