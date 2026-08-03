# 2026-08-03 -- Level 2 multi-color price tiers

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / widgets (Trader View L2 skin)
- **Related:** `CHANGELOG.md` §2026-08-03 -- Level 2 multi-color price tiers

## Task

Turn on Webull-style multi-color Level 2 price levels (same price = same band, stepped shades, size heat bars).

## Goal

Trader View / Trading tab Level 2 montage shows obvious green/red price bands and size bars without a new feed or toggle.

## Why it mattered

The DAS tier path already existed but was too faint to read as "multi-color levels," so it looked like the feature was off.

## What we changed

- Saturated `L2_DAS_TIER_BID` / `L2_DAS_TIER_ASK` and brighter `L2_DAS_SIZE_BAR_*` in `chart_api.ts`
- Size bars grow from price toward MM in `DepthLadder.tsx`
- Neon size/price text classes in `marketData.css`

## How it works now

`assignPriceTiers` groups by price; `tierBackground` picks the next palette step; `sizeBarStyle` overlays a brighter same-hue bar by relative size. No feed changes -- pure UI.

## Why this approach

Kept the existing montage pipeline instead of a new component or settings flag. Rejected a true rainbow DAS palette because the reference screenshot is green/red shade steps. Rejected a feature toggle -- user asked to turn it on as the default look.

## Verification

`npx vitest run src/ibkr/dasDepthTiers.test.ts` -- 4 passed.

## Follow-ups

If bands still feel soft on a specific monitor, tune only the palette constants. Optional: aggregate MM rows per price client-side if IB ever sends one row per price only (tiers still step).

## Keywords

level 2, multi-color, DAS montage, price tiers, size bar, DepthLadder, Webull
