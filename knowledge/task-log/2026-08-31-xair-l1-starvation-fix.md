# 2026-08-31 — Fix L1 starvation that hid new gappers (XAIR)

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-31 "Fresh unpriced scanner names can no longer be starved out of L1 forever" · `PROBLEM_LOG.md` 2026-08-31 "XAIR ... alphabetical tie-break starved L1" · `DEFERRED_LOG.md` D-009 (untraced ticker cold-snapshot gap, same investigation)

## Task

User reported XAIR trading up ~30% but never appearing on the Gappers table, and asked why. Diagnose and fix.

## Goal

Explain the exact mechanism keeping XAIR (and any future hot new name) out of Gappers, fix the root cause so a freshly-admitted name reliably gets its first L1 quote, and make integrity actually catch this class of failure instead of reporting pass.

## Why it mattered

Gappers/Gainers are the desk's premarket discovery surface -- a name the operator would trade on can be invisible for its entire life if it loses a starvation race that has nothing to do with how hot it actually is. `/api/scan/integrity` reported `pass` the whole time, so nothing would have surfaced this without the user noticing by eye.

## What we changed

- `backend/hod_momo_active.py`: `_ranked_symbols` tie-breaks still-unpriced (score `0.0`) rows on IB's own scanner `rank` instead of the symbol string. New `_discovery_candidates` + a discovery-admission step in `build_active_set` reserves `HOD_MOMO_ACTIVE_DISCOVERY_SLOTS` (6) slots *inside* the existing 40-symbol capacity for unpriced rows, ranked by IB rank, with `HOD_MOMO_DISCOVERY_HOLD_SEC` (20s) rotation so a permanently-unquotable name yields its slot. `build_active_set` gained an optional `now` param for deterministic tests.
- `backend/constants_hod_momo.py`: added the two constants above (auto re-exported via the `constants.py` barrel).
- `backend/ibkr/scanner_hydrate.py`: `stub_row` stamps `admitted_ts` once; it survives every later rank-only or reprice merge because both paths spread the prior row (`{**prior, ...}`).
- `backend/integrity_live.py`: `_row_price_coverage` now also judges Gainers whenever Gappers is displayed and live (Gappers is a filtered projection of Gainers), and reports age from the oldest unpriced row's `admitted_ts` instead of `roster_ts` (which a busy table rewrites every IB push, so it could never age past the grace window on its own).
- Tests: `backend/tests/test_hod_momo_active.py` (rank tie-break, discovery quota ordering, hold-timeout rotation), `backend/tests/test_scanner_hydrate_admitted_ts.py` (admitted_ts stamping/preservation), `backend/tests/test_integrity_row_price_dependency.py` (Gainers dependency coverage).

## How it works now

Gappers is a projection: `ibkr/gapper_view.derive_rows` only keeps Gainers rows that already have a price and clear `GAPPER_MIN_GAP_PCT`. A row only gets a price by winning one of two IBKR L1 pools -- the displayed active-tab table, or the reserved 40-symbol HOD pool. `hod_momo_active.build_active_set` fills that pool in three passes now: Former Momo first (capped), then up to 6 unpriced rows by IB rank (the discovery quota), then a round-robin of ranked Gappers/Gainers/Afterhours for whatever capacity remains. Any row with a real score still competes on merit in the round-robin regardless of the quota -- discovery only exists for rows no score has reached yet. Once a discovery-admitted row gets its first tick, it drops out of the discovery pool automatically (score is no longer `0.0`) and never needs the quota again.

Integrity's row-price coverage now treats Gainers as a dependency of Gappers, not an independent, undisplayed table nobody asked about -- because that's literally what it is. The age it judges against is the specific unpriced row's own admission time, not a roster-commit clock that a hot table resets on every single IB push.

## Why this approach

