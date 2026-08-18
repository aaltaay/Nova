# 2026-08-18 -- Gainers freeze: historical fills never send against pacing debt

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-18 (Historical fills never send) · `PROBLEM_LOG.md` 2026-08-18 (Gainers prices froze) · ADR 012 amendment

## Task

After the chart-fill fix (`fe192b3`), the user reported Gainers scanner prices frozen. Diagnose root cause and fix architecturally, not with a patch.

## Goal

Restore live L1 scanner ticks while keeping store-first charts that fill completely. No brute force; respect IB pacing as a hard send rule.

## Why it mattered

Scanner rows are the desk's primary surface. A chart feature silently freezing them is a regression of the core product, and the shared IB socket means any historical misbehavior is an L1 risk.

## What we changed

- `backend/ibkr/historical_service.py`: `warm` sheds on any pacing wait (like `background`); `open_chart` sleeps only short 2s/15s windows; longer 10-min-bucket debt is rescheduled via `loop.call_later` through `_reschedule_after_wait`. In-flight path follows the same rule. Added `_SHORT_PACING_WAIT_SEC`.
- `backend/chart_bars.py`: `/bars` skips `_schedule_ibkr_fill` when the stored series is complete and fresh.
- `backend/routes/ticker.py`: ticker WS warm loop skips `schedule_fill` for complete+fresh series.
- ADR 012 and `single-market-data-feed.mdc`: send rule documented; sleep-then-send listed as a rejected alternative.
- `backend/tests/test_historical_service.py`: red-first tests for warm shed and open_chart no-send on long wait.

## How it works now

`reqHistoricalData` is never sent while pacing `wait_seconds > 0` beyond IB's short same-contract (2s) / identical-request (15s) windows. `background` and `warm` shed on any wait. `open_chart` sleeps only a short window; global-bucket debt is re-queued with `call_later` so the IB connect-loop stays free for `reqMktData` ticks. Complete+fresh series do not re-queue fills at all. During a budget hole a pane may honestly sit at "filling..." while the scanner keeps ticking.

## Why this approach

The previous fix optimized for "charts must fill" and treated pacing as a delay to sleep through. But the IB loop is shared: any `reqHistoricalData` sent into a pacing debt consumes the socket that L1 ticks need. The correct invariant is a send rule, not a sleep policy -- pacing debt means "do not send," and open_chart's urgency is handled by rescheduling (which re-checks pacing on wake) rather than by sleeping on the loop. Rejected: (a) keep sleep-then-send with a longer cap (still sends into debt); (b) a second clientId for historicals (violates ADR 010 one-client rule); (c) dropping open_chart fills entirely (charts would stay thin). Skipping `schedule_fill` for complete+fresh series removes the largest source of unnecessary pacing pressure at the source.

## Verification

- `py -3 -m pytest backend/tests` -- 1198 passed.
- Red-first: `test_warm_sheds_when_pacing_wait_and_store_has_bars` and `test_open_chart_does_not_send_when_global_bucket_wait_exceeds_cap` failed before the fix, pass after.
- Live API (still on old code at poll time): `/api/movers` prices moved between two polls 8s apart (AIXC 1.61->1.651, XOS 4.25->4.185, CDTG 4.7->4.75); `/api/mode` `ib_loop_lag_ms` last 8.6ms, `wedged=false`. Post-restart confirmation of the new send rule in logs is the remaining live check.

## Follow-ups

- Restart the API so the new send rule is live; confirm `historical fill rescheduled` (not `deferred ... wait 3xx`) appears under pacing pressure and that Gainers keep ticking during a chart burst.
- Do not reopen unless L1 ticks stall again with `ib_loop_lag_ms` wedged.

## Keywords

gainers frozen, L1 starved, pacing wait, HistoricalShed, sleep-then-send, call_later, reqMktData, ADR 012, ADR 010, warm priority, ib_loop_lag_ms
