# Problem log (agent-maintained)

This file is a **shared memory** of errors fixed and problems identified in this repo. Agents should **search here first** (repo search or open this file) when symptoms look familiar.

## How agents update this file

1. **When:** After you fix a failing build, test, linter error, runtime error, or incorrect behavior; or after you identify a non-obvious root cause worth remembering.
2. **Where:** Prepend a new `##` section **immediately below** the `<!-- ENTRIES_START -->` marker (newest entries at the top).
3. **Keep it short:** A few lines per field is enough.

Entry template (copy and fill in):

```markdown
## YYYY-MM-DD — Short descriptive title

- **Symptom:** What failed or misbehaved (error text, stack trace one-liner, or user-visible behavior).
- **Cause:** Root cause in plain language.
- **Fix:** What changed (conceptually; file paths if helpful).
- **Keywords:** comma, separated, terms, for, search
```

<!-- ENTRIES_START -->

## 2026-07-13 — Level 2 Reconnecting forever on Symbol cap + stale scan age

- **Symptom:** Scanner looked unstable: header showed "updated ~5962s ago" on Movers, Level 2 for SHPH showed a book with a yellow "Reconnecting…" badge that never cleared, latency looked high.
- **Cause:** (1) IBKR depth hard-capped at 3 symbols; EHGO/GFUZ/LVLU held the slots. Concurrent `subscribe_async` calls raced through `qualifyContractsAsync` before reserving a slot (triple `reqMktDepth` for EHGO in logs). Eviction either was not loaded in the live process or did not stop `l2.continuous`, so SHPH reconnects got `Symbol cap reached` and closed the WS. DepthLadder hid that error whenever a prior book existed and only showed "Reconnecting…". (2) `App.tsx` `fetchData` wrote `lastScan` from gappers, then movers, then afterhours — after-hours timestamps freeze after the session, so Movers inherited a multi-hour-old age.
- **Fix:** Serialize depth subscribe with an asyncio lock; reserve the subscription slot before qualify; make eviction async, loop until under cap, and stop continuous L2 for the victim. DepthLadder shows backend error text even with a cached book. Tab-aware `scanAgeForTab` drives the header age.
- **Keywords:** Reconnecting depth, Symbol cap reached, IBKR_MAX_DEPTH_SYMBOLS, subscribe race, qualifyContractsAsync, updated 5962s ago, last_scan afterhours overwrite, scanAgeForTab, EHGO GFUZ LVLU SHPH

## 2026-07-13 — Level 2 Connecting depth flicker on reconnect

- **Symptom:** Side-panel Level 2 for EHGO (and others) cycled between "Connecting depth for EHGO…" and a real book, then back again, without the user changing symbols.
- **Cause:** Stacked issues. (1) `DepthLadder` treated `!connected` as "wipe the ladder", so any WebSocket close/remount replaced a healthy book with Connecting even though the last book was still in state. (2) `ws_depth` unsubscribed / stopped continuous immediately on last-viewer close, so React remounts tore down `reqMktDepth` before reattach. (3) Live probe on EHGO showed the reconnect loop was actually hitting `Symbol cap reached (3 max…)` — slots stuck on AAPL/VMAR/SHPH from earlier browsing with leaked/orphaned viewer counts, so EHGO could never hold a stable subscribe.
- **Fix:** Keep last book visible across reconnects; ignore transient empty DOM frames; surface backend error text; add `IBKR_DEPTH_RELEASE_GRACE_SEC` + `release_when_idle()`; only stop continuous / unsubscribe after grace when still idle; `_evict_for_capacity()` frees idle slots (or force-evicts a leaked one) when a new symbol needs a line.
- **Keywords:** Connecting depth, Level 2 flicker, Symbol cap reached, IBKR_MAX_DEPTH_SYMBOLS, _evict_for_capacity, DepthLadder, useIbkrDepth, release_when_idle, EHGO, AAPL VMAR SHPH slot leak

## 2026-07-13 — SMART depth requested without isSmartDepth=True (false 10092 / L1-only forever)

- **Symptom:** User bought NASDAQ TotalView but Nova only ever showed L1 (`l1_fallback=True`) for every ticker tested (SHPH, YSXT, QTTB, F, AAPL). Gateway logs showed `snapshot perms=REALTIME_TOP` and every `reqMktDepth` was rejected with error 10092 ("Deep market data is not supported for this combination of security type/exchange").
- **Cause:** `backend/ibkr/depth.py` called `ib.reqMktDepth(contract, numRows=10)` on a SMART-qualified Stock with the default `isSmartDepth=False`. IBKR requires either a *direct* exchange (e.g. `ISLAND` for TotalView) or `isSmartDepth=True` on SMART (TWS API ≥974 / BookTrader-style aggregated depth). With `False` on SMART, Gateway rejects the combination for *all* symbols — independent of TotalView entitlement. Confirming evidence after the fix: Gateway warning 2152 listed `Depth: NASDAQ; IEX` as available for AAPL.
- **Fix:** Added `IBKR_DEPTH_SMART=True` and `IBKR_DEPTH_NUM_ROWS=10` to `constants.py`. `subscribe_async` now calls `reqMktDepth(..., numRows=..., isSmartDepth=True)`; `cancelMktDepth` / L1-fallback cancel use the same flag. Regression tests in `TestSmartDepthFlag`.
- **Keywords:** Level 2, TotalView, isSmartDepth, SMART, error 10092, REALTIME_TOP, reqMktDepth, L1 fallback, AAPL depth

## 2026-07-13 — Out-of-order chart trade crashed React and blanked the entire app

