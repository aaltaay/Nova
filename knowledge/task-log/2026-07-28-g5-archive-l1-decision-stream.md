# 2026-07-28 -- G5: archive HOD L1 decision stream

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / hod-momo / archive
- **Related:** `CHANGELOG.md` § Archive HOD L1 decision stream · `PROBLEM_LOG.md` § Archive records tape but not L1 · audit G5

## Task

Remediate capture-audit finding G5: archive the L1 tick stream that drives HOD evaluation, not only open-ticker tape.

## Goal

Active-set L1 ticks that call `on_trade_update` also land in `archive.db` `l1_ticks`, with tests covering the writer and both bridge call sites.

## Why it mattered

Without the decision stream on disk, "did we capture it?" can never be answered for the full HOD pool -- only for symbols that had an open tape subscription.

## What we changed

- Schema + allowlist: `l1_ticks` in `archive/db.py`; cold table list + counter constants
- `capture.record_l1_tick` (same writer pattern as tape)
- `ibkr_bridge._archive_l1_tick` hooked after `on_trade_update` in `apply_l1_quote` and `apply_table_quotes`
- Tests for round-trip write and both bridge paths

## How it works now

HOD feed and archive are paired at the bridge: same symbol/price/ts/volume/day_high that entered the engine are persisted. Archive errors never blank the live path.

## Why this approach

Hook at the bridge (after the active-set gate + successful `on_trade_update`) rather than inside `ticks.py` or the engine -- that records exactly what HOD evaluated, not every raw IB tick, and keeps archive non-fatal at the call site. Full historical backfill is impossible (past L1 was never stored); only new sessions gain coverage.

## Verification

`pytest tests/test_archive_capture.py tests/test_ibkr_bridge.py` -- 14 passed.

## Follow-ups

Phase 3 (G2/G3) market-data-type honesty; later replay exporter can prefer `l1_ticks` over tape when present.

## Keywords

G5, l1_ticks, archive, on_trade_update, apply_l1_quote, decision stream
