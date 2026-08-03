# 2026-08-03 -- Level 2 classic DAS rainbow price tiers

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / widgets (Trader View L2 skin)
- **Related:** `CHANGELOG.md` §2026-08-03 -- Level 2 classic DAS rainbow price tiers

## Task

Match classic DAS / montage multi-color Level 2: each distinct bid/ask price level gets a different hue (yellow, green, cyan, red, blue, …), same palette on both sides.

## Goal

Trader View Level 2 reads like the DAS screenshots -- rainbow price bands, not green-bids / red-asks fade.

## Why it mattered

The prior green/red shade punch-up was the wrong mental model. User clarified with DAS screenshots: hue cycles by price rank.

## What we changed

- `L2_DAS_TIER_COLORS` shared rainbow palette (bid/ask aliases deprecated)
- `tierBackground(tierIndex)` -- no side argument
- `DepthLadder` uses shared size-bar wash + `das-l2-row--tiered` dark ink
- Vitest covers shared palette wrap

## How it works now

`assignPriceTiers` advances on each new price. Tier N maps to `L2_DAS_TIER_COLORS[N % len]` for both bids and asks. MM rows at the same price share one band.

## Why this approach

Rejected Webull-style mono-hue fade after user screenshots. Kept one shared palette (true DAS) instead of separate bid/ask rainbows. White size wash works on every hue; dark text for contrast on bright bands.

## Verification

`npx vitest run src/ibkr/dasDepthTiers.test.ts`

## Follow-ups

Optional later: aggregated `# MM / SIZES` summary strip above the MM detail list (visible in one of the reference shots).

## Keywords

level 2, DAS, rainbow, multi-color, price tiers, DepthLadder, montage
