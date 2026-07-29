# 2026-07-28 -- G8: refresh HOD active set on roster commit

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / hod-momo
- **Related:** `CHANGELOG.md` § G8 · `PROBLEM_LOG.md` § G8 · audit G8

## Task

Rebuild the HOD active set and wake L1 reconcile as soon as a HOD-eligible scanner roster commits, instead of waiting for the next reconcile sleep.

## Goal

New gappers/gainers/afterhours admits enter evaluation immediately; `request_reconcile` short-circuits the L1 reconcile wait.

## Why it mattered

`apply_l1_quote` only rebuilt when the active set was empty, so the first leg of a fresh mover could be missed until the next ~1s reconcile.

## What we changed

- `scanner_l1.request_reconcile` + Event-backed wait in `reconcile_loop`
- `hod_roster_hooks.on_hod_roster_commit` (refresh + wake) called from hydrate `commit_table` and legacy discovery/movers/afterhours writers
- Losers ignored

## How it works now

Roster write -> refresh active set from live caches -> set reconcile event -> L1 subscribes new HOD symbols without waiting out the full sleep.

## Why this approach

Shared hook module keeps `ibkr_bridge` under the file-size limit and gives one place for hydrate + legacy runners. Event wake (not a shorter sleep) avoids busy-polling.

## Verification

`pytest tests/test_scanner_hydrate_hod_roster.py tests/test_scanner_l1.py tests/test_scanner_session_adr008.py tests/test_hod_momo_active.py tests/test_ibkr_bridge.py` -- 37 passed.

## Follow-ups

Phase 6 enrichment snapshots; Phase 7 Former Momo sub-cap.

## Keywords

G8, request_reconcile, on_hod_roster_commit, active set, roster commit
