# 2026-07-29 -- Chart pane wedge + live tip repair

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / Trader charts
- **Related:** `CHANGELOG.md` §2026-07-29 -- Chart panes self-heal · `PROBLEM_LOG.md` §2026-07-29 -- Chart panes stuck on timeout

## Task

Investigate why Full Day and 10-Second Trader panes stayed on "Chart bars timed out" after IBKR came back (while 1Min/5Min recovered), and fix recovery + live tip behavior.

## Goal

After a transient Gateway/event-loop wedge, every grid pane self-heals without a manual reload; Full Day tip tracks live trades; 10Sec can open a tip from a forward trade after a stale historical paint.

## Why it mattered

User saw three progressive states: all Loading while IBKR offline, all timed out, then 1m/5m painted while Full Day and 10s stayed red. That feels like "the new 10s chart is broken" when the real failure was a reconnect wedge plus missing retry/poll for those two timeframes.

## What we changed

- `useChartBars`: one background retry (~5s + jitter) after foreground failure with empty store; clear retry on symbol/TF change; re-apply `lastTrade` after any successful paint.
- `liveTradeApply` / `useChartLiveTrade`: daily tip updates via ET `YYYY-MM-DD` bucket; intraday allows forward-jump tip candles; daily never invents a new period bar.
- `tickerChartData`: `etCalendarDateString`, daily `tradeBucket`, string-aware `isOutOfOrderTrade`.
- `ibkr/bars.py`: log `slot_wait` vs `fetch` + `bars=` count; record `ibkr.historical_slot_wait`.

## How it works now

Wedge → client AbortError → red overlay → ~5s later one silent `/bars` retry → paint clears overlay. Once painted, any WS trade updates matching 1Day tip or opens/updates 10Sec tip even after a gap. Next wedge: look for `IBKR bars timing … slot_wait=` to see gate queue vs Gateway time.

## Why this approach

- **Retry over refetch poll for 10Sec/1Day:** poll would fight small-bar pacing and daily TTL; one retry after failure is enough for reconnect wedges.
- **Pure `mergeLiveTradeCandle`:** testable without mounting LWC; hook stays thin.
- **Log-only for the wedge itself:** morning API_WEDGED root cause was already fixed; tonight's 49s lag needs timing evidence before another backend structural change.

## Verification

- Vitest: liveTradeApply, barsErrorRetry, tickerChartData, chart suites
- pytest: test_ibkr_bars / test_ibkr_bars_cache
- `npm run build`

## Follow-ups

- On the next natural wedge, read `IBKR bars timing` lines -- if `slot_wait` dominates, consider interactive priority tuning; if `fetch` dominates, Gateway/history payload.

## Keywords

Chart bars timed out, Full Day, 10Sec, loop_lag, error retry, live tip, tradeBucket, historical_slot_wait
