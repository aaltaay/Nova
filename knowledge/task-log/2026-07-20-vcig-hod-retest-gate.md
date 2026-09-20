# 2026-07-20 — VCIG late HOD fire: Running Up vs new-high gate

- **Status:** completed
- **Agents:** hod-momo
- **Domain:** hod-momo / market-feed (HOD truth)
- **Related:** `CHANGELOG.md` §2026-07-20 HOD fresh new high · `PROBLEM_LOG.md` §2026-07-20 VCIG late Squeeze

## Task



## Goal

Correct HOD gate semantics (new high, not retest) and a clear user-facing answer on Running Up.

## Why it mattered



## What we changed

- `session_high_raised_ts` + `HOD_MOMO_NEW_HOD_GRACE_SEC` (60s)
- `fails_hod_gate` → `hod:not_new` / `hod:stale_new` when no fresh raise
- Initial bars/tick6 seed no longer opens the alert window
- Regression tests for retest vs observed raise

## How it works now



## Why this approach



## Verification

- Live: `backend/.cache/hod-momo-2026-07-20.json` VCIG Squeeze 10/11 @ 12:24:14Z / $1.34; `hod_momo.log` first VCIG 12:22:19Z `high_unseeded` then fire.
- `pytest` HOD high/filters/engine/persist/consolidation — 45 passed.

## Follow-ups



## Keywords
