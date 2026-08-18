# 2026-08-18 -- hod_surge_after_seed was a stale-seed window bug

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo
- **Related:** `PROBLEM_LOG.md` 2026-08-18 hod_surge_after_seed · `CHANGELOG.md` same day

## Task

Decide whether the leftover afterhours `hod_surge_after_seed` warn was a real bug or warmup noise. User rejected treating it as an accepted tradeoff.

## Goal

Integrity and Squeeze must share one definition of "5 minutes." Stale chart bars must not pretend that window exists.

## Why it mattered

Calling a lying integrity warn a "tradeoff" hid a real composition bug: HOD high can use all-day store highs, but Squeeze is last-5-minutes ending at the latest print. Fossils from 90 minutes ago cannot be that path.

## What we changed

- `filter_bars_to_recent`: surge seed only keeps store 1Min bars within 15 minutes of now.
- Session high still uses full-session store bars.
- `count_surge_none_after_seed` uses >=2 prices in `price_surge`'s window, not first-to-last span.

## How it works now

Squeeze is computable when two prices exist in the last 5 minutes of the latest print (live L1 or actually-recent store). A quiet afterhours name with a gap is market truth. A dense window that still returns None is the only integrity defect.

## Why this approach

Do not IB-fetch the missing 5 minutes (that was the budget problem). Do not lower the check to silence it. Do not copy dead bars into the live buffer. Align seed and integrity with the function Squeeze already runs. The next completeness (not this patch) is rolling scanner L1 into 1Min store so names we have been streaming always have a live minute path without `reqHistoricalData`.

## Verification

- Red-first tests: stale store does not poison buffer; stale+fresh tick is not surge_none; gapped span is not a defect.
- `py -3 -m pytest backend/tests/test_hod_momo_surge_seed.py backend/tests/test_hod_momo_integrity.py backend/tests/test_hod_momo_high.py` -- 38 passed.

## Follow-ups

Roll scanner L1 last into `bars_intraday` (queued, off the IB loop) so the store stays current for streamed names. Charts and HOD then share one live minute series.

## Keywords

hod_surge_after_seed, squeeze, stale bars, price_surge window, afterhours integrity
