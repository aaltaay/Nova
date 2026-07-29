# 2026-07-29 -- Approaching HOD alert + side quote panel viewport fit

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo | widgets
- **Related:** `CHANGELOG.md` 2026-07-29 Approaching HOD

## Task

1. Fire an earlier heads-up when price re-touches the day's high after a pullback (not only on a fresh new-HOD breakout).
2. Fix the side quote panel so it fits the viewport without looking vertically stretched.

## Goal

Strategy 13 "Approaching HOD" with dip-reset re-arm at 0.5%; side panel shows chart + stats + Level 2 without empty scroll gap.

## Why it mattered

AMIX at 09:35 touched a prior HOD of 5.44 without firing strategy 10 (correct -- requires a *new* HOD). The user still wants attention on that re-approach. Separately, the side quote panel wasted vertical space (tall chart, single-col stats, empty bottom).

## What we changed

- New `backend/hod_momo_approach.py` latch + `approach_block_reason`.
- Strategy 13 in `constants_hod_momo.py` (schema v8); wired in `hod_momo_trade.py`.
- Frontend `STRATEGY_META` + `HOD_MOMO_APPROACH_STRATEGY_ID`.
- Side panel CSS: capped chart, 2-col stats, depth fills leftover height, overflow hidden.
- `CHART_HEIGHT_PANEL` 320 → 200.
- Tests: `test_hod_momo_approach.py` (A1–A9); replay phantom checks exclude Nova-only 13.

## How it works now

- **Arm:** price ≤ session_high × (1 − 0.005).
- **Fire:** seeded stale high (outside 60s new-HOD grace), price within HOD epsilon, latch armed → one alert, latch cleared.
- **Hover:** no re-fire until another 0.5% dip.
- **Breakout ticks:** blocked as `approach:fresh_new_hod` so strategy 10/11 own them.
- Latch is in-memory only (restart = not armed until next dip).
- Side panel is a bounded flex column; Level 2 flex-grows into remaining space.

## Why this approach

- Separate strategy 13 (not relaxing `requires_hod` on 10/11) preserves Warrior breakout parity.
- Dip-reset by percent (not cents or a fixed timer) scales across $0.50 and $6 names and matches the user's "one alert per genuine re-approach" ask.
- Viewport fit via CSS density + chart cap, not a layout reorder (LOCKED chart-on-top stays).

## Verification

- `pytest` approach/engine/models/persist + replay phantom tests green; full suite previously 1026 pass before replay fix; replay 2/2 pass after.
- Vitest hod_momo + tickerDetailComposition: 25 passed.

## Follow-ups

- Optional: persist approach latch across restart (currently intentional in-memory).
- Live watch: confirm Approaching HOD rows appear distinctly (amber `#FFC107`) on the next real re-test.

## Keywords

Approaching HOD, strategy 13, dip-reset, re-approach, session high, quote panel, viewport fit, CHART_HEIGHT_PANEL