- **Symptom:** Clicking/switching symbols could turn the whole Nova page black. Chrome DevTools showed an uncaught `TickerChart` exception from `lightweight-charts` ("Cannot update oldest data ...") followed by React reporting that an error occurred in `<TickerChart>` and recommending an error boundary.
- **Cause:** `TickerChart` merged REST candles with live WebSocket trades. Its update effect handled only `trade bucket == latest candle` and `else`, treating every unequal timestamp as a newer candle. A delayed/out-of-order trade whose bucket was *older* than the latest REST candle therefore reached `candleSeries.update()`. `lightweight-charts` requires monotonic time and throws on older data. The exception was uncaught, and no chart-level error boundary existed, so React unmounted the application tree. Concurrent REST requests also lacked stale-response protection, allowing a previous symbol/timeframe response to overwrite the current chart after rapid switching.
- **Fix:** Extracted chart time/order helpers to `frontend/src/tickerChartData.ts`; `TickerChart` now rejects invalid and older trade buckets before calling the chart library. REST loads use a monotonically increasing request version so stale responses cannot mutate the current chart. Added `TickerChartErrorBoundary` around the imperative chart so any future library exception degrades only the chart, not the scanner. Extracted chart controls to keep `TickerChart.tsx` at 300 lines. Added Vitest and three ordering regression tests.
- **Keywords:** blank page, black screen, TickerChart crash, Cannot update oldest data, lightweight-charts monotonic time, out-of-order WebSocket trade, stale REST response, error boundary, rapid symbol switching

## 2026-07-13 — Root logger had no console handler, slowing down live debugging

