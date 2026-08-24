# 2026-08-24 — Scanner names-first admission (ADR 010 decision 5)

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-24 · `PROBLEM_LOG.md` 2026-08-24 — Premarket scanners empty · ADR 008 amendment 2026-08-24 · ADR 010 decision ledger

## Task

Operator launched the installer build at 08:28 ET, IB Gateway logged in live, and both
Gappers and Gainers stayed empty. First ask was a health check; after the tables stayed
empty the ask escalated to "permanent fix, investigate why this was never taken care of,
plan it deeply before touching code."

## Goal

Two deliverables, both approved before implementation:

1. Remove the architectural cause of empty scanner tables, not the symptom.
2. Close the governance gaps that let the same failure hide for a year, so the next
   session cannot "fix" it in the wrong layer again.

## Why it mattered

This is a premarket trading desk. Empty Gappers and Gainers between 04:00 and 09:30 ET
is the product being unavailable during the only window it exists for. Worse than the
outage: every dashboard said healthy. `/api/health` reported `connected`, market-data
farms were OK, the IB loop was not wedged, and `/api/scan/integrity` reported
`scanner_gainers: pass`. The operator had no way to tell "still loading" from "dead," and
neither did the first agent pass in this session, which reported stack health and advised
waiting.

## What we changed

- `backend/ibkr/scanner_hydrate.py` rewritten: `hydrate_rows` builds stub rows from the
  ranked batch and no longer imports discovery at all. `commit_table` refuses empty
  batches, clears `ibkr_bridge_last_error` on a landed roster, and triggers the Gappers
  projection after a Gainers commit. `row_from_quote` and the module-level
  `_known_rows` cache are gone -- the table cache is the only roster memory.
- `backend/ibkr/gapper_view.py` (new): pure `derive_rows` plus `refresh`, the sole
  `gapper_cache` writer under `discovery=ibkr`. Persist and WS broadcast hop to the HTTP
  loop because `refresh` is called from L1 handling on the IB connect loop.
- `backend/ibkr/scanner_session.py`: premarket desired leases reduced to Gainers.
- `backend/ibkr/scanner_stream.py`: dropped the "gappers empty, borrow gainer symbols"
  branch; a failed commit now records a `feed_error` reason.
- `backend/ibkr/discovery.py`: `get_gappers` and `_meets_min_gap` deleted;
  `reprice_mover_row` writes back the resolved `prev_close` so a stub becomes a real row.
- `backend/ibkr_bridge.py`: `apply_l1_quote` refreshes the Gappers projection after
  repricing Gainers.
- `backend/hod_momo_integrity_scanner.py`: Gainers with no roster while IBKR is connected
  inside its window is `fail`, not `pass`.
- `backend/scanner_runners/{discovery,movers}.py` + `backend/adapters/ibkr_scanner.py`:
  one-shot IBKR discovery refuses; `_run_gainers_update_ibkr` deleted.
- `frontend/src/types/scanner.ts` allows null price fields and carries `rank`;
  `EmptyState.tsx` premarket copy explains the projection instead of referencing bridge
  timeouts that no longer wipe the table.
- `scripts/Invoke-NovaMorningCheck.ps1`: new Gainers leg; premarket zero-gappers demoted
  to WARN because it is now a legitimate market state.
- Governance: ADR 010 decision ledger, ADR 008 amendment, `single-market-data-feed.mdc`
  rules + anti-patterns, `verification-before-completion.mdc` blast-radius rows,
  PROBLEM_LOG `Fix class` field.

## How it works now

One writer per table, and quotes never decide existence.

IB pushes a ranked batch to `scanner_stream._on_batch`. `commit_table` writes those names
in IB rank order with `price=None`, stamps the roster clock, and broadcasts
`roster_replace`. Scanner L1 reads the committed cache to choose subscriptions, and each
tick flows through `reprice_mover_row`, which fills price and writes back `prev_close`.
Premarket Gappers is `gapper_view.derive_rows(gainer_cache)` filtered at
`GAPPER_MIN_GAP_PCT`, refreshed on every Gainers commit and every L1 tick, and it stamps
`gapper_cache_ts` only when it actually has rows. Gappers still freezes at 09:30 ET.

