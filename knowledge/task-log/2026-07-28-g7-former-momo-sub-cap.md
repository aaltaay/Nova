# 2026-07-28 -- G7: Former Momo sub-cap (20 slots)

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo
- **Related:** `CHANGELOG.md` § G7 · `PROBLEM_LOG.md` § G7 · audit G7

## Task

Cap Former Momo priority admits at 20 so live Gappers/Gainers/Afterhours keep half the 40-slot HOD pool.

## Goal

25 former + 30 live movers -> 20 former + 20 live; excess former uncovered as `former_momo_over_cap`; admin rejects lists longer than 20.

## Why it mattered

A bloated Former Momo list (hundreds of symbols) could fill all 40 slots and starve live movers on the busiest days.

## What we changed

- `HOD_MOMO_FORMER_MOMO_MAX_SLOTS = 20`
- `build_active_set` caps priority admits; over-cap reason tracked
- Admin validation uses the sub-cap

## How it works now

Former Momo still admits first, but only up to 20. Remaining capacity is round-robin live tables.

## Why this approach

User-approved half-pool policy (20). Soft uncover + hard admin reject -- runtime never silently drops without a reason, and UI cannot save a list that would guarantee starvation.

## Verification

`pytest tests/test_hod_momo_active.py tests/test_hod_momo_former.py` -- 16 passed.

## Follow-ups

Phase 8 audit doc remediation section + full suite.

## Keywords

G7, Former Momo, sub-cap, former_momo_over_cap, HOD_MOMO_FORMER_MOMO_MAX_SLOTS