- **Symptom:** While diagnosing the Level 2 flicker (entry below), `ibkr.depth`'s `logger.info`/`warning`/`error` calls that would have shown the bug immediately (`"IBKR: subscribed depth for SHPH"`, `"depth rejected server-side..."`, etc.) never appeared in the terminal running `uvicorn`/`run_api.py` — only `uvicorn`'s own access-log lines did. Had to open and `grep` `backend/logs/blast.log` by hand to see what our own code was actually doing.
- **Cause:** `main.py` only ever attached a `RotatingFileHandler` to the root logger (`logging.getLogger().addHandler(_file_handler)`), never a `logging.StreamHandler()`. Every module logger (`logging.getLogger(__name__)`) propagates to root by default, so all of it silently went to disk only.
- **Fix:** Extracted logging bootstrap out of `main.py` into `backend/logging_setup.py` (`configure_logging()`), which now attaches both a console `StreamHandler` and the rotating file handler to the root logger with the same formatter, plus the UTF-8 console reconfiguration that previously only existed in `run_api.py` (needed for the `uvicorn main:app` direct-import dev path, which skips `run_api.py`'s entrypoint fix). This is also a `backend-modularity`/file-size-limit cleanup — `main.py` was already over its 200-line target.
- **Keywords:** invisible logs, root logger no console handler, blast.log grep, StreamHandler, propagate, live debugging slow, logging_setup.py

## 2026-07-13 — Level 2 depth ladder flickered between empty and real book after L1 fallback

- **Symptom:** After the previous L1-fallback fix (see entry below), the user still reported "I only see 'Waiting for book data'... I don't really see level 2" and the panel sometimes needing a refresh. A raw WS probe against `/ws/ibkr/depth/SHPH` showed the real bug: every real L1 tick produced **two** `book` messages back-to-back — one empty (`bids=0 asks=0 l1_fallback=False`) immediately followed by the real one (`bids=1 asks=1 l1_fallback=True`) — repeating for the life of the connection.
- **Cause:** `ib_async`'s `Wrapper.startTicker` caches `Ticker` objects per `hash(contract)`, so `ib.reqMktData(contract, ...)` called during the L1 fallback returns the **same** `Ticker` instance that `ib.reqMktDepth(contract, ...)` had already returned. `backend/ibkr/depth.py`'s `subscribe_async()` and `_fallback_to_l1()` both did `ticker.updateEvent += lambda t: ...` without ever detaching the previous listener, so after falling back both `_on_update_book` (reads `ticker.domBids`/`domAsks`, empty forever since depth was cancelled) and `_on_update_ticker` (reads `ticker.bid`/`ticker.ask`, real L1 data) stayed wired to the one shared `Ticker`. Every real tick fired both, racing an empty book against the real one straight into the same WS queue — which is exactly what made the frontend ladder flicker/never settle, independent of the async-rejection timing fixed earlier.
- **Fix:** Added `_attach_update_handler(symbol, ticker, handler)` / `_detach_update_handler(symbol)` to `backend/ibkr/depth.py`, tracking the exact listener function wired per symbol in `_update_handlers`. `_attach_update_handler` always detaches the previous listener (via `ticker.updateEvent -= handler`) before wiring the new one, used in `subscribe_async()`'s depth path, its L1-fallback except branch, and `_fallback_to_l1()`. `unsubscribe()` also detaches on cleanup. Verified live: a fresh raw WS probe against SHPH after the fix showed 60+ consecutive `book` messages, all `l1_fallback=True` with populated bid/ask, no more empty interleaved frames. Added `TestUpdateHandlerReplacement` to `tests/test_ibkr_safety.py` (shared-ticker regression test).
- **Keywords:** Level 2 flicker, DepthLadder never stable, l1_fallback race, ib_async Ticker cache, startTicker hash(contract), updateEvent double listener, reqMktDepth reqMktData same ticker, stale listener leak, _attach_update_handler, _detach_update_handler

## 2026-07-13 — Level 2 DepthLadder stuck on "Waiting for book data" forever + WS viewer-count leak

- **Symptom:** After wiring `DepthLadder` into the scanner side panel, the Level 2 section for real symbols (e.g. SHPH) never showed a book — it stayed on "Waiting for book data…" indefinitely. Separately, the user also intermittently hit a fully blank page after clicking a symbol, requiring a manual refresh.
- **Cause (Level 2 stuck):** `backend/ibkr/depth.py`'s `reqMktDepth()` call for some small-cap NASDAQ contracts (`tradingClass=SCM`) returns successfully *synchronously* (no Python exception), so the existing `try/except` around it never fires the L1 fallback. IBKR Gateway then rejects the request **asynchronously** via `errorEvent` with code `10092` ("Deep market data is not supported for this combination of security type/exchange"). Since nothing listened for that event, `_on_update_book` never ran, the depth queue stayed empty, and the WS `stream()` generator only ever sent heartbeat "ping"s — so the frontend correctly showed `connected=true, book=null` forever. Confirmed via `backend/logs/blast.log` (root logger has no console handler, so these `logger.info`/`logger.warning` calls were invisible in the terminal — only written to the rotating file).
- **Cause (viewer-count leak, related):** `routes/trading.py`'s `ws_depth` sent the `{"type": "subscribed"}` frame *before* entering the `try/finally` that pairs `ws_viewer_opened()`/`ws_viewer_closed()`. If the client disconnected in that narrow window (React StrictMode double-invoking effects, or fast symbol switching), `send_text()` itself raised `WebSocketDisconnect` outside the try block, permanently inflating the viewer refcount with no matching decrement — eventually starving the `IBKR_MAX_DEPTH_SYMBOLS` budget.
- **Cause (blank page — investigated, not reproduced in a stable session):** Reproduced twice, but only while backend/frontend files were being actively edited (uvicorn `--reload` / Vite HMR churn tearing down WebSockets mid-render). A dedicated rapid-fire click test (`agent-browser batch`, 6 clicks across 4 symbols in <5s) with no concurrent edits did **not** reproduce it — body HTML stayed intact. Likely the same dev-server churn pattern already logged below ("client ID already in use"), now also affecting the frontend Vite HMR side. No code fix applied for this specific report; flag if it recurs with a stable, non-editing session.
- **Fix:** Added `IBKR_ERROR_DEPTH_NOT_SUPPORTED = 10092` to `constants.py`. `depth.py` now installs a one-time `ib.errorEvent` listener (`_install_error_hook`) per IBKR connection; on code 10092 it matches the rejected contract by `conId` and calls `_fallback_to_l1()` (cancels the depth request, subscribes L1 top-of-book instead, sets `l1_fallback=True`) instead of leaving the book empty forever. `routes/trading.py`'s `ws_depth` now performs `ws_viewer_opened()` + the "subscribed" send + the whole stream loop inside one try/finally, with a `viewer_opened` flag so `ws_viewer_closed()` only runs when `ws_viewer_opened()` actually ran. Added `TestDepthAsyncErrorFallback` (4 tests) to `tests/test_ibkr_safety.py`.
- **Keywords:** Level 2 waiting for book data, depth ladder stuck, IBKR error 10092, Deep market data is not supported, reqMktDepth async rejection, errorEvent, L1 fallback, ws_viewer_opened leak, blast.log, root logger no handler, blank page needs refresh, React StrictMode double effect, WebSocketDisconnect outside try

## 2026-07-13 — Ticker detail panel stuck on frozen premarket gapper price while movers table stayed live

- **Symptom:** With `discovery_provider=ibkr`, a symbol's ticker detail panel showed a stale price/prev_close (e.g. VEEE: price=12.01, prev_close=4.34) while the exact same symbol's row in the Gainers/Losers table was live and correct (price=25.05, prev_close=4.82). Confirmed via direct API comparison (`/api/movers` vs `/api/ticker/{symbol}`) — not a caching/browser issue.
- **Cause:** `_find_ibkr_cache_row()` in `main.py` searched `(_gapper_cache, _gainer_cache, _loser_cache)` in that order and returned the first match. Gappers intentionally stop refreshing once the market formally opens (see the "Market Open Halt" rule), so `_gapper_cache` holds a permanently frozen premarket snapshot for any symbol discovered as a gapper earlier in the session. When that same symbol later also becomes an active gainer/loser (continuously repriced every `IBKR_REPRICE_INTERVAL_SEC` by `_reprice_ibkr_caches`), the lookup kept resolving to the frozen gapper row instead of the live gainer/loser row, because gapper cache was checked first. `_fetch_ticker_snapshot_ibkr` (used by the ticker detail endpoint) relies on this helper, so the detail panel inherited the stale value while `/api/movers` (which reads `_gainer_cache`/`_loser_cache` directly, bypassing the helper) stayed correct.
- **Fix:** Reordered the search in `_find_ibkr_cache_row()` to `(_gainer_cache, _loser_cache, _gapper_cache)` so a live gainer/loser row always wins over a frozen gapper row for the same symbol; gapper cache is now only consulted as a fallback for symbols that aren't an active mover. Also removed leftover `[DEBUG]` print statements and a throwaway `_debug_timing.py` script used to diagnose this. Added `backend/tests/test_ibkr_cache_priority.py` covering the priority order.
- **Keywords:** ticker detail stuck, ticker panel stale, VEEE, _find_ibkr_cache_row, _fetch_ticker_snapshot_ibkr, gapper cache frozen, market open halt, IBKR discovery provider, movers table vs ticker detail mismatch

## 2026-07-13 — IBKR-sourced mover rows had internally inconsistent price/change fields

- **Symptom:** After switching `discovery_provider` to `ibkr`, some `/api/movers` rows showed `price - prev_close != change_abs` and `change_abs / prev_close != change_pct` (e.g. VEEE: price=24.42, prev_close=4.34, but change_abs=19.6 when it should be 20.08).
- **Cause:** `_handle_trade` (Alpaca's WS trade stream handler in `main.py`) always overlays the latest Alpaca trade price onto `_gainer_cache`/`_loser_cache` rows regardless of which provider built them, via `_apply_trade_to_mover_list`. It recomputes `change_pct`/`change_abs` from the row's own `prev_close`, so each individual update stays self-consistent — but it runs on Alpaca's own price ticks, which race against the periodic IBKR scan tick (every `GAINERS_INTERVAL_SEC`) that rebuilds the same rows from a different snapshot basis. The two feeds interleaving on the same cache produced rows whose fields were correct at two different instants, not one.
- **Fix:** Added an early return in `_handle_trade` when `_get_discovery_provider() == "ibkr"`, so Alpaca's WS overlay no longer touches gapper/mover caches while IBKR is the active provider. IBKR-sourced rows now only refresh on the scan cadence (20s), which is internally consistent by construction.
- **Keywords:** discovery provider, IBKR scanner, prev_close mismatch, change_pct inconsistent, _handle_trade, _apply_trade_to_mover_list, WS overlay race, movers endpoint

## 2026-07-13 — Live IB Gateway without paper; spend risk

- **Symptom:** User could not complete paper Gateway login; logged into live Gateway with real funds while wiring Nova.
- **Cause:** Paper account uses a separate username; Gateway “Paper Trading” mode must use that paper user. Connection mode was previously tied to `IBKR_LIVE_TRADING_CONFIRMED`, conflating data vs orders.
- **Fix:** `IBKR_GATEWAY_MODE` for port; `IBKR_ORDERS_ENABLED` default false; `ibkr/safety.py` SSOT blocks all place/bracket until unlocked.
- **Keywords:** IBKR live Gateway, paper trading, ORDERS_ENABLED, safety.py, spend lock, Level 2

## 2026-07-12 — News/hotness column missing from Gappers, Movers, After Hours tables

- **Symptom:** The red/orange/yellow news-freshness indicator was gone from the main scanner tables (only visible on the separate Catalysts tab).
- **Cause:** An earlier densify pass (`73acb8c`) trimmed `SCANNER_COLUMNS` in `frontend/src/constants.ts` down to 8 columns and dropped the `['newest_headline_at', 'News']` entry. The render path (`NewsCell`, the `case 'newest_headline_at'` in `renderCell`, and the `.news-flame`/`.flame-hot`/`.flame-warm`/`.flame-cool` CSS) was never removed — it just had nothing pointing to it since `SCANNER_COLUMNS` drives which columns `ScannerTable` renders.
- **Fix:** Re-added `['newest_headline_at', 'News']` to `SCANNER_COLUMNS` (after `Volume`, closest to the pre-densify layout). No changes needed in `ScannerTable.tsx` — the rendering logic was already intact.
- **Keywords:** News column missing, newest_headline_at, NewsCell, flame-hot, flame-warm, flame-cool, SCANNER_COLUMNS, densify regression

## 2026-07-11 — Sidebar chart sat beside Stock Quote again (layout regression)

- **Symptom:** After a layout update, single-click sidebar showed Price Chart and Stock Quote side-by-side; user had previously had chart on its own top row.
- **Cause:** JSX was stacked (chart then `.cq-info-row`) but `.cq-root--columns` CSS still used `display:grid` with three columns, so the chart and info-row became peer grid cells. `.chart-grid` styles for the full-page 2×2 were also missing.
- **Fix:** Root is now flex column (`cq-root--stacked`); multi-col only on `.cq-info-row`. Added `.chart-grid { grid-template-columns: 1fr 1fr }`.
- **Keywords:** sidebar regression, cq-root--columns, cq-root--stacked, chart beside quote, chart-grid 2x2

## 2026-07-11 — Single-click must keep sidebar; full page is double-click only

- **Symptom:** After the prior fix, any ticker click replaced the scanner with a full detail page — removing the side panel UX users still wanted for quick lookup.
- **Cause:** `selectedSymbol` was overloaded to mean “navigate to full page,” so single-click left the scanner.
- **Fix:** Split state: `selectedSymbol` → `SidePanel` only; `tradingSymbol` → `TickerDetailPage`. Symbol rows use `SymbolSelectButton` (click / double-click). Back clears `tradingSymbol` only.
- **Keywords:** double-click, SidePanel, tradingSymbol, selectedSymbol, TickerDetailPage, SymbolSelectButton

## 2026-07-11 — Clicking a ticker did not open a trading/detail screen with charts

- **Symptom:** User clicked a symbol and expected a dedicated trading/detail view with graphs; the UI stayed on the scanner with only a narrow side panel (often perceived as “no graphs”).
- **Cause:** `selectedSymbol` only drove `SidePanel` beside the scanner — there was no full-page navigation. Charts existed in the 380px panel but did not replace the main content.
- **Fix:** When `selectedSymbol` is set, `App.tsx` renders `TickerDetailPage` (Back + large `TickerChart` + fundamentals) instead of the scanner layout. Extracted `useTickerStream`, `TickerDetailContent`, types/formatters. Empty bars fall back to mock candles for drawing-tool verification.
- **Keywords:** ticker click, SidePanel, TickerDetailPage, chart missing, navigation, drawing tools, mock bars

## 2026-07-11 — `validate_trade_plan` accepted inverted longs and rejected exact $0.20 stops

- **Symptom:** (1) A long plan with stop *above* entry (e.g. entry `$5.00`, stop `$5.10`, target `$5.30`) could pass risk validation because distances used `abs()`. (2) A correct plan with stop exactly `$0.20` below entry (entry `$5.00`, stop `$4.80`) was rejected with "Stop of $0.20 exceeds the $0.20 max."
- **Cause:** (1) Absolute-value distance math treated upside-down longs as valid. (2) Binary float: `5.0 - 4.8 == 0.20000000000000018`, so `stop_distance > RISK_MAX_STOP_DOLLARS` was True at the exact ceiling.
- **Fix:** `backend/strategy/risk.py` `validate_trade_plan` now requires stop `<` entry and target `>` entry for longs, and rounds stop/reward distances to 2 decimal places (cents) before comparing to `RISK_MAX_STOP_DOLLARS` / computing R:R. Locked by `tests/test_arithmetic_correctness.py` and extended `tests/test_risk.py`.
- **Keywords:** validate_trade_plan, abs stop distance, inverted long, float precision, RISK_MAX_STOP_DOLLARS, 0.20 exceeds 0.20, round cents, profit loss ratio

## 2026-07-11 — `electron-builder` fails with `EPERM: ... rename 'release\win-unpacked.tmp' -> 'release\win-unpacked'`

- **Symptom:** `npm run electron:pack` (and a bare `npx electron-builder --win nsis --x64` retry) consistently failed at the packaging step with `⨯ EPERM: operation not permitted, rename '...\release\win-unpacked.tmp' -> '...\release\win-unpacked'`, immediately after `downloaded label=electron progress=100%`. The failure was 100% reproducible on retry (not a one-off), which ruled out the usual "transient antivirus scan" explanation. Manually deleting `release\win-unpacked.tmp` between attempts worked fine (proving the *directory* itself, not a locked file inside it, was the problem) — `[System.IO.File]::Open(...,'ReadWrite','None')` on the largest file in that folder (`electron.exe`) succeeded with no lock, confirming no single file was held open.
- **Cause:** Windows (unlike Linux/macOS) refuses to rename a directory while **any process holds an open handle on that directory itself or one of its ancestors** — even a read-only file-system-watch handle, not just a write lock. `Run Nova Desktop.bat` (`npm run electron:dev`) was left running in the background from an earlier step in the same session; its Vite dev server (chokidar-based file watcher) held a recursive watch handle rooted at `frontend/`. Because `electron-builder`'s output dir (`frontend/release/`) lives *under* that same watched root, extracting the electron.zip into `release\win-unpacked.tmp` and then renaming it inherited an ancestor-directory lock from the still-running watcher, so the rename was denied every time, regardless of retries.
- **Fix:** Stopped the dev Electron/Vite process tree (`taskkill /F /T /PID <bat-process-pid>`) before repackaging. Deleted the stale `release\win-unpacked.tmp` (now deletable, confirming the lock was gone) and re-ran `npx electron-builder --win nsis --x64` — succeeded immediately. **Going forward:** never run `npm run electron:pack` / `electron-builder` while `electron:dev` (or any other recursive watcher rooted at or above `frontend/`, e.g. a bare `vite`/`tsc --watch`) is running in the same workspace tree; stop dev watchers first, package, then restart dev mode if still needed.
- **Keywords:** electron-builder EPERM rename win-unpacked.tmp, electron-builder packaging fails Windows, directory rename access denied Windows open handle, chokidar file watcher directory lock, vite dev server holds directory handle, electron:pack fails while electron:dev running, NSIS build EPERM

## 2026-07-11 — Backend API served stale code after `taskkill /F` on a `uvicorn --reload` PID

- **Symptom:** `GET /api/journal/metrics` consistently returned a JSON payload missing the newly added `includes_mock_data` field, even after multiple `WatchFiles detected changes ... Reloading...` cycles confirmed in the uvicorn log and even though calling `compute_metrics()` directly via `py -3 -c` in the same shell/cwd returned the correct, up-to-date dict. `netstat -ano | findstr :8000` showed **two** PIDs both `LISTENING` on `127.0.0.1:8000`, one of which (`tasklist`/`Get-Process`) belonged to a genuinely running `python3.13.exe` using ~264MB of memory that was never referenced by the current terminal's uvicorn output.
- **Cause:** Earlier in the session, port 8000 was already bound by a stale backend from a previous run. `taskkill /F /PID <that-pid>` was used to free the port — but that PID was the **outer process** in the `uvicorn --reload` parent/child pair (the reloader process spawns a separate worker subprocess that actually serves requests). Force-killing only the outer PID left the **child worker orphaned**, still bound to the port and still serving the old, pre-edit code. A brand-new `uvicorn --reload` was then started successfully on the same port (Windows allowed a second `LISTENING` socket to coexist), so two servers were live simultaneously: the new one with fresh code (receiving my direct test requests inconsistently) and the orphaned old one (pinned to the frontend's already-established keep-alive HTTP connections, so the running UI kept talking to stale code no matter how many times the new code reloaded).
- **Fix:** Identified the orphan via `tasklist | findstr python` cross-referenced against the uvicorn terminal log's own reported PIDs, then `taskkill /F /PID <orphan-worker-pid>` (not the reloader PID) to kill the actual leftover worker. After that, `netstat` showed exactly one `LISTENING` entry and the API immediately returned current code. **Going forward:** when a port conflict requires killing a prior `uvicorn --reload` instance, kill the entire process tree (e.g. `taskkill /F /T /PID <pid>` to include child processes) rather than a single PID, and afterward verify with `netstat -ano | findstr :PORT | findstr LISTENING` that only one PID remains before trusting any response from that port.
- **Keywords:** uvicorn --reload orphan process, stale code served, duplicate LISTENING socket same port Windows, taskkill /F leaves child worker running, WatchFiles reload not reflected, FastAPI response missing new field, netstat two PIDs same port, taskkill /T process tree

## 2026-07-10 — UnicodeEncodeError crashing the API process on Windows console output

- **Symptom:** Log/print statements containing non-ASCII characters (e.g. `→`) raised `UnicodeEncodeError: 'charmap' codec can't encode character ... : character maps to <undefined>` when run from a plain Windows console/`cmd.exe` window. The error persisted even after adding a console-stdio fix (below) — it kept firing from inside `logging.StreamHandler.emit`.
- **Cause:** Two separate encoding gaps, found by live-running the app after the first fix:
  1. Windows consoles default to the `cp1252` codepage for Python's `stdout`/`stderr`, which cannot represent most Unicode characters. `uvicorn --reload` also spawns a fresh child interpreter via `multiprocessing.spawn`, which re-reads `PYTHONIOENCODING` from the environment at startup rather than inheriting the parent's already-reconfigured streams.
  2. **Root cause of the residual crash:** `backend/main.py` creates a `logging.handlers.RotatingFileHandler("blast.log", ...)` with no `encoding=`/`errors=` argument. Python opens files with the platform's locale-preferred encoding (`cp1252` on Windows) and **strict** error handling by default — unlike `sys.stderr`, which Python already defaults to `errors="backslashreplace"`. So even with console stdio fixed, the file handler alone still raised on any non-ASCII character.
- **Fix:** `backend/run_api.py` calls `_force_utf8_io()` before importing `uvicorn` (sets `PYTHONIOENCODING=utf-8:backslashreplace` / `PYTHONUTF8=1` env vars plus `sys.stdout`/`stderr.reconfigure(...)`) to cover console output. `backend/main.py`'s `RotatingFileHandler` now passes `encoding="utf-8", errors="backslashreplace"` explicitly to cover the log file. Verified by actually starting the app (`scripts/Start-NovaApi.ps1`) after each change — the first fix alone still crashed; both together started clean. `tools/course_memory/recall.py` now also reconfigures its own stdout/stderr before printing arbitrary Obsidian or Pinecone content; replacing one literal arrow was insufficient because retrieved notes can contain any Unicode character.
- **Keywords:** UnicodeEncodeError, charmap codec, cp1252, Windows console encoding, PYTHONIOENCODING, PYTHONUTF8, uvicorn --reload multiprocessing spawn, stdout reconfigure, RotatingFileHandler encoding, logging FileHandler default encoding strict errors

## 2026-07-10 — pytest collection SyntaxError "source code string cannot contain null bytes"

- **Symptom:** `py -3 -m pytest backend/tests/test_ibkr_safety.py` failed at collection with `SyntaxError: source code string cannot contain null bytes`, even though the test file itself had no syntax errors.
- **Cause:** `backend/tests/__init__.py` was created via PowerShell `'' | Out-File 'backend/tests/__init__.py'`, which defaults to **UTF-16 with BOM** encoding on Windows PowerShell. Python's import machinery reads `.py` files as UTF-8/ASCII by default, so the UTF-16 null bytes between characters were interpreted as literal null bytes, breaking the package import before the test module itself was even reached.
- **Fix:** Rewrote `backend/tests/__init__.py` using the `Write` tool (which writes plain UTF-8, no BOM) instead of PowerShell `Out-File`/`echo` redirection.
- **Keywords:** SyntaxError, null bytes, pytest collection error, UTF-16 BOM, PowerShell Out-File, __init__.py encoding, Windows

## 2026-05-04 — GitHub Actions invalid workflow due to secrets in job conditional

- **Symptom:** GitHub Actions Check Suite failed immediately with "Invalid workflow file... Unrecognized named-value: 'secrets'". The deploy didn't trigger in Railway.
- **Cause:** GitHub Actions does not allow accessing `secrets.*` within job-level `if` conditionals. The expression `secrets.RAILWAY_TOKEN != ''` caused a parsing error that failed the entire workflow before any jobs could run.
- **Fix:** Removed the secret check from the job's `if` condition in `.github/workflows/deploy.yml`. Instead, moved the check into the `Deploy backend service` bash step, where it verifies `[ -z "$RAILWAY_TOKEN" ]` and safely exits if the token is omitted.
- **Keywords:** GitHub Actions, Invalid workflow file, Unrecognized named-value: 'secrets', job conditional, deploy.yml
## 2026-04-28 — Empty gapper list after server restart (SIP feed not supported)

- **Symptom:** No gappers appeared after starting the backend despite many market gaps. Logs showed: `Alpaca WS auth failed: code 409, 'insufficient subscription'` (repeating), `avg_volume bars API returned 403: "subscription does not permit querying recent SIP data"`, `HOD Momo enrichment: snapshot fetch returned empty`. `gappers-2026-04-28.json` contained `{"gappers": []}`.
- **Cause:** `_get_feed()` defaulted to `"sip"` (hardcoded fallback) when `ALPACA_DATA_FEED` was not set in `.env`. The user's Alpaca account only supports the IEX (free) feed, so all SIP REST calls got 403 and the SIP WebSocket got 409 — resulting in zero data.
- **Fix:** Changed default to `"iex"` via `DATA_FEED_DEFAULT` in `constants.py`. Added auto-fallback (`_try_fallback_to_iex()`) triggered on 403 REST and 409 WS errors. Added UI Settings dropdown for feed selection. Set `ALPACA_DATA_FEED=iex` in `.env`.
- **Keywords:** gappers empty, SIP, IEX, 403, 409, insufficient subscription, data feed, ALPACA_DATA_FEED, fallback

## 2026-04-23 — GitHub Actions “Backend tests” exit 5 with no tests

- **Symptom:** `CI / Deploy` failed on **Backend tests** with “Process completed with exit code 5”; **Frontend build** passed; **Deploy to Railway** skipped.
- **Cause:** `pytest` exits **5** when no tests are collected. The workflow intended to treat 5 as success, but GitHub’s `bash` runs with **`set -e`**, so the shell exited as soon as `pytest` returned 5—before `PYTEST_EXIT=$?` and the `if` ran.
- **Fix:** Run pytest under `set +e`, capture `$?`, then `set -e` and branch on 5 vs other codes.
- **Keywords:** GitHub Actions, pytest, exit code 5, set -e, errexit, no tests collected

## 2026-04-23 — Railway “Wait for CI” skipped frontend; GitHub Actions failed

- **Symptom:** Frontend deployments **SKIPPED** with “CI check suite failed”; backend kept updating; latest UI commits never went live.
- **Cause:** `frontend/scripts/check-railway-api-base.mjs` treated **any** environment with `RAILWAY_PROJECT_ID` as a Railway build. That variable is sometimes copied into **GitHub Actions** repo/org variables; GitHub runners are not Railway, and `VITE_API_BASE_URL` is often unset there → `prebuild` exited 1 → `frontend-build` job failed.
- **Fix:** Require `RAILWAY_PROJECT_ID && !GITHUB_ACTIONS` for the strict check; add a bash default `VITE_API_BASE_URL` in `.github/workflows/deploy.yml` for the build step.
- **Keywords:** Wait for CI, GitHub Actions, RAILWAY_PROJECT_ID, prebuild, frontend-build, skipped

## 2026-04-23 — HOD Momo tab still invisible after tab-bar `overflow-x: auto`

- **Symptom:** Production showed only Gappers / Movers / After Hours / Catalysts; **HOD Momo** never appeared even after adding horizontal scroll on `.tab-bar`.
- **Cause:** `.tab-spacer { flex: 1 }` sat between the tab buttons and “updated … ago” in the **same** flex row. The spacer kept absorbing free space in a way that blocked a proper `min-width: 0` scroll region, so the fifth tab stayed clipped.
- **Fix:** Wrap only the tab `<button>`s in `.tab-bar-scroll` (`flex: 1; min-width: 0; overflow-x: auto`); keep the scan-age as a sibling with `flex-shrink: 0`; remove `.tab-spacer`.
- **Keywords:** HOD Momo, tab bar, flex, overflow, tab-spacer, clipped

## 2026-04-23 — Railway frontend “unreachable” while `/config.json` returned 200

- **Symptom:** Backend healthy; frontend still disconnected; fetching `/config.json` on the frontend host returned HTTP 200 but HTML, not JSON.
- **Cause:** Static hosting SPA fallback served `index.html` for unknown paths when `config.json` was absent from `dist` (postbuild skipped or file not deployed). Bootstrap treated the failed JSON path as failure and fell back to `http://localhost:8000`.
- **Fix:** Inject `<meta name="nova-api-base">` at Vite build from `process.env.VITE_API_BASE_URL`; read meta first in `resolveApiBase`. Validate `/config.json` bodies look like JSON before parsing.
- **Keywords:** Railway, static, SPA fallback, config.json, VITE_API_BASE_URL, localhost, CORS

## 2026-04-23 — `/api/health` stuck at `{"status":"loading",...}` on Railway

- **Symptom:** Hitting the deployed `/api/health` always returned `loading` with `latency_ms: 0`; UI appeared broken; browser console empty for that symptom.
- **Cause:** `_cached_health` defaults to `loading` and is only updated by `_ping_health()` (Alpaca `/v2/account`). Lifespan called `_ping_health` only when `_alpaca_headers()` was non-`None`. With **no** `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` in the Railway Backend environment, the ping never ran and scans returned early without updating health.
- **Fix:** If credentials are missing at startup, set `_cached_health` to `error` with a clear message and `logger.warning(...)`.
- **Keywords:** health, loading, APCA_API_KEY_ID, APCA_API_SECRET_KEY, Railway, Alpaca, lifespan

## 2026-04-23 — Production UI “backend unreachable” (follow-up: Vite inlining missing)

- **Symptom:** After setting `VITE_API_BASE_URL` on Railway, the hosted UI still showed “Backend unreachable”; the production JS bundle still referenced `http://localhost:8000` only.
- **Cause:** Some Railway frontend builds did not substitute `import.meta.env.VITE_API_BASE_URL` into the emitted chunks even when the variable existed in the dashboard (stale asset hash `index-B-3w0dfo.js` unchanged), so the browser never called the real backend URL.
- **Fix:** Emit `dist/config.json` in `postbuild` from `VITE_API_BASE_URL` / `NOVA_API_BASE`, and resolve the API base in `main.tsx` before loading `App` (fetch `/config.json` when Vite did not inline). `constants.ts` prefers `window.__NOVA_API_BASE__` from that bootstrap.
- **Keywords:** Railway, Vite, VITE_API_BASE_URL, config.json, runtime bootstrap, backend unreachable, localhost

## 2026-04-23 — Production UI “backend unreachable” while Railway backend is healthy

- **Symptom:** Hosted frontend on Railway stayed on loading then showed disconnected / “Backend unreachable”; `curl` to the backend `/api/health` and `/api/gappers` returned 200. Downloaded production `assets/index-*.js` still contained `localhost` / `:8000`, not the Railway backend hostname.
- **Cause:** `VITE_*` variables are inlined at **Vite build time**. Setting `VITE_API_BASE_URL` in the Railway dashboard without a **new** frontend build left the old bundle. Optional: GitHub Actions was configured for `main` only while the repo default branch is `master`, so “wait for CI” could block or never align with pushes.
- **Fix:** Documented behavior via a `prebuild` script that exits non-zero on Railway when `VITE_API_BASE_URL` is unset. Extended `.github/workflows/deploy.yml` to `main` and `master` (including the deploy job condition). Operators must **Redeploy** the Frontend service after setting or changing the variable.
- **Keywords:** Railway, Vite, VITE_API_BASE_URL, build time, CORS, backend unreachable, localhost, Wait for CI, master branch

## 2026-04-16 — Railway Railpack “could not determine how to build” on monorepo root

- **Symptom:** Railway build failed with Railpack: `Script start.sh not found`, `Railpack could not determine how to build the app`, and the analyzed tree showed the full repo (`.cursor/`, `backend/`, `frontend/`, etc.) with no Python at the service root.
- **Cause:** Default builder Railpack only inspects the configured build root. With **Root Directory** left at the repo root, there is no `requirements.txt` or `pyproject.toml` at `./` (Python lives under `backend/`). The old `backend/railway.toml` alone is not applied unless the service points “Config as code” at `/backend/railway.toml`, and `builder = "nixpacks"` is ignored when the platform defaults to Railpack.
- **Fix:** Added a **root `railway.toml`** that sets `builder = "DOCKERFILE"` and `dockerfilePath = "Dockerfile"`, plus a **root `Dockerfile`** that `COPY backend/` and runs uvicorn on `$PORT`. Added **`backend/Dockerfile`** and switched **`backend/railway.toml`** to the same Docker builder for deployments where Root Directory is `backend`. Added **`.dockerignore`** to shrink build context.
- **Keywords:** Railway, Railpack, monorepo, Dockerfile, root directory, Nixpacks, build failed, start.sh

## 2026-04-16 — Volume frozen in scanner lists and ticker detail panel despite continuous data loading

- **Symptom:** Volume column in gapper/mover tables never updated while price changed in real time. Ticker detail panel "Volume" field also stuck at the value fetched on initial load. Zero-volume tickers showed `—` instead of `0`.
- **Cause:** (1) `_handle_trade()` only read `S` (symbol) and `p` (price) from the Alpaca trade WS message, discarding `s` (trade size). (2) `_broadcast_trade_update()` payload had no volume field, so ticker-detail WS clients never received updated volume. (3) `fmtVolume()` used `if (!v)` which treats `0` as falsy.
- **Fix:** `_handle_trade` now extracts `size = int(msg.get("s") or 0)` and adds it to the `volume` field of every updated cache entry (gapper, after-hours, gainer, loser). `_apply_trade_to_mover_list` accepts a `size` param and accumulates it. `_handle_trade` returns the new cumulative volume. `_ws_stream_loop` passes that to `_broadcast_trade_update`, which now includes `volume` in its JSON payload. Frontend `TickerTradeUpdate` interface gains `volume: number | null`; the `trade_update` handler updates `daily_bar.volume` and recomputes `rel_volume` accordingly. `fmtVolume` changed to `if (v == null)`. Drift from WS gaps self-heals via the existing periodic `_fetch_snapshots` scan loop.
- **Keywords:** volume, fmtVolume, _handle_trade, _broadcast_trade_update, trade size, real-time, accumulate, daily_bar, TickerTradeUpdate, rel_volume

## 2026-04-16 — Gapper gap % wrong during pre-market (using day-before-yesterday close)

- **Symptom:** Pre-market gapper table showed inflated gap percentages (e.g., BIRD +432% instead of -22%). Stocks with a large yesterday move appeared as massive gappers even if they were gapping DOWN in pre-market. Stock quote panel also showed wrong change % vs previous close.
- **Cause:** Alpaca snapshot `prevDailyBar` semantics differ by session. During pre-market (before 9:30 ET), `dailyBar` = yesterday's completed regular session bar, and `prevDailyBar` = the session before that (two days ago). The code always used `prevDailyBar.c` as "previous close" regardless of session, so during pre-market it computed gap vs the wrong reference (two days ago vs yesterday).
- **Fix:** Added `_pick_prev_close(snap)` helper in `backend/main.py` that inspects `dailyBar.t` (the bar timestamp). If the bar's date in ET is before today, `dailyBar` is yesterday's close and is returned. Otherwise returns `prevDailyBar.c`. Updated `_compute_gappers()` and `_run_focus_scan()` to use this helper. Updated `_fetch_ticker_snapshot()` to expose `prev_close`, `session_close`, `session_prev_close` fields. Frontend `TickerDetailContent` now uses `snap.prev_close` and shows a Webull-style two-line quote (main line = last regular-session close, sub-line = Pre:/After: with extended-hours price and change vs session close) during pre-market/after-hours.
- **Keywords:** gapper, prev close, prevDailyBar, dailyBar, pre-market, gap percent, Alpaca snapshot, bar timestamp, session close, two-line quote, pre-market quote

## 2026-04-15 — Quote side panel flashes empty / “screen disappears” on ticker click

- **Symptom:** Clicking a scanner row to open a quote briefly blanked the side panel or showed “No data found” before the spinner or quote appeared.
- **Cause:** After `selectedSymbol` updates, React renders **once before** the WebSocket `useEffect` runs. In that frame `loading` and `refreshing` were still false and `detail` was null, so the UI matched the **empty-state** branch (`!loading && !refreshing && !detail && selectedSymbol`). Runtime logs (`panel_branch` with `showEmpty: true` then `showSpinner: true`) confirmed the ordering.
- **Fix:** Treat that pre-effect gap as loading: `awaitingPreEffectFrame = selectedSymbol && !detail && !loading && !refreshing && !fetchFailed`, and `showFullSpinner = loading || awaitingPreEffectFrame`. Show “No data found” only when `fetchFailed` is set after a real WS close/error without an `initial` message (not StrictMode cleanup).
- **Keywords:** side panel, ticker click, flash, empty state, useEffect ordering, WebSocket, quote, StrictMode

## 2026-04-15 — After-hours tab: strong ticker missing despite large move (e.g. MAMO)

- **Symptom:** A symbol looked like a clear after-hours mover (large % change, volume) but never appeared on the After Hours list / tab count stayed low; manual Alpaca snapshot showed a large move vs `dailyBar.c`.
- **Cause:** The gap math and 10% threshold were fine. Alpaca’s `/v2/assets/{symbol}` can return **`tradable: false`** for an otherwise active listing (e.g. `overnight_halted` while another mover like AREB stays `tradable: true`). The scanner only requested snapshots for symbols passing **`tradable`** in `_get_tradable_symbols`, so those names were never scanned.
- **Fix:** Added `SCAN_REQUIRE_TRADABLE` (default `True`) and env **`BLAST_SCAN_REQUIRE_TRADABLE`** (`true`/`false`) so operators can include non-tradable active listings when needed; documented in `constants.py`.
- **Keywords:** after hours, MAMO, tradable false, Alpaca assets, scan universe, overnight_halted, BLAST_SCAN_REQUIRE_TRADABLE

## 2026-04-15 — Alpaca WS “connection limit exceeded” (406) and stale live prices

- **Symptom:** Scanner UI did not update second-by-second; backend log showed repeated `Alpaca WS auth failed` with `code: 406`, `msg: 'connection limit exceeded'`. Sometimes two “connecting” lines appeared close together in `blast.log`.
- **Cause:** `uvicorn --reload` without the `watchfiles` package falls back to **StatReload**, which ignores `--reload-exclude`. The rotating log (`backend/logs/blast.log`) and disk cache (`backend/.cache/`) changed frequently; each change restarted the worker. Overlapping processes each tried to open Alpaca’s market-data WebSocket; Alpaca allows **one** concurrent WS per API key, so new workers got 406 until slots cleared. Multiple long-lived terminals could also leave several backends running at once, making the limit worse.
- **Fix:** Add `watchfiles` to `backend/requirements.txt` so reload exclusions apply; pass `--reload-exclude logs --reload-exclude .cache` in `Run Stock Alert.bat`; keep `ALPACA_WS_BACKOFF_CAP` at 60s to avoid hammering reconnects. When debugging, kill **all** `python3.13` / uvicorn workers (not only `py.exe`) and avoid running several API instances in parallel.
- **Keywords:** Alpaca, WebSocket, 406, connection limit exceeded, uvicorn reload, StatReload, watchfiles, reload-exclude, blast.log, .cache, gappers.json, live data, stale

<!-- (New entries go above this comment; keep newest at top.) -->
