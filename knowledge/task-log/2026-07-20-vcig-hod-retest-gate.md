# 2026-07-20 — VCIG late HOD fire: Running Up vs new-high gate

- **Status:** completed
- **Agents:** hod-momo
- **Domain:** hod-momo / market-feed (HOD truth)
- **Related:** `CHANGELOG.md` §2026-07-20 HOD fresh new high · `PROBLEM_LOG.md` §2026-07-20 VCIG late Squeeze

## Task

Explain Warrior Running Up vs HOD Momentum; diagnose why Nova fired VCIG at 08:24:14 when Warrior’s true HOD was ~08:02; say whether Nova implements Running Up; fix if root cause is clear.

## Goal

Correct HOD gate semantics (new high, not retest) and a clear user-facing answer on Running Up.

## Why it mattered

False HOD Squeeze alerts on pullback/retest confuse parity with Warrior and train the wrong trade idea (HOD break vs Running Up curl).

## What we changed

- `session_high_raised_ts` + `HOD_MOMO_NEW_HOD_GRACE_SEC` (60s)
- `fails_hod_gate` → `hod:not_new` / `hod:stale_new` when no fresh raise
- Initial bars/tick6 seed no longer opens the alert window
- Regression tests for retest vs observed raise

## How it works now

HOD Momentum strategies need a recent *raise* of session high while price stays near that high. Running Up (strategy 12) still skips HOD. Warrior’s separate Running Up widget is the research model for no-HOD surge alerts.

## Why this approach

- Rejected “keep at-HOD gate”: matches neither BA101 nor the VCIG tape.
- Rejected same-tick-only new HOD: Warrior KB allows momentum confirm within ~1 minute — grace window covers that.
- Rejected feeding Warrior rows into Nova: research-only constraint preserved.

## Verification

- Live: `backend/.cache/hod-momo-2026-07-20.json` VCIG Squeeze 10/11 @ 12:24:14Z / $1.34; `hod_momo.log` first VCIG 12:22:19Z `high_unseeded` then fire.
- `pytest` HOD high/filters/engine/persist/consolidation — 45 passed.

## Follow-ups

- Restart API to load gate.
- Optional: separate Running Up UI surface (Warrior sibling widget).
- Error 10089 delayed MD → late L1 admission (ibkr-ops / market-data subscription).

## Keywords

VCIG, Running Up, HOD Momentum, Squeeze, session_high_raised_ts, BA101, retest
