# 2026-07-28 -- G9: persist session_high_raised_ts grace clock

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo
- **Related:** `CHANGELOG.md` § Persist session_high_raised_ts · `PROBLEM_LOG.md` § session_high_raised_ts lost · audit G9

## Task

Persist the new-HOD grace clock (`session_high_raised_ts`) across API restarts.

## Goal

Save/load round-trip restores raised timestamps; restart does not force `hod:not_new` for already-elevated symbols.

## Why it mattered

Highs were already persisted, but without the grace clock the gate treated every post-restart tick as "not a new HOD" until price made another high.

## What we changed

- `save_highs` payload includes `session_high_raised_ts`
- `_load_highs_from_disk` restores it with float coercion
- Round-trip test + existing restart regression updated

## How it works now

Highs file is the single restart source for high truth *and* the grace clock that `fails_hod_gate` reads.

## Why this approach

Extend the existing highs blob rather than a second cache file -- same throttle/flush path, no new I/O surface.

## Verification

`pytest tests/test_hod_momo_persist.py tests/test_hod_momo_high.py` -- 21 passed.

## Follow-ups

Phase 5 (G8) roster-commit active-set refresh.

## Keywords

G9, session_high_raised_ts, save_highs, hod:not_new, restart
