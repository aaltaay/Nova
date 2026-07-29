# 2026-07-29 — HOD multi-strategy pills stack vertically

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo / widgets (UI)
- **Related:** `CHANGELOG.md` §2026-07-29 -- HOD strategy pills stack · `PROBLEM_LOG.md` §2026-07-29 -- HOD multi-strategy pills clipped

## Task

Show multiple strategies for one ticker stacked under each other instead of clipped side-by-side.

## Goal

Full strategy names readable on multi-strategy collapsed rows without breaking table virtualization.

## Why it mattered

Collapsed-by-symbol rows often carry Squeeze 5% + 10% (or float + squeeze); horizontal pills made the second tag unreadable.

## What we changed

- CSS: column flex for `.hod-strategy-pills`; slightly wider strategy cell
- `hodMomoRowLayout.ts`: tag list, per-row height, prefix offsets
- Table virtualizer: `computeVisibleRowRangeFromOffsets`
- Constants: `HOD_MOMO_STRATEGY_PILL_LINE_PX`, max inline pills raised to 4

## How it works now

One strategy → 32px row. Each extra stacked pill adds 18px. Scroll math uses cumulative offsets so taller rows do not desync the window.

## Why this approach

Variable-height offsets keep virtualization correct; raising every row to fit N pills would waste space on the common single-strategy case. Rejected tooltip-only / "+N" without stacking -- user asked to see both names.

## Verification

Vitest: `hodMomoRowLayout.test.ts`, `HodMomoAlertTable.test.ts`, `HodMomoAlertTable.render.test.tsx` (12 tests).

## Follow-ups

Reload the HOD tab to pick up the CSS/JS change.

## Keywords

strategy pills, stack, virtualization, HOD Momo alert table