Invariants worth memorizing:

- Roster admission never awaits a COLD IB call.
- An unpriced row is honest; a missing row and a `0.00` row are both lies.
- An empty IB batch never advertises a fresh scan.
- One empty table may never vouch for another empty table.
- `discovery=ibkr` has exactly one roster writer, enforced at the adapter.

## Why this approach

**Rejected: raise the 20s `on_ib` ceiling or shrink `IBKR_COLD_SNAPSHOT_BATCH`.** Same
architecture, slower death. IB completes snapshots on `tickSnapshotEnd` around 11s, so a
50-name roster on a shared socket loses this race whenever the desk is busy -- which is
exactly when the operator needs the table.

**Rejected: port the 2026-07-14 `TOP_OPEN -> TOP_PERC_GAIN` fallback into the lease.**
That fallback was correct about the market and useless in practice: it lived on the
one-shot path, which the 2026-08-07 authoritative cutover made unreachable. Moving it
would still have left admission gated on `snapshot_quotes`.

**Rejected: set `IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=false` to revive one-shot.** Dual
owners racing on one Gateway socket is the documented 2026-07-29 wedge. ADR 010 decision
10 already bans half-on flags; rollback is git revert.

**Rejected: keep `TOP_OPEN_PERC_GAIN` as a second premarket lease "just in case."** It
answers Warning 165 before 09:30 by design. Keeping it costs a scanner slot and, more
importantly, leaves a plausible-looking dead code path -- the precise thing that absorbed
three separate fix attempts.

**Chosen shape:** make the product definition explicit (a premarket gapper *is* a gainer
clearing the gap floor) and let the feed that actually works own it. IB rank replaces
local re-sorting because re-sorting invents a second ranking that visibly disagrees with
IB as L1 ticks land.

**On why the governance work was not optional.** The code fix alone would have been the
eleventh fix to this symptom. The audit found the bug was invisible by construction:
every hydrate test replaced `snapshot_quotes` with an instant perfect fake, so CI could
never see a timeout; integrity classified a dead Gainers feed as `pass`; the morning
autopilot probed only Gappers; ADR 010 said "Accepted" while its own footer claimed
Tasks 1 and 3 were "not yet" (they had shipped in the same commit), steering later
sessions away from hydrate. The AST guard, the Gainers integrity failure, the Gainers
morning leg, and the ADR decision ledger each close one of those blind spots.

## Verification

- `py -3 -m pytest backend/tests` -> **1287 passed**, exit 0.
- `backend/tests/test_scanner_names_first.py` (9 tests) written **red first**; recorded
  baseline reproduced the outage exactly: `TimeoutError: IB on_ib timed out after 20.0s
  [snapshot_quotes]` escaping `commit_table`, empty batch returning `True`, and integrity
  asserting `pass` for dead Gainers.
- `npm run build` -> clean (`tsc -b && vite build`).
- `npm test -- --run` -> **161 files / 707 tests passed**.
- `py -3 -m ruff check backend/` -> only two pre-existing findings
  (`alerts/channels_store.py`, `archive/bar_builder.py`), none in changed files.
- Live desk: see Follow-ups -- the ship landed at 09:30 ET, so the premarket projection
  has test evidence only until tomorrow's window.

## Follow-ups

- **Live premarket confirmation owed (04:00-09:30 ET).** Confirm Gainers names appear
  before any `snapshot_quotes` completes and that Gappers fills only with real gaps.
  Today's window closed as this shipped; do not record the projection as live-verified
  until that run.
- Consider a CI gate that compares ADR decision-ledger rows against shipped evidence, so
  "accepted but not implemented" is machine-detectable rather than folklore.
- Frontend could show an explicit "waiting for L1" affordance for `price === null` rows;
  today they render as `—`.

## Keywords

scanner admission, names-first, ADR 010 decision 5, gapper_view, snapshot_quotes,
on_ib timeout, empty gappers, empty gainers, Warning 165, TOP_OPEN_PERC_GAIN,
single roster owner, integrity pass, premarket outage
