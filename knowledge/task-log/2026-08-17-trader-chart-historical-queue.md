# 2026-08-17 -- Trader charts fetch one historical at a time

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-17 -- Trader charts fetch one pane at a time · `PROBLEM_LOG.md` 2026-08-17 -- Trader 2x2 charts timeout (25s cancel stampede)

## Task

Fix Trader 2x2 chart timeouts: fetch panes one after another (or one batch with a covering budget), and stop cancelling a historical that another pane is still waiting on, without introducing new issues.

## Goal

Opening a ticker paints 5m / 1m / Full Day / 10s without the red "Chart bars timed out" overlay caused by four parallel 25s clocks and `run_coro` cancel.

## Why it mattered

Live tape and Level 2 were fine, so the desk looked "up," but three of four chart panes went red after a long load. IPST logs showed 5Min taking 19.4s then three `run_coro timed out after 25.0s (cancel accepted)` lines. Cancel meant 10Sec and 1Day never cached, so retries looped.

## What we changed

- Added `barsFetchQueue.ts`: one in-flight HTTP historical, priority insert (1Min/5Min, then daily, 10Sec last).
- `ensureBars` arms the 25s abort only after dequeue; same-key calls still coalesce.
- `ensureBarsBatch` is sequential `/bars` with per-TF limits (10Sec keeps 1500).
- `useChartBars` aborts the in-flight/queued fetch on symbol change or hide so a stale 10Sec cannot block the next ticker.
- Ticker WS no longer calls `warm_symbol_bars` (that warm raced the grid).
- `bars_cache.get_or_fetch` runs the IBKR pull in a detached task; caller cancel does not kill it. Failures still are not cached.
- Did not change global `run_coro` cancel (needed for reconnect generation safety).

## How it works now

Trader panes share one client queue. Each timeframe gets a full 25s once it reaches the wire. IBKR still serves one historical at a time. If HTTP/`run_coro` gives up, the Gateway request can finish and land in the TTL cache so the 5s retry or next poll paints. Switching symbols aborts queued work for the old name.

## Why this approach

- **Rejected raising the global 25s timeout to 90s:** one hung pane would spin "Loading" forever and still stampede if four clocks start together.
- **Rejected changing `run_coro` to never cancel:** that cancel exists so a timed-out bridge cannot race a reconnect (PROBLEM_LOG 2026-07-23). Scope the "keep running" behavior to bars cache only.
- **Rejected keeping `/bars/batch` as one HTTP with a longer budget:** 10Sec needs limit=1500; a shared 500-bar batch would trim it. Sequential `ensureBars` reuses single-flight and per-TF limits.
- **Rejected leaving ticker-WS warm:** it started 1Min/5Min/1Day as interactive work on the same cold slot and ate the first pane's budget.
- **Priority instead of ChartGrid-only fetch:** Quote Panel and polls use the same queue, so two windows cannot open parallel historicals. In-flight work is never preempted (matches ADR 010: finish the one request, then take the next).

## Verification

- `py -3 -m pytest tests/test_ibkr_bars_cache.py tests/test_historical_gate.py -q` -- 13 passed (includes caller-cancel-still-caches).
- `npx vitest run src/chart src/components/ChartGrid.test.tsx` -- 41 passed (serialize, priority, abort-skip, 10Sec in grid warm).

## Follow-ups

Reload the Trader UI (and let the API `--reload` pick up `bars_cache`) to use the queue. Do not reopen WS warm unless it is droppable and cannot start until the grid queue is idle. Global `run_coro` cancel stays as-is.

## Keywords

chart bars timed out, historical queue, barsFetchQueue, bars_cache, run_coro cancel, 10Sec, IPST
