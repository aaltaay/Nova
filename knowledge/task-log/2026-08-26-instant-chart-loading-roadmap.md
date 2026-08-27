# 2026-08-26 -- Instant chart loading roadmap (D-003 implementation)

- **Status:** completed (code + tests); live verification pending
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-26 "Instant chart loading roadmap" · `PROBLEM_LOG.md` 2026-08-26 "Trader 10Sec / Full Day charts starved" · `DEFERRED_LOG.md` D-003 · `knowledge/task-log/2026-08-26-chart-hist-loading-soak.md` · ADR 012

## Task

Implement the four-phase plan from the chart-hist-loading soak: make Trader chart panes paint near-instantly by protecting IB's 60-req/10-min historical budget, giving empty panes true priority over already-painted stale panes, and painting provisional 10Sec candles from the tape Trader already streams.

## Goal

Each phase ships with fresh, passing tests and does not regress the shared IB socket (scanner L1, tape, depth). D-003 stays open until a live restart confirms the fix; this session does not close it on pytest evidence alone.

## Why it mattered

10Sec and Full Day panes sat on "Loading IBKR historical..." for minutes because three uncoordinated consumers (Large Cap's daily-bar respray, priority-blind chart refetches, and a cold 10Sec pane with no live overlay) shared one small IB rate budget. The fix touches a shared resource (IB historical scheduler) that has starved the desk before (2026-08-18 Gainers freeze), so it had to be surgical and test-proven per phase, not a single big patch.

## What we changed

- **Phase 0 (observability):** `HistoricalPacing.snapshot()` in `backend/ibkr/historical_pacing.py`; `historical_service.pacing_snapshot()` accessor; exposed at `/api/metrics/ops.historical_pacing`.
- **Phase 1 (Large Cap budget guard):** `large_cap_metrics.schedule_daily_fill` gained a once-per-04:00-ET-session guard (`_scheduled_this_session`, keyed by `market.session_key_et()`). `large_cap_hooks.on_large_cap_roster_commit` also skips the call entirely when the store already has a complete daily series.
- **Phase 2 (priority honesty):** `chart_bars.fetch_chart_bars` picks `open_chart` only for a genuinely empty store; a store with stale/incomplete bars gets `warm` (sheds on any pacing wait). Non-interactive (scan/nova_os) callers are untouched -- they stay `background` regardless of store state.
- **Phase 3 (tape-based 10Sec):** New `backend/ibkr/tape_10sec.py` -- 10-second OHLCV buckets built from tape prints (`tape_stream._on_tape_update`), volume = summed print sizes, enqueued via the existing non-blocking `archive.write_queue` (`source=ibkr_l1`). Heartbeat flush wired into `scanner_l1.flush_loop` next to `l1_minute.flush_elapsed`.
- **Phase 4 (Trader-seam warm):** `tape_stream._subscribe_locked` schedules a `warm` 10Sec hist fill on the first subscriber for a symbol, guarded by the same store-settled check `routes/ticker.py` uses for its warm timeframes.

## How it works now

The 60-req/10-min IB historical budget is now visible (`/api/metrics/ops.historical_pacing.window_used`). Large Cap spends at most one token per symbol per session for its daily bars, instead of respraying on every roster commit and every 15-min TTL miss. A `/bars` HTTP call only asks for top priority when the pane has nothing to show; a pane that already painted something asks politely and steps aside under pacing pressure. A Trader 10Sec pane gets real candles from the tape within a few prints (well under the old multi-minute wait), while the true 4-hour IB history still lands in the background and replaces the provisional candles by candle identity (`UNIQUE(symbol, timeframe, ts)`, hist always wins) -- this never fakes `store_series_complete`, so the real fill is still scheduled.

## Why this approach

Per-phase, test-first changes on a shared resource (IB historical scheduler) instead of one big patch, because this exact area has been "fixed" wrong before by treating the symptom (2026-08-18 sleep-then-send froze Gainers L1; multiple 25s-timeout patches in July made the desk worse). Tape-based provisional 10Sec bars were chosen over raising `IBKR_HISTORICAL_MAX_CONCURRENT` (IB's real ceiling is the 60/10-min budget, not concurrency -- more concurrency only empties the bucket faster) and over a new client-side timeout overlay (ADR 012 deliberately deleted that pattern). Reusing `l1_minute.py`'s exact bucket/enqueue/flush shape for `tape_10sec.py` keeps the write-queue discipline (ADR 010: no synchronous SQLite on the IB socket callback) instead of inventing a second pattern.

Rejected: closing D-003 on pytest evidence alone. The running Nova process could not be located from this agent shell (likely a different Windows session than the API/Electron sidecar), and blindly restarting or killing a process this agent cannot positively identify -- on a machine with a live IBKR account -- is not something to do without the user's hand on it. Verification-before-completion still applies: the entry stays open with an explicit re-verification checklist instead of a soft "should work" claim.

## Verification

`py -3 -m pytest backend/tests -q` (excluding the pre-existing unrelated `test_news_impact.py`/`test_news_sentiment.py` transformers-import flake): 1386 passed. Focused runs during development: `test_historical_service.py` (8), `test_op_metrics.py` (6), `test_large_cap_hooks.py` + `test_large_cap_metrics.py` (17), `test_ibkr_bars.py` + `test_ibkr_bars_cache.py` + `test_setups_stream.py` + `test_routes_nova_os.py` (36), `test_tape_10sec.py` (4, new file), `test_ibkr_tape_stream.py` + `test_scanner_l1.py` + `test_l1_minute.py` (31) -- all green.

Live verification **not yet run** (see Follow-ups).

## Follow-ups

`DEFERRED_LOG.md` D-003 stays open (status `blocked`) with the exact next steps: restart Nova, then check `/api/metrics/ops.historical_pacing.window_used` across two Large Cap commits, open a cold Trader symbol and confirm 10Sec paints within seconds, and re-check scanner L1 freshness in the same window (blast-radius rule). Only then move D-003 to Closed and write the PROBLEM_LOG close-out confirming the live numbers. Phase 5 (raise `IBKR_BARS_STORE_FRESH_INTRADAY_SEC`, `keepUpToDate` streaming hist for 10Sec, separate `snapshot_quotes` p95 investigation) intentionally not started -- do not start without the user asking.

## Keywords

D-003, historical_pacing, Large Cap schedule_daily_fill, once-per-session guard, chart_bars priority, open_chart, warm, tape_10sec, l1_minute, ADR 012, ADR 010, 60/10 min bucket, Trader 10Sec, live verification pending