- **IB rank over alphabet, not a synthetic urgency score:** IB already ranks its scan by the metric that matters (percent gain for `TOP_PERC_GAIN`). Recomputing a second heuristic score from fields that don't exist yet (that's the whole problem -- they're `None`) would just reinvent IB's own answer worse. Using the rank IB already sent is zero extra cost and exactly correct.
- **Reserved quota, not "give zero-score rows a chance in the normal queue":** rejected. The live desk had ~40 already-priced rows filling capacity every single tick -- a zero-score row would never be *reached* by round-robin no matter how it's tie-broken, because priced rows always sort ahead of unpriced ones in the same category queue. Only a slot carved out *before* round-robin runs guarantees new names get evaluated at all.
- **Quota carved inside capacity 40, not added on top:** the p95 quote/eval-age SLO is tied to that capacity number; raising it changes a different tradeoff (more L1 sockets vs. discovery latency) that wasn't asked for and has spare headroom (`IBKR_L1_STREAM_BUDGET`=95, only ~40 in use) if it's ever wanted later. Taking 6 slots from priced rows costs those 6 the least-important round-robin admissions, which is the correct price to pay for never permanently blacklisting a new hot name.
- **Hold-timeout rotation instead of a permanent quota lock:** without it, a single illiquid/broken-contract name at the best IB rank would squat the quota forever and block every other new name from ever getting a first look. 20s is long enough for a normal `reqMktData` subscribe + first tick; short enough that operators don't wait minutes for a scanner column to fill during a busy premarket.
- **`admitted_ts` per row, not fixing `roster_ts` semantics:** `roster_ts` is deliberately "last commit for the whole table" and other code already depends on that meaning (freshness checks, WS revision bumps). Adding a narrower per-row timestamp is additive and doesn't risk that existing contract.
- **Gainers as a coverage dependency of Gappers, not "judge every live table always":** the existing design deliberately scopes coverage to displayed tables because an undisplayed live table legitimately has zero L1 by design (bounded L1 budget). Gainers is the one exception because Gappers *reads from* it, not because "it might be interesting" -- adding it unconditionally for every live table would misfire on tables nobody is choosing to look at.

## Verification

- `py -3 -m pytest backend/tests/test_hod_momo_active.py backend/tests/test_scanner_hydrate_admitted_ts.py backend/tests/test_integrity_row_price_dependency.py -v` — 21 passed.
- `py -3 -m pytest -q` (full backend suite) — 1456 passed, 1 pre-existing failure (`test_mover_columns.py::test_decorate_rows_attaches_earnings_window`, confirmed via `git stash` to fail identically with this session's changes removed -- unrelated order-dependent flake, tracked as `DEFERRED_LOG.md` D-008).
- Restarted the live API process to load the fix, reconnected to IB Gateway (already logged in, no 2FA needed). Fresh `/api/movers` poll: unpriced-gainer count went from 11 to **0**; `/api/gappers` grew from ~14 rows to 17, newly including `YDDL`, `WETO`, `WBUY` -- names that were previously stuck unpriced at IB ranks 3/4/6. `backend/logs/api-console.log` shows `ibkr.ticks: subscribed last-price` for every previously-`null` symbol within seconds of restart.
- Blast-radius re-check on the shared HOD active-set pool (per `verification-before-completion.mdc`): `/api/hod-momo/debug/integrity` showed `hod_active_set: active=40/40`, quote/eval age p95 0.59s (well under the 2s SLO), `hod_enrichment` 98% -- no regression from adding the discovery step.

## Follow-ups

- `DEFERRED_LOG.md` D-009: a separate, untraced finding from the same investigation -- `/api/ticker/XAIR`'s cold snapshot path returned empty with a blank exception message while `reqHistoricalData` bars fetched fine for the same symbol at the same time. Different code path (`ticker_ibkr.py`), not fixed here.
- `DEFERRED_LOG.md` D-008 extended with corroborating evidence that the earnings-day-offset test flake is pre-existing and order-dependent, not caused by this session's changes.

## Keywords

XAIR, gappers, gainers, L1 starvation, hod_momo_active, discovery quota, alphabetical tie-break, IB scanner rank, scanner_hydrate, admitted_ts, row_price_coverage, integrity, HOD active set, ADR 008
