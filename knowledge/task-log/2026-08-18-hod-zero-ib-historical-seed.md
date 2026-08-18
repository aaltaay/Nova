# 2026-08-18 -- Zero-IB-cost HOD seeding (store-only + tick-6)

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo | market-feed
- **Related:** `CHANGELOG.md` 2026-08-18 HOD seeding is store-only · ADR 008 amendment 2026-08-18 · `.cursor/rules/single-market-data-feed.mdc` rule 8

## Task

Stop HOD Momo from spending the shared IBKR historical budget. HOD should watch what is already hot and moving; it does not need exact pre-admission reconstruction.

## Goal

Steady-state HOD makes zero `reqHistoricalData` calls. Charts keep the 60/10min token bucket. A Gainers name breaking high of day still pings.

## Why it mattered

HOD surge seed was a `priority=background` historical fill per newly admitted symbol. That competed with Trader panes (max 4 timeframes per symbol) for IB's 60 requests / 10 minutes. The desk was paying HOD reconstruction cost on names the operator could already see going up on Gainers.

## What we changed

- `hod_momo_surge_seed.py`: `seed_symbol` reads `bars_store` only; empty store = live-only. Deleted IB fetch, retry, and `no_history` classification.
- `hod_momo_high.py`: observed-warmup self-seed after `HOD_MOMO_OBSERVED_SEED_WARMUP_SEC` (60s) from max observed print, `open_alert_window=False`.
- `hod_momo_flow.py`: `count_surge_none_after_seed` skips buffers shorter than the squeeze window (kills the live `hod_surge_after_seed` WARN flap on fresh admits).
- Integrity: dropped `hod_surge_seed_backlog`; reworded `hod_surge_after_seed`.
- ADR 008 + single-market-data-feed rule 8 updated in the same change.

## How it works now

HOD truth = tick-6 + observed prints. If tick-6 never arrives, after 60s of watching the max print becomes the floor without firing a new-HOD alert. Squeeze = local 1Min bars if a chart already paid for them; otherwise the buffer fills from live ticks and Gainers `change_pct` is the admission-leg substitute. First print still cannot invent HOD (`open_alert_window=False` on warmup; first seed from zero does not open grace).

## Why this approach

Option A (keep IB fills, reserve tokens for `open_chart`) still spends historicals on HOD and needs a scheduler the desk did not ask for. Option B (store-only + tick-6 + warmup) matches the product statement: watch what is already hot. Rejected: reconstructing the admission leg from IB history for never-charted names -- that is the token burn. Rejected: inventing HOD from the first last print -- that is the original false-alert bug.

Tradeoff accepted: no squeeze ping for the admission leg of never-charted names; premarket-high truth for those names waits on warmup/observation (tick-6 is often RTH-only). Charted names keep store truth.

## Verification

- Red-first then green: `backend/tests/test_hod_momo_surge_seed.py` store-hit / store-miss / never-calls-`request_bars` / span-skip; `test_hod_momo_high.py` observed-warmup.
- `py -3 -m pytest backend/tests -k "hod_momo or surge_seed or integrity"` -- 166 passed.

## Follow-ups

- Tune 60s warmup if premarket tick-6 absence is noisy.
- Chart 10Sec live-append / viewport freeze is out of scope.

## Keywords

hod momo, surge seed, bars_store, tick-6, observed warmup, reqHistoricalData, historical budget, squeeze
