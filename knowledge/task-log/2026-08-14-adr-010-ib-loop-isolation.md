# 2026-08-14 -- ADR 010 IB loop isolation (classification only)

- **Status:** completed (Task 0 only)
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-14 -- ADR 010 · `PROBLEM_LOG.md` 2026-08-14 -- Premarket API_WEDGED banner

## Task

Lock the long-term IB loop isolation design after the 2026-08-14 premarket `API_WEDGED` soak, without moving `ib_async` off uvicorn during a live session.

## Goal

ADR 010 accepted, HOT/COLD SSOT in code with a failing-loud unknown-label rule, hydrate/`snapshot_quotes` proven COLD, inventory written so Task 2 cannot "discover" sites mid-cutover.

## Why it mattered

The banner was a health-probe timeout on a live PID, not a dead API. A timeout/grace/auto-heal patch would hide the desk flash and still leave L1 and `placeOrder` on the starved loop. Classification had to exist first so a later task cannot call hydrate HOT.

## What we changed

- Added `architecture/decisions/010-ib-loop-isolation.md` (two loops, one clientId, honest HTTP-up / IB-bounded invariant, inventory appendix).
- Backfilled ADR 008/009 rows on `architecture/README.md` and added 010.
- Added `backend/ibkr/work_class.py` + `backend/tests/test_ibkr_work_class.py`.
- Added rule 9 + anti-patterns to `.cursor/rules/single-market-data-feed.mdc`.
- No runtime IB move. No auto-heal change.

## How it works now

`classify(label)` is the SSOT. Persistent scanner, L1/depth/tape, and place/cancel are HOT. `snapshot_quotes`, `hydrate_rows`, surge-seed, enrichment, reprice, and historicals are COLD. Unknown labels raise. The process still runs IB on uvicorn until Tasks 1-2.

## Why this approach

Wrote law + tests before the loop move because a half-migrated `_loop` during `NOVA_API_RELOAD=1` is worse than today's starve. Rejected shipping auto-heal demotion as the fix (Task 4 stays last). Rejected a feature flag (two-loop half-on). Inventory includes listing_flags, ticker_ibkr, journal fills, strategy executor, reprice, and afterhours so Task 2 is a checklist, not a hunt.

## Verification

`py -3 -m pytest tests/test_ibkr_work_class.py -q` -- 20 passed (run from `backend/`).

## Follow-ups

- Task 1+2: supervisor + move every `ib.*` (not during a live reload session).
- Task 3: one scheduler, batch=5, wait-one in-flight, integrity warn on dropped seeds.
- Task 4 last: WEDGED never kills (Vite + Electron); desk blocks on `ib_loop_lag`.
- Task 5: live soak.

## Keywords

ADR 010, work_class, HOT, COLD, snapshot_quotes, hydrate_rows, API_WEDGED, loop isolation
