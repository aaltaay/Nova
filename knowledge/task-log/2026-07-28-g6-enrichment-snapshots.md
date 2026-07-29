# 2026-07-28 -- G6: archive enrichment snapshots for replay

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo / archive
- **Related:** `CHANGELOG.md` § G6 · `PROBLEM_LOG.md` § G6 · audit G6

## Task

Archive per-session enrichment inputs (avg_volume, float, 52wk high) so replay can prime without production-alert stand-ins.

## Goal

`update_ticker_snapshot` UPSERTs `enrichment_snapshots` when those fields change; replay `prime_symbol` prefers archived values.

## Why it mattered

RVOL/float-gated strategies could not be faithfully replayed -- enrichment was live-only and discarded.

## What we changed

- Schema + `record_enrichment_snapshot` / `load_enrichment_snapshot`
- Hook in `hod_momo_market.update_ticker_snapshot` (change-only, non-fatal)
- Replay priming prefers archive over alert stand-ins

## How it works now

One row per (symbol, session_date). Writes only when avg_volume / float / 52wk change. Replay loads that row when present.

## Why this approach

UPSERT + change detection avoids writing on every price tick. Replay preference order: archive -> meta -> production alert.

## Verification

`pytest tests/test_archive_capture.py tests/test_hod_momo_enrichment.py` -- 12 passed.

## Follow-ups

Phase 7 Former Momo sub-cap.

## Keywords

G6, enrichment_snapshots, avg_volume, replay prime, update_ticker_snapshot
