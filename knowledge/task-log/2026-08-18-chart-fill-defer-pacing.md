# 2026-08-18 -- Chart fills defer on pacing instead of dropping

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` §2026-08-18 -- Chart fills defer on pacing instead of staying on stubs · `PROBLEM_LOG.md` §2026-08-18 -- Chart fill dropped on pacing wait · ADR 012

## Task

User asked to check whether charts still had gaps after the store-first / viewport work. If not, call it a day.

## Goal

Prove whether remaining thin panes were leftover viewport bugs or a data-side hole, then close the hole and get the full suites green.

## Why it mattered

The previous session fixed zoom-on-live-tip. The user-visible "almost empty pane" could still happen because 1Hour (and other derived TFs) never left a 9-bar stub. A store-wide query showed 55 symbols / 437 1Hour rows. Isolated fetch worked; a grid open did not. That is the original "problems have shifted" report, one layer down.

## What we changed

- `historical_service.request_bars`: pacing wait no longer returns the stub for `open_chart` / `warm`. Those priorities sleep, then fetch. `background` still sheds.
- Shed / defer log at INFO (`historical fill deferred`, `historical fill shed`).
- `_persist_derived` reads `CHART_DEFAULT_BARS` so a completed series is not reset by a short 1Min derive.
- `store_series_complete` uses `IBKR_BARS_STORE_MIN_BARS` (1Hour needs 24, 5Min needs 200).
- Removed dead `shouldFitContentOnHistoryPaint`, unused `opts.fitContent`, and `CHART_BARS_ERROR_RETRY_*`.
- Test repairs (pre-existing red, not chart): depth `is_ready`, executor `IBKR_FORCE_ONE_SHARE`, news `_today_et` binding, runtime_state health source, account `cold_slot` reset, Vitest `subscribeTicketSessionUnlock` mock.

## How it works now

HTTP stays store-first. A chart click still returns immediately. The scheduled fill, if paced, waits and then calls IB. A 9-bar derived 1Hour is not "complete." Only background work may drop on pacing. Deferrals show up in `api-console.log`.

## Why this approach

Deferral beats drop because the wait is already bounded (same-contract 2s, identical 15s) and `_run_fetch` already slept it -- the early return was the bug, not missing machinery. Raising `HistoricalShed` for background (instead of returning the stub) keeps one observable path. Per-timeframe mins beat `>= 8` because one session of 1Hour is ~9 bars and must not count as a 3-month fill. Rejected: bumping concurrency (IB same-contract cap is 5/2s regardless). Rejected: deleting 1Min derive (today's coarse panes should still paint immediately).

## Verification

- Red-first: `test_open_chart_fetches_when_pacing_wait_and_store_has_stub` and `test_persist_derived_skips_when_store_already_longer` failed, then passed.
- `py -3 -m pytest backend/tests` -- 1196 passed.
- `npx vitest run` -- 692 passed / 158 files.
- `py -3 tools/doc_invariants.py` -- OK.
- Live after API restart: AIXC burst 1Min/5Min/15Min/30Min/1Hour/1Day. First poll 1Hour=5, 1Day=0. 25s later 400/400/400/400/400/232 (1Min is 1 D). Log: `historical fill deferred AIXC 1Day: wait 1.7s`.

## Follow-ups

Symbols that already sat on pre-fix stubs fill on the next ticker open. No need to wipe `archive.db`.

## Keywords

chart gaps, 1Hour, pacing wait, derive, store_series_complete, AIXC, ADR 012, is_ready, IBKR_FORCE_ONE_SHARE
