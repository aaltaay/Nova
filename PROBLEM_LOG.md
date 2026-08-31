# Problem log (agent-maintained — MANDATORY)

This file is a **shared memory** of errors fixed and problems identified in this repo. Agents should **search here first** (repo search or open this file) when symptoms look familiar.

**Mandatory for every agent** in this project (parent sessions and all Nova specialists). Rule: `.cursor/rules/problem-log.mdc`. Fixing a bug without a new entry here is a constitution violation. Lifecycle footers must declare `problem_log=<entry>|skipped|n/a`.

## How agents update this file

1. **When:** After you fix a failing build, test, linter error, runtime error, or incorrect behavior; or after you identify a non-obvious root cause worth remembering. **Required** — not optional for “obvious” or “quick” fixes.
2. **Where:** Prepend a new `##` section **immediately below** the `<!-- ENTRIES_START -->` marker (newest entries at the top).
3. **Keep it short:** A few lines per field is enough.

Entry template (copy and fill in):

```markdown
## YYYY-MM-DD — Short descriptive title

- **Symptom:** What failed or misbehaved (error text, stack trace one-liner, or user-visible behavior).
- **Cause:** Root cause in plain language.
- **Fix:** What changed (conceptually; file paths if helpful).
- **Fix class:** admission | ownership | surfacing | infra — see below.
- **Keywords:** comma, separated, terms, for, search
```

**Fix class** (added 2026-08-24) makes repeat-offender areas visible:

| Class | Meaning |
|-------|---------|
| `admission` | Changed the contract for whether data exists at all (a row, a record, a cache entry) |
| `ownership` | Changed who writes a piece of state, or fencing / quiet windows between writers |
| `surfacing` | Only changed how a failure is displayed or logged; the failing mechanism still works the same way |
| `infra` | Dependency, loop, transport, packaging, or process-level fix |

If a symptom keeps returning and every prior entry is `surfacing`, stop patching the
message and go read the admission contract. Ten consecutive `surfacing` fixes on empty
scanners is exactly how the 2026-08-24 outage survived for a year.

<!-- ENTRIES_START -->

## 2026-08-31 -- IBKR session frozen 7h with Gateway port open; "Open Gateway" button did nothing

- **Symptom:** User reported "im clicking this and still not attaching itself properly." `/api/ibkr/status` showed `connected: false` while `transport_connected: true` and `preferred_port_reachable: true` (IB Gateway itself healthy, logged in, port 4001 listening the whole time). `/readyz` showed `state: degraded, unusable_since` 7+ hours in the past. Last log line from the dialer was `earn_usable begin (connect)` / `positions cache refreshed after connect` at 00:15:05 -- nothing after, ever, until restart at 08:18. `py-spy` confirmed the IB-loop OS thread was genuinely idle (short-timeout `select()`, matching the loop-lag sampler's own cadence), i.e. an asyncio-level stuck await, not an OS-level deadlock. The Trading prerequisites checklist showed "Log into IB Gateway" (2FA copy) even though the socket was up and 2FA was already done; "Open live Gateway" only focused the (already-focused, already-healthy) Gateway window and returned `already_listening` -- a guaranteed no-op in this exact state.
- **Cause:** Three compounding design gaps, all rooted in the same assumption ("the dialer task will notice its own problem"): (1) `refresh_completed_orders_cache`'s `cold_slot(label="completed_orders")` lock acquire (`ibkr/ib_scheduler.py`) had no timeout -- a stranded/never-released holder (or a stuck `reqCompletedOrdersAsync` whose cancellation the underlying `ib_async` call did not honor) blocked every future cold job forever with zero exception and zero log line. (2) `earn_usable`'s warm-up phase had no *overall* deadline on top of each inner call's own timeout, so a bypass of any inner bound hung the whole promotion-to-READY step. (3) The "stuck unusable > 30s, force reconnect" watchdog lived *inside* `session_reconnect.handle_transport_up_unusable` -- the same dialer task it was supposed to rescue -- so once that task itself froze, the watchdog could never run again. Separately, `gatewayPortOpenButSessionDown()` (frontend) required `ibkrTransportConnected !== true` to show the honest "Reconnect" CTA, so the exact stuck state (transport *up*, session not READY) fell through to the "log into Gateway" 2FA copy instead. And `launch_or_focus_gateway`'s `already_listening` branch decided purely from the TCP port, never checking Nova's own `is_ready()`, so the button had no path to actually fix a frozen session.
- **Fix:** New `ibkr/session_watchdog.py` -- an independent sibling IB-loop task (spawned via `loop_supervisor.spawn_ib`, alongside the loop-lag sampler, which proved sibling tasks survive a frozen dialer since it kept sampling the whole 7 hours) that owns stuck-unusable force-reconnect *and* a dialer heartbeat check (`session_reconnect.dialer_heartbeat_age_sec()`, stamped at the top of every `_reconnect_once`); a dead or heartbeat-stale dialer gets its IB object discarded and the task cancelled+respawned. `ib_scheduler.cold_slot` now bounds its lock acquire (`IBKR_COLD_SLOT_ACQUIRE_TIMEOUT_SEC`) and raises `ColdSlotTimeout` instead of hanging. `session_usable.earn_usable` wraps the whole warm-up in an overall `IBKR_EARN_USABLE_TIMEOUT_SEC` deadline and aborts (does not promote to READY) if exceeded. `routes/trading.py`'s `/api/ibkr/launch-gateway` now checks `is_ready()` after an `already_listening` result and calls `force_reconnect()` (returning `action: "rebuild_session"`) instead of leaving the button a no-op. Frontend `gatewayPortOpenButSessionDown()` relaxed to key off `preferredPortReachable` alone (the function is only called when `!connected`, so the port state alone is sufficient); the checklist now also surfaces `session_state` in the detail line, and the launch button refreshes status immediately instead of waiting up to 5s.
- **Fix class:** infra
- **Keywords:** IBKR session frozen, earn_usable hang, cold_slot lock stranded, reqCompletedOrdersAsync hang, stuck unusable, session_watchdog, dialer heartbeat, py-spy, already_listening no-op, gatewayPortOpenButSessionDown, Trading prerequisites, rebuild_session

## 2026-08-28 -- Premarket VWAP was 09:30-only

- **Symptom:** AEMD 1Min had no real VWAP through 04:00-09:30 even after the leftover-to-open diagonal was removed. The orange line started at the bell.
- **Cause:** 2026-08-25 chose a 09:30 ET RTH anchor (IBKR / TradingView regular-hours). That skips the premarket tape this desk actually trades. Live AEMD: 341 premarket bars / 15.0M shares never entered the accumulator.
- **Fix:** `CHART_VWAP_SESSION_START_SEC` is now `SESSION_PREMARKET_START_MIN_ET * 60` (04:00 ET). One session from 04:00-16:00. Overnight leftover gap stays.
- **Fix class:** chart / frontend
- **Keywords:** VWAP, premarket, 04:00, CHART_VWAP_SESSION_START_SEC, AEMD
- **Related:** CHANGELOG 2026-08-28 -- Chart VWAP starts at 04:00 ET premarket

## 2026-08-28 -- VWAP leftover-to-open diagonal on overnight 1Min

- **Symptom:** AEMD 1Min VWAP was a near-straight dashed orange line from the prior evening (~$2.25) up to the open, ignoring the 4:00 / 7:00 spikes. Axis tag said `VWAP $3.01` while the line sat well below the candles through premarket.
- **Cause:** Session VWAP is RTH-only (09:30-16:00). After 16:00 the close value carries flat (AEMD leftover $2.2547 at 23:59). Premarket has no points. `sampleVwapOntoBars` skipped those bars instead of inserting whitespace, so yesterday 23:59 and today 09:30 were adjacent in the LineSeries. lightweight-charts draws a straight line between adjacent points -- a 571-minute fake diagonal. 15.0M premarket shares never entered the RTH accumulator (by design from 2026-08-25).
- **Fix:** Paint only the newest ET day. Emit whitespace on skipped bars so the library cannot interpolate the hole. Empty / premarket-only title is `VWAP (09:30 ET)`. Trail: `py -3 tools/vwap_probe.py AEMD`.
- **Fix class:** chart / frontend
- **Keywords:** VWAP, premarket, overnight, LineSeries, whitespace, leftover, AEMD, sampleVwapOntoBars, 09:30, interpolation
- **Related:** CHANGELOG 2026-08-28 -- Chart VWAP no longer draws a leftover-to-open diagonal; 2026-08-25 session VWAP; 2026-08-26 walk-with-bars

## 2026-08-28 -- Desk refreshed and Start API appeared while the API process was still alive

- **Symptom:** Operator saw the UI refresh a few times and thought the API stopped. Daily start at 08:22 logged `API health still failing after 60s` / `apiListen=False`. At 09:11 Vite fired a burst of HMR updates. During soak, `/api/health` missed a 4s probe and the header showed a red Start API while Desk stayed green.
- **Cause:** Three stacked issues, same family as 2026-07-14 / 2026-08-14 / 2026-08-17. (1) `Start-NovaApi.ps1` always set `NOVA_API_RELOAD=1`, so every daily / Run Nova / Vite Start API path was WatchFiles-on. (2) Lifespan logged `instance starting` at 08:22:25 and `HTTP ready` at 08:23:59 -- 94s with no listener -- because `init_sentry()` + cache/DB restore run before `yield`. Daily start's 60s health wait expired in that hole. (3) HTTP loop lag spiked to 4360ms (`ib_cold_inflight=snapshot_quotes`); a 4s `/api/health` abort is `API_WEDGED` / `health.status=disconnected`, which paints Start API. The PID never died (16820 / instance `86bbb510002d`). The 09:11 "refreshes" were Vite HMR of `index.css` + Dashboard/Trader modules, not an API restart. Yahoo sockets were stable (~125), so this was not the 2026-08-26 yfinance thread pile-up.
- **Fix:** Launcher default is `NOVA_API_RELOAD=0` (`-Reload` opt-in). Daily `HealthWaitSec` default is 180. Live process was not restarted (a post-09:30 restart would lose today's Gappers freeze). `init_sentry` blocking yield is parked as D-006 -- editing `app_lifespan.py` now would WatchFiles-kill this reload=true process.
- **Fix class:** infra
- **Keywords:** NOVA_API_RELOAD, Start-NovaApi, WatchFiles, Vite HMR, Start API, API_WEDGED, health timeout, init_sentry, HTTP ready, snapshot_quotes, loop_lag, daily-start

## 2026-08-27 -- Large Cap earnings countdown used last report

- **Symptom:** Live `fetch_fundamentals('AAPL')` returned `earnings_date=2026-07-30` and `days_to_earnings=-28`. Large Cap painted that as a red "-28d" under Earnings.
- **Cause:** `fundamentals.py` read `info.get("earningsDate") or info.get("earningsTimestamp")`. `.info` has no `earningsDate` key. `earningsTimestamp` is the last/current event and stays parked for days after the report. The next date is `earningsTimestampStart` / `End`.
- **Fix:** Store `earnings_ts` + `earnings_date` from `earningsTimestamp` (scanner dots) and `earnings_next_date` from Start/End. `large_cap_metrics.build_row_metrics` now counts down from `earnings_next_date` only.
- **Fix class:** admission
- **Keywords:** earningsTimestamp, earningsTimestampStart, days_to_earnings, Large Cap, yfinance, AAPL, last report

## 2026-08-26 -- Trader 10Sec / Full Day charts starved of IBKR historical tokens for minutes

- **Symptom:** Opening a Trader tab on a cold symbol (MSS) painted 5-Minute and 1-Minute instantly but left 10-Second and Full Day (1Day) on "Loading IBKR historical..." for several minutes. `/api/metrics/ops` showed `ibkr.historical_bars` pinned at 60/60 sends with no new send for ~7.5 minutes, even though a completed IB pull only takes ~331ms (p50).
- **Cause:** Three things sharing IB's 60-req/10-min historical budget with no ordering: (1) `large_cap_hooks.on_large_cap_roster_commit` scheduled a background `1Day` fill for **every** Large Cap roster name on **every** roster commit and every 15-min TTL miss, regardless of whether the store already had a complete series -- daily bars do not change intraday, so this was pure respray. (2) `chart_bars.fetch_chart_bars` gave `open_chart` (top) priority to **any** interactive `/bars` call, including panes that already painted from a stale store -- so a 30s reconciliation poll on a fine 1Min pane competed at the same priority as a genuinely blank 10Sec/1Day pane. (3) 10Sec has no live overlay path (unlike 1Min's `l1_minute.py`), so a cold 10Sec pane has nothing to show until its full 4-hour `reqHistoricalData` pull lands.
- **Fix:** (Phase 0) `HistoricalPacing.snapshot()` + `/api/metrics/ops.historical_pacing` makes the 60-req/10-min bucket observable instead of only visible in log greps. (Phase 1) `large_cap_metrics.schedule_daily_fill` gained a once-per-04:00-ET-session guard, and `large_cap_hooks` skips the schedule entirely when the store already has a complete daily series -- both call sites (roster commit, TTL-miss recompute) go through the same guard. (Phase 2) `chart_bars.fetch_chart_bars` now schedules `open_chart` only when the store is genuinely empty; a pane that already painted something (stale/incomplete) gets `warm`, which sheds on any pacing wait instead of competing for the budget. Background/scan callers (`interactive=False`) are unaffected. (Phase 3) New `ibkr/tape_10sec.py` rolls the tick-by-tick prints Trader already streams into live 10-second OHLCV buckets (`source=ibkr_l1`, volume = summed print sizes), enqueued the same non-blocking way as `l1_minute.py`'s 1Min overlay (ADR 010 write-queue) -- so the 10Sec pane has candles within seconds regardless of the hist queue. (Phase 4) First tape subscriber for a symbol now also schedules a `warm` 10Sec hist fill (store-settled guarded), so the full 4h history is usually already inflight by the time the pane needs it.
- **Fix class:** ownership (who gets to spend the shared IB historical budget, and who owns the provisional 10Sec candle)
- **Verified by:** Fresh full backend pytest run: 1386 passed (one pre-existing unrelated transformers-import flake in `test_news_sentiment.py`, not touched by this change). New/updated coverage: `test_historical_service.py` (pacing snapshot), `test_large_cap_hooks.py` + `test_large_cap_metrics.py` (17 tests, once-per-session + store-complete guards), `test_ibkr_bars.py` (36 tests, priority split by store state), `test_tape_10sec.py` (4 tests, bucket/flush/source/timeframe), `test_ibkr_tape_stream.py` (15 tests incl. 2 new for the warm-on-subscribe seam). **Live verification is still pending** -- the running Nova API process could not be located/restarted from this agent session (see `DEFERRED_LOG.md` D-003), so `historical_pacing.window_used` and a live cold-symbol 10Sec paint time have not yet been re-measured after this fix. Do not treat this entry as closing D-003 until that live check runs.
- **Keywords:** Loading IBKR historical, 10Sec, 1Day, Full Day, MSS, ADR 012, historical_service, historical_pacing, 60/10 min bucket, Large Cap schedule_daily_fill, once-per-session guard, chart_bars priority, open_chart, warm, tape_10sec, l1_minute, D-003

## 2026-08-26 -- API stopped serving :8000 after the mover fundamentals warm piled up yfinance threads

- **Symptom:** Within an hour of shipping the mover enrichment hook, `run_api.py` was still alive with a healthy IB socket but had **no listener on :8000** -- `/api/health` returned nothing, and the process held ~300 ESTABLISHED HTTPS sockets to Yahoo. A second API refused to start because `api_instance_lock` correctly reported the (genuinely alive, just not serving) PID.
- **Cause:** `mover_enrich_hooks.on_mover_roster_commit` copied `large_cap_hooks` and started a **new daemon thread per roster commit**. Large Cap gets away with that -- one table, rare commits. The mover tables are three (gainers/losers/afterhours) and commit every couple of minutes, and on a cold fundamentals cache every one of those threads runs up to 50 sequential `yf.Ticker(sym).info` calls, each opening its own session and its own `ThreadPoolExecutor`. Overlapping warms stacked hundreds of threads and Yahoo sockets onto the API process until uvicorn stopped accepting on :8000. `fetch_fundamentals_batch`'s TTL skip does not help while the cache is still cold, because all the overlapping threads request the same not-yet-cached symbols.
- **Fix:** Made the warm **single-flight** in `backend/mover_enrich_hooks.py`: one worker thread ever, with incoming symbols coalesced into a module-level pending set that the running worker drains before exiting. The worker releases its slot while still holding the same lock a producer checks, so a commit arriving during shutdown cannot see a live-but-exiting worker and drop its symbols. `mover_enrich_view` (read side) was unaffected.
- **Fix class:** ownership
- **Verified by:** New `test_mover_warm_is_single_flight` proves a second and third commit queue instead of spawning threads and that both batches are still fetched; 1397 pytest green. Live after restart: API healthy on :8000 and established socket count trending **down** (145 → 132 → 131 → 124 over 90s) instead of climbing.
- **Keywords:** api not listening, port 8000, uvicorn stopped accepting, yfinance thread pile-up, Yahoo ESTABLISHED sockets, mover_enrich_hooks, fetch_fundamentals_batch, single-flight, daemon thread per commit, large_cap_hooks, api_instance_lock false positive

## 2026-08-26 -- Gainers columns empty all session: half the rows unpriced, Gap %/RVOL/Float/Short Int./Mkt Cap never filled

- **Symptom:** The Gainers table showed red `N/A` for CHANGE on ~half its rows with `—` price and `0` volume, `N/A` for GAP % on **every** row, and `—` for FLOAT / SHORT INT. / MKT CAP plus `N/A` for the RVOL sub-line on every row -- premarket through the close. Some rows populated after 09:30 and the rest never did. Every scanner integrity check reported `pass` the whole time.
- **Cause:** Three unrelated gaps stacked up.
  1. **L1 starvation.** `DashboardPage` declared the L1 active tab **only from the tab-click handler**, so on mount/reload `l1ActiveTab` stayed at `DEFAULT_ACTIVE_TAB` (`gappers`). Gappers freezes at 09:30 and a frozen table deliberately contributes no symbols (`ibkr_bridge.symbols_for_tab`, ADR 008), so `OWNER_SCANNER` subscribed **nothing**: today's log showed 6 distinct scanner subscriptions for the entire 10:01-16:00 window versus 134 for `hod`. The 25 rows that did have prices were HOD's `top_gainer` quota inside its 40-slot pool; the other 25 were exactly the symbols in `hod_active` `uncovered_symbols`. `HodMomoDock` had already fixed this for itself with a mount effect; the main tab never got the same treatment.
  2. **Gap % never computed.** `discovery.reprice_mover_row` set price/change/volume and never touched `gap_percent`, and the session open (IB tick type 14) was read only on the COLD `snapshot_quotes` path, never on the streaming ticker.
  3. **No enrichment under IBKR.** `ibkr_bridge.enrich_ibkr_mover` computed RVOL + fundamentals but was **never called** (only re-exported by `scan_runners`), and both functions that do fetch yfinance fundamentals (`universe.enrich_gappers`, `scanner_runners.movers`) return early when `discovery=ibkr`. The keys were absent from the payload entirely, not null.
- **Fix:** (1) `DashboardPage` declares the visible `mainTab` for L1 in a `useEffect` on mount and every change; `tabHints` still drops non-scanner tabs. (2) `ticks_handler` reads `ticker.open` and threads it through `scanner_l1.on_l1_quote` → `ibkr_bridge.apply_l1_quote` → `reprice_mover_row`, which computes `(open - prev_close) / prev_close`; without an open it keeps the prior gap rather than reusing `change_pct`. (3) New `mover_enrich_hooks` warms yfinance off-loop on roster commit (mirrors `large_cap_hooks`); new pure `mover_enrich_view.decorate_rows` fills RVOL/float/short interest/market cap at the three **serialization** points (`routes/scan._strip_blocked`, `scanner_push.broadcast_roster_replace`, `_snapshot_payload`) so a frozen table's stored values stay immutable. Dead `enrich_ibkr_mover` removed. RVOL denominator is yfinance `average_volume`, never `state.avg_volume_cache` -- see the 2026-07-16 entry below where Alpaca IEX averages blew RVOL up 100x-3000x; the scanner badge now reads `yfinance avg` (ticker detail still genuinely uses Alpaca and keeps its own label). Added `scanner_<table>_row_prices` integrity check so a displayed live table with unpriced rows past a 180s admission grace fails instead of passing silently, plus `tab_counts` per declared table in the L1 subscription state.
- **Fix class:** admission
- **Verified by:** 1395 pytest / 822 Vitest / `npm run build` all green, incl. 11 new tests in `backend/tests/test_mover_columns.py`. Live after restart: `owner=scanner` reached **50 distinct** symbols (was 6 all day) and a `/ws/scanner` probe declaring the live `afterhours` table showed `tab_counts={'afterhours': {'requested': 50, 'streaming': 50}}` with `active_tab` climbing 5→50; `/api/scan/integrity` emitted `scanner_afterhours_row_prices: 50/50 rows priced`. `/api/movers` CRE now carries `market_cap=13715238, float=1102703, short_interest=31617, short_ratio=0.59, rel_volume=71.6`. A direct `ib_async` probe on a spare clientId confirmed a streaming `reqMktData` ticker really does carry `open` within 5s (CRE open=6.09 vs close=2.57, AAPL open=310.24 vs 309.90), so the gap math has a real input. Browser screenshot of the Gainers table shows populated Float/Short Int./Mkt Cap and a `YFINANCE AVG` badge.
- **Keywords:** gainers columns empty, N/A change, gap_percent null, rel_volume N/A, float em-dash, market cap missing, short interest missing, L1 starvation, OWNER_SCANNER, set_active_tab, l1ActiveTab, DEFAULT_ACTIVE_TAB, tabHints, symbols_for_tab frozen, ADR 008, enrich_ibkr_mover dead code, mover_enrich_view, mover_enrich_hooks, tick 14 open, reprice_mover_row, yfinance average_volume, avg_volume_cache, scanner_row_prices integrity, tab_counts

## 2026-08-26 -- VWAP did not walk with painted chart bars

- **Symptom:** The orange VWAP overlay sat still (or stepped once a minute) while candles kept painting to the right, especially on 10Sec and on the live forming bar of every intraday pane.
- **Cause:** Session VWAP was accumulated only from closed 1Min store bars and sampled onto the pane with a one-minute bucket. That made 10Sec a staircase (six candles sharing one 1Min close, including lookahead inside the minute). Tape updates paint new candle times through `mergeLiveTradeCandle` without changing `indicatorBars`, so the VWAP series stopped at the last store bar. L1 1Min overlay also does not flush the forming minute until it closes.
- **Fix:** `vwapSourceForPane` keeps 1Min bars before a sub-minute window (09:30 anchor) and splices in that pane's own bars for the visible slice. `sampleVwapOntoBars` can `extendToTime` onto the live tip. `useChartLiveTrade` publishes `liveTipTime` when a new bucket opens.
- **Fix class:** ownership
- **Keywords:** VWAP, 10Sec, painted bars, live tip, sampleVwapOntoBars, vwapSourceForPane, mergeLiveTradeCandle, forming bar, session VWAP
- **Related:** CHANGELOG 2026-08-26 -- VWAP did not walk with painted chart bars; 2026-08-25 session VWAP single series

## 2026-08-26 -- Chart drawings were per-pane, bled across symbols, and died on reload

- **Symptom:** A horizontal line drawn on the 1Min pane was invisible on the 5m / 1D / 10Sec panes and in the Quote Panel chart. Every drawing vanished on page reload and on restart. A level drawn on AAPL stayed painted over TSLA after switching symbol.
- **Cause:** Each `TickerChart` constructed its own `DrawingManager` in a `useEffect` with no shared store and no persistence, so one symbol had up to five disconnected drawing sets that all died on unmount. Nothing cleared the manager on symbol change, hence the bleed. Sharing anchors across timeframes is not free either: intraday series carry ET-shifted epoch numbers while 1Day+ series carry `'YYYY-MM-DD'` strings, and `timeScale.timeToCoordinate` returns `null` for an off-scale time -- so a naive share would make trend/vertical/cross lines silently paint nothing.
- **Fix:** ADR 015. Backend `chart_drawings.py` + `GET/PUT/DELETE /api/chart-drawings/{symbol}` (schema_version, refuse-loud). Frontend `chartDrawingsStore.ts` (per-symbol shared store, deduped GET, debounced PUT), `chartDrawingTime.ts` (canonical epoch + snap-to-nearest-bar per pane, clamp at edges), `chartDrawingHydrate.ts`. `useChartDrawingManager` now hydrates from the store and clears on symbol change.
- **Fix class:** ownership
- **Keywords:** chart drawings, horizontal line, trend line, DrawingManager, lightweight-charts-drawing, timeToCoordinate null, timeframe, persistence, symbol bleed, ADR 015

## 2026-08-26 -- Fresh chart drawing erased by an in-flight GET

- **Symptom:** With a slow/wedged API, a just-drawn line could disappear a moment after placement.
- **Cause:** Found while building ADR 015, before shipping. `fetchDrawings` called `setLocal` unconditionally, so a `GET` that started before the draw and returned `drawings: []` bumped the store revision and made every pane rebuild from the empty server list. `setLocal` also bumped the revision when content was unchanged, causing needless rebuilds that drop the held selection.
- **Fix:** `fetchDrawings` captures the revision at request start and discards the server payload if it moved while the request was pending (local edit wins). `setLocal` returns early when the list is unchanged.
- **Fix class:** ownership
- **Keywords:** chart drawings, race, stale GET, revision, clobber, chartDrawingsStore

## 2026-08-26 -- Buying-power reject had no pop-up

- **Symptom:** Operator placed META BUY 1 LMT @ 596.54 live. Ledger: `rejected` / `BUYING_POWER` / "estimated notional 596.54 exceeds BuyingPower 552.79". Almost no notification. Order never reached IB (`order_id` null, `broker_sent_ms` null).
- **Cause:** Place failures only set a small `manual-order-result` span under the ticket. Cancel/flatten already used `alertApp`. Place did not. Confirm pop-up fired (~9s), then the reject hid in the footer.
- **Fix:** `notifyOrderRejected` -> `alertApp` on ticket/hotkey/flatten fails. Titles keyed by `reason_code` (BUYING_POWER = "Not enough buying power"). Receipt JSON now includes `reason_code`.
- **Fix class:** surfacing
- **Keywords:** BUYING_POWER, estimated notional, BuyingPower, Activity trail, alertApp, ManualOrderTicket, META, pop-up

## 2026-08-26 -- Instance lock false-alive PID blocked API restart

- **Symptom:** After the sidecar HTTP socket died (new connects refused, IB still attached), `run_api.py` exited: "another Nova API is already running (pid=4916)" even though that PID was gone (`tasklist` empty).
- **Cause:** `_pid_alive` used `OpenProcess(SYNCHRONIZE)`, which can succeed on a just-killed Windows PID. Reclaim never ran.
- **Fix:** Query `GetExitCodeProcess`; only 259 (`STILL_ACTIVE`) counts as alive. Access-denied still fail-closed (assume alive).
- **Fix class:** infra
- **Keywords:** api-instance.lock, _pid_alive, OpenProcess, SYNCHRONIZE, GetExitCodeProcess, STILL_ACTIVE, pid 4916, Error 326


## 2026-08-26 -- Dual API stole clientId 17; desk said connecting / Error 1100

- **Symptom:** Trading prerequisites: IB Gateway (session READY) red -- "port is open, but Nova session is not READY (reconnect stuck or Error 1100) (reason: connecting)". Door trail: Failed to fetch. Health probe timed out while a PID still "listened". Gateway 4001 was up and logged in.
- **Cause:** Two Nova APIs were alive: morning `run_api.py` (pid 54868, 06:38) and a later `uvicorn main:app` (pid 54840, 08:12). Both used clientId 17. The stray uvicorn got Error 326 until Gateway restarted at 08:47, then stole the slot. The sidecar's listen socket died (Established leftovers only, new HTTP refused) so door trail and fresh probes failed. Prerequisites keyed the leftover `connecting` reason to Error 1100 copy, which this was not.
- **Fix:** Single-instance lock at `main` import (`api-instance.lock`, schema_version 1). Error hook installed before `connectAsync`; Error 326 sets `session_reason=client_id_in_use` with dedicated prereq copy. Door trail maps `Failed to fetch` to a dual-API hint. Stopped the stray uvicorn and restarted the dead-listen sidecar.
- **Fix class:** ownership
- **Keywords:** Error 326, clientId 17, dual API, uvicorn, run_api.py, session READY, connecting, Failed to fetch, door trail, Error 1100, listen socket

## 2026-08-26 -- Chart line Delete missing and anchors snap to candle close

- **Symptom:** Clicking a drawn vertical line showed the blue handle, but Delete left it in place. Horizontal, vertical, cross, and trend anchors also locked to the candle close instead of the high/low wick under the cursor.
- **Cause:** `useChartDrawingManager` had no delete key listener. Separately, Lightweight Charts defaults to `CrosshairMode.Magnet`; drawing placement consumed the magnetized click point, so its Y coordinate followed the candle close.
- **Fix:** Plain Delete/Backspace calls `removeDrawing` on the selected id. The price chart now uses `CrosshairMode.Normal`, preserving the exact cursor price for drawing anchors.
- **Fix class:** ownership
- **Keywords:** chart, drawing, wick, tail, candle close, CrosshairMode, Magnet, Normal, VerticalLine, HorizontalLine, Delete, Backspace, DrawingManager

## 2026-08-25 -- Global app bar overlaps when zoomed

- **Symptom:** Zooming the desk painted MARKET CLOSED on Scanner/Trader, the red lock on BP / Net Liq, and smashed Account / Working / Settings.
- **Cause:** `.global-app-bar` was a single 40px nowrap flex row. Left/right had `min-width: 0`, so they shrank while children stayed nowrap and overflowed visibly onto neighbors. A growing spacer also stole width from the scanner (Look Up clipped to "Look").
- **Fix:** CSS grid (`max-content | 1fr | max-content`). Below 1680px scanner takes a second full row. Removed the spacer. Dock mode tabs no longer shrink.
- **Fix class:** surfacing
- **Keywords:** global-app-bar, zoom, overlap, MARKET CLOSED, trade lock, Net Liq, header wrap

## 2026-08-25 -- HotkeyDispatchProvider setState-during-render on profile writes

- **Symptom:** Browser console: `Cannot update a component (HotkeyDispatchProvider) while rendering a different component (HotkeyManager)` after deleting a Nova Action in Settings.
- **Cause:** `useHotkeyProfile` called `dispatch.reloadNovaActions()` (parent `setState`) from inside a `setProfile` updater. React runs that updater while rendering `HotkeyManager`.
- **Fix:** Persist in the updater only; sync the dispatcher with `setTimeout(0)` after the write (`syncDispatch`).
- **Fix class:** ownership
- **Keywords:** hotkeys, setState-during-render, reloadNovaActions, useHotkeyProfile, HotkeyDispatchProvider

## 2026-08-25 -- Graphify wired opt-in so agents skipped it

- **Symptom:** Graphify CLI was installed and `graphify query` worked, but agents answered architecture/vault questions from markdown instead of querying the graph. No usage log existed (`graphify-out/memory/` empty; `cost.json` only counted rebuilds).
- **Cause:** `.cursor/rules/graphify.mdc` had `alwaysApply: false` (agent-requested). The skill is a rebuild playbook; the query fast path was easy to skip. Bare `graphify query` did not record a savings meter.
- **Fix:** Always-on short rule; required wrapper `tools/graphify_ask.py` that records cited-note token savings to `graphify-out/usage.json`; session brief shows the meter.
- **Fix class:** ownership
- **Keywords:** graphify, alwaysApply, graphify_ask, usage.json, token savings, skip

## 2026-08-25 -- Wake up, approve IBKR Mobile 2FA, login still doesn't complete

- **Symptom:** Operator wakes up, IB Gateway is showing the Second Factor Authentication prompt, approves it on the phone -- nothing happens. Has to go back to the Nova UI and click login/launch again. `%USERPROFILE%\.nova\ibc\Logs\IBC-*.txt` this morning: `Second Factor Authentication initiated` at 03:40:11, dialog finally closes at 08:52:44 (operator's approval), immediately followed by `Duration since login: 18754 seconds` / `Re-login after second factor authentication timeout in 5 second` -- IBC discarded the approval it just received and started a brand-new login (which the operator then had to approve a second time). Confirmed live again mid-session tonight at 20:30-20:38 (independent run, same pattern) and previously on 2026-08-20, where an unattended prompt looped through 8 login attempts and hit IBKR's own "Too many failed login attempts. Please wait 55 seconds" twice.
- **Cause:** IBC's `SecondFactorAuthenticationTimeout` (180s, matches IBKR's own limit) is compared against wall-clock time since Log In was clicked, not since the operator actually saw the prompt. Nova's `_align_ibc_trading_mode("live")` cleared `AutoRestartTime` and set `AutoLogoffTime` every launch, so the live Gateway logged itself off at 11:45 PM nightly and needed a fresh cold login at the 03:40 scheduled `NovaDailyStart` run -- while the operator was asleep. By the time a human looked at the screen hours later, IBC's own timeout had long passed, so the approval was silently thrown away and a fresh (second) prompt appeared, which is what looked like "approving did nothing."
- **Fix:** Live now keeps the same week-long `AutoRestartTime` token paper already used (`backend/constants_ibkr.py` `IBKR_IBC_LIVE_AUTO_RESTART_TIME`, `backend/ibkr/launch_gateway.py::_align_ibc_trading_mode`) -- a routine cold start reuses the existing session instead of forcing a nightly cold login. Clearing the `jts.ini` Restart=OK token (`clear_restart_token()`) is now opt-in via a new `force_fresh_login` flag on `launch_or_focus_gateway` / `POST /api/ibkr/launch-gateway`, not automatic on every live launch. Local IBC `config.ini`: `ReloginAfterSecondFactorAuthenticationTimeout=no` so an unattended prompt no longer retry-loops into a rate limit. New `backend/ibkr/second_factor.py` reads the IBC log to detect a prompt that has already sat open longer than 180s (`second_factor_pending` / `_age_sec` / `_stale` on `GET /api/ibkr/status`); the UI (`TradingPrerequisitesGate`, `GatewayDisconnectedBanner`) now shows "Start fresh login" instead of a dead focus-only retry, which restarts IBC with `force_fresh_login=true` (kills the stuck Authenticating process via `_stop_gateway_process()`, since a stalled prompt holds no LISTEN port for `_stop_listen_ports` to find).
- **Fix class:** admission
- **Keywords:** IBKR Mobile, Second Factor Authentication, 2FA, IBC, SecondFactorAuthenticationTimeout, ReloginAfterSecondFactorAuthenticationTimeout, AutoRestartTime, AutoLogoffTime, Restart=OK, stale prompt, force_fresh_login, launch_or_focus_gateway, rate limit

## 2026-08-25 -- Unattended 03:40 daily start never reached the AutoRestartTime fix at all

- **Symptom:** Verifying the fix above by closing Nova and re-running the morning start script, `%USERPROFILE%\.nova\ibc\config.ini` still had the old `AutoLogoffTime=11:45 PM` / `AutoRestartTime=` (blank) values on disk, even after the Python code fix was committed and pushed.
- **Cause:** `backend/ibkr/launch_gateway.py::_align_ibc_trading_mode` only runs inside Nova's Python process, triggered by a UI action hitting `POST /api/ibkr/launch-gateway` or `/gateway-mode`. `scripts/Start-NovaDaily.ps1` (the script the 03:40 / 06:00 / AtLogon scheduled tasks actually run) starts IBC directly via `Start-Process` in `Start-IbGateway` -- it never calls the Nova API at all, because the API is not even running yet when Gateway needs to launch. The exact unattended path that caused the original bug (nobody awake at 03:40) was never touched by the code fix, only the UI-driven Paper/Live click path was.
- **Fix:** Added `Repair-IbcAutoRestartConfig` to `scripts/Start-NovaDaily.ps1`, called at the top of `Start-IbGateway`, which directly rewrites `AutoRestartTime=11:45 PM` / `AutoLogoffTime=` in the local `config.ini` before any launch decision -- self-healing regardless of which path (UI click or unattended scheduled task) runs first. Verified line-for-line on a scratch copy (`Compare-Object`) that only those two lines change.
- **Fix class:** ownership
- **Keywords:** Start-NovaDaily.ps1, unattended path, scheduled task, AutoRestartTime, config.ini, two writers, IBC, self-heal, verification caught it

## 2026-08-25 -- Depth cap force-eviction silently killed a possibly-active viewer's line; test class shared state across methods

- **Symptom (1):** None reported -- found by inspection right after the depth fan-out fix, at the user's request ("did you see other clear bugs?"). `evict_for_capacity`'s force-evict branch (`ibkr/depth/subscribe.py`) picks a victim whose `viewer_count` might be a genuinely active viewer, not a "possible leak" as its own log message hedges, and tore the line down with zero notification to that viewer.
- **Cause (1):** At `IBKR_MAX_DEPTH_SYMBOLS` cap with no idle candidate, the code force-evicts `others[0]` and clears its viewer count, then calls `unsubscribe()` -- there was no code path telling any WS route still holding a queue open on that symbol that its line just died. The viewer's `stream()` would just heartbeat-ping forever with no book updates and no error, identical in shape to the tape freeze this session already fixed.
- **Fix (1):** `state.push_error(symbol, message, evicted=True)` (a `_broadcast` sibling of `push_book`) now fires before `unsubscribe()` in the force-evict branch. `routes/trading.py`'s `ws_depth` loop now checks `item.get("type") == "error"` on queue items (previously it always wrapped every non-None queue item as a "book"), sends the error, and closes the socket on `evicted=True` so the frontend's existing backoff reconnects it.
- **Symptom (2):** Found while writing a regression test for (1): asserting a *specific* victim symbol name failed intermittently depending on which other tests in `TestDepthCap` ran first in the same pytest session.
- **Cause (2):** Five of six `setup_method`s in `test_ibkr_safety.py` that manipulate `ibkr.depth` state call `importlib.reload(depth_mod)` but not `depth_mod.reset_all()`. `reload()` only re-executes the **facade** (`ibkr/depth/__init__.py`); `ibkr.depth.state`'s module-level dicts (`_subscriptions`, `_ws_viewers`, `_viewer_queues`, ...) are a separately-loaded module already in `sys.modules` and are never re-executed, so they silently accumulate across test methods and even across classes within the same pytest session. One class (`TestSmartDepthFlag`) already had a fix for this with a comment ("Import-time reset was removed (Phase 2)") -- it was never propagated to the other five.
- **Fix (2):** Added `depth_mod.reset_all()` to all five affected `setup_method`s.
- **Fix class:** (1) admission (missing notification path) + (2) ownership (test isolation between shared-state consumers).
- **Verified by:** New test `test_force_evict_notifies_any_open_viewer_queue` (constructs its own isolated symbol set via an explicit `reset_all()` precisely because of bug 2, then asserts whichever symbol is actually evicted received the notification) plus full `tests/test_ibkr_safety.py` (34 passed) and full backend suite (1353 passed). Live: restarted the local API with IB Gateway connected live, confirmed a normal single-viewer `/ws/ibkr/depth/DAIC` connection still streams book updates correctly through the restructured message loop (5/5 books received, no regression).
- **Keywords:** force-evict, evict_for_capacity, possible leak, Symbol cap reached, push_error, ws_depth message loop, importlib.reload does not reset submodules, test isolation, setup_method, TestDepthCap, cross-test contamination

## 2026-08-25 -- Level 2 depth given the same per-viewer fan-out fix as tape, preemptively

- **Symptom:** None reported yet -- fixed preemptively after diagnosing the tape freeze below. `ibkr/depth/state.py` shared the exact same single-shared-queue-per-symbol shape that caused tape's surviving viewer to receive zero of 1,902 archived prints.
- **Cause:** `push_book(symbol, book)` wrote into one `_queues[symbol]` and `stream(symbol)` read from that same single queue. Two viewers of the same symbol (a StrictMode double-mount, or two genuine Trader tabs both showing depth for the same ticker -- an explicitly supported case per `single-market-data-feed.mdc`) would be competing consumers: each book update goes to whichever viewer's task is next in the queue's internal FIFO, never both. Depth did **not** have tape's other bug (an idle-release linger that could cancel a still-watched line) -- `release_when_idle` already re-checks `viewer_count` inline before releasing, and `subscribe_async` already serializes via a single `get_subscribe_lock()`, so only the queue-fan-out defect applied here.
- **Fix:** Same shape as the tape fix: `_queues` replaced with `_viewer_queues: dict[str, list[asyncio.Queue]]`; `push_book` broadcasts to every registered queue; new `open_viewer_queue`/`close_viewer_queue`; `stream()` now takes a queue directly instead of a symbol; `has_queue` renamed `is_subscribed` (checks `_subscriptions`, decoupled from queue lifecycle). `routes/trading.py`'s `ws_depth` opens/closes its own per-connection queue in a `finally` block, matching `ws_tape`'s structure.
- **Fix class:** admission (single-consumer queue never delivered to more than one reader).
- **Verified by:** `pytest backend/tests/test_depth_stability.py backend/tests/test_ibkr_depth_state.py backend/tests/test_ibkr_safety.py` (47 passed) + full backend suite (1343 passed). Live: restarted the local API with IB Gateway connected live; opened two concurrent WebSocket viewers to `/ws/ibkr/depth/DAIC` and held both open for 15s -- both received the identical count (15 book updates each), confirming fan-out rather than a competing split.
- **Keywords:** Level 2 depth, competing consumers, single shared queue, fan-out, push_book, open_viewer_queue, has_queue, is_subscribed, DepthLadder, preemptive fix, tape_stream parity

## 2026-08-25 -- Time & Sales froze: linger released a still-watched line, and viewers competed for one shared queue

- **Symptom:** User report: "time and sale is stuck... it is just not moving." DAIC's tape stopped at `16:33:40` and WVVIP's at `16:32:46`; the LIVE badge stayed green with no error.
- **Cause:** Two stacked bugs in `backend/ibkr/tape_stream.py`. (1) `blast.log` showed `subscribed DAIC` twice 0.4s apart (a React StrictMode double-mount) followed by `unsubscribed DAIC` exactly `IBKR_TAPE_LINGER_SEC` (16.0s) after the first subscribe returned. The discarded socket's cleanup scheduled a 16s linger before releasing the IB line; the surviving socket's reattach skipped `subscribe_async` (queue already existed) and therefore never called `_cancel_linger`, so the linger fired unconditionally 16s later and cancelled a line someone was still watching. Archive `tape_ibkr` confirmed zero prints for any symbol after the unsubscribe timestamp. (2) Even after fixing the linger, a live soak against the running API (two WS to `/ws/ibkr/tape/DAIC`, discard the first) proved a **second** bug: with one shared `asyncio.Queue` per symbol, two viewers are competing consumers, not fan-out subscribers -- the archive recorded 1,902 new DAIC prints during a 24s window while the surviving viewer's WebSocket received **zero** of them (only a single 15s heartbeat ping), because the discarded socket's still-running server task kept winning the race to drain the queue and silently failing to deliver (its own socket was already closed).
- **Fix:** `_schedule_linger`'s deferred release now re-checks `viewer_count(symbol) > 0` before cancelling (same shape as depth's `release_when_idle`); `ws_viewer_opened` also cancels any pending linger so a reattach that skips `subscribe_async` still stops it. `subscribe_async` is now serialized per symbol with an `asyncio.Lock` so two racing callers can't both attach a handler. Queue architecture changed from one shared queue per symbol to one queue per *viewer* (`open_viewer_queue`/`close_viewer_queue`); `_push_queue` now broadcasts to every registered queue for a symbol. `_release_subscription` broadcasts a `{"type":"error","released":true}` notice to any still-open viewer so its socket closes and its frontend backoff reconnects, instead of silently orphaning it.
- **Fix class:** ownership (linger/viewer refcount) + admission (single-consumer queue never delivered to more than one reader).
- **Verified by:** `pytest backend/tests/test_ibkr_tape_stream.py backend/tests/test_ibkr_tape_side.py backend/tests/test_archive_capture.py backend/tests/test_archive_write_queue.py backend/tests/test_depth_stability.py backend/tests/test_ibkr_safety.py` (81 passed) + full backend suite (1342 passed). Live: restarted the local API with IB Gateway connected live, ran the exact double-mount race against the running `/ws/ibkr/tape/DAIC` twice -- post-fix run delivered 166 prints / 0 errors across a 24s window spanning the 16s linger mark (pre-second-fix run on the same harness showed 0 prints delivered despite 1,902 archived); the fan-out fix's soak delivered 1,148 prints matching the archive's concurrent count, connection stayed open throughout.
- **Keywords:** time and sales stuck, tape frozen, IBKR_TAPE_LINGER_SEC, StrictMode double-mount, reqTickByTickData, cancelTickByTickData, competing consumers, single shared queue, fan-out, viewer_count, release_when_idle, LIVE badge lying, DAIC WVVIP

## 2026-08-25 -- Afterhours reprice crashed every quote tick: sort() on a name-only admitted row with gap_percent=None

- **Symptom:** Live log spamming `ERROR ibkr.scanner_l1 scanner_l1: apply_quote failed for DAIC` on essentially every L1 quote tick (found while soak-verifying the tape fix above), with traceback ending in `afterhours_discovery.py:112: TypeError: '<' not supported between instances of 'NoneType' and 'NoneType'`.
- **Cause:** `reprice_afterhours_rows_ibkr` appends the original row unchanged (`updated.append(r)`) when a row has no price/quote yet, then does `updated.sort(key=lambda x: x["gap_percent"], reverse=True)`. Per ADR 010, a scanner name is admitted as a row immediately with `price=null`/`gap_percent=null` before its first L1 tick ("roster admission is name-only") -- so the moment any afterhours row was still unpriced alongside a priced one, the sort had to compare `None` against `None`/a float, which Python 3 does not support.
- **Fix:** New `_gap_sort_key` maps `gap_percent is None` to `float("-inf")` so unpriced rows sort to the bottom instead of raising; `updated.sort(key=_gap_sort_key, reverse=True)`.
- **Fix class:** admission (the sort didn't account for the documented name-only admission contract).
- **Verified by:** New regression test `test_reprice_afterhours_rows_ibkr_tolerates_unpriced_row` (mixed priced + unpriced rows, was a guaranteed `TypeError` pre-fix); `pytest backend/tests/test_afterhours_discovery.py` (3 passed). Live: restarted the local API with the fix in place -- zero new `apply_quote failed` lines in `blast.log` across 20+ minutes of continuous afterhours L1 ticks (prior restart without the fix reproduced the crash within seconds).
- **Keywords:** afterhours reprice, apply_quote failed, TypeError NoneType, sort key None, gap_percent, roster admission name-only, ADR 010, scanner_l1, ibkr_bridge

## 2026-08-25 -- `test_execution_latency_regressions.py` failed only when pytest ran from inside `backend/`

- **Symptom:** `cd backend && pytest` raised `ModuleNotFoundError: No module named 'tools'` collecting `test_execution_latency_regressions.py`; the same test passed when invoked as `pytest backend/` from the repo root (how CI runs it), so it had been silently ignored in verification notes for at least one prior session (see CHANGELOG 2026-08 entry noting "ignored pre-existing `test_execution_latency_regressions` tools import").
- **Cause:** The test imports `from tools import execution_latency_probe`; `tools/` lives at the repo root as a sibling of `backend/`, not inside it. Every other `backend/tests/*.py` file that needs a repo-relative import already does `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` (to reach `backend/`) -- this file needed the same idiom one level further up to reach the repo root, and never had it; it only worked by accident when the repo root happened to already be on `sys.path` (running `pytest backend/` from that root).
- **Fix:** Added `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))` before the `tools` import, matching the existing per-test-file convention rather than adding a new `conftest.py` pattern.
- **Fix class:** infra.
- **Verified by:** `pytest tests/test_execution_latency_regressions.py` from both `backend/` and the repo root (6 passed each way); full backend suite from `backend/` (1342 passed, this file no longer excluded).
- **Keywords:** ModuleNotFoundError tools, sys.path, pytest rootdir, test_execution_latency_regressions, cwd-dependent test failure

## 2026-08-25 -- VWAP showed a different value on every chart timeframe

- **Symptom:** The orange VWAP tag disagreed pane to pane for the same symbol at the same moment. Measured live on DAIC: 10Sec $3.73, 1Min $3.87, 5Min $3.79, 15Min $3.76, 1Hour $3.74 -- a 14-cent spread on a $3.88 stock. AIXI spread $1.22-$1.37 (over 11%). A 15Min store caught mid-refill briefly produced $0.61 on that same $3.88 stock.
- **Cause:** VWAP was accumulated separately inside each pane from that pane's own bar array, via `VwapMvwapEmaCrossover` from `lightweight-charts-indicators`. That indicator has no session anchor -- it resets only on a calendar-day change and then accumulates from whatever bar happens to be first in the array. Each timeframe holds a different slice of history (per-timeframe `IBKR_BAR_DURATION` plus the 500-bar trim), so each one anchored somewhere different: 10Sec at 4h ago, 1Min at 500 minutes ago, the coarser panes at 04:00 ET. On 1Day/1Week/1Month every bar is its own calendar day, so the line was just `(H+L+C)/3` per bar, not a VWAP at all. Using per-bar `hlc3` as the price proxy added a second, bar-size-dependent error on top.
- **Fix:** One session VWAP, accumulated only from 1Min bars and sampled onto each pane's bar times (`frontend/src/chart/vwapSession.ts` + `useVwapSourceBars.ts`). Anchored at 09:30 ET, stops accumulating at 16:00 ET, resets per ET day. Every pane draws the same series, so they cannot drift. Disabled on daily and above. `CHART_TIMEFRAME_BAR_LIMITS['1Min']` raised 500 -> 1000 so the source still reaches 09:30 late in the day; axis title says `(partial)` when it does not.
- **Fix class:** ownership
- **Keywords:** VWAP, session VWAP, timeframe mismatch, chart overlay, VwapMvwapEmaCrossover, lightweight-charts-indicators, hlc3, anchor, 09:30 ET, IBKR_BAR_DURATION, bar limit trim
- **Related:** `CHANGELOG.md` 2026-08-25 -- One session VWAP shared by every chart timeframe; task-log `knowledge/task-log/2026-08-25-session-vwap-single-series.md`

## 2026-08-25 -- Chart filling hint covered the time axis and TradingView mark

- **Symptom:** Quote Panel 1m chart showed "as of ... filling..." painted on top of the first time label (e.g. 1:30 PM) and the TradingView logo in the bottom-left corner.
- **Cause:** `.chart-filling-hint` was `position: absolute; left: 8px; bottom: 4px` inside `.chart-body`, the same corner lightweight-charts uses for the time axis and attribution logo.
- **Fix:** Move the filling status into the chart header chip. Lift the TradingView attribution with CSS so it sits in the plot, not on the time labels.
- **Fix class:** surfacing
- **Keywords:** chart, filling hint, overlap, time axis, TradingView attribution, Quote Panel, tickerChart.css

## 2026-08-25 — IBKR ScannerSubscription.marketCapAbove is in millions, not raw dollars

- **Symptom:** Diagnostic probe (`tools/ibkr_scan_params.py`, pre-production research for the Large Cap swing table) set `marketCapAbove=50_000_000_000` ($50B, raw dollars) on `HOT_BY_VOLUME` / `TOP_VOLUME_RATE` / `MOST_ACTIVE` / `TOP_PERC_GAIN` / `TOP_PERC_LOSE`. Every filtered run returned **zero rows**, even for scan codes whose unfiltered baseline plainly contained >$50B names (NVDA, INTC).
- **Cause:** IB's live `reqScannerParametersAsync()` XML documents the field's wire code as `marketCapAbove1e6` with `<suffix>*1,000,000</suffix>` — the value must be supplied in **millions of USD**. $50B raw dollars was interpreted as a $50 trillion floor, filtering out every listed US equity. Confirmed via a direct XML dump (`RangeFilter id=MKTCAP`) rather than assumption.
- **Fix:** Pass `marketCapAbove` in millions (e.g. `50_000` for a $50B floor) everywhere in the codebase, present and future. `aboveVolume` (`SimpleFilter id=VOLUME`, `IntField`, no `*1,000,000` suffix) is unaffected — raw share counts are correct as-is. Also discovered `stockTypeFilter='CORP'` (the plain wire value, not the XML-internal `inc:CORP` label) is required to exclude ETFs/ETNs/REITs/CEFs from `HOT_BY_VOLUME` / `TOP_VOLUME_RATE` / `MOST_ACTIVE` results — `instrument="STK"` alone does not exclude them, since ETFs are `STK`-typed contracts in IB's model.
- **Fix class:** infra
- **Keywords:** ScannerSubscription, marketCapAbove, reqScannerParameters, millions, units, stockTypeFilter, CORP, ETF pollution, Large Cap scanner, TOP_VOLUME_RATE

## 2026-08-25 — Exchange filter silently blanked the scanner desk to 1 row

- **Symptom:** Premarket, IB Gateway connected and live, `/api/health` and `/api/ibkr/status` both healthy. `/api/movers` and `/api/gappers` REST returned full rosters (50 gainers, 28-31 gappers). Probing `/ws/scanner` directly confirmed the backend was pushing `roster_replace` with the full roster and rising revisions. The UI nav badges nonetheless showed `Gappers 1` / `Gainers 1`, with only the symbol whose detail panel had been opened (AMIX) visible. Losers/Afterhours empty was correct (premarket lease design, ADR 008) but Gappers/Gainers being reduced to 1 row was not.
- **Cause:** Two compounding gaps, one contract and one default. `frontend/src/hooks/useExchangeFilter.ts`'s `filterRows` dropped any row whose `exchange` field was falsy (`r.exchange && selected.includes(r.exchange)`), and the default selection (`SCANNER_EXCHANGE_DEFAULTS`) was `['NASDAQ']` only -- narrowing was always active unless a user manually selected every option. Nothing populates `exchange` under IBKR discovery: `backend/ibkr/scanner_hydrate.py` hard-coded `"exchange": None` on every admitted row, and the only bulk populator (`backend/universe.py`'s Alpaca `/v2/assets` refresh) never runs when `discovery=ibkr`. The single exception is `backend/ticker_alpaca.py`, which fills in one symbol's exchange when its detail panel is opened -- explaining why exactly one row (AMIX) survived. The filter itself is a client-only concern that never surfaced its own effect: an empty table looked identical whether the feed was dead or the filter was active, violating the fail-loud requirement in `single-market-data-feed.mdc` rule 4.
- **Fix:** Frontend: extracted the predicate as an exported pure `filterRowsBySelection()` and changed it to fail open -- a row is only dropped when its exchange is known AND not selected; unknown/null/empty always passes. Changed `SCANNER_EXCHANGE_DEFAULTS` to all options instead of NASDAQ-only. Added a visible "N rows hidden by exchange filter" banner on `DashboardPage` so a future deliberate narrowing is never silent again. Backend (marginal improvement, not the fix): `backend/ibkr/scanner_stream.py`'s `_symbols_from_rows` now also reads `contract.primaryExchange` off the same IB scan row (free -- no extra IB call) and threads a symbol->exchange map through `commit_table` -> `hydrate_rows` -> `stub_row`, normalized via a new `exchanges.normalize_ib_exchange()`. Verified live that IB rarely populates this field on raw scan rows (2 of 81 rows got a real exchange after the fix), so the frontend fail-open + all-exchanges-default change is what actually prevents the blanking.
- **Fix class:** surfacing (the underlying data gap -- IBKR rows have no listing exchange at admission time -- is real and mostly unfixable from the scan API; the actual defect was a UI filter treating "unknown" as "excluded" with a narrow default, silently).
- **Keywords:** exchange filter, SCANNER_EXCHANGE_DEFAULTS, filterRows, NASDAQ only, fail open, blanked desk, gappers 1 row, gainers 1 row, primaryExchange, exchange null, scanner_hydrate, single-market-data-feed, silent hide

## 2026-08-24 — Premarket scanners empty: roster admission required a cold quote

- **Symptom:** Fresh installer launch at 08:28 ET. `/api/health` `connected`, IB Gateway logged in live on 4001, market-data farms OK, `ib_loop_lag_ms.wedged=false`. Gappers and Gainers both showed zero rows for 10+ minutes. Logs: `scanner_stream: opened gainers (TOP_PERC_GAIN)` then repeating `IB on_ib timed out after 20.0s [snapshot_quotes]` / `scanner_stream: hydrate failed for gainers`, plus `Warning 165, reqId ...: Historical Market Data Service query message:no items retrieved` for gappers. `/api/mode` showed `last_gainer_scan: 0.0` while `last_gapper_scan` advanced with 0 rows. `/api/scan/integrity` reported `scanner_gainers: pass`.
- **Cause:** Two separate faults on one broken contract. (1) `ibkr/scanner_hydrate.hydrate_rows` refused to admit any symbol as a table row until a COLD `snapshot_quotes` (`reqTickersAsync`) batch returned price + `prev_close`. That call hops HTTP -> IB via `on_ib` with a `IBKR_QUOTE_BATCH_TIMEOUT_SEC + 5` = 20s ceiling; with ~50 new names at batch size 5 and IB completing snapshots on `tickSnapshotEnd` (~11s each) while SPY charts, depth and tape shared the IB loop, it could not finish. The exception left `commit_table` unreached, so `gainer_cache_ts` stayed 0 and scanner L1 had no roster to subscribe to (`symbols_for_tab` reads the cache), making the gap self-sustaining. (2) The premarket Gappers lease used `TOP_OPEN_PERC_GAIN`, which measures today's open against the prior close; before 09:30 there is no open, so IB returned an empty list, and an empty-but-successful commit still called `mark_live` and stamped `last_scan` — advertising a fresh scan of nothing. Integrity then classified Gainers with no timestamp as `pass` ("OK if another scanner list is live"), so two dead tables vouched for each other. The correct behavior was already written down as ADR 010 decision 5 (accepted 2026-08-14) and never implemented; the 2026-07-14 `TOP_OPEN -> TOP_PERC_GAIN` fallback lived on the one-shot path that the 2026-08-07 authoritative cutover made unreachable.
- **Fix:** Names-first admission. `scanner_hydrate` no longer imports discovery at all: a ranked IB name becomes a row immediately with `price=None`, IB rank order preserved, and the L1 hot path (`reprice_mover_row`, which now writes back the resolved `prev_close`) fills price/change. New `ibkr/gapper_view.py` projects premarket Gappers from the live Gainers roster at `GAPPER_MIN_GAP_PCT` and is the only `gapper_cache` writer under `discovery=ibkr`; the `TOP_OPEN_PERC_GAIN` premarket lease is gone. `commit_table` refuses empty batches (no `mark_live`, no timestamp) and clears `ibkr_bridge_last_error` on a landed roster; a failed commit now sets it so REST `feed_error` shows a reason. Integrity fails Gainers with no roster while IBKR is connected inside its window. One-shot IBKR discovery is dead by construction: both runners refuse and `adapters/ibkr_scanner.py` raises; `discovery.get_gappers` deleted. Morning check gained a Gainers leg. Guard test asserts `scanner_hydrate` never references `snapshot_quotes` again.
- **Fix class:** admission (prior ten entries on this symptom were `surfacing` / `ownership` / `infra`).
- **Keywords:** empty gappers, empty gainers, last_gainer_scan 0, snapshot_quotes, on_ib timeout, hydrate failed, Warning 165, TOP_OPEN_PERC_GAIN, names-first, gapper_view, ADR 010 decision 5, scanner admission, integrity pass

## 2026-08-19 -- Installer .env missing IBKR_ENABLED; no door-trail UI

- **Symptom:** After NSIS install, IB Gateway showed API connected and phone 2FA succeeded. Nova stayed IBKR offline. Trading prerequisites: `IBKR_ENABLED` fail, session reason `disabled`. Door trail not visible.
- **Cause:** `%APPDATA%\Nova\.env` was an old Alpaca stub (`IBKR_GATEWAY_MODE=live` only). Packaged Electron does not read the repo `.env`. Door trail was JSONL + GET only -- no panel.
- **Fix:** Sidecar merges missing connection keys (`IBKR_ENABLED`, host, ports) without adding spend gates. UI: Door trail on prerequisites and Activity.
- **Keywords:** installer, APPDATA, IBKR_ENABLED, door trail, audit, disabled, NSIS

## 2026-08-19 -- Live click with paper still on 4002 skipped 2FA

- **Symptom:** Operator clicked Live. Trail showed `plan=start_ibc` / `launched_ibc`. No SECOND FACTOR. Status stayed `connected=false`, `intent=live`, preferred 4001 dark, paper 4002 still LISTEN.
- **Cause:** One IBC / one `C:\Jts` hijacks the existing paper window. Live `start_ibc` did not stop 4002 and did not clear `Restart=OK`, so IBC never opened a cold live login.
- **Fix:** `start_ibc` and `replace_target` call `launch_or_focus_gateway(..., force_restart=True)`. Force restart stops both listen ports. Live also clears `Restart=OK`. Reconnect-only stays when the target port is already up.
- **Keywords:** Live, 2FA, IBC, 4002, start_ibc, force_restart, Restart=OK, dual Gateway

## 2026-08-19 -- Paper mode must not dial live 4001

- **Symptom:** After a Paper click with 4002 still dark, Nova connected to 4001 as paper, refused the live account, and the trail filled with `refused` rows. IBC harvest also tagged old live 2FA onto the paper click.
- **Cause:** `_resolve_config` used a leftover "paper often listens on 4001" probe. IBC harvest read the last 120 lines of the existing live IBC log. One IBC install also cannot keep two Gateway processes -- a second start retargets the same window.
- **Fix:** Paper always dials 4002. Harvest only the IBC log suffix from this click. Heal-before-dial respects intentional suppress first.
- **Keywords:** trail, paper, 4001, refuse, IBC harvest, dual Gateway


## 2026-08-19 -- Paper/Live killed the other session and asked 2FA again

- **Symptom:** Switching Paper then Live closed Gateway and required Mobile 2FA every time. Operator expected on-the-fly flips.
- **Cause:** ADR 013 `force_ibc` stopped both 4001 and 4002 and every Gateway window. One process is one IB account, but Nova did not keep two processes. Intentional heal also expired after 2 minutes and could yank to the other door.
- **Fix:** Reconnect when the target port is already listening. Start IBC only if that port is dark, without killing the other. Replace only a wrong-class session on the target port. Intentional mode stays set until that door connects.
- **Keywords:** Paper, Live, 2FA, dual Gateway, force_restart, switch_plan, reconnect


## 2026-08-19 -- Gateway password field stayed empty

- **Symptom:** Login showed username (or Live Trading) but the password box was blank.
- **Cause:** Nova blanked `IbPassword` so IBC would not click Log In, then waited on an IBC log suffix for "Setting user name". That wait timed out, so `type_password_only` never ran. Disk password was restored later, after the form was already empty. Java also ignores SendInput unless IBC focuses the field.
- **Fix:** Stop blanking the password. Point `IbLoginId` at `IbLoginIdLive` or `IbLoginIdPaper` before IBC starts. IBC fills both fields and clicks Log In. Live 2FA is on the phone after that.
- **Keywords:** IbPassword, empty password, IBC, type_password_only, IbLoginIdLive


## 2026-08-19 -- 2FA code box never appears after IBC Log In

- **Symptom:** Gateway already logged in (farms green, Client 17 red). Operator never saw the authentication-code panel.
- **Cause:** IBC fills credentials and clicks Log In. Paper/simulated login does not use 2FA (IBC source). Live 1016+ puts the code box in the same Login window after it retitles to SECOND FACTOR AUTHENTICATION. `jts.ini` `Restart=OK` also reuses the week session.
- **Fix:** Live force-restart skips IBC, clears `Restart=OK`, leaves the Login window up. Operator clicks Live Trading then Log In.
- **Keywords:** 2FA, SECOND FACTOR AUTHENTICATION, IBC, Log In, Restart=OK, Client 17

## 2026-08-19 -- Live 2FA skipped because of AutoRestart, not missing IBC

- **Symptom:** Operator wanted IBC to fill username/password and still get an IBKR Mobile code. Skipping IBC left a blank login. With IBC, login finished in seconds with no phone prompt (Simulated Trading).
- **Cause:** IBC AutoRestart is a week-long Gateway token. IBKR does not send 2FA on those logins. IBC also cannot send the phone prompt -- only IBKR can, after Log In on a live cold session. TradingMode=live plus paper Simulated Trading still means no live 2FA.
- **Fix:** Live force-restart uses IBC again. Live align writes `AutoLogoffTime` and clears `AutoRestartTime` in local IBC config. Paper restore keeps `AutoRestartTime=11:45 PM`.
- **Keywords:** IBC, 2FA, IBKR Mobile, AutoRestart, AutoLogoff, Live switch, autofill

## 2026-08-19 -- IBC auto-login hid the Live 2FA screen

- **Symptom:** Operator expected IBKR Mobile / login to stay on screen for a Live switch. Gateway went straight to farms green + Client 17 red. No lasting Authenticating window.
- **Cause:** IBC is set to type saved credentials and click Log In. Log: Trading mode=live, Click button: Log In, Authenticating for ~3s, Login has completed, Simulated Trading config dialog. 2FA is not required when IB accepts that auto-login. Nova then refused paper-on-live.
- **Fix:** Live `force_restart` launches Gateway exe without IBC so the login screen stays. IBC log steps are copied onto `ibkr-gateway-trail.jsonl` (`actor=ibc`). Paper still uses IBC.
- **Keywords:** IBC, auto-login, 2FA, Authenticating, Simulated Trading, Live switch, Client 17, gateway trail


## 2026-08-19 -- Live click snapped back to Paper on port 4001

- **Symptom:** Operator clicked Live. Capsule flashed Live then returned to Paper. They were sure they were already live because 4001 was open from an earlier session. API log: intentional live, then `clearing intentional mode live (follow paper account)`, then `broker_account_kind=paper -- disconnecting`, then self-heal paper on 4001.
- **Cause:** Three facts were one label. Port 4001 was treated as live. Unattended follow-paper ran during the Live click and persisted paper. `request_gateway_mode` then redialed the same paper socket and refused it.
- **Fix:** ADR 013. Switch plan: already live = no-op; paper vs live = force IBC (`TradingMode`) and stop the listen PIDs (including java). Follow-paper is skipped while intentional live is set. Capsule uses account kind + intentional, not the port.
- **Keywords:** Live capsule, snap-back, 4001, follow paper, DU, ADR 013, force_restart, IBC TradingMode


## 2026-08-19 -- API Client 17 red: paper account on live mode

- **Symptom:** After a cold IBC start, Gateway farms green and port 4001 LISTEN, but API Client stayed disconnected. Logs: connect succeeded then `refusing session -- PAPER account ... while establishing live mode (accounts=['DUQ266899'])` and immediate disconnect. Repeats every ~11s.
- **Cause:** Open live / `IBKR_GATEWAY_MODE=live` always required a live account id. IBC came back as paper (DU…) on 4001. Paper-pin disconnect left Client 17 red. Follow-Gateway only flips when the *other port* is up, so same-port paper-on-4001 never healed.
- **Fix:** If managedAccounts are paper while Nova asked live, persist paper and keep the socket (safe demote). Never auto-promote live. Paper reconnect may dial 4001 when 4002 is dark.
- **Keywords:** API Client disconnected, Client 17, DUQ266899, paper-pin, 4001, follow paper account


## 2026-08-19 -- Open live Gateway killed a logged-in session

- **Symptom:** IBKRPRO farms green on live 4001; Nova Trading prerequisites still said log in / 2FA and showed Open live Gateway. Clicking it restarted IBC (process start 13:47). API :8000 later refused. 03:55 morning check failed `ibkr_status reason=connecting` even though Gateway + API health passed.
- **Cause:** `launch_or_focus_gateway(live|paper)` always Stop-Process'd a running Gateway then spawned IBC. Prerequisites always rendered those buttons. Loud login banner treated `live_port_open_but_disconnected` and missing status fields as a login outage. Morning check failed on the first `connecting` snapshot instead of waiting for READY.
- **Fix:** Attach/focus when the requested API port is already listening, or when Gateway is up with neither port open (2FA). Launch buttons only for a true launch action. Banner hides for port-open-but-disconnected and API probe misses. Morning check retries connecting/synchronizing up to ~90s.
- **Keywords:** Open live Gateway, already_listening, 4001, Trading prerequisites, session READY, morning-check, connecting, IBC kill, flicker


## 2026-08-18 -- pytest still could write the operator cache (import-time path snapshot)

- **Symptom:** Per-file monkeypatches did not stop pollution. `cache._CACHE_DIR` and `HOD_MOMO_CONFIG_FILE` are baked at import, so an autouse fixture that ran after `import cache` still pointed at `backend/.cache`. Live `.env` `IBKR_GATEWAY_MODE=live` could also leak into paper tests.
- **Cause:** Isolation was opt-in per test file (2026-07-20 ledger, 2026-07-23 fake LBGJ). No session-wide pin before backend imports.
- **Fix:** `backend/tests/conftest.py` sets `NOVA_CACHE_DIR` and paper Gateway mode at import, then autouse-rebinds `_CACHE_DIR`, legacy paths, and HOD config/blocklist file constants per test.
- **Keywords:** pytest, NOVA_CACHE_DIR, conftest, cache pollution, hod-momo-config, IBKR_GATEWAY_MODE, LBGJ

## 2026-08-18 -- Volume is not hist ownership for 1Min candles

- **Symptom:** After the L1 hist-protect UPSERT (`WHERE volume = 0 OR excluded.volume > 0`), a red test with a volume=0 hist candle (halt / illiquid AH) still jumped high from 1.40 to 9.99 on one L1 last. The same SQL also let an L1 row with volume=50000 rewrite a hist candle.
- **Cause:** Two writers shared `(symbol, timeframe, ts, source=ibkr)`. Volume was used as a lock. IB historical minutes can be volume=0, so the clause treated hist as live. An integrity alarm on OHLC drift would have caught it after the hangover, not prevented the shared identity.
- **Fix:** Unique candle is `(symbol, timeframe, ts)`. Hist writes `source=ibkr` and always replaces. L1 writes `source=ibkr_l1` and updates only `WHERE source = ibkr_l1`. `init_db` migrates legacy DBs by copying `ibkr` first, then other sources into gaps.
- **Keywords:** bars_intraday, l1_minute, candle unique, ibkr_l1, volume=0 hist, UPSERT WHERE source, ADR 012

## 2026-08-18 -- L1 live 1Min upsert would clobber IB historical candles

- **Symptom:** Scanner L1 last prices write the same `bars_intraday` table charts read. The first upsert SQL did `close = excluded.close` and `high = MAX(...)` even when the row already had IB historical volume. A red test showed a hist candle (o=1.20 h=1.40 l=1.10 c=1.35 v=2938) become high=9.99 after one L1 last of 9.99.
- **Cause:** Live last is not a trade bar. Sharing one table without a hist-protect clause meant the HOD seed writer could rewrite Quote/Trader 1Min OHLC, and `_persist_derived` is only safe because it derives from the hist fetch payload -- HTTP `/bars` 1Min reads the mixed store.
- **Fix:** `enqueue_intraday_bar` UPSERT `WHERE volume = 0 OR excluded.volume > 0`. L1 may insert a missing minute and refine a volume=0 live row. It must not touch a hist row. Coverage still is not stamped. `test_l1_upsert_does_not_clobber_hist_ohlc` plus live `/bars` OHLC invariants.
- **Keywords:** bars_intraday, l1_minute, chart OHLC, hist clobber, UPSERT WHERE, volume=0, ADR 012

## 2026-08-18 -- hod_surge_after_seed afterhours warn: stale store bars poisoned Squeeze

- **Symptom:** After zero-IB HOD seeding shipped, `/api/integrity` stayed `hod_surge_after_seed` warn: "13 seeded symbol(s) still have surge=None" for 40+ minutes in afterhours. Last trade age was ~1s. Chart 1Min in `bars_intraday` was 35-99 minutes stale for 76/80 HOD symbols; tape `bars_1m` was empty for almost all of them.
- **Cause:** Two stacked mistakes. (1) `seed_symbol` copied the last 15 stored 1Min bars into the live surge buffer with no recency filter, so RTH fossils from ~15:20 ET sat next to a 16:50 live print. (2) `count_surge_none_after_seed` treated first-to-last span >= 5 min as "the squeeze window elapsed." `price_surge` only looks at the last 5 minutes of the latest print, so those fossils made integrity yell while Squeeze correctly returned None. This is not afterhours illiquidity we should "accept." It is a window mismatch the check invented.
- **Fix:** Session high still seeds from full-session store bars. Surge buffer only takes bars younger than `HOD_MOMO_SURGE_SEED_BARS` minutes. Integrity counts None only when that same window has >=2 prices (the case where Squeeze should return a number). Sparse/gapped tapes are not a Nova failure.
- **Keywords:** hod_surge_after_seed, surge=None, afterhours, bars_intraday stale, squeeze window, price_surge, filter_bars_to_recent, count_surge_none_after_seed

## 2026-08-18 -- IB loop wedged 67s: synchronous SQLite archive writes per tape print

- **Symptom:** Trading prerequisites modal red: "Nova API (:8000) -- IB loop wedged -- desk blocked." `/api/mode` showed `ib_loop_lag_ms` `last_ms=48453`, `max_ms=67091`, `wedged=true`, `high_streak=35` while `http_loop_lag_ms` stayed at **11ms** and uvicorn answered in 2-33ms. IB Gateway was connected and READY the whole time. `hod_momo.log` showed L1 ticks arriving in bursts of ~50 symbols in 0.4s separated by **10-12s gaps**. Charts and scanner prices looked frozen; T&S kept printing.
- **Cause:** Not `reqHistoricalData` and not pacing. `py-spy dump` caught the `nova-ib-loop` thread inside `archive/capture.py::record_tape_print` in **8 of 8 samples**, called from `ibkr/tape_stream.py::_on_tape_update` -> `ib_async` `tcpDataProcessed`, i.e. **inside the IB socket callback**. Every tape print ran two full synchronous SQLite transactions: `record_tape_print` (a fresh `sqlite3.connect` + `PRAGMA foreign_keys` + `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL` + INSERT + `commit` + `close`) and then `bump_counter` (all of that again). `ibkr_bridge._archive_l1_tick` did the same per L1 tick. `archive/db.get_connection()` is documented "one connection per call", so cost scaled linearly with print rate: a 45M-share / 430x-RVOL runner (PFSA) put thousands of connections per second in front of every `reqMktData` tick. The IB loop is where L1 is delivered (ADR 010), so the archive write path starved the entire desk's market data while the HTTP loop looked perfectly healthy -- which is exactly why the banner fires on IB lag alone.
- **Fix:** New `backend/archive/write_queue.py` splits producer from writer. IB-loop producers (`tape_stream`, `ibkr_bridge._archive_l1_tick`, `bar_builder` minute rollover via `queued=True`) only append to bounded in-memory deques -- the lock is never held across disk I/O. One `archive.write_queue` drain task on the HTTP loop pops batches every 1s and writes them via `asyncio.to_thread` with **one** connection, `executemany`, and a single commit; counters are bumped once per batch by delta. Overflow drops oldest and counts it under `tape_dropped` so loss is visible rather than unbounded RAM or a second wedge. Offline backfill/rollup keeps the direct write so callers still read rows back immediately.
- **Keywords:** IB loop wedged, ib_loop_lag_ms, API_WEDGED, desk blocked, py-spy dump, record_tape_print, bump_counter, get_connection per call, sqlite on event loop, tcpDataProcessed, tape_stream, record_l1_tick, reqMktData starved, ADR 010, archive write queue, charts frozen, scanner frozen

## 2026-08-18 -- Whole scanner column froze: one dominant tab hint, zero L1

- **Symptom:** Gainers prices did not change on the live desk. `/api/integrity` showed `l1_active_tab: 0` with `l1_active_hod: 40` while 50 gainer rows existed; a `/ws/scanner` listener got **0 `price_patch` in 12s**, reproducible after every page reload. HOD ticks and `scanner_l1_age_sec` were both ~199s stale at the same instant.
- **Cause:** Not IB historical pacing (the prior session's theory). `scanner_tab_registry.get_dominant_tab()` collapsed all clients to **one** table, but the desk renders several at once (main tab + scanner dock). `DEFAULT_ACTIVE_TAB` is `gappers` and is not persisted, so every reload declared `gappers` -- frozen after 09:30, so `symbols_for_tab` correctly returned `[]` (ADR 008). That emptied `_active_tab_symbols`, and `flush_loop`'s `if sym in _active_tab_symbols` filter then dropped **every** row for **every** table and `continue`d. Total silent feed outage with `l1_error: null`. Same failure when two desk windows sat on Gappers and one on Gainers: majority won, the Gainers window froze. The prior session measured 30 patches/12s only because its own probe had sent `set_active_tab: gainers`.
- **Fix:** Clients now declare the **set** of displayed tables (`tabs: [...]`, `tab` kept for compat). `get_active_tables()` returns the union, most-demanded first. `scanner_l1` tracks `_active_tab_tables` (symbol -> owning table) instead of one set, so `flush_loop` emits one `price_patch` **per table** and cannot cross-tag a frozen table's rows. A displayed table with rows that streams nothing now sets `subscription.error` instead of going quiet. `HodMomoDock` declares its table in an effect (mount included), so a restored dock roster is not silent.
- **Keywords:** gainers frozen, price_patch missing, l1_active_tab 0, dominant tab, DEFAULT_ACTIVE_TAB gappers, frozen table starves L1, _active_tab_symbols, ADR 008, scanner dock, multi-window starvation, set_active_tab tabs

## 2026-08-18 -- /bars 500s: bars_store calls in chart_bars broke two ways

- **Symptom:** After the pacing send-rule commit, `GET /api/ticker/{sym}/bars` 500'd on every stored+ready chart: first `NameError: name 'bars_store' is not defined` (thin store), then `AttributeError: 'str' object has no attribute 'get'` once a series was complete.
- **Cause:** Two mistakes in the same edit. (1) `fetch_chart_bars` referenced `bars_store`, which that module only imports lazily inside helpers. (2) `is_coverage_fresh(symbol, timeframe)` was the wrong signature -- it takes a coverage **dict** (`historical_service.py` had it right); the symbol string landed on `coverage.get`. Every existing test patched `_store_read` and either ran with `is_ready=False` or an empty store, and the new tests mocked `is_coverage_fresh` itself, so the real call shape ran zero times in the suite.
- **Fix:** `_store_series_settled(timeframe, bar_count, coverage)` helper with the module's lazy-import style; `routes/ticker.py` warm skip passes `stored.get("coverage")` too. Fill branch reports `filling=True` honestly. Regression tests now use the **real** `is_coverage_fresh` with `fetched_ts` in the fixture coverage, so the signature is exercised.
- **Keywords:** NameError, AttributeError, bars_store, is_coverage_fresh signature, chart_bars, 500, lazy import, mocked seam hid call shape, stored+ready path

## 2026-08-18 -- Gainers prices froze after chart-fill fix

- **Symptom:** After commit `fe192b3` (chart fill defer), Gainers scanner rows stopped updating while Quote Panel ticks still moved. Log showed `historical fill deferred ... wait 333.8s` / `wait 167.9s` lines.
- **Cause:** The "defer instead of drop" fix slept `min(wait, 16.0)` then sent `reqHistoricalData` anyway. With the 60 req / 10 min bucket exhausted, each warm/open_chart request sent into a 200-600s pacing debt. Historicals share the single IB Gateway socket with `reqMktData` L1 ticks (ADR 010), so the historical storm starved the scanner L1 streams. Verification of the chart fix measured candle counts, not L1 freshness or `ib_loop_lag_ms`.
- **Fix:** Send rule is now "never send `reqHistoricalData` while `wait_seconds > 0` beyond IB's short 2s/15s windows." `warm` sheds on any wait like `background`. `open_chart` sleeps only short windows; long 10-min-bucket debt is rescheduled via `loop.call_later` (no sleep on the IB loop). `/bars` and ticker WS skip `schedule_fill` when the stored series is complete and fresh. Red-first tests in `test_historical_service.py`.
- **Keywords:** gainers frozen, L1 starved, pacing wait, HistoricalShed, sleep-then-send, ib_loop_lag_ms, reqMktData, ADR 012, ADR 010, warm priority

## 2026-08-18 -- Chart fill dropped on pacing wait

- **Symptom:** After the viewport fix, some panes still showed only today's candles (1Hour ~9 bars store-wide). Isolated 1Hour filled to 400; a 6-timeframe burst did not. No shed line in the log.
- **Cause:** `request_bars` returned the stored stub whenever pacing wait > 0 and the store had any bars. `_run_fetch` already knew how to sleep the wait. A 9-bar 1Min-derived stub counted as "has bars," so the real 3-month 1Hour fetch never ran. Same-contract cap (5 / 2s) on a chart grid made this the default. Two helpers hid it: `store_series_complete` treated 8 bars as done, and `_persist_derived` read with `limit=len(derived)` so it could not see a longer series.
- **Fix:** `open_chart` / `warm` fall through to `_run_fetch`. Background still sheds. Per-timeframe min bar counts. Derived write reads `CHART_DEFAULT_BARS`. Shed/defer log at INFO.
- **Keywords:** 1Hour stub, pacing, HistoricalShed, derive_from_1min, store_series_complete, AIXC, ADR 012, same-contract cap

## 2026-08-18 -- Chart history arrived but panes stayed on the live tip

- **Symptom:** After ADR 012, Trader CDTG 5Min/10Sec showed 1-2 candles, Full Day was blank, 1Min looked only like the last hour. Graphs still felt slow. No red timeout.
- **Cause:** Several stacked bugs, not one timeout. (1) `bars_patch` / background `setData` did not fit the time scale, and MACD's child range copied last-N back onto the price chart. (2) Live ticks invented the first candle on an empty series, so later history stayed zoomed on "now." (3) ChartGrid abort cancelled the shared `/bars` HTTP, so 10Sec/1Day never landed. (4) `bars_store.read` treated a 1-row tape `bars_1m` as a complete 1Min chart. (5) Daily indicator conversion dropped every 1Day bar (`typeof time !== 'number'`). (6) The Desktop/API process started at 10:36 and never loaded the 11:43 ADR 012 worker -- `/bars` had no `coverage`.
- **Fix:** Session-sized time scale after every full `setData`. Parent-to-child oscillator sync only. No first candle from a tick. Shared fetch ignores caller abort. Chart store is `bars_intraday` only; stub series are not "fresh." Daily bars get numeric times. Restarted the API so store-first actually ran.
- **Keywords:** CDTG, chart gaps, fitContent, bars_patch, MACD logical range, bars_1m, 1Day, AbortError, coverage, filling, ADR 012

## 2026-08-18 -- Chart timeout was the wrong constraint

- **Symptom:** Clicking a scanner row (AIXC) or switching Trader symbols always started with "Chart bars timed out -- IBKR historical may be busy." The same overlay kept coming back after queue, cache, retry, and cancel-stampede patches.
- **Cause:** Nova serialized all historicals (and snapshots, and completed orders) through one `cold_slot` mutex, then stacked a client one-at-a-time queue and a 25s abort on top. IB's documented limits are 50 simultaneous historicals and a *rate* budget (60/10 min, 6+ same contract / 2s, identical / 15s). A click queued behind surge seed (HTTP loop awaiting `assert_ib_loop`) and `snapshot_quotes`. AbortError from the 25s timer *or* symbol-switch cleanup painted the same red string.
- **Fix:** Store-first `/bars` + paced `historical_service` (ADR 012). Historicals leave `cold_slot`. Surge seed hops `on_ib` at background priority. Client queue and 25s abort deleted. UI shows coverage / filling instead of a dead-end timeout.
- **Keywords:** Chart bars timed out, IBKR historical may be busy, AIXC, cold_slot, barsFetchQueue, run_coro, surge_seed, ADR 012, historical_service

## 2026-08-18 -- MACD pane empty with toggle on

- **Symptom:** Quote chart MACD button was active. The MACD label showed under the candles. Histogram, MACD line, and signal line were missing (empty black pane).
- **Cause:** Two stacked issues. (1) Quote slot is a fixed height. `measureChartFillHeight` sized the price LWC before the oscillator existed, and the body was not clipped, so the candle canvas covered the MACD chart. Grid already reserved oscillator space; the quote panel did not. (2) `computeMacdPane` dropped warmup NaNs, so the oscillator series was shorter than the price series. Logical-range sync then showed a window with no MACD points.
- **Fix:** Keep whitespace points so MACD/RSI length matches price bars. Remeasure fill height when oscillator count changes. `overflow: hidden` on `.chart-body` and `flex-shrink: 0` on oscillators. Do not consume the oscillator paint key until series exist.
- **Keywords:** MACD, oscillator, quote panel, lightweight-charts, whitespace, measureChartFillHeight, logical range, SNDQ

## 2026-08-17 -- False Disconnected + hung quote after refresh

- **Symptom:** After a hard refresh on Trader F: yellow Disconnected next to Paper/Live, "Loading quote for F...", all four panes "Chart bars timed out", header Gateway delayed. API chip stayed green. Positions still showed last Net Liq.
- **Cause:** `useIbkrStatus` boots as `connected=false` until the first poll, and last-good account work treated that as a real drop. Ticker WS waits forever for `initial` while `build_ticker_fast` sits behind inflight `snapshot_quotes`. Four chart panes abort at 25s and only retried once. Gateway was connected; `market_data_delayed` is paper Error 10167, not offline.
- **Fix:** Persist last status in sessionStorage; hide Disconnected until status is known; do not stale the account book before the first connected session; seed quote from GET `/api/ticker/{symbol}` at 2.5s; retry empty charts up to 8 times; apply the F5 desk epoch from the already-mounted hotkey provider.
- **Keywords:** Disconnected, Loading quote for F, Chart bars timed out, GATEWAY delayed, snapshot_quotes, hard refresh, F5

## 2026-08-17 -- Last-good wipe on IBKR disconnect

- **Symptom:** When IBKR dropped, Working Orders, Positions, and Orders (Today) went empty even though the last snapshot was still in React state a tick earlier.
- **Cause:** `IbkrAccountContext` and `useClosedOrders` treated `!ibkrConnected` as "clear the book" instead of "freeze the last good snapshot." Flatten/Cancel then had nothing to show, and reconnect looked like a blank desk.
- **Fix:** Keep the last rows, set `stale` / `staleSince`, and put the last-known message on `error` so existing `disabled={Boolean(error)}` gates (Flatten, Cancel, Fill, hotkeys) stay closed. Banner copy lives in `disconnectCopy.ts`.
- **Keywords:** last-good, disconnect, IbkrAccountContext, useClosedOrders, stale, Flatten, Cancel

## 2026-08-17 -- Epoch-0 L1 ticks wrote 1969-12-31

- **Symptom:** `archive.db` and `archive_cold/1969-12-31/` held L1 rows with `ts=0` / date 1969-12-31. Daily bars (`bars_1d`) stayed empty.
- **Cause:** `exchange_ts_unix` called `.timestamp()` on a datetime that was still the Unix epoch, so the guard that was meant to reject missing stamps accepted `0.0`. `record_l1_tick` wrote it. No 1m-to-1d rollup ran in maintenance.
- **Fix:** Require unix > 1e9 (`ARCHIVE_L1_MIN_UNIX_TS`). `record_l1_tick` returns on `ts<=0`. `purge_epoch_zero_l1` deletes those rows and the 1969 cold folder on `init_db`. `rollup_daily` writes `bars_1d` from `bars_1m` inside `run_maintenance_once`.
- **Keywords:** 1969-12-31, epoch 0, exchange_ts_unix, record_l1_tick, bars_1d, rollup_daily, archive_cold

## 2026-08-17 -- Closed-orders warm 500d off the IB loop

- **Symptom:** After hours, `GET /api/ibkr/orders/closed` returned HTTP 500 (`RuntimeError: ib.* must run on the IB connect-loop`) when `ib.trades()` was empty.
- **Cause:** `closed_orders_async` called `refresh_completed_orders_cache` on the uvicorn loop. ADR 010 `cold_slot` / `assert_ib_loop` rejects that. The blotter never reached the ledger overlay.
- **Fix:** Skip the completed-orders warm unless already on the IB loop. Connect-time warm still runs there. Empty IB list plus ledger overlay is enough for Nova-placed fills.
- **Keywords:** orders/closed, closed_orders_async, assert_ib_loop, ADR 010, completed_orders, HTTP 500

## 2026-08-17 -- Orders (Today) showed ledger fills as 0 / 0 / 0

- **Symptom:** IVF Filled rows on Orders (Today) showed Order ID 0, qty 0, filled 0. The same fills were already in `execution_ledger.db` as 19085 / 19112, BUY 1.
- **Cause:** `GET /api/ibkr/orders/closed` returned only `ib.trades()` / completed-order replay. Session `orderId` and `totalQuantity` are often 0 on that replay. The route never read the ledger.
- **Fix:** `overlay_closed_orders` merges this session's Nova place/bracket rows onto the IB list (match permId, then order_id, then symbol+side when id is 0). UI formats a missing id as `--`. IB-only rows stay `ib_recovered`.
- **Keywords:** Order ID 0, Orders Today, closed_orders, overlay_closed_orders, execution_ledger, IVF

## 2026-08-17 -- Ledger omitted permId and roster JSON

- **Symptom:** IVF fills in `execution_ledger.db` had client `order_id` and payload qty 1, but no IB `permId`, no filled qty / avg, cancel rows often had no symbol, and today's `gappers-*.json` / `gainers-*.json` were missing. `init_db` on an existing ledger also raised `sqlite3.OperationalError: no such column: perm_id` when an index was created before ALTER.
- **Cause:** Reserve payload never snapshotted requested vs sent qty or spend/short gates. Telemetry never wrote `permId` / fill size onto the row. Cancel-all sometimes omitted symbol; cancel with only `order_id` did not look the symbol up. ADR 008 `commit_table` updated RAM only -- the old `scan_loop` JSON writers no longer run when persistent scanners are authoritative. A first draft of the schema put `CREATE INDEX ... perm_id` in the same `executescript` as `CREATE TABLE IF NOT EXISTS`, so existing DBs skipped CREATE TABLE and failed on the index.
- **Fix:** `build_reserve_payload` records requested/sent qty, `short_entry`, and gates. `ensure_executions_columns` ALTERs then indexes. `record_broker_facts` from orderStatus/execDetails. Cancel looks up symbol from the prior ledger row (open orders only if IB is connected). `persist_roster` writes dated JSON from `commit_table`.
- **Keywords:** permId, perm_id, requested_qty, sent_qty, cancel symbol, gappers json, commit_table, no such column, execution_ledger

## 2026-08-17 -- Orders (Today) ignores execution ledger

- **Symptom:** IVF Filled rows showed Order ID 0, qty 0, filled 0. Same-session NOMA cancels showed real ids (72165, 72159).
- **Cause:** Closed-orders UI reads IB `ib.trades()` + `reqCompletedOrders` (`order.orderId`). Completed-order replay often has session `orderId=0` and empty qty. Nova already persisted those IVF fills in `execution_ledger.db` as order_id 19085 / 19112 with payload qty 1. The blotter never queries the ledger. `permId` is not stored or shown.
- **Fix:** Diagnosis only this pass. Next: ledger-first Orders (Today) for Nova-placed rows; persist `permId` + fill qty; label IB-recovered rows. Do not stand up hosted Postgres as the live book.
- **Keywords:** Order ID 0, IVF, execution_ledger, permId, reqCompletedOrders, Orders Today, closed_orders

## 2026-08-17 -- T&S resubscribe on Scanner | Trader

- **Symptom:** Switching Scanner and Trader showed Time & Sales ERROR "Resubscribing in 10s -- please wait" while API and Gateway chips stayed green. Level 2 often still painted.
- **Cause:** Scanner called `closeTraderView()`, which emptied tabs and unmounted `StockViewTabs`. `useIbkrTape` closed `/ws/ibkr/tape/{symbol}`; last viewer ran `cancelTickByTickData`. IB rejects a new `reqTickByTickData` on the same instrument for 15s (`IBKR_TAPE_RESUBSCRIBE_GUARD_SEC`). Open net / Gateway up does not waive that rule. The desk was being destroyed, not the socket dying.
- **Fix:** Scanner | Trader is a view switch (`traderViewActive` + hidden `nova-trader-desk-slot`) so tape/L2 hooks stay mounted. Backend linger delays IB cancel 16s; remount reuses the live ticker. Last-tab X still tears down (linger covers a fast reopen).
- **Keywords:** Resubscribing in 10s, Time & Sales, reqTickByTickData, 15s guard, closeTraderView, traderViewActive, tape linger, IPST

## 2026-08-17 -- Trader 2x2 charts timeout (25s cancel stampede)

- **Symptom:** Opening Trader on IPST: 5-Minute painted; 10-Second / Full Day / 1-Minute sat on "Chart bars timed out -- IBKR historical may be busy." L2 and Time & Sales stayed live. Gateway/API chips green.
- **Cause:** Four panes (plus `/bars/batch` + ticker-WS warm) all start a 25s `run_coro` clock, but IBKR historical is one serial cold slot. First 5Min took 19.4s (`slot_wait=4.7s fetch=14.7s`) after HOD `snapshot_quotes` and a 25.8s IB-loop lag at 13:17. The other three hit 25s and `run_coro` **cancelled** them (`cancel accepted`), so 10Sec (4h of 10s bars) and 1Day (5Y) never finished or cached. Retries repeated the same cancel loop. When idle and sequential, the same 10Sec fetch is ~7s and 1Day ~1s.
- **Fix:** Client historicals now go through a priority queue (1Min/5Min, then daily, 10Sec last). The 25s abort starts at dequeue, not at pane mount. `ensureBarsBatch` is sequential `/bars` (10Sec keeps limit=1500). Ticker WS no longer warms historicals. `bars_cache.get_or_fetch` runs the IBKR pull in a detached task so `run_coro` cancel cannot kill a fetch another pane or retry still needs. Did not change global `run_coro` cancel (reconnect-safety).
- **Keywords:** Chart bars timed out, IPST, 10Sec, 1Day, run_coro, cancel accepted, historical_slot, CHART_BARS_FETCH_TIMEOUT_MS, snapshot_quotes preempt


## 2026-08-17 -- Place showed Network error; order never reached Gateway

- **Symptom:** Live ticket showed "Network error" after placing. Working orders empty. Ledger row TRUG 09:44:25 ET stuck at `validated` with no `order_id`.
- **Cause:** IB connect-loop was wedged on a historical (`ib_cold_inflight=historical`, lag 9-20s). `execute` persisted `validated` then hopped `ensure_handlers` / `placeOrder` onto that loop. The browser never got a usable JSON body and the ticket catch-all said "Network error". Gateway was up; this was not wifi.
- **Fix:** Reject place/cancel/replace while `loop_lag.is_wedged()` (`IB_LOOP_WEDGED`) before the IB hop. Ticket maps fetch/parse throws to an honest "check Working Orders" message instead of "Network error".
- **Keywords:** Network error, TRUG, validated, IB loop wedged, historical, placeOrder, ManualOrderTicket, IB_LOOP_WEDGED

## 2026-08-17 -- Trader click flashed Trading prerequisites (false API_WEDGED)

- **Symptom:** Pressing Trader opened the full-screen Trading prerequisites modal with Nova API ERROR / "Port held by a hung process (health timed out)" and a Start API button. Gateway, IBKR enabled, and orders were all green. Paper/Live looked like it did not switch.
- **Cause:** Opening Trader (SPY charts + L2 + tape) stalled the HTTP loop long enough that the header's 4s `/api/mode` probe timed out. `diagnoseBackend` labeled that single timeout `API_WEDGED`. `buildTradingPrerequisites` treated WEDGED like API_DOWN (`blockDesk` + Start API). The capsule also preferred session `mode` over configured `gateway_mode`, so a Live click stayed orange while the socket was still paper. Confirm dialog sat at z-50 under the gate (z-9000).
- **Fix:** WEDGED probe miss no longer blocks the desk or offers Start API (only API_DOWN / server `ib_loop_lag.wedged`). Header `/mode` uses the same 2-fail grace as scanner polls. Capsule follows `gateway_mode`. App dialogs sit at z-index 10000.
- **Keywords:** Trading prerequisites, API_WEDGED, Trader, Start API, hung process, Paper Live, gateway_mode, diagnoseBackend, GlobalBarStatusBridge

## 2026-08-16 -- Live pin + IBC paper restart looked like Gateway closed

- **Symptom:** Morning desk blocked on "Trading prerequisites" / "ACTION REQUIRED -- IB Gateway login" / Gateway offline, targeting LIVE 4001. Operator thought Gateway had closed overnight.
- **Cause:** Gateway was running (PID since 12:22 AM) as paper on 4002. IBC `TradingMode=paper` + `AutoRestartTime=11:45 PM` restarted it as paper. Nova still had sticky `intentional_gateway_mode=live` from last night's capsule click, so follow-Gateway would not attach. The UI treated that mismatch as a login/2FA failure.
- **Fix:** Immediate: POST `/api/ibkr/gateway-mode` paper (session READY). Lasting: expire sticky intent after 120s when preferred is dark and alternate is up; prerequisites CTA "Use paper/live Gateway"; hide the loud login banner on port-mismatch hints.
- **Keywords:** IB Gateway, paper, live, 4001, 4002, IBC AutoRestart, intentional_gateway_mode, follow-Gateway, trading prerequisites, 2FA

## 2026-08-16 -- tsc unused BACKEND_DIAG_FLAG_WEDGED in auto-heal

- **Symptom:** `npm run build` failed: `backendAutoHeal.ts(8,3): error TS6133: 'BACKEND_DIAG_FLAG_WEDGED' is declared but its value is never read.`
- **Cause:** ADR 010 removed `API_WEDGED` from `AUTO_HEAL_FLAGS` (never kill a live PID) but left the unused import.
- **Fix:** Import only `BACKEND_DIAG_FLAG_DOWN`.
- **Keywords:** tsc, TS6133, backendAutoHeal, API_WEDGED, unused import

## 2026-08-14 -- API_WEDGED mid-trade (shared loop + auto-heal kill)

- **Symptom:** Premarket Trading prerequisites showed Nova API CRITICAL / Auto-restarting API. `/livez` and `/api/health` timed out at 8s while PID still listened. Desk blocked mid-session.
- **Cause:** `ib_async` shared uvicorn's loop. HOD seed historicals + `snapshot_quotes(40)` + WETO bars occupied that loop for 7-51s. UI 4s `/mode` + 2.5s `/health` probes classified `API_WEDGED` and called `startLocalApi` (kill :8000). Process was never dead.
- **Fix:** ADR 010 -- dedicated IB connect-loop (`loop_supervisor`), one cold scheduler (no 40-wide snapshot), execute lock released before place/cancel, `API_WEDGED` removed from auto-heal, desk blocks on `ib_loop_lag.wedged`.
- **Keywords:** API_WEDGED, loop_lag, connect-loop, on_ib, ib_scheduler, auto-heal, snapshot_quotes, surge_seed

## 2026-08-14 -- Premarket API_WEDGED banner (loop starved, process never died)

- **Symptom:** Trading prerequisites flashed Nova API CRITICAL ("Port held by a hung process (health timed out)") and "Auto-restarting API" with no user action. Desk blocked while Gateway/orders chips stayed green.
- **Cause:** Shared uvicorn+ib_async event loop starved 7-51s. Trigger burst 08:14-08:16 ET: HOD surge-seed `reqHistorical` for ~25 symbols, HOD enrichment `snapshot_quotes` of 40 symbols (`run_ibkr` default label), mass scanner L1 subscribe, then WETO Trader open (multi-timeframe bars + depth + tape). First `run_coro` 25s timeout at 08:15:58; `loop_lag` hit 30s then 50.8s (`API_WEDGED` streak 3 at 08:19:21). UI `/api/mode` (4s, no grace) + `/api/health` (2.5s) timed out and armed session-once auto-heal. PID 40232 never died (up since 06:05:57, no WatchFiles). Circuit breaker only opens after 3x5s lag -- after the UI already decides to kill. Chronic ~2.3s lag all morning already sat next to the 2.5s probe.
- **Fix:** Not patched this turn. External soak running at `C:\Users\aalta\.nova\soak\` (1Hz livez/health/mode + pid + lag). Process recovered ~08:21:40 same instance `1866c7cd0078`; `lag_max_ms` still 50790. Do not treat the banner as a real restart.
- **Keywords:** API_WEDGED, health timeout, loop_lag, run_coro, HOD surge seed, enrichment snapshot_quotes, WETO, auto-heal, GlobalBarStatusBridge, PID 40232

## 2026-08-10 -- Port heal stuck on timeout (paper .env, live Gateway)

- **Symptom:** IB Gateway green (API/farms connected) on live port 4001; Nova prerequisites still blocked targeting paper 4002. Status: `disconnect_hint=paper_port_refused_live_listening`, `gateway_self_heal=null`, session stuck connecting/disconnected after reconnect.
- **Cause:** Self-heal was eligible only when preferred connect failed as `"refused"`. On Windows a dark preferred port often times out instead; timeout while preferred was dark never tried the alternate. Heal lagged the TCP truth already shown in status probes.
- **Fix:** Probe-based `alternate_heal_eligible` + reconnect fast path (`preferred_dark`): preferred dark + alternate up → attach/persist. Timeout while preferred still listens remains non-heal.
- **Keywords:** gateway_heal, self-heal, 4001, 4002, preferred_dark, timeout, paper_port_refused_live_listening, follow-Gateway

## 2026-08-07 -- Paper scanners empty (quiet window + Error 10089)

- **Symptom:** Paper Gateway connected (`mode=paper`, `connected=true`) but Gappers/Gainers/Losers empty; `last_scan=0` for hours; integrity showed frozen/empty caches.
- **Cause:** Three stacked issues: (1) `in_ready_quiet_window` stayed True forever when `_shadow[table]` was `[]` (`not []` is True), pausing one-shot discovery; (2) persistent stream was shadow-only so UI caches never filled, while one-shot `TOP_PERC_*` timed out against the same clientId leases; (3) paper API lacks paid live MD -- Error 10089 on snapshots, so hydrate wrote 0 rows even after (1)/(2).
- **Fix:** Timed-only quiet window; `IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=True`; detect 10089 and fall back to delayed market data type 3 via `maybe_fallback_to_delayed_market_data`. Keep paper for orders; share live MD with paper for real-time.
- **Keywords:** empty scanners, paper, Error 10089, delayed, quiet window, IBKR_SCANNER_PERSISTENT_AUTHORITATIVE, reqMarketDataType, share market data

## 2026-08-06 -- Route place test expected qty=5 under FORCE_ONE_SHARE

- **Symptom:** test_place_order_route_happy_path_delegates_to_orders_module failed assert 1.0 == 5.0 while shipping usable-session WIP.
- **Cause:** MASTER TEST QTY GATE (IBKR_FORCE_ONE_SHARE=True) clamps place qty to 1; the route happy-path test still asserted requested qty 5 without disabling the gate.
- **Fix:** Monkeypatch IBKR_FORCE_ONE_SHARE=False on execution.service and execution.qty_gate for that wiring test (qty-gate behavior covered in test_execution_qty_gate.py).
- **Keywords:** IBKR_FORCE_ONE_SHARE, test_routes_trading, qty clamp, MASTER TEST GATE


## 2026-08-04 -- HOD Momo TIME order wrong (AEHG above later PTIR/PLTU)

- **Symptom:** HOD Momo list showed AEHG TIME 10:40:14 above PTIR 10:40:36 / PLTU 10:40:37; IPCX 10:39:16 at bottom. Looked like rows were reshuffling vs first-in TIME.
- **Cause:** UI sorted/pinned on `created_ts` (emit/wall after consolidation) while TIME column renders trade `timestamp`. AEHG print lagged emit by ~32s so emit-sort put it above later prints.
- **Fix:** `alertDisplayUnix` prefers `timestamp`; first-catch = earliest trade TIME; sort newest first-catch on top; burst window uses the same clock.
- **Keywords:** HOD Momo, sort, TIME, created_ts, consolidation lag, AEHG, PTIR, collapseAlertsBySymbol, first-catch


## 2026-08-04 -- IBKRPRO up but Trading prerequisites said not READY / login

- **Symptom:** IB Gateway window showed API Server **connected** + Market Data Farm ON (live), but Nova Trading prerequisites painted **IB Gateway (session READY)** red with "Log into IB Gateway… 2FA". `/api/ibkr/status` had `preferred_port_reachable=true`, `connected=false`, `session_state=synchronizing`, `last_connectivity_code=1100`, `disconnect_hint=live_port_open_but_disconnected`. Fresh `connectAsync(clientId=17)` from a side script succeeded; in-process reconnect thrashed TimeWait and never reached READY until API restart.
- **Cause:** (1) Error 1100 left the long-lived API (~23h, reload) unable to re-earn usable; sticky `synchronizing` + dead transport made the desk look like a login failure. (2) Prerequisites copy keyed only on `!ibkrConnected`, so "port open / Nova stuck" was mislabeled as 2FA. (3) `earn_usable` transport-down path set reason `disconnected` without clearing `SYNCHRONIZING`; reconnect_loop had no crash fence around iterations.
- **Fix:** Restart API restored READY immediately. Code: honest prereq detail + **Reconnect** CTA when preferred port is open; `earn_usable` clears SYNCHRONIZING on transport_down; reconnect_loop wraps each iteration so a crash cannot kill the dialer; SYNCHRONIZING+TCP-down clears before redial.
- **Keywords:** IBKRPRO, session READY, synchronizing, Error 1100, live_port_open_but_disconnected, Trading prerequisites, 2FA false alarm, earn_usable, reconnect_loop, clientId 17

## 2026-08-03 -- Sample shell crashed: IbkrAccountProvider missing

- **Symptom:** App error boundary / "Failed to start": `useIbkrAccountContext must be used within IbkrAccountProvider` from `GlobalAppBar` under `SampleShell`.
- **Cause:** Live `AppShell` wraps `IbkrAccountProvider`, but sample mode returns `<SampleShell />` without that provider. Header lock/account work made `GlobalAppBar` call `useIbkrAccountContext` directly; sample still used the old "no provider" isolation.
- **Fix:** Mount `IbkrAccountProvider` inside `SampleDataProvider` in `SampleShell` (provider already returns fixture state when sample is active -- no live poll).
- **Keywords:** IbkrAccountProvider, useIbkrAccountContext, SampleShell, GlobalAppBar, AppErrorBoundary

## 2026-08-03 -- Vite PARSE_ERROR: JSX in useTradingPinGate.ts

- **Symptom:** App fail overlay: `[plugin:vite:oxc] Expected '>' but found Identifier` at `useTradingPinGate.ts:36` (`open={open}`).
- **Cause:** Hook returned `<TradingPinDialog …/>` JSX but lived in a `.ts` file. Oxc only parses JSX in `.tsx` / `.jsx`. Flatten PIN tests mocked the hook, so Vitest never transformed the broken file.
- **Fix:** Rename to `useTradingPinGate.tsx` (imports stay extensionless).
- **Keywords:** vite, oxc, PARSE_ERROR, useTradingPinGate, JSX, .ts vs .tsx

## 2026-08-03 -- symbolOrders is not defined after Orders (Today) account-wide

- **Symptom:** Stock View error boundary: `symbolOrders is not defined`.
- **Cause:** Account-wide change removed the `symbolOrders` memo but left a "Show sample" branch still referencing it.
- **Fix:** Use `orders.length === 0` in that branch (`StockViewOpenOrdersDock.tsx`).
- **Keywords:** symbolOrders, ReferenceError, Orders Today, StockViewOpenOrdersDock

## 2026-08-03 -- Orders (Today) showed 0 while watching another ticker after a fill

- **Symptom:** After flattening TGHL, Stock View on UPC showed Orders (Today) badge `0` and "No orders for UPC…"; user thought the fill was missing.
- **Cause:** Dock filtered working/closed rows and badge by the open Stock View symbol.
- **Fix:** Orders (Today) is account-wide; only Working/Filled/Canceled/Partial/All segments filter. Empty copy updated accordingly.
- **Keywords:** Orders Today, symbol scope, UPC, TGHL, closed orders, badge count

## 2026-08-03 -- Alpaca account RTT looked like "the API"; desk stayed usable when Gateway/API were down

- **Symptom:** Header showed `up · Alpaca account RTT …` while scanners/charts could still look live; no single front door telling the user to get Nova API + IB Gateway up before trusting the desk or trading.
- **Cause:** `cached_health` / API chip SoT was Alpaca `GET /v2/account`. Heal pieces (Start API, Gateway banner, spend badge) existed in isolation; no shared prerequisites checklist; bridge hardcoded `API_WEDGED` on `/mode` failure.
- **Fix:** `mark_nova_process_health()` for API chip; remove Alpaca RTT + Alpaca header chip; `TradingPrerequisitesGate` blocks desk when API or Gateway down (no data wipe); bridge uses `diagnoseBackend`.
- **Keywords:** Alpaca account RTT, API chip, nova_process, TradingPrerequisitesGate, API_DOWN, API_WEDGED, IB Gateway, trading prerequisites

## 2026-08-03 -- Time & Sales Time/Price columns flush together

- **Symptom:** In Stock View TIME & SALES, values looked like `09:35:024.3101` -- Time and Price had no gap (Size spacing was fine). Side/Exch were hidden.
- **Cause:** Narrow-pane `@container md-pane (max-width: 200px)` set Time to `48px`. At ~0.85rem tabular-nums, `HH:MM:SS` overflows the cell and butts into Price. No `column-gap` on the grid.
- **Fix:** Narrow Time column `48px` → `68px`; default Time `62px` → `72px`; `column-gap: 8px` on cols/rows; `white-space: nowrap` on `.ts-col--time` (`frontend/src/ibkr/marketData.css`).
- **Keywords:** Time & Sales, tape, ts-panel, column-gap, md-pane, Time Price spacing, overflow

## 2026-07-31 -- Sentry ERROR-log flood made the product-bug inbox useless

- **Symptom:** ~55k Sentry error events/7d on `python-fastapi`; high-priority email alert fired constantly; top issues were "IBKR not connected", bridge keep-cache, Unknown reqId, Error 326/1100 -- all `environment=production` on a local desktop. Real bugs (`startReq`, client ReferenceErrors) were buried.
- **Cause:** Default LoggingIntegration promotes every `logger.error`/`exception` to an Issue. App loggers (`ibkr_bridge`, scanner runners, `session_errors`) logged expected Gateway churn at ERROR (often twice: bridge + runner). `BenignIbkrErrorFilter` only covered `ib_async.*`. `observability.init_sentry` did not set `environment` or `before_send`. Alert 3710085 emails on any high-priority issue with frequency 0.
- **Fix:** Explicit LoggingIntegration + `before_send` denylist; downgrade bridge/keep-cache/1100/101 log levels; expand BenignIbkr codes/needles; ops-once fingerprinted captures; client stack + provider-shell filter; WS send-after-close as disconnect; `SENTRY_ENVIRONMENT=local`; bulk ignore/resolve historical noise. Alert rule still needs manual disable in Sentry UI.
- **Keywords:** Sentry, LoggingIntegration, before_send, bridge failed, ib=none, Unknown reqId, Error 1100, Error 326, environment=production, BenignIbkr, session_unusable, client_errors

## 2026-07-31 -- Error 1100 left session stuck unusable while socket stayed up

- **Symptom:** After IB Error 1100 ("Connectivity between IB and TWS has been lost"), GATEWAY chip stayed green (`/api/ibkr/status.connected=true` from raw socket) while charts/positions/L2 failed with "IBKR not connected" (`get_ib()` None because session stayed `degraded`). Manual reconnect sometimes hit Gateway Authenticating (port open, handshake timeout) and thrashed. After core status SoT landed, consumers still gated on socket-only (`chart_bars.is_connected`, integrity `ibkr_connected`, smoke "connected") and the loud login banner would fire on transport_up + !usable.
- **Cause:** `session_errors` set `DEGRADED` on 1100 but 1101/1102 only logged (dead end). `reconnect_loop` only redialed when `not isConnected()`, so a soft blip with TCP still up idled forever on `await _sleep_reconnect(5)`. Status advertised socket as `connected`. Warm-up had no positions timeout and no mid-sync revoke fence. Daily start treated Authenticating window title / LISTEN as healthy skip.
- **Fix:** Linear pipeline: 1100 revokes usable + stamps `unusable_since` + wakes loop; 1101/1102 enqueue restore (`data_lost`/`data_kept`) and run single-flight `earn_usable`; stuck unusable >30s force disconnect+recreate; port-open+timeout auth-backoff (no alternate heal); status `connected`=usable, `transport_connected`=socket, `session_reason` published. Consumers: banner only when !transport / ports dark; chart_bars + integrity + smoke require `is_ready`/usable; `unavailable_detail()` at get_ib() None sites; Start-NovaDaily waits for API port then status.connected and loud-warns for phone 2FA (no Gateway kill / no IBC edits).
- **Keywords:** Error 1100, 1101, 1102, degraded, stuck unusable, earn_usable, auth-backoff, Authenticating, transport_connected, session_reason, reconnect_loop, get_ib, GatewayDisconnectedBanner, chart_bars, integrity_live, smoke_check, Start-NovaDaily

## 2026-07-31 -- Empty gappers/gainers: `startReq` removed by the 2026-07-30 ib_async pin bump

- **Symptom:** IB Gateway connected (`/api/ibkr/status` `connected: true`, `market_data_type: 1`), discovery provider `ibkr`, but `/api/gappers` and `/api/movers` returned `gappers: []` / `gainers: []` / `losers: []` with `last_scan: 0.0` all session. `/api/integrity` `scanner_ibkr_bridge` failed with `AttributeError: 'Wrapper' object has no attribute 'startReq'`.
- **Cause:** The 2026-07-30 order-truth session (`957209c`, see below) bumped `ib_async` from PyPI `2.1.0` to git `next@c9f4c14` to make Error 10349 a warning instead of a hard cancel. That commit range also replaced `Wrapper.startReq` / `wrapper.reqId2Subscriber` with a typed `RequestRegistry` (`wrapper.requests.open(key, container=...)`) and typed subscription registry (`wrapper.subscriptions.subs_of_type(ScannerSub)`). `backend/ibkr/discovery.py`'s `_one_shot_scanner()` and `recover_scanner_slots()` still called the removed legacy facade, so every one-shot scanner request (gappers/gainers/losers/HOD seeds) raised `AttributeError` instead of returning rows. Scanner discovery was never re-verified after the pin bump because that session's own verification was scoped to order placement.
- **Fix:** Added `ibkr/discovery._open_scan_future()` — tries `wrapper.requests.open(ReqIdKey(reqId), container=...)` first, falls back to legacy `wrapper.startReq` for older pins, raises a loud `IbkrDiscoveryError` if neither exists. `recover_scanner_slots()` now walks `wrapper.subscriptions.subs_of_type(ScannerSub)` first, with the same legacy `reqId2Subscriber` dict fallback. Added `backend/tests/test_ibkr_async_scanner_api_compat.py`, which imports the **real** installed `ib_async` (not a fake) and asserts the exact surface these two functions need, plus an end-to-end call into `_open_scan_future()` against a genuine unconnected `IB()` — so the next incompatible pin bump fails a pytest in CI instead of silently emptying the scanner tables.
- **Keywords:** startReq, AttributeError, ib_async, c9f4c14, RequestRegistry, ScannerSub, reqId2Subscriber, empty gappers, empty gainers, last_scan=0, scanner_ibkr_bridge, pin bump, requests.open, subs_of_type

## 2026-07-30 -- Error 10349 false-Cancelled lied that live CYCU order failed

- **Symptom:** Live BUY 1 CYCU (order 95053) written to execution ledger as `failed` / `BROKER_REJECT` / `Cancelled` with error "Order TIF was set to DAY based on order preset." UI Working Orders still showed Pending/PreSubmitted held until next open; no position.
- **Cause:** (1) `ib_async` 2.1.0 (PyPI) treats IB Error 10349 as a hard cancel even though the order stays live. (2) Nova left `tif` blank on `MarketOrder`, triggering 10349. (3) `OrderWatch` first-ack-wins froze `Cancelled` and `finish_place` wrote ledger `failed` ~150ms before IB moved the same order to `PreSubmitted` (Warning 399: held until next RTH). (4) No ledger reconcile / open_orders re-check.
- **Fix:** Pin `ib_async` to git `next@c9f4c14` (10349=warning); always set `tif=DAY`; ACK upgrade Cancelled→PreSubmitted; grace + open_orders heal before BROKER_REJECT; closed_orders skips Cancelled still in openTrades; cancel verifies gone; surface `held_until` from Warning 399.
- **Keywords:** 10349, TIF, DAY, Cancelled, PreSubmitted, CYCU, 95053, false reject, BROKER_REJECT, Warning 399, held until open, ib_async

## 2026-07-30 -- API_WEDGED hid open-order truth during CYCU place

- **Symptom:** `/api/ibkr/status`, `/positions`, `/orders`, `/account` timed out (8s) while Gateway ports still listened; event-loop lag logged 22–35s; UI looked empty/stale.
- **Cause:** Sustained uvicorn loop lag from stacked IBKR `run_coro` / completed-orders refresh timeouts; health probes hung so Nova could not refresh Working Orders even though IB still held PreSubmitted 95053.
- **Fix:** Kill-restart API (Stop-NovaPorts + run_api); `loop_lag` exposes `wedged` after streak ≥3 samples ≥5s; `run_coro` circuit breaker reduces inflight when wedged.
- **Keywords:** API_WEDGED, loop_lag, run_coro, circuit breaker, health timeout, CYCU

## 2026-07-30 -- Shared header status strip missing on Trader

- **Symptom:** Scanner header showed MARKET HOURS / API / GATEWAY / Sample / history / lookup; Trader header did not -- looked like two different bars.
- **Cause:** `GlobalAppBar` was shared, but the middle status strip came from `ScannerBarBridge` inside `DashboardPage`. Unmount on Trader called `setScannerBarProps(null)`, so the strip vanished.
- **Fix:** AppShell `GlobalBarStatusBridge` always publishes status; store merges patches and never nulls the whole bar on route change; Dashboard only patches freshness.
- **Keywords:** GlobalAppBar, ScannerBarBridge, scannerBarStore, Trader, shared header, status strip, setScannerBarProps null

## 2026-07-30 -- Quote Panel chart time axis clipped / unreadable

- **Symptom:** Quote Panel Price Chart showed candles + volume but no readable time labels under the plot (empty dark band where the x-axis should be).
- **Cause:** Chart body was fixed at `CHART_HEIGHT_PANEL=280` while the slot used `max-height: min(320px, 40vh)` + `overflow: hidden`. Header + toolbar (~100px) + 280px body exceeded the slot, so lightweight-charts painted the time axis below the clip edge.
- **Fix:** Raise slot to `min(400px, 55vh)` (`CHART_PANEL_SLOT_MAX_PX`); panel variant uses `fillParentHeight` so LWC sizes to leftover space inside the card (same pattern as Trader grid).
- **Keywords:** Quote Panel, Price Chart, time axis, clipped, overflow hidden, CHART_HEIGHT_PANEL, lightweight-charts, fillParentHeight

## 2026-07-30 -- OPEN/DEFERRED: Premarket stack must be up before 04:00 ET (no manual morning start)

- **Symptom:** If Nova API / IB Gateway come up after the 04:00-09:30 ET gappers window, Gappers stays empty for the rest of the session (by design once mode=market). User should not have to manually start the stack every morning.
- **Cause:** Session-owned gappers roster (ADR 008) only hydrates while live in premarket. Late start after open cannot backfill that day's gappers table. Overnight Gateway/API reliability is a separate ops problem from the API_WEDGED fix shipped the same day.
- **Fix:** **Not fixed this session.** Tracked for a later chat: harden overnight Gateway (IBC AutoRestart + 2FA-at-6am path) so `NovaDailyStart` brings API+Gateway up before 04:00 ET without a human. Do not reopen the empty-gappers-after-open product rule unless product wants a frozen prior-session snapshot.
- **Keywords:** OPEN, DEFERRED, premarket, 04:00 ET, gappers empty, NovaDailyStart, IBC, overnight Gateway, manual morning start

## 2026-07-30 -- Morning empty scanners / API_WEDGED (daily-start encoding + completed-orders flood)

- **Symptom:** User wakes up, logs in, sees empty Gappers/Gainers/Losers, header `API_WEDGED` / `CONNECTING…`, "Loading market data…". Same shape yesterday. Backend sometimes still served `/api/movers` with 50/50 rows while the UI could not.
- **Cause:** Three layers. (1) IB Gateway was down overnight until ~10:34 (no scanner data in premarket). (2) `Start-NovaDaily.ps1` used UTF-8 punctuation without BOM; Task Scheduler's powershell 5.1 mangled the recycle branch so a wedged overnight API survived 6 AM. (3) Empty Closed Orders UI polls every 5s each called `reqCompletedOrdersAsync` (no cooldown), plus sync log I/O on the event loop -- `/api/health` missed the 2.5s frontend probe and the UI stuck on Loading.
- **Fix:** ASCII-only daily bootstrap with real recycle + health wait; API launcher hidden/file-redirect (QuickEdit-safe); completed-orders 300s cooldown (`force=True` on connect); QueueHandler logging off the loop thread; ps1 ASCII guard test; py-spy note in requirements-dev.
- **Keywords:** API_WEDGED, empty scanners, morning, NovaDailyStart, daily-start.log, encoding, em dash, completed-orders, reqCompletedOrdersAsync, loop_lag, QuickEdit, QueueHandler

## 2026-07-30 -- GATEWAY connected vs IBKR offline contradiction

- **Symptom:** Header showed green "GATEWAY connected · LIVE" and red "IBKR offline" at the same time; Net Liq `--`.
- **Cause:** Account cluster used `live = ibkrConnected && summary?.connected`. While Gateway was up but `/api/ibkr/account` had not returned yet (or failed), the UI fell into the offline branch and reused the "IBKR offline" label -- a different signal than the GATEWAY market-data chip.
- **Fix:** `resolveAccountChromeState`: offline only when Gateway is down; loading → "Account…"; poll error → "Account unavailable"; ready → Day P&L / Net Liq metrics.
- **Keywords:** IBKR offline, GATEWAY connected, GlobalAppBar, Net Liq, account summary, contradiction

## 2026-07-30 -- Integrity warn false positives (tick age / surge seed / delayed data)

- **Symptom:** Recurring Integrity warn banner: `hod_ticks_flowing` / `scanner_l1_stream` at ~3.9s (want <=3s), `hod_surge_after_seed` with many surge=None, Uncovered list -- especially afterhours and with a chart open.
- **Cause:** (1) `scanner_l1_stream` used price-change recency (`get_last_ok_ts`) instead of socket event liveness. (2) Tick warn threshold 3s applied 24/7 with no session awareness. (3) Nova detected IBKR delayed-data / max-tickers (Error 10167 / 101) but never fed that into evaluators. (4) Surge seed was one-shot: empty history and `HistoricalBusy` (open chart) both marked the symbol seeded forever. (5) Daily Gateway re-auth left IBC `AutoRestartTime` empty.
- **Fix:** Event-liveness timestamp in `ticks_handler`; session-scaled warn gates; delayed/max-tickers downgrade tick alarms to informational; seed requeue + `no_history` classification; local IBC `AutoRestartTime=23:45` + `NovaDailyStart` task.
- **Keywords:** Integrity warn, hod_ticks_flowing, scanner_l1_stream, surge=None, HistoricalBusy, delayed market data, AutoRestartTime, afterhours

## 2026-07-29 -- Failed to start the app (ScannerBarBridge case collision)

- **Symptom:** Black screen: `Failed to start the app. Check the console.` Console: `The requested module '/src/components/ScannerBarBridge.ts' does not provide an export named 'ScannerBarBridge'`.
- **Cause:** On Windows (case-insensitive FS), Vite resolved `import … from './ScannerBarBridge'` to `scannerBarBridge.ts` (the store) instead of `ScannerBarBridge.tsx` (the component). The `.ts` store has no `ScannerBarBridge` export, so bootstrap threw before React mounted.
- **Fix:** Renamed the store to `scannerBarStore.ts`, deleted `scannerBarBridge.ts`, cleared Vite cache, restarted the frontend.
- **Keywords:** Failed to start the app, ScannerBarBridge, case-insensitive, Windows, Vite module resolve

## 2026-07-29 -- Chart panes stuck on timeout after IBKR wedge (Full Day / 10Sec)

- **Symptom:** After IBKR reconnect, all Trader chart panes showed "Chart bars timed out -- IBKR historical may be busy." Later 1Min/5Min recovered; Full Day and 10-Second stayed red until a hard reload. Logs: `event loop lag 49184ms`, `run_coro timed out after 25.0s` (NUWE), while DFNS `/bars` eventually returned 200.
- **Cause:** (1) Client abort at 25s during the wedge left a permanent error overlay -- Full Day / 10Sec have no `CHART_REFETCH_SEC` poll. (2) Daily live tip was hard-gated off in `useChartLiveTrade`. (3) Successful foreground paint did not re-apply an already-seen `lastTrade`, so tips stayed at the REST tip until a new print (market CLOSED = none).
- **Fix:** One background error retry (~5s) in `useChartBars`; ET calendar-day `tradeBucket` for 1Day + live tip merge; always re-apply `lastTrade` after paint; forward-jump candle for intraday; `IBKR bars timing … slot_wait=… fetch=…` log for next wedge.
- **Keywords:** Chart bars timed out, Full Day, 10Sec, loop_lag, run_coro, AbortError, CHART_REFETCH_SEC, live tip, tradeBucket, historical_slot_wait

## 2026-07-29 -- Chart "Cannot update oldest data" on all panes

- **Symptom:** Trader charts (1m / 5m / Full Day) showed red overlay `Cannot update oldest data, last time=[object Object], new time=[object Object]` after the Phase 2-4 barsStore incremental paint.
- **Cause:** `paintBars` called `series.update()` on the last *two* candles. lightweight-charts only allows updating the series tip (same time) or appending a newer time; updating the penultimate bar after the tip exists throws. Daily times stringify as `[object Object]` (BusinessDay).
- **Fix:** Incremental path updates only the newest candle; on throw, fall back to full `setData`. `canIncrementalBarsUpdate` requires a shared prefix and tip-only change or single append.
- **Keywords:** Cannot update oldest data, lightweight-charts, series.update, incremental bars, paintBars, BusinessDay, [object Object]

## 2026-07-29 -- Chart UI remount / inactive-tab poll storm

- **Symptom:** Even after backend caching, charts felt sluggish on tab switch / maximize; inactive Trader tabs kept hammering `/bars`; Full Day waited behind ticker detail.
- **Cause:** (1) `useChartInstance` destroyed LWC when height/fill flipped; (2) `TickerChartErrorBoundary key={symbol}` remounted on every symbol; (3) hidden tabs kept `CHART_REFETCH_SEC` intervals; (4) `ChartGrid` gated on `detailReady`; (5) every poll did full `setData` + indicator recompute; (6) `isoToEtTime` ran expensive `toLocaleString` per bar x3.
- **Fix:** Phases 2-4 -- `barsStore` + batch warm, incremental tail updates, day-cached ET offset, stable chart instance, `chartActive` pause, mount charts immediately, 3-pane default (15m toggle), overlay paint keyed on barsRevision.
- **Keywords:** ChartGrid, useChartInstance, barsStore, chartActive, detailReady, setData, isoToEtTime, Trader tabs, incremental bars

## 2026-07-29 -- Chart historical stampede (no cache)

- **Symptom:** Opening a ticker or switching Trader tabs made charts load slowly; Full Day / other panes often showed "Chart bars timed out -- IBKR historical may be busy."
- **Cause:** Each `TickerChart` independently called `/api/ticker/{sym}/bars`. Stock View mounts 4 panes (plus Quote Panel). All hit `reqHistoricalDataAsync` through a single `historical_gate` lock with no TTL cache and no in-flight coalescing, so identical requests serialized and piled up with 30s background refetches.
- **Fix:** Phase 1 -- `ibkr/bars_cache.py` TTL cache (20s intraday / 15min daily) + async single-flight; `GET .../bars/batch`; warm grid timeframes on ticker WS connect. Expired cache never served; 503 stays loud (no stale last-good).
- **Keywords:** chart bars, IBKR historical, timeout, historical_gate, bars_cache, single-flight, ChartGrid, stampede

## 2026-07-29 -- Stock Quote looked outside Level 2

- **Symptom:** In Trader View, "STOCK QUOTE" sat in its own bar above Level 2 / Time & Sales, so the hierarchy read as Quote outside the depth widgets instead of one Stock Quote containing both.
- **Cause:** `StockViewRail` mounted a separate `StockViewQuoteCard` above the trade stack, while L2/T&S lived in a second module card (`StockViewDepthTape`). Two borders + two titles looked like peer widgets.
- **Fix:** Drop the standalone quote card from the rail. `StockViewDepthTape` is one Stock Quote card: stats strip + L2 | T&S inner panes. Split storage key `.v3` with lower default depth share so TRADE keeps space.
- **Keywords:** Stock Quote, Level 2, Time & Sales, StockViewRail, StockViewDepthTape, widget hierarchy, sv-quote-depth-card

## 2026-07-29 -- Trader TRADE widget clipped (Trading Hours cut off)

- **Symptom:** In Trader View the right-rail TRADE ticket was cut off at the bottom; Trading Hours (and sometimes submit) were unreachable. Blue arrows in user screenshot pointed at TRADE title and the clipped bottom edge.
- **Cause:** `.sv-rail__depth` used `flex: 0 0 72%` (flex-shrink: 0) so L2/T&S never yielded height. The trade stack had `overflow: hidden`, and `.sv-module-card__body` also clipped (`overflow: hidden`), so the order ticket's natural height was truncated instead of scrolling. `STOCK_VIEW_ORDER_PANE_MIN_PX = 140` was far shorter than the full ticket.
- **Fix:** Depth becomes shrinkable (`flex: 1 1 pct`); TRADE card `flex-shrink: 0` with min-height 320px; open-card body `overflow-y: auto`; default split 52% depth (storage key `.v2`); max depth clamp 68%.
- **Keywords:** Trader View, TRADE widget, clipped, Trading Hours, sv-rail__depth, flex-shrink, overflow hidden, order pane min, depthOrderSplitPct

## 2026-07-29 -- Listening rejected Ctrl+Alt modifier chord

- **Symptom:** While rebind showed "Listening…", Alt+letter recorded fine but Ctrl+Alt did nothing.
- **Cause:** TanStack `hotkeyChordFromKeydown` returns null without a non-modifier key. Our first `bareModifierRecord` treated a second modifier as "contaminated," so Ctrl+Alt could never complete.
- **Fix:** Track a set of armed modifiers and emit on the last modifier keyup; `bindingFromModifiers` / `eventMatchesModifierChord` support Ctrl+Alt; default menu chord set to `{ key: 'Alt', ctrl: true }`.
- **Keywords:** shortcuts menu, Ctrl+Alt, Listening, bareModifierRecord, modifier-only chord, TanStack

## 2026-07-29 -- Hold-Alt shortcuts menu dead in real UI (inputs + override)

- **Symptom:** After hard refresh, hold-Alt still did not open the shortcuts cheat-sheet for the user; unit tests had passed.
- **Cause:** (1) Menu keydown bailed on `isEditableTarget`, so Alt was ignored whenever ticker search / any input had focus (normal Nova state). (2) Accidental Listening rebind could store `shortcutsMenuKey` as a letter, so Alt no longer matched. Playwright only passed after clicking the blank page + clearing storage.
- **Fix:** Allow Escape/menu chord even in inputs; one-time `SHORTCUTS_MENU_DEFAULT_EPOCH` clears stored menu overrides on load; Playwright e2e covers clean, focused-input, and override-migration paths.
- **Keywords:** shortcuts menu, Alt, isEditableTarget, localStorage, shortcutsMenuKey, menu-default-epoch, Playwright

## 2026-07-29 -- Hold-Alt shortcuts menu / Listening ignored bare Alt

- **Symptom:** Shortcuts cheat-sheet on Alt felt broken; while rebind showed "Listening…", pressing Alt did nothing but letter keys recorded fine.
- **Cause:** `@tanstack/hotkeys` `hotkeyChordFromKeydown` returns null for modifier-only keydowns, so bare Alt never completed a rebind. Bare Alt peek was also bubble-phase only, so the browser could steal Alt for the menu bar before Nova handled it.
- **Fix:** Capture-phase menu keydown/keyup + preventDefault on Alt release; match Alt via `code` (AltLeft/AltRight); parallel bare-modifier recorder in `ShortcutRebindSession` / `bareModifierRecord.ts` so Listening accepts Alt/Ctrl/Shift/Meta alone.
- **Keywords:** shortcuts menu, Alt, Listening, TanStack HotkeyRecorder, modifier-only, bareModifierRecord, capture phase

## 2026-07-29 -- Quote Panel could not scroll (overflow clipped chart / T&S)

- **Symptom:** User could not scroll the scanner Quote Panel to see the full chart and Time & Sales; content was clipped at the viewport.
- **Cause:** `.side-panel` / `.side-panel-body` / `.detail-body` used nested `height: 100vh` + `overflow: hidden` flex columns designed to "fit viewport," while quote + chart + L2 + T&S + fundamentals exceeded that height -- overflow was clipped, not scrolled. Casual L2 mounts also burned `IBKR_MAX_DEPTH_SYMBOLS` (3) slots.
- **Fix:** Quote Panel is L1-only (removed `DepthTapePanel`); `.side-panel-body` uses `overflow-y: auto`; chart max-height raised. L2/T&S move to tabbed Trader View (max 3 tabs).
- **Keywords:** Quote Panel, scroll, overflow hidden, side-panel-body, Level 2, Time & Sales, Trader tabs, IBKR_MAX_DEPTH_SYMBOLS

## 2026-07-29 -- HOD multi-strategy pills clipped horizontally in STRATEGY column

- **Symptom:** Tickers that fired more than one strategy showed two pills on one line; the second label was cut off mid-text at the column edge (e.g. "Squeeze Alert - Up…").
- **Cause:** `.hod-strategy-pills` used `flex-direction: row` with `overflow: hidden` and a fixed 32px row height for virtualization -- two long strategy names cannot fit side-by-side in the STRATEGY column.
- **Fix:** Stack pills vertically (`flex-direction: column`); grow row height per extra pill; switch the HOD table virtualizer to prefix-offset windowing (`hodMomoRowLayout.ts`).
- **Keywords:** HOD Momo, strategy pills, clip, overflow, flex-direction column, virtualization, multi-strategy

## 2026-07-29 -- HOD strategies 2–9 mass-disabled + Approaching HOD (#13) missing from live config

- **Symptom:** HOD Settings showed price filters as `0` for several strategies; float strategies (3/6/9) appeared inert; selecting Approaching HOD (#13) never loaded a config (API returned only strategies 1–12). Live `hod-momo-config.json` had `schema_version: 7`, strategies 2–9 `enabled: false`, and no strategy 13 -- while Squeeze #10/#11 still fired.
- **Cause:** (1) Price `0` is by design for strategies without a price band (Squeeze, Low Float Med Rel Vol, Approaching HOD) -- not a load bug; #6/#9 already had `max_price=19.99` / `min_price=20`. (2) After schema v5 re-enabled non-Former strategies once, a later mass-disable left only Squeeze (+ Running Up) on; v5 cannot re-run once schema ≥5. (3) Approaching HOD (schema v8 / `ID_MAX=13`) never landed because a long-lived API process stayed on pre-v8 code and kept rewriting disk without #13.
- **Fix:** Bumped `HOD_MOMO_CONFIG_SCHEMA_VERSION` to 9. Migration re-enables non-Former strategies, ensures #13 exists, restores zeroed price bands on strategies 4/6/8/9. `get_configs()` fills any missing id from defaults and persists. Settings UI offers Load Defaults instead of infinite "Loading…". Restarted API so migration applied (disk schema 9).
- **Keywords:** HOD Momo, schema v9, mass-disable, Approaching HOD, strategy 13, min_price, max_price, enabled false, hod-momo-config.json

## 2026-07-29 -- API_WEDGED after cold IBKR READY (event loop starved by zombie snapshot reqMktData + dual discovery)

- **Symptom:** `/api/health` + `/livez` timed out for minutes right after an IBKR reconnect while the process stayed alive; `loop_lag` climbed 3s -> 21s -> 32s -> 65s. Repeated `IBKR: snapshot timeout (15s) for N symbols` + `run_coro timed out (cancel accepted)`. App unusable each morning after Gateway login.
- **Cause:** Two compounding defects on a cold Gateway:
  1. `snapshot_quotes`/`reqTickersAsync` opened one snapshot `reqMktData` per contract. `asyncio.wait_for` cancelled only the local *await* on timeout — the IB-side lines were never cancelled, so each timed-out batch left "zombie" snapshot reqIds streaming ticks onto the shared uvicorn event loop. My first cancel attempt used `ib.cancelMktData(contract)`, which looks up `endTicker(ticker, "mktData")`; snapshot tickers are registered under tickType `"snapshot"`, so it found reqId 0 and no-op'd.
  2. Dual discovery owners raced after READY: one-shot `scan_loop` (`run_coro [gappers]` bridge) *and* the ADR 008 persistent `scanner_stream` both opened timed requests; the stream is slow to hydrate on a cold Gateway, so one-shot kept winning and re-stamping the loop.
- **Fix:**
  - `ibkr/discovery.py`: in `snapshot_quotes` finally block, cancel every qualified contract's snapshot line via `_cancel_snapshot_tickers` — pop reqId from `wrapper.ticker2ReqId["snapshot"]` and send `client.cancelMktData(reqId)`. Snapshot zombies no longer stream after a timeout.
  - `ibkr/scanner_stream.py`: `in_ready_quiet_window()` now true for `IBKR_SCANNER_WARMUP_QUIET_SEC` (raised to 120s) *and* until every desired table has a shadow roster batch — the persistent stream is the single discovery owner while it warms.
  - `scan_loop.py`: `_ibkr_one_shot_paused()` defers one-shot discovery to the stream during that window.
  - Verified: truly cold restart — peak `loop_lag` 28.8ms, zero `/api/health` timeouts over 150s (was 60s+ wedge); gappers=46 gainers=50.
- **Keywords:** API_WEDGED, loop_lag, cold start, IBKR READY, reqTickersAsync, cancelMktData, snapshot, zombie reqId, scanner_stream, one-shot discovery, run_coro timed out, event loop

## 2026-07-28 -- Short chip showed Unknown while listing.ibkr still null

- **Symptom:** Stock View chip read "Short: Unknown" during ticker load even when Gateway/tick 236 were fine seconds later.
- **Cause:** `ShortabilityChip` treated null/undefined `listing.ibkr` the same as a real fail-closed `unknown` state.
- **Fix:** Null/undefined → `Loading...` (`data-state=loading`); Unknown only after an IBKR listing payload exists.
- **Keywords:** ShortabilityChip, Unknown, Loading, listing.ibkr, tick 236, false broken feeder

## 2026-07-28 -- Trader View unclickable (Stock View height collapsed to 0)

- **Symptom:** Stock View / sample Trader looked painted but clicks did nothing -- `elementFromPoint` over Short / L2 / ticket hit `#root`; `.stock-view-page` and rail height were 0.
- **Cause:** `AppErrorBoundary` wraps healthy children in anonymous `<div>` remount hosts. Stock View needs a body / `#root` / `.nova-shell--ticker-detail` flex column; those plain wrappers stayed `display:block` with ~4px height, so the shell collapsed while overflow content still painted. Hit-testing ignored the painted controls.
- **Fix:** Boundary host class `app-shell-host` + `stock-view.css` flex-fill rules under `body:has(.nova-shell--ticker-detail)`.
- **Keywords:** Trader View, Stock View, unclickable, elementFromPoint, #root, AppErrorBoundary, app-shell-host, flex height collapse

## 2026-07-28 -- Former Momo crowd-out starved live HOD admits

- **Symptom:** On busy days a huge Former Momo list could occupy nearly all 40 HOD L1 slots, leaving live Gappers/Gainers with 0-1 admits (audit G7).
- **Cause:** Priority admission had no sub-cap; admin allowed lists up to the full active-set capacity.
- **Fix:** `HOD_MOMO_FORMER_MOMO_MAX_SLOTS = 20`; excess former uncovered as `former_momo_over_cap`; admin rejects >20.
- **Keywords:** G7, Former Momo, crowd-out, former_momo_over_cap, active set capacity

## 2026-07-28 -- Enrichment inputs not archived (replay RVOL/float ceiling)

- **Symptom:** Replay could not faithfully re-evaluate RVOL/float/52wk gates; those fields were computed live and discarded (audit G6).
- **Cause:** No durable store for avg_volume / float_shares / fifty_two_week_high; replay primed from production-alert stand-ins only.
- **Fix:** `enrichment_snapshots` UPSERT from `update_ticker_snapshot` on change; `hod_momo_replay.prime_symbol` prefers archived rows.
- **Keywords:** G6, enrichment_snapshots, avg_volume, float, fifty_two_week_high, replay

## 2026-07-28 -- HOD active-set refresh lagged roster commit (missed first leg)

- **Symptom:** A symbol newly admitted to Gappers/Gainers/Afterhours could miss its first HOD-evaluable ticks until the next L1 reconcile cycle (~1s+).
- **Cause:** Active set rebuild was tied to empty-set bootstrap / reconcile cadence, not to roster commit (audit G8).
- **Fix:** `hod_roster_hooks.on_hod_roster_commit` refreshes the active set and `scanner_l1.request_reconcile()` wakes the reconcile wait after hydrate + legacy roster writers (not losers).
- **Keywords:** G8, active set, roster commit, request_reconcile, first leg miss

## 2026-07-28 -- session_high_raised_ts lost on restart mutes HOD as hod:not_new

- **Symptom:** After an API restart mid-session, symbols that already raised HOD go quiet -- strategies fail `hod:not_new` until the next fresh high raise, even though highs themselves were restored.
- **Cause:** `save_highs` / `_load_highs_from_disk` persisted session_highs/day_highs/source/seeded but omitted `session_high_raised_ts` (the new-HOD grace clock).
- **Fix:** Include `session_high_raised_ts` in the highs payload on save and restore with float coercion on load (audit G9).
- **Keywords:** session_high_raised_ts, hod:not_new, save_highs, restart, G9, new-HOD grace

## 2026-07-28 -- Zombie L1 subscriptions after IBKR reconnect silently starve HOD

- **Symptom:** After an IB Gateway drop + reconnect, HOD Momo can stop evaluating symbols while everything still looks subscribed: `ticks._subs` keeps entries from the dead connection, reconcile counts them as active, and no new ticks ever arrive.
- **Cause:** `backend/ibkr/ticks.py` never clears `_subs` on disconnect or READY generation bump, and `subscribe()` short-circuits when the symbol is already present (`ticks.py:159-161`). `set_owner_symbols` therefore computes desired == current and never issues `reqMktData` on the new connection.
- **Fix:** Added `ticks.clear_all_subscriptions` (detach handlers, drop `_subs` without cancelMktData on a dead socket). `client._on_session_ready` runs it after both READY sites. Session-level `session_errors.py` handles 1100 (set_degraded), 1101/1102, farm 2104/2106/2108, max-tickers 101, delayed 10167. Former xfail now passes.
- **Keywords:** zombie L1, reconnect, reqMktData, ticks _subs, HOD silent, generation fencing, 1100 1101 1102, session_errors

## 2026-07-28 -- Delayed IBKR market data is indistinguishable from real-time

- **Symptom:** A paper (or non-entitled) Gateway login can feed 15-minute-delayed prices into scanner tables and HOD alerts with no indication anywhere -- not in `/api/ibkr/status`, not in the UI, not in logs.
- **Cause:** No `reqMarketDataType` call existed, Error 10167 was only flagged in `session_errors` without status/UI, and `ticks.py` stamped `quote_ts = time.time()` while `price = last or close` could present close as last.
- **Fix:** READY calls `reqMarketDataType(1)`. Status returns `market_data_type` + `market_data_delayed`. Ticks prefer exchange time and pass `quote_quality=close_fallback` through scanner_l1 / apply_l1_quote into `price_patch`. Header Gateway chip shows amber `delayed`.
- **Keywords:** reqMarketDataType, delayed data, Error 10167, last or close, receive clock, paper account, quote_ts, close_fallback

## 2026-07-28 -- Archive records tape but not the L1 stream that drives HOD evaluation

- **Symptom:** Replaying 2026-07-17 (89,084 archived prints) through the real HOD engine reproduces momentum alerts for densely-taped symbols (SDOT/BIYA/CJMB) but cannot reproduce production alerts for CNF, WZRD, SLND, KLRS -- those fired live on L1 ticks that were never archived (4 / 1 / 2,728 / 833 prints on record).
- **Cause:** `tape_ibkr` only captures symbols with an active `reqTickByTickData` subscription (open ticker). The L1 `reqMktData` tick stream that `ibkr_bridge.apply_l1_quote` feeds into `hod_momo.on_trade_update` was not recorded anywhere, so post-hoc capture verification had a hard ceiling.
- **Fix:** Added `archive.db` table `l1_ticks` + `capture.record_l1_tick`. `ibkr_bridge.apply_l1_quote` and `apply_table_quotes` call `_archive_l1_tick` (non-fatal) immediately after a successful `on_trade_update` for active-set symbols. Historical 2026-07-17 fixture is unchanged -- only new sessions get L1 decision-stream coverage.
- **Keywords:** archive coverage, tape_ibkr, l1_ticks, L1 tick stream, replay parity, capture verification, hod momo

## 2026-07-24 — HOD Momo session bleed (yesterday PM alerts in Today)

- **Symptom:** HOD Momo tab showed `(96)` under Today (Live) but the table had ~20 rows; oldest entry was 6:43 PM the previous calendar day instead of archiving under Thu Jul 23 history.
- **Cause:** Session rollover used calendar midnight + 4 AM hour gate while cache filenames use 04:00 ET `session_key_et()`. `load_state()` also overwrote `session_date` with calendar today before rollover, so a restart between midnight–4 AM permanently skipped archive. Badge counted raw alert fires; table collapses to one row per symbol.
- **Fix:** Align `current_date_et()` with `session_key_et()`, reconcile stale alerts on load into dated archives, stop pre-setting `session_date` in `load_state()`, and show collapsed symbol count in tab/header (raw fire count when higher).
- **Keywords:** hod momo, session_key, 04:00 ET, today live, alert count, collapse, archive, rollover

## 2026-07-24 — `hotkeys` agent missing from contract test's expected set

- **Symptom:** `py -3 -m pytest tools/test_agent_contract.py -q` failed `test_discovery_finds_registered_agents` with an unexpected extra item `'hotkeys'` in the discovered agent set.
- **Cause:** When the `hotkeys` specialist was scaffolded (Phase G3), its id was never added to this test's hard-coded expected set, even though it was correctly registered in `registry.json` and had a spec file on disk. Found incidentally while removing the `daddy` agent from the same test file.
- **Fix:** Added `"hotkeys"` to the expected set in `tools/test_agent_contract.py`.
- **Keywords:** test_discovery_finds_registered_agents, hotkeys agent, agent_contract, registry.json, missing test fixture
- **Related:** `CHANGELOG.md` § 2026-07-24 — Remove daddy dispatcher; zero-hop specialist routing

## 2026-07-24 — Gateway offline looked like empty scanners

- **Symptom:** With IB Gateway logged out, Gainers/Losers showed Integrity fail + “No gainers in the feed right now” with no loud login CTA. After Gateway came back, empty tables still looked like “no data” while the scanner was resubscribing.
- **Cause:** Disconnected copy only lived in a small header chip and plain `EmptyState` text; `HodMomoIntegrityBanner` reports HOD/L1 age, not Gateway login. After reconnect, `EmptyState` fell through to the generic empty message because `ibkr.connected` was already true while ADR 008 roster/L1 was still warming.
- **Fix:** Mounted non-dismissible `GatewayDisconnectedBanner` above `TabNav` with mode-aware copy + `launchIbGateway` CTA. Added `useIbkrReconnectWarmup` (45s) so Gainers/Losers empty state shows reconnect copy during resubscribe. Feature constants in `ibkr/gatewayUxConstants.ts`.
- **Keywords:** IB Gateway, disconnected banner, empty gainers, reconnect warm-up, launchIbGateway, ACTION REQUIRED, EmptyState, ADR 008
- **Related:** `CHANGELOG.md` § 2026-07-24 — Loud IB Gateway login banner + reconnect warm-up empty state · `knowledge/task-log/2026-07-24-ibkr-gateway-login-ux.md`

## 2026-07-24 — HTTP 200 execution rejections were timed as browser successes

- **Severity:** Medium — execution-observability correctness; broker behavior and safety gates were unaffected.
- **Symptom:** Manual place, per-order cancel, and cancel-all called `timing.complete(response.ok)` before parsing JSON. Nova normally represents handled execution rejection as HTTP 200 with `{ok:false}`, so browser timing samples labeled rejected operations `outcome=ok`.
- **Cause:** The frontend treated HTTP transport success as the execution result even though ADR 007's API contract separates transport status from the body-level `ok` verdict. Flatten, Fill now, and Nova Actions inherit these clients, so the wrong label propagated across every instrumented higher-level action.
- **Fix:** Added the shared `parseTimedExecutionResponse` public helper. It parses the body first and completes timing only when both `response.ok` and `body.ok !== false`; JSON/network failures complete false and preserve throwing behavior. Place, per-order cancel, and cancel-all use it; higher-level Flatten, Fill now, and Nova Actions now inherit the corrected outcome. Regression tests cover HTTP 200 rejection, non-2xx despite `{ok:true}`, network failure, alerts, and polling recovery.
- **Keywords:** timing.complete response.ok, HTTP 200 rejection, body ok false, browser timing outcome, place order, cancel order, cancel all, Flatten, Fill now, Nova Action
- **Related:** `CHANGELOG.md` § 2026-07-24 — Add clock-safe end-to-end execution measurement and dashboard · `knowledge/task-log/2026-07-24-end-to-end-execution-measurement.md`

## 2026-07-24 — Fill-leg telemetry pushed the execution callback owner over its file limit

- **Severity:** Low — maintainability gate; execution behavior and broker safety were unaffected.
- **Symptom:** Final `maintainer_checks.py --fail-on-findings` added a change-scoped `FILE_SIZE` finding because `backend/execution/telemetry.py` reached 407 lines after bracket-leg attribution.
- **Cause:** Cached reconciliation evidence mapping remained inline with callback/watch ownership even though it is a separate transformation concern. The new leg role, side, reference, and aggregate-eligibility fields pushed the existing module seven lines over the 400-line limit.
- **Fix:** Extracted cached-fill deduplication and evidence mapping to `backend/execution/reconciliation.py`; `telemetry.note_reconciliation_fill` remains the compatibility entry and delegates without issuing requests. Focused telemetry tests and Ruff pass, and the maintainer scan no longer reports an execution-scope file-size finding.
- **Keywords:** execution telemetry, file size, 407 lines, maintainer_checks, reconciliation fill, bracket leg attribution
- **Related:** `CHANGELOG.md` § 2026-07-24 — Add clock-safe end-to-end execution measurement and dashboard · `knowledge/task-log/2026-07-24-end-to-end-execution-measurement.md`

## 2026-07-24 — Cancel failures were hidden and latency imports bypassed the feature API

- **Severity:** Medium — user-visible trading feedback and frontend dependency integrity; broker gates were unaffected.
- **Symptom:** Cancel buttons in Account and Stock View caught network failures without showing the operator an error, while non-2xx/body-level cancel rejection could also return without visible feedback. The new timing integration additionally imported `execution_latency` internals directly from sibling features, triggering cross-feature dependency warnings.
- **Cause:** The handlers assumed the next account poll was sufficient recovery and discarded the exception. Timing helpers were added before the feature had a public ADR-005 barrel, so consumers coupled to internal module paths.
- **Fix:** Added `cancelIbkrOrderWithFeedback`: HTTP/body/network failures open Nova's existing danger alert and account polling refreshes in `finally`. Both cancel handlers delegate to it. Added `execution_latency/index.ts` and migrated every external timing/dashboard import to the public surface; Stock View also consumes the existing IBKR barrel for the new cancel helper. Regression tests cover backend rejection, network failure, alert copy, and polling recovery.
- **Keywords:** cancel error hidden, TradingTab, StockViewPage, alertApp, polling refresh, cross-feature deep import, execution_latency index, ADR 005
- **Related:** `CHANGELOG.md` § 2026-07-24 — Add clock-safe end-to-end execution measurement and dashboard · `knowledge/task-log/2026-07-24-end-to-end-execution-measurement.md`

## 2026-07-24 — Mixed benchmark SLA and bracket-child fills corrupted parent metrics

- **Severity:** High — audit/evidence correctness; broker mutation and safety gates were unaffected.
- **Symptom:** A bounded window containing both synthetic and paper benchmark rows could report `mixed_population=false` and an aggregate SLA pass because both shared `mode=paper`/`source=benchmark`. Separately, target/stop callbacks were attached to the parent bracket execution without leg identity, so SELL exit fills could use the parent BUY side/entry reference and enter parent first/complete-fill and slippage aggregates.
- **Cause:** The mixed flag recomputed population from coarse mode/source fields instead of the normalized per-row `_population`. Bracket child watches carried only `order_id`/`execution_id`; evidence therefore fell back to parent payload side/reference, and child callbacks were allowed to persist parent ack/fill stages.
- **Fix:** Normalized population is now the mixing authority. Mixed aggregate distributions are labeled diagnostic-only and aggregate `sla_pass` is null; only normalized population segments carry SLA verdicts, with insufficient samples explicit. Bracket parent/target/stop watches now persist leg role, actual side, known leg reference/source, and aggregate eligibility. Child evidence remains visible but cannot update parent stages or enter parent-entry fill/slippage/provenance aggregates; migrated unattributed evidence is excluded. Query caps now use `EXECUTION_METRICS_QUERY_LIMIT`.
- **Keywords:** mixed benchmark population, synthetic paper SLA, bracket target fill, bracket stop fill, inverted slippage, child leg attribution, aggregate_eligible, benchmark_synthetic, benchmark_paper
- **Related:** `CHANGELOG.md` § 2026-07-24 — Add clock-safe end-to-end execution measurement and dashboard · `knowledge/task-log/2026-07-24-end-to-end-execution-measurement.md`

## 2026-07-24 — Frontend latency tests initially missed browser/test runtime boundaries

- **Severity:** Low — test/integration setup; no order or production runtime failure.
- **Symptom:** The first focused frontend run failed because React Testing Library lacked its DOM peer, the new dashboard test ran without jsdom, and timing completion referenced `window.setTimeout` in Node-only trading-client tests. Existing mocks also asserted the old one-argument place/flatten signatures.
- **Cause:** The new feature crossed three explicit boundaries—RTL package peers, Vitest environment selection, and browser animation-frame fallback—but the first pass assumed each was implicit. Timing options also intentionally extended established client calls, so their contract assertions needed to include the new metadata argument.
- **Fix:** Added `@testing-library/dom`, marked the dashboard render test `@vitest-environment jsdom`, made the non-RAF fallback use `globalThis.setTimeout`, and updated affected tests to assert timing/reference metadata. Focused 21/21 and full frontend 452/452 now pass; lint/build pass.
- **Keywords:** latency dashboard, React Testing Library, @testing-library/dom, jsdom, window is not defined, requestAnimationFrame fallback, placeIbkrOrder timing options
- **Related:** `CHANGELOG.md` § 2026-07-24 — Add clock-safe end-to-end execution measurement and dashboard · `knowledge/task-log/2026-07-24-end-to-end-execution-measurement.md`

## 2026-07-24 — Cancel/replace reused stale order acknowledgment and produced negative latency

- **Symptom:** Historical cancel/replace execution rows could have `broker_ack_ns < broker_sent_ns`; latency rollups silently dropped those negative values without explaining why.
- **Cause:** IBKR cancel and price-replace reuse the original `orderId`. `telemetry.watch_order(order_id)` also reused the original `OrderWatch`, including its already-set ack stamp, and `store.mark_ack_by_order_id` updated every same-boot row sharing that order id rather than the one mutation being observed. A later cancel/replace could therefore inherit an ack that happened before its own send.
- **Fix:** Every cancel/replace now creates a fresh watch bound to its `execution_id`; callback persistence targets that execution, and order-id fallback selects only the newest same-boot row. Rollups retain old rows but report negative/cross-boot/legacy exclusions by reason. Regression coverage proves original and cancel acks remain distinct.
- **Keywords:** negative ack delta, cancel latency, replace latency, reused orderId, stale OrderWatch, broker_ack_ns, broker_sent_ns, execution_id correlation
- **Related:** `CHANGELOG.md` § 2026-07-24 — Add clock-safe end-to-end execution measurement · `knowledge/task-log/2026-07-24-end-to-end-execution-measurement.md`

## 2026-07-23 — Per-operation latency review found reconnect, lock-scope, cross-boot, attribution, and probe-isolation defects

- **Symptom:** Operation-level latency was not observable, and the first implementation review found several ways its evidence or adjacent execution behavior could be wrong: replacement IB clients could stop producing ack/fill telemetry; one slow ack could block urgent sends for up to five seconds; persisted monotonic timestamps could produce invalid cross-restart deltas; the header could imply Alpaca account HTTP RTT was generic API/IBKR latency; benchmark percentiles could include prior runs; and integrity still exposed counters from a retired table-reprice loop.
- **Cause:**
  - **HIGH — reconnect wiring:** one process-global “handlers wired” flag treated every future IB instance as the original object, so reconnect replacement skipped event registration.
  - **HIGH — lock scope:** `execution.service.execute()` awaited broker ack while still inside the global reserve/validate/send lock.
  - **MEDIUM — clock scope:** SQLite persisted `perf_counter_ns` stamps without recording the process boot that owned the monotonic clock.
  - **MEDIUM — attribution:** top-level health `latency_ms` came from Alpaca `/v2/account`, but the payload/header did not name that source.
  - **LOW — probe isolation:** latency summaries selected recent ledger rows globally rather than rows belonging to the current benchmark run.
  - **LOW — stale integrity:** `table_reprice` health fields survived after the loop was retired and no longer represented the active scanner price path.
- **Fix:**
  - Wire order telemetry once per IB object via weak instance identity; replacement clients now receive their own status/execution/error handlers.
  - Keep reservation, validation, persistence, and synchronous broker send under the global lock, then release it before the ack wait.
  - Add a `boot_id` ledger column/migration and require same-boot rows for callbacks and latency rollups; legacy rows remain stored but cannot enter monotonic deltas.
  - Expose explicit health, latency, and market-data sources. The frontend allowlists `alpaca_account_http` as “Alpaca account RTT” and suppresses unknown/legacy sources.
  - Give each synthetic/paper probe a unique idempotency prefix and filter its summary to that prefix; add send→fill and ack→fill rollups.
  - Replace retired table-reprice counters with `scanner_l1` age without restarting the old loop or adding requests.
  - Verification also removed a dead `WORKING_AAPL` test fixture and an obsolete ESLint suppression. The act setup itself was already correct; see the existing 2026-07-22 “FIXED: Vitest act() environment” entry rather than duplicating that diagnosis.
- **Keywords:** per-operation latency, reconnect telemetry, WeakSet, execution lock, ack wait, perf_counter_ns, boot_id, cross-restart delta, Alpaca account RTT, benchmark prefix, table_reprice, scanner_l1 age
- **Related:** `CHANGELOG.md` § 2026-07-23 — Add bounded per-operation latency measurement and harden timing correctness · `knowledge/task-log/2026-07-23-per-operation-latency-measurement.md`

## 2026-07-23 — Live Flatten of fractional IBKR lot rejected (Error 10243); UI treated Cancelled as success

- **Symptom:** Flatten on live leftover `0.0642` shares of IBKR submitted `SELL 0.0642 MKT`, then IBKR cancelled ~86ms later with **Error 10243**: "Fractional-sized order cannot be placed via API. Please use desktop version to place this order." Position stayed open. Execution receipt could still look `ok: true` with `broker_status: Cancelled`, so the Flatten UI did not show a clear failure.
- **Cause:** (1) IBKR's TWS API hard-refuses fractional `totalQuantity` — not a Nova sizing bug. (2) Nova never preflight-blocked non-whole share qty on the place path. (3) `Cancelled` / `ApiCancelled` / `Inactive` were treated as successful acks in `execution.telemetry` / `finish_place` whenever `placeOrder` returned locally.
- **Fix:** Preflight reject fractional qty in `execution.validate` (`QTY_FRACTIONAL_API`) and in FE `buildExitFullPosition` before place. Wire `errorEvent` on order watches; `finish_place` returns `ok=false` when ack is a terminal reject status with no fill (maps 10243 → clear desktop-close message). Constants: `IBKR_ERROR_FRACTIONAL_API` / `IBKR_FRACTIONAL_ORDER_API_MSG`.
- **Keywords:** Error 10243, fractional shares, Flatten, QTY_FRACTIONAL_API, finish_place, Cancelled, IBKR leftover, 0.0642

## 2026-07-23 — Former Momo watchlist bloated to 433 symbols, crowding out every live mover from the 40-slot HOD active set (root cause of the earlier "39 priority symbols" follow-up)

- **Symptom:** Integrity banner showed `Uncovered (watched, not live): SLAI, SKHZ, STFS, CVM, NVVE, COLAR, MAAS, JLHL...` (417 uncovered) even after the stale-cache fix above. `/api/hod-momo/debug/integrity` showed `active=40/40` with `priority_reasons` = `former_momo` for 39 of the 40 slots, leaving exactly one slot for the combined live Gappers+Gainers+Afterhours union.
- **Cause:** Strategy #1's `former_momo_list` (`backend/.cache/hod-momo-config.json`) had grown to **433 symbols** — not the small hand-curated watchlist the feature was designed for (default seed is `["SPRC"]`; the literal ticker `"TEST"` and mega-caps like `AAPL`/`TSLA`/`NVDA`/leveraged ETFs `SOXL`/`TQQQ` are present, which no one manually adds to a penny-stock momentum watchlist). `former_momo_priority_symbols()` returns the list in file order and `hod_momo_active.build_active_set()` admits priority symbols before any table-ranked row, so only the **first ~39 entries in list order** ever get a slot — WLDS *is* in the list (near position 420) but can never win a priority slot under the 40-symbol capacity. `hod_momo_admin.update_config()` already rejects any UI edit that would push the list past `HOD_MOMO_ACTIVE_SET_CAPACITY` (40), which proves the bloat did not happen through the normal one-ticker-at-a-time UI path (`StrategyConfigurator.tsx`) — the 433-entry file predates that guard or was written by some other direct-state path, not by this session.
- **Fix:** Not applied yet — pruning/resetting `former_momo_list` is destructive to whatever the user actually intended to keep, so it needs the user's explicit choice rather than a silent agent rewrite. Diagnosis + the current 433-entry list are reported to the user for a decision (reset to default vs. hand-pick a short list vs. reserve a capacity floor for live movers regardless of Former Momo size).
- **Keywords:** former_momo_list, Former Momo Stock, 433 symbols, priority_reasons, build_active_set, HOD_MOMO_ACTIVE_SET_CAPACITY, WLDS crowded out, hod-momo-config.json, update_config guard

## 2026-07-23 — AH scanner sticky `ibkr_bridge_last_error` never cleared, painting Integrity fail/warn forever after one transient timeout

- **Symptom:** `/api/integrity` kept showing `scanner_ibkr_bridge: IBKR discovery bridge error (Ns ago): afterhours: TimeoutError: TimeoutError()` with the age climbing every poll (4165s → 4336s → …) even though `AH discovery (IBKR): source=ah_scan raw=50 rows=14`-style success logs kept landing every ~15-45s the whole time.
- **Cause:** `state.ibkr_bridge_last_error` is set by `ibkr_bridge.run_ibkr()` on any bridge exception and is only ever cleared by a caller explicitly resetting it on a later success. `scanner_runners/discovery.py` and `scanner_runners/movers.py` already do this (see the two entries below from the same day's Error-322/reconnect work), but `scanner_runners/afterhours.py` — added afterward — never got the same clear-on-success line for either `run_afterhours_discovery_scan()` or `run_afterhours_focus_scan()`. One `label="afterhours"` timeout early in the session therefore stayed sticky for the rest of the process's life regardless of how many AH scans succeeded afterward.
- **Fix:** Added `state.ibkr_bridge_last_error = ""` to both AH success paths in `backend/scanner_runners/afterhours.py` (after the IBKR-sourced discovery scan populates `afterhours_cache`, and after the IBKR-sourced focus/reprice scan updates it), mirroring the existing `movers.py`/`discovery.py` pattern. Added regression tests in `backend/tests/test_scanner_runners_afterhours.py`.
- **Keywords:** ibkr_bridge_last_error, scanner_ibkr_bridge, sticky integrity error, afterhours.py, TimeoutError, Integrity fail, AH discovery, run_afterhours_discovery_scan, run_afterhours_focus_scan

## 2026-07-23 — HOD active-set stale cache permanently excluded symbols admitted after freeze (WLDS lockout); highs wiped on every restart

- **Symptom:** WLDS was clearly rolling in after-hours (top-of-table, +104% change, RVOL 5743x) but never appeared in the HOD Momo alert system — `on_trade_update` was never being called for it. `/api/hod-momo/debug/symbol/WLDS` showed `session_high: null`, `high_seeded: false` while its `TickerSnap` (a separate, unrelated data path) looked live. Additionally, every backend restart (including a routine dev `--reload` on file save) silently reset every symbol's `session_highs`/`day_highs`/`session_high_seeded` to empty, throwing away high-of-day truth the engine had already correctly caught minutes earlier.
- **Cause:** `refresh_hod_active_set()` (`backend/ibkr_bridge.py`) memoized HOD's tracked symbol pool behind an `id()` + `len()` signature of the three scanner-table caches. Per ADR 008, Gappers/Gainers/Afterhours tables freeze immutable at 09:30/16:00/20:00 ET — once frozen, those cache list objects are never reassigned again, so the signature stops changing forever, and the function kept returning whatever snapshot it last computed at/near freeze time. Any symbol admitted into a table after that point (or that only entered the union after the last recompute) was permanently excluded from HOD evaluation for the rest of the session, even though its live price kept flowing to other subscribers (e.g. an open detail chart) via a separate path. Separately, `HodMomoState.session_highs`/`day_highs`/`session_high_source`/`session_high_seeded` were in-memory-only fields with no disk persistence — `hod_momo_persist.load_persisted_state()` only reloaded configs/blocklist/alerts, not highs.
- **Fix:** Removed the memoization entirely — `refresh_hod_active_set()` now always calls the pure, sub-millisecond `hod_momo_active.build_active_set(...)` fresh on every tick (no IO, ~40-70 small dict rows, cheap enough to not need caching). Deleted the now-dead `_hod_active_cache`/`_hod_active_cache_sig` globals, the `force=` parameter, and the `invalidate_hod_active_cache()`/`_invalidate_active_cache()` reset-helper pair that existed only to manage that cache. Bumped `hod_momo_surge_seed.py`'s silent "no usable bars" one-shot-seed-failure log from `DEBUG` (suppressed by the `INFO` root logger) to `WARNING` so a failed historical seed is visible instead of vanishing. Added `cache.save_hod_momo_highs()`/`load_hod_momo_highs()` (dated JSON, same pattern as alert snapshots) and `hod_momo_persist.save_highs()`/`flush_pending_highs_save()` (same throttled-dirty-flag pattern as `save_alerts`), wired into `apply_session_high()`, the 1s consolidation flush loop, and app shutdown; `load_persisted_state()` now restores highs for the current ET trading session on startup.
- **Follow-up (not fixed — separate issue, out of scope for this pass):** Live verification after the fix found WLDS *still* excluded from the 40-slot active set — not by the stale cache (confirmed gone via `/api/hod-momo/debug/integrity` showing a freshly-recomputed, fully-utilized `active=40/40` set with sub-second quote ages) but because the manually-curated "Former Momo" priority list (`hod_momo_admin` strategy config) currently holds 39 symbols, which `build_active_set()` admits unconditionally *before* any table-ranked round-robin — leaving only 1 of 40 slots for all of Gappers+Gainers+Afterhours combined, and that slot went to a different symbol. This is a capacity/priority-list-size tradeoff in `hod_momo_active.build_active_set()`, not a caching bug; needs a separate decision (prune the list, raise capacity, or reserve slots for top live movers).
- **Keywords:** WLDS, refresh_hod_active_set, id() len() memoization, stale active-set cache, ADR 008 table freeze, session_highs wiped on restart, HodMomoState persistence, hod_momo_surge_seed no usable bars, Former Momo priority list capacity crowd-out

## 2026-07-23 — Fake LBGJ $2.40 / +30% HOD alerts from pytest writing live cache

- **Symptom:** HOD alert table showed LBGJ at 05:59:06 PM with price `$2.40`, `+30.00%`, RVOL `10.00x`, volume `1.0M` — not a high-of-day and not matching the live tape (~$0.03, session high `$0.0608`).
- **Cause:** `tests/test_hod_momo_consolidation.py` builds those exact fixture fields, runs `flush_consolidated_loop()`, and called real `hod_momo_persist.save_alerts()` with no cache monkeypatch — overwriting `backend/.cache/hod-momo-YYYY-MM-DD.json`. A pytest run during ADR 008 verification (~17:59) wrote only those two fake alerts; the API reload ~18:07 loaded them as “today’s” alerts. Strategies were Former Momo (#1) and Low Float (#7) — not Squeeze/HOD-break — so HOD was never required.
- **Fix:** Monkeypatch `save_alerts` / `flush_pending_alert_save` (and alert notify) in that test; clear polluted today’s alerts via API. Real tape never produced `$2.40`.
- **Keywords:** LBGJ, fake alert, pytest cache pollution, hod-momo-2026-07-23.json, test_hod_momo_consolidation, save_alerts, $2.40, +30%, sample fixture

## 2026-07-23 — ADR 008 review found frozen-table mutation leak + three under-delivered plan items

- **Symptom:** A self-review of the "just-completed" ADR 008 work found that `ibkr_bridge.apply_l1_quote()`/`apply_table_quotes()` unconditionally repriced `gainer_cache`/`loser_cache`/`afterhours_cache` (and, when both were empty, `gapper_cache`) on every L1 tick with **no** frozen-table check — HOD's reserved L1 pool keeps ticking retained symbols after their table freezes (09:30/16:00/20:00) by design, so those ticks were silently mutating a table the product contract says is immutable for the rest of the session. Separately, `ibkr/scanner_l1.flush_loop()` tagged the *entire* flushed tick batch with `scanner_tab_registry.get_dominant_tab()` — if a client was viewing a frozen tab as their active tab, HOD-only ticks for that table's retained symbols would be forwarded to the frontend labeled with that frozen table's name, mutating the displayed "frozen" row.
- **Cause:** The frozen/live `TableState` model (ADR 008) was added to `runtime_state`, but the two functions that actually reprice backend caches from live ticks were never updated to consult it, and the WS batch-tagging logic labeled by "which tab a client is looking at" rather than "which owner (scanner-tab vs HOD-only) this tick actually belongs to."
- **Fix:** Added `ibkr.scanner_session.is_table_frozen(state, table)` (shared by runners, `ibkr_bridge`, and integrity) and gated every cache-reprice branch in `apply_l1_quote`/`apply_table_quotes` on it. `scanner_l1.py` now tracks `_active_tab_symbols` (exactly what is subscribed under `OWNER_SCANNER`) and `flush_loop` only forwards ticks for symbols in that set, tagged with the table actually driving that subscription — HOD-only ticks for symbols outside the active tab are dropped from the WS payload instead of leaking into any table. Also fixed two under-delivered plan items from the same pass: `scanner_hydrate.hydrate_rows()` now diffs against a per-table/per-session known-rows cache and cold-quotes only newly admitted symbols (was re-quoting the full roster every batch); `evaluate_scanner_integrity()` now takes a `*_frozen` flag per table and passes matching-session-frozen tables instead of failing/warning on their (by-design, ever-growing) cache age.
- **Keywords:** apply_l1_quote, apply_table_quotes, frozen table mutation, ADR 008, is_table_frozen, flush_loop, active_tab_symbols, dominant_tab leak, scanner_hydrate, known_rows, evaluate_scanner_integrity, frozen bypass

## 2026-07-23 — Error-322 recovery would cancel desired persistent scanner leases

- **Symptom:** With ADR 008 persistent `ScanDataList` handles open, `recover_scanner_slots()` walked every `ScanDataList` in `ib.wrapper.reqId2Subscriber` and cancelled them — including the currently-desired Premarket/RTH/AH leases — so a one-shot Error 322 recovery could silently tear down the push scanner mid-session.
- **Cause:** Recovery was written for the one-shot poll era and had no ownership-aware lease registry fence.
- **Fix:** `ibkr/scanner_stream.persistent_reqids()` tracks desired lease reqIds; `recover_scanner_slots()` skips those ids when reclaiming orphans/in-flight one-shots. Covered by `test_recover_skips_persistent_leases`.
- **Keywords:** Error 322, recover_scanner_slots, persistent_reqids, ScanDataList, ADR 008, scanner_stream

## 2026-07-23 — Squeeze Alert #11 (5% in 5min) silently disabled by a zeroed surge_pct despite `enabled: true`

- **Symptom:** `backend/.cache/hod-momo-config.json` had strategy 11 ("Squeeze Alert - Up 5% in 5min") persisted with `"enabled": true`, `"surge_window_min": 5` (the correct default window), but `"surge_pct": 0.0`. `hod_momo_filters.evaluate_strategy()`'s surge gate (`if cfg.surge_pct > 0 and cfg.surge_window_min > 0`) treats `surge_pct == 0` as "gate disabled," so the strategy fired on RVOL/float alone with no momentum requirement at all — the opposite of what a "Squeeze — Up 5% in 5min" alert is supposed to check for. `HOD_MOMO_CONFIG_SCHEMA_VERSION` had been stuck at `5` in `constants_hod_momo.py` even though `hod_momo_persist._migrate_loaded_configs()` already contained a `version < 6` branch (Former Momo default-list seed) — every load re-ran that idempotent branch and re-saved `schema_version: 5` forever, so no future migration could ever be scheduled to run exactly once.
- **Cause:** A historical bug (not reproduced from current code) zeroed `surge_pct` for strategy 11 while leaving `surge_window_min` at its default — most likely an earlier manual edit or a prior migration bug that touched `surge_pct` without updating `surge_window_min` in lockstep. Nothing detected or repaired this because schema migrations are additive/one-shot by design and no version bump existed to trigger a targeted repair.
- **Fix:** Bumped `HOD_MOMO_CONFIG_SCHEMA_VERSION` to `7` (`constants_hod_momo.py`). Added a `version < 7` migration in `hod_momo_persist._migrate_loaded_configs()` that repairs exactly strategies #10/#11 when `surge_pct == 0` **and** `surge_window_min` still equals that strategy's own default window (10/10 for #10, 5/5 for #11) — restoring `surge_pct` to 10.0/5.0 respectively. A deliberately changed `surge_window_min` (e.g. a user-customized window) is left untouched, since it no longer matches the default-window guard.
- **Keywords:** surge_pct zeroed, schema_version stuck, Squeeze Alert 5% 5min, HOD_MOMO_CONFIG_SCHEMA_VERSION, hod-momo-config.json, silent no-op filter, migration never advances

## 2026-07-23 — Integrity banner stayed red after Gateway re-login; Error 322 silently returned empty instead of raising

- **Symptom:** After signing back into IB Gateway, `/api/ibkr/status` showed `connected: true` and gainers/losers caches were fresh (<1s old), but the HOD Momo Integrity banner still showed `scanner_ibkr_bridge` FAIL with a `ib=none` message recorded ~146s earlier. Separately, when IBKR Error 322 fired mid-scan, `scan_symbols()` returned `[]` with no exception — indistinguishable from "market genuinely has 0 rows" — so the earlier 2026-07-23 leak fix (cancel-in-`finally` + `_scan_lock`) prevented *new* leaks but could not recover from slots already exhausted without a full Nova API restart.
- **Cause:** (1) `state.ibkr_bridge_last_error` was only ever cleared by a *successful* movers/gapper refresh — nothing cleared it when the IBKR session itself transitioned back to READY, so a disconnect-window failure outlived the reconnect until the next scan happened to land rows for gainers specifically (`movers.py` only checked `if gainers:`, not `if gainers or losers:`). (2) `ib_async.IB` defaults to `RaiseRequestErrors=False`, so Error 322 resolves the scanner request's own future to `[]` with no exception — `_one_shot_scanner()` had no way to distinguish "IBKR rejected this request" from "IBKR answered with zero symbols," so there was no signal to recover leaked slots and retry.
- **Fix:** `ibkr/client.py`'s `reconnect_loop()` now calls `_clear_sticky_bridge_error_on_ready()` at both places it reaches `session_state.set_ready()` (normal reconnect and alternate-port self-heal) — a disconnect-window error can no longer outlive reconnect. `scanner_runners/movers.py` widened the clear condition to `if gainers or losers:`. `ibkr/discovery.py._one_shot_scanner()` now registers a scoped `errorEvent` listener (hasattr-guarded so minimal test doubles are unaffected) that flags IBKR Error 322 for the matching reqId and raises the new `IbkrScannerSlotExhaustedError` instead of returning an empty result; `scan_symbols()` (via `_scan_once_with_recovery()`) catches that once, calls the new `recover_scanner_slots(ib)` — which cancels tracked in-flight reqIds plus any `ScanDataList`-typed entry in `ib.wrapper.reqId2Subscriber` (never mktData/tick/order subscribers, never disconnects) — and retries the scan exactly once under the same `_scan_lock` hold. A second consecutive Error 322 surfaces as a normal `IbkrDiscoveryError` failure rather than looping.
- **Keywords:** ibkr_bridge_last_error, sticky banner, session READY, reconnect self-heal, Error 322, RaiseRequestErrors, IbkrScannerSlotExhaustedError, recover_scanner_slots, ScanDataList, reqId2Subscriber, Integrity fail

## 2026-07-23 — IBKR Error 322: scanner subscription leak on wait_for timeout

- **Symptom:** Integrity fail banner stuck with `scanner_ibkr_bridge ... TOP_PERC_GAIN timed out`, `scanner_losers: 0 rows`, `hod_volume_seeds: watch_seed_size=0`, while L1 still showed live gainer prices and alerts could fire. Logs flooded with `Error 322: Only 10 simultaneous API scanner subscriptions are allowed` and `Error 365: No scanner subscription found`.
- **Cause:** `scan_symbols()` wrapped `ib.reqScannerDataAsync(sub)` in `asyncio.wait_for(..., 20s)`. `reqScannerDataAsync` only calls `cancelScannerSubscription` *after* its future completes. On timeout, wait_for abandons the await **without** cancelling — each hung scan leaks one of IBKR's hard max of 10 API scanner slots. After ~10 leaks, every later scan is rejected (Error 322) and returns 0 symbols (Error 365), so losers/seeds go empty. Gainer `age=0s` was dishonest: L1 reprice bumps `gainer_cache_ts` on the last-good membership without a successful movers refresh. Page refresh alone could not fix this (backend process held the leaked Gateway slots).
- **Fix:** Replace the black-box wait_for wrapper with `_one_shot_scanner()` that opens via `reqScannerSubscription`, awaits with timeout, and **always** `cancelScannerSubscription` in `finally`. Serialize one-shot scans with a lock so this process never needs more than one of the 10 slots. Already-leaked Gateway slots require an IB reconnect / API restart once to clear.
- **Keywords:** Error 322, Error 365, cancelScannerSubscription, reqScannerDataAsync, scanner subscription leak, TOP_PERC_GAIN timeout, watch_seed_size=0, Integrity fail

## 2026-07-23 — Sticky scanner_ibkr_bridge Integrity fail banner after TOP_PERC_GAIN timeout

- **Symptom:** HOD Momo page shows red "Integrity fail" with `scanner_ibkr_bridge: IBKR discovery bridge error (Ns ago): gainers: IbkrDiscoveryError(... TOP_PERC_GAIN timed out after 20s)` long after the feed recovered (and often with live alerts still firing). Sibling noise: `scanner_losers: 0 rows and cache Ns old` also hard-failed the merge even when Top Gainers was healthy.
- **Cause:** (1) `ibkr_bridge.run_ibkr` writes `state.ibkr_bridge_last_error` on any timeout, but only `run_discovery_scan()` (gappers) cleared it — and gappers are offline by design during RTH, so a one-shot gainers timeout stuck forever. (2) `evaluate_scanner_integrity` treated any non-empty sticky bridge string as hard `fail`, and empty/stale losers as hard `fail`, so either alone painted the flat merged banner red even when gainers were live.
- **Fix:** Clear `ibkr_bridge_last_error` on successful `run_gainers_update()` when gainers rows land. Demote `scanner_ibkr_bridge` to `warn` when gainer cache is still fresh. Treat empty/stale losers as `pass` (secondary list) whenever gainers are live. Alert suppression remains HOD-scoped (REQ-HOD-004).
- **Keywords:** scanner_ibkr_bridge, ibkr_bridge_last_error, TOP_PERC_GAIN, TimeoutError, Integrity fail banner, sticky error, scanner_losers, run_gainers_update

## 2026-07-23 — Former Momo silently auto-grew forever + re-seeded from alert history on every restart

- **Symptom:** Not a crash — a design flaw found during HOD brainstorming (`docs/hod_brainstorming.html` REQ-HOD-005/006). `hod_momo_trade.on_trade_update` called `_former.remember_former_momo(symbol)` every time **any other** strategy fired, permanently appending that ticker to strategy 1's `former_momo_list` (persisted to disk, never pruned). `hod_momo_persist.load_persisted_state()` additionally called `bootstrap_former_momo_from_alerts()` on every process start, re-seeding the list from that day's alert history. Net effect: the "manual" Former Momo watchlist was neither manual nor bounded — it silently accreted every ticker that ever alerted, session after session.
- **Cause:** The feature was designed to mirror Warrior's "Former Momo Stock" tag (auto-detect names that already hit HOD Momentum) rather than as a user-curated list, so every alert fire and every restart mutated it as a side effect with no cap and no user visibility into why a symbol appeared.
- **Fix:** Removed the auto-remember call site in `hod_momo_trade.on_trade_update` and the bootstrap-from-alerts call in `hod_momo_persist.load_persisted_state`. Deleted the now-dead `remember_former_momo()` / `bootstrap_former_momo_from_alerts()` functions from `hod_momo_former.py`. `former_momo_list` is now edited only via the strategy-1 config API (`StrategyConfigurator.tsx`) — manual only. Added `hod_momo_former.former_momo_priority_symbols()` (manual list, order-preserving, dedup'd) and wired it as `build_active_set()`'s `priority_symbols` in `ibkr_bridge.refresh_hod_active_set()` and as `extra_symbols` in `universe.refresh_hod_momo_universe()`, replacing the old `hod_momo_session_focus.session_focus_active_priority()`/`session_focus_extra_symbols()` calls (alert-history + sticky-memory inputs — sticky was already dead code since nothing called `remember_session_focus()` in production). Effect: Former Momo members now get guaranteed HOD active-set admission — same live-L1 pipeline every Top Gainer flows through — regardless of Top Gainers rank, without any alert-fire side effect. Seeded a one-time default (`HOD_MOMO_FORMER_MOMO_DEFAULT_LIST = ["SPRC"]`) via config schema v6 migration (only if the persisted list is still empty — never clobbers a user-customized list). `hod_momo_session_focus.py` itself is left intact (still unit-tested) but is no longer called from the active-set build path.
- **Keywords:** Former Momo, remember_former_momo, bootstrap_former_momo_from_alerts, session_focus_active_priority, priority_symbols, build_active_set, manual watchlist, REQ-HOD-005, REQ-HOD-006, schema v6

## 2026-07-23 — API restart cascade: hot-reload race + two confirmed IBKR lifecycle defects (correction + fix)

- **Symptom:** Repeated API restarts around 10:18–10:19 while editing backend files; browser showed a ~2.5s health delay during one of those restarts. The 2026-07-23 "API_WEDGED" entry below attributed delayed health to health and `scan_loop` sharing asyncio's default thread pool.
- **Cause (corrected):** That shared-pool diagnosis was wrong — Starlette/FastAPI `async def` routes run on AnyIO's worker pool, not asyncio's default `ThreadPoolExecutor` used by `scan_loop`'s `run_coro` bridge; they were never contending for the same pool. The real 10:18–10:19 sequence was a **development hot-reload cascade**: sequential backend file writes triggered `uvicorn --reload`'s WatchFiles workers while a second API-start attempt (frontend auto-heal or a manual restart) raced for port 8000, occasionally producing `WinError 10048` (address already in use). Two separate, real lifecycle defects were also confirmed during the investigation, independent of the reload race: (1) `ibkr/client.py` exposed the raw socket the instant `connectAsync()` returned, before account-kind validation or positions/completed-orders cache warm-up finished, so background scanner/L1/chart/account tasks could hit a half-ready IBKR session; (2) `ibkr/client.run_coro()` timed out without cancelling its submitted `run_coroutine_threadsafe` future, so a stale coroutine kept running against the old session after a reconnect. The original 2.5s health-delay's root cause is still not proven beyond "hot reload was in flight" — no direct loop-lag/instance-id evidence existed at the time.
- **Fix:** Added an honest 5-state IBKR session machine (`ibkr/session_state.py`: DISCONNECTED/CONNECTING/SYNCHRONIZING/READY/DEGRADED) with a monotonic generation counter; `get_ib()` now returns the client only when `is_ready()` (session READY, not just socket-connected). `run_coro()` cancels its future on timeout and raises `StaleIbkrSessionError` if the generation changed mid-call. Added per-process `instance_identity.py`, `loop_lag.py` sampling, and `/livez` + `/readyz` endpoints so the next delay is measured, not inferred. Replaced arbitrary port-killing in `frontend/scripts/vite-nova-start-api.ts` with a file-based cross-process lock, stricter (HTTP 200 + schema + new-instance-id) restart verification, and an ownership check in `scripts/Stop-NovaPorts.ps1` so only Nova-owned processes on :8000 get force-stopped. Corrected the comment in `constants_scanner.py` that previously stated the disproven shared-pool theory.
- **Keywords:** API_WEDGED, hot reload, WatchFiles, WinError 10048, port 8000, ibkr session readiness, run_coro cancellation, stale generation, instance_id, loop_lag, livez, readyz, single supervisor lock

## 2026-07-23 — HOD alerts muted by scanner-bridge TimeoutError (integrity_fail_suppress)

- **Symptom:** Live HOD L1 looks healthy (ticks flowing, active quote/eval p95 ~0.75s, RVOL known ~95%) but session gate FAILS and strategy evals are mostly blocked. Debug counters: `integrity_fail_suppress` ≫ `strategy_*_fired` (e.g. 6418 suppress vs 5 Squeeze fires in one RTH window). User perception: “HOD scanners not working well.”
- **Cause:** `hod_momo_trade.on_trade_update` calls `integrity_is_failing()`, which reads the **merged** integrity status (`integrity_live._last_merged_status`). A transient `scanner_ibkr_bridge` fail (`gainers: TimeoutError`) flips the whole merge to `fail` even when `parts.hod_momo` is only `warn`/`pass`. HOD strategy passes are then forced `blocked_by=integrity_fail_suppress`.
- **Fix (shipped 2026-07-23):** Added `integrity_live.hod_integrity_is_failing()`, which reads only the cached `hod` partition (`_last_report["hod"]["status"]`) instead of the flat merged status. `hod_momo_trade.on_trade_update`'s suppress check now calls this scoped accessor instead of `integrity_is_failing()`. A scanner-tab-only failure (e.g. sticky `scanner_ibkr_bridge` TimeoutError) can no longer suppress HOD fires; a genuine `hod`-scope failure (dead/stale ticks, empty active set — `evaluate_hod_integrity()`'s own `hod_ticks_flowing`/`hod_active_set` checks) still suppresses as before. `/api/integrity`'s flat merged status and banner are unchanged. Regression tests: `backend/tests/test_integrity_live_builders.py::test_hod_integrity_is_failing_scoped_to_hod_partition`, `backend/tests/test_hod_momo_engine.py::test_integrity_fail_suppress_ignores_scanner_only_fail` / `::test_integrity_fail_suppress_blocks_on_hod_scope_fail`.
- **Keywords:** HOD Momo, integrity_fail_suppress, scanner_ibkr_bridge, TimeoutError, merge_integrity, session_gate FAIL, false mute, hod_integrity_is_failing, REQ-HOD-004

## 2026-07-23 — API_WEDGED: health timeout, Start API was click-only

- **Symptom:** Header `API_WEDGED` / “Backend hung (no health response)” while Gateway chip still looked connected; Start API required a click.
- **Cause:** uvicorn still LISTEN on :8000 but sync `/api/health` shared asyncio’s default thread pool with `scan_loop`’s IBKR `run_coro` waits (25s). Pool saturated → health probe timed out (WEDGED). IBKR TimeoutErrors were the load; the pool conflict made liveness fail.
- **Fix:** (1) async `/api/health` (no default-pool parking). (2) dedicated `scan_executor` for scan_loop. (3) auto-heal once per session on WEDGED/DOWN via `maybeAutoHealBackend`.
- **Keywords:** API_WEDGED, health timeout, Start API, auto-heal, scan_executor, ThreadPoolExecutor, IBKR bridge TimeoutError

## 2026-07-23 — useWorkspace outside WorkspaceProvider (HMR / no auto-recover)

- **Symptom:** Full-view error: `useWorkspace must be used within WorkspaceProvider`; Retry did nothing useful.
- **Cause:** Usually Vite HMR duplicated the context module (Provider from one copy, consumer from another → null). Soft Retry only remounted children under the same broken identity. Also AppShell’s page boundaries sat below AppShell’s own `useWorkspace` call for some paths.
- **Fix:** `AppErrorBoundary` auto hard-reloads once on fatal provider/hook errors (`appErrorRecovery.ts`); Retry becomes “Reload Nova” for those; outer `app-shell` boundary wraps `AppShell`.
- **Keywords:** useWorkspace, WorkspaceProvider, AppErrorBoundary, HMR, auto-reload, context skew

## 2026-07-23 — Alpaca still offered/defaulted as scanner source

- **Symptom:** Settings showed “Scanner Source → Alpaca (Free)”; header could show green `FEED: Alpaca IEX` / `ALPACA ok` while IB Gateway was still logging in, implying the live scanner was fine.
- **Cause:** Soft-toggle from 2026-07-13 left `DISCOVERY_PROVIDER_DEFAULT=alpaca` and `OPTIONS=("alpaca","ibkr")`. Frontend hydrated from that default before `/api/config`, hiding the Gateway chip. Settings POST could write `NOVA_DISCOVERY_PROVIDER=alpaca` over `.env`. Integration chip labeled `Alpaca` meant news/listing aux, not scanner health.
- **Fix:** Lock product to IBKR-only (`DEFAULT=ibkr`, `OPTIONS=("ibkr",)`); coerce/persist ibkr in `_get/_set_discovery_provider` and `POST /api/config`; remove Scanner Source dropdowns; rename aux chip to `News`; update attribution, decision note, and `single-market-data-feed.mdc`.
- **Keywords:** discovery_provider, Alpaca scanner, Scanner Source, FEED Alpaca IEX, IBKR-only, soft-toggle, hydrate race

## 2026-07-22 — Sentry flooded by expected IBKR / chart-dispose noise

- **Symptom:** Sentry `altay-studio` / `python-fastapi` showed thousands of unresolved ERROR events: Error 300 Can't find EId, Error 10089 market-data subscription, open/completed orders timeouts, Gateway ConnectionRefused / “API port … open”, and client `Object is disposed` (TradingView).
- **Cause:** Only Error 162/365 were in `IBKR_BENIGN_LOG_ERROR_CODES`; reconnect and late-cancel races still hit ERROR → Sentry. Client intake filtered Vite HMR but not chart dispose races. PYTHON-FASTAPI-126 (`closedFilterFromToday is not defined`) was a one-shot HMR crash mid-refactor (already fixed).
- **Fix:** Expand benign IBKR codes/needles (300, 354, 10089, 10189 + timeout/port/peer-closed substrings); ignore `Object is disposed` in `/api/client-errors`. Keep Error 101 (max tickers) as ERROR. Resolve/ignore matching Sentry issues after deploy/restart.
- **Keywords:** Sentry, IBKR_BENIGN_LOG_ERROR_CODES, Error 300, Error 10089, Object is disposed, client_errors, PYTHON-FASTAPI

## 2026-07-22 — FIXED: Vitest act() environment (IS_REACT_ACT_ENVIRONMENT)

- **Symptom:** Vitest stderr: `The current testing environment is not configured to support act(...)` on manual `createRoot` + `act()` mounts; real “update was not wrapped in act” warnings were also suppressed. Diagnosed 2026-07-20 (audit only). After enabling the flag: `WorkspaceContext.test.tsx` still printed 2× “An update to WorkspaceProvider … was not wrapped in act(...)”.
- **Cause:** React 19 `isConcurrentActEnvironment()` reads `globalThis.IS_REACT_ACT_ENVIRONMENT`; nothing in the repo set it, and `vite.config.ts` had no `test.setupFiles`. WorkspaceProvider’s `/api/config` fetch then resolved after sync `act(render)`, so `setDiscoveryProvider` / `setAlpacaFeed` escaped act.
- **Fix:** (1) Added `frontend/src/testSetup/reactActEnvironment.ts` + `test.setupFiles` in `vite.config.ts`. (2) Deferred the mocked config fetch in `WorkspaceContext.test.tsx` until after the defaults assertion, then released under `await act`; flush config before symbol-update interactions. Full suite: 99 files / 422 passed; zero “not configured” and zero “was not wrapped in act” warnings.
- **Keywords:** IS_REACT_ACT_ENVIRONMENT, act() environment, Vitest setupFiles, reactActEnvironment, WorkspaceContext, warnIfUpdatesNotWrappedWithActDEV

## 2026-07-22 — Completed-orders warm hung reconnect + GET /orders/closed

- **Symptom:** After adding `reqCompletedOrdersAsync` post-connect warm-up, IBKR reconnect stalled and `GET /api/ibkr/orders/closed` timed out (~15s+) when Gateway was in **Read-Only** API mode. Logs showed `Error 321 … API interface is currently in Read-Only mode` and `completed orders request timed out`; positions still refreshed.
- **Cause:** `await ib.reqCompletedOrdersAsync(False)` had no application-level timeout. Under Read-Only / wedged Gateway the coroutine never completed, blocking `reconnect_loop` after positions warm and blocking `closed_orders_async`’s empty-list warm path.
- **Fix:** `IBKR_COMPLETED_ORDERS_TIMEOUT_SEC` (10s) + `asyncio.wait_for` inside the single-flight lock in `refresh_completed_orders_cache`; failures log and return (best-effort). Empty closed list remains a real empty, never a hung request.
- **Keywords:** reqCompletedOrdersAsync, Read-Only, Error 321, closed_orders_async, IBKR_COMPLETED_ORDERS_TIMEOUT_SEC, hang, reconnect_loop

## 2026-07-21 — HOD Momo rows jump position and re-stamp their time on every re-fire

- **Symptom:** User report: "each row is supposed to be a timed record that stay forever… they're moving, they're just getting re-ordered." Rows in the HOD Momo / Running Up tables visibly changed position and their displayed "time" column whenever a previously-caught symbol fired again.
- **Cause:** `collapseAlertsBySymbol` (`frontend/src/hod_momo/collapseAlertsBySymbol.ts`) walked the newest-first `alerts` feed and used **whichever occurrence of a ticker it encountered first in that walk** to seed the collapsed row's `id`/`timestamp`/`created_ts`/position. Because the array is rebuilt fresh every render and a re-fire is always the newest entry (front of the array), a re-fire made that ticker's "first occurrence" the newest fire again — moving the row and updating its stamp to the re-fire's time instead of its original catch time. The existing test `preserves newest-first ticker order` asserted this exact buggy behavior.
- **Fix:** Added a second pass that, for each ticker, finds the **oldest** occurrence in the full-session `alerts` array (the true first catch — `today_alerts` has no TTL, so it's always present) and overrides the collapsed row's `id`/`timestamp`/`created_ts` with it; rows are then sorted by that anchor descending. Live snapshot fields (price/rvol/change%) and strategy tag/burst-badge merging are unchanged — only identity/position/stamp are pinned. Also upgraded `HodMomoAlertTable` from an unbounded "load more on scroll" batch table to real fixed-window virtualization, since the reordering symptom made a related, previously-undiscovered risk visible: DOM row count for that table only ever grew and never shrank as the user scrolled.
- **Keywords:** HOD Momo, collapseAlertsBySymbol, row reorder, timestamp, first catch, newest-first, virtualization, computeVisibleRowRange, DOM growth, infinite scroll

## 2026-07-20 — `npm run build` failed: TradingTabProps missing `initialSection`

- **Symptom:** `tsc -b` failed with `TS2322: Property 'initialSection' does not exist on type 'IntrinsicAttributes & TradingTabProps'` in `TabModuleHost.tsx`, blocking `npm run build`.
- **Cause:** An earlier, still-uncommitted change ("Account header replaces Trading tab") nested the `reports` workspace module under Account/Trading (`workspace/registry.ts`: `showInTabNav: false`, "Nested under Account (header)") and updated `TabModuleHost.tsx` to route `activeTab === 'reports'` into `<TradingTab initialSection="reports">` — but `TradingTab.tsx` was never updated to declare or use that prop, leaving `ReportsTab` (the actual Reports panel) orphaned and unreferenced anywhere.
- **Fix:** Added `initialSection?: 'overview' | 'reports'` to `TradingTabProps`, local `section` state, an Overview/Reports toggle in the Account view, and render `<ReportsTab />` when `section === 'reports'`.
- **Keywords:** TS2322, TradingTabProps, initialSection, ReportsTab, TabModuleHost, orphaned component, npm run build

## 2026-07-20 — 18 execution/executor/routes-trading tests failed after switching Gateway to live

- **Symptom:** `pytest tests/test_execution_service.py tests/test_executor.py tests/test_routes_trading.py` had 18 failures — `assert False is True` on route/execute happy paths, buying-power / max-concurrent / sell-without-position gates asserting the wrong thing. Each file passed alone in earlier sessions; nothing in the diff touched those gates. Full-suite `pytest` also showed the same 18 (plus one pre-existing unrelated `test_hod_momo_universe.py` failure).
- **Cause:** `ibkr/safety.py::assert_orders_allowed()` reads `gateway_mode()`, which is `os.environ.get("IBKR_GATEWAY_MODE", ...)` — a **real, unmocked env read**, independent of the `client_mod.account_mode()` / `client_mod.broker_account_kind()` mocks the tests already patched. The paper-simulating test helpers (`_arm_paper()` in `test_execution_service.py`, `_arm_ibkr_execution()` in `test_executor.py`, `_arm_paper_gates()` in `test_routes_trading.py`) only mocked the *connection* mocks, never the *env target*. These tests were only "paper-safe" as long as the developer's real `.env` said `IBKR_GATEWAY_MODE=paper`. Earlier the same day, `.env` was manually flipped to `IBKR_GATEWAY_MODE=live` while debugging a disconnect issue — every test relying on the ambient ("paper") default then hit `assert_orders_allowed`'s live branch and got rejected with `"Live trading requires IBKR_LIVE_TRADING_CONFIRMED=true"` before ever reaching the buying-power/position/idempotency logic under test. Separately, `test_routes_trading.py` also creates a module-level `TestClient(app)`, whose first request lazily fires `main.py`'s real FastAPI lifespan/background bootstrap (`app_lifespan._bootstrap_runtime` → `strategy.risk.reconstruct_from_journal()` + `nova_os.recovery.run_startup_recovery()`) against the real on-disk journal/cache (only `execution.store.cache_dir` was isolated, not `journal.db.cache_dir` / `nova_os.events_db.cache_dir`) — a second, independent way real dev-machine state could leak into and pollute the process-global `strategy.risk._state` singleton (and the real `backend/.cache/execution_ledger.db`, confirmed to hold 353 accumulated rows) for the rest of a pytest session.
- **Fix:** Test helpers now pin `IBKR_GATEWAY_MODE=paper` via `monkeypatch.setenv` (or `patch.dict(os.environ, ...)` in the non-monkeypatch `_arm_paper_gates()` tuple) alongside the existing connection mocks, so paper-simulating tests never depend on the real `.env`. `test_routes_trading.py`'s fixture also isolates `journal.db.cache_dir` / `nova_os.events_db.cache_dir` to `tmp_path` and stubs `app_lifespan._bootstrap_runtime` to a no-op (these are route-wiring tests that already mock the IBKR/execution boundary — the real bootstrap has nothing to verify there). Added a `strategy.risk.reset_day()` call to the autouse fixtures in `test_execution_service.py` / `test_executor.py` as defense-in-depth against the loss-halt singleton leaking across tests regardless of trigger.
- **Keywords:** IBKR_GATEWAY_MODE, gateway_mode, assert_orders_allowed, Live trading requires IBKR_LIVE_TRADING_CONFIRMED, test pollution, TestClient lifespan, _bootstrap_runtime, strategy.risk singleton, execution_ledger.db, cross-file test isolation

## 2026-07-20 — Disconnected while Gateway green (paper target + live port only)

- **Symptom:** IB Gateway farms ON / live login, Nova Stock View showed bare “Disconnected”; Paper/Live switch either 404’d (stale API) or later silently reappeared as Paper after a failed Live attempt.
- **Cause:** (1) Self-heal is intentionally live→paper only — paper Nova never auto-dials 4001. (2) Intentional-switch “suppress heal” was a ~18s timer, so after expiry reconnect_loop could heal live→paper and persist `.env` with no UI context. (3) Timeout was heal-eligible like refuse (Error 326 / wedged live could flip to paper). (4) Connection intent lived as scattered `_mode`/`_broker_account_kind` + `_last_heal`/`_suppress_heal_until` with no durable status-visible record. (5) Empty-state copy always said “live port 4001” even in paper mode.
- **Fix:** Sticky `intentional_gateway_mode` (not a timer); heal only on `"refused"`; TCP port diagnostics + `disconnect_hint` on `/api/ibkr/status`; clear stale `gateway_self_heal` on preferred connect; wake `reconnect_loop` on switch; actionable Stock View copy + gateway-mode 404 → restart API; mode-aware empty IBKR message. MDC corrected: heal is not bidirectional.
- **Keywords:** disconnect, port mismatch, 4001, 4002, self-heal, paper pin, intentional_gateway_mode, disconnect_hint, gateway-mode 404, sticky intent

## 2026-07-20 — Native browser confirm/alert popups in trading UI ("localhost:5173 says")

- **Symptom:** Clicking Live (and other destructive actions) opened the OS/browser native dialog titled “localhost:5173 says” with plain OK/Cancel — mismatched Nova’s dark trading chrome and felt broken.
- **Cause:** Call sites used `window.confirm` / `window.alert` / `window.prompt` / bare `alert()` instead of an in-app modal. There was already a shadcn `AlertDialog` for place-order confirm, but no global imperative API for other surfaces.
- **Fix:** Added `frontend/src/ux` (`confirmApp` / `alertApp` / `promptApp` + `AppDialogHost`) mounted in `App.tsx`, styled with Nova tones (default/warning/danger), and migrated every product call site away from native popups.
- **Keywords:** window.confirm, window.alert, window.prompt, AppDialogHost, confirmApp, localhost says, pretty dialog, global UX

## 2026-07-20 — Clicking "Live" in Stock View did nothing (capsule was a status mirror, not a switch)

- **Symptom:** Clicking the Live segment of the Paper/Live capsule in Stock View just popped a `window.confirm` and then reverted to showing Paper — no Gateway port change, no error, no feedback about why.
- **Cause:** `StockViewAccountModeCapsule` (`frontend/src/stock_view/StockViewTradingChrome.tsx`) only called `window.confirm()` with explanatory copy; there was no backend endpoint or client call to actually change `IBKR_GATEWAY_MODE` or reconnect. Self-heal (`gateway_heal.py`) only ever flips live→paper automatically, so even a real attempt to dial the live port would have silently reverted to Paper on a refused/timed-out connection with no error surfaced.
- **Fix:** Added `ibkr.client.request_gateway_mode(mode)` — persists + applies `IBKR_GATEWAY_MODE`, suppresses self-heal for one connect attempt (`gateway_heal.suppress_self_heal`/`self_heal_suppressed`), disconnects, and polls the background reconnect loop's result (the sole connector, since `ib_async` doesn't support concurrent `connectAsync`). Refuses to accept a live-port connection whose account classifies as paper. New `POST /api/ibkr/gateway-mode` route; capsule now calls it and shows the real error inline instead of a silent revert. Never touches `IBKR_LIVE_TRADING_CONFIRMED`.
- **Keywords:** Paper Live switch, StockViewAccountModeCapsule, gateway-mode, IBKR_GATEWAY_MODE, self-heal suppress, request_gateway_mode, window.confirm no-op, status mirror

## 2026-07-20 — Flatten NO_POSITION while Positions showed shares (positions vs portfolio dual-source) + BuyingPower fail-open

- **Symptom:** UI Flatten / manual SELL refused with `NO_POSITION` ("no long position to reduce") while Positions panel showed SPY qty 1. Separately, a transient `ib.accountValues()` failure could let a priced LMT BUY through without a BuyingPower check.
- **Cause:** (1) Positions UI used `get_portfolio()` / `ib.portfolio()`; validate + flatten used `get_positions()` / `ib.positions()` — successful-but-empty positions cache vs populated portfolio. Failed reads were already raised as `IbkrAccountError`, but the dual-cache split still produced a false "flat" for sells. (2) `get_account_summary()` swallowed `accountValues()` exceptions into `{"connected": False}` without `pending`, so `check_account_and_position` skipped both BP branches and returned OK for LMT BUY.
- **Fix:** Added `account.long_qty` (positions-only SSOT) wired through validate (`POSITION_UNAVAILABLE` vs `NO_POSITION`), `executor_flatten`, and `positions_for_ui` (qty from positions, MTM from portfolio join). Refresh positions after connect. `get_account_summary`/`refresh_account_summary` raise `IbkrAccountError`; `/api/ibkr/account` → 503; priced BUY → `BUYING_POWER_UNKNOWN`. FE disables Flatten/exit when account poll `error` is set. UI Flatten remains `source="manual"`.
- **Keywords:** long_qty, NO_POSITION, POSITION_UNAVAILABLE, BUYING_POWER_UNKNOWN, get_positions, get_portfolio, Flatten, dual-source, fail-open BuyingPower, accountValues, positions_for_ui

## 2026-07-20 — IBKR positions/orders empty-on-error lie (flatten could skip the SELL and cancel the stop)

- **Symptom:** A transient IBKR positions/orders read failure (disconnect, API exception) returned `[]` from `get_positions`/`get_portfolio`/`open_orders`/`closed_orders`, which the routes turned into HTTP 200 + `[]`, and the UI rendered as "No open positions." / "No open orders." — indistinguishable from a genuinely flat account. `execution/validate._position_qty` and `strategy/executor_flatten._actual_position_qty` both treated that `[]` the same as "no position exists," so a failed read during a deliberate `flatten_positions()` call could skip the market SELL for a real open position **and still cancel its protective stop/target**, leaving it naked with no safety order.
- **Cause:** `backend/ibkr/account.py` / `backend/ibkr/orders.py` disguised "cannot read" as "nothing there" by returning `[]` on both `ib is None` (disconnected) and on any `except Exception`. Every downstream consumer (routes, `execution/validate`, `strategy/executor` kill-switch, `strategy/executor_flatten`) had no way to distinguish a failed read from a real empty account/order book.
- **Fix:** Added `IbkrAccountError` (`backend/ibkr/errors.py`). `get_positions`/`get_portfolio`/`open_orders`/`closed_orders` now raise it instead of returning `[]`. `routes/trading.py` catches it and returns HTTP 503 for the three read routes, and a structured `{ok:false,error}` for `DELETE /api/ibkr/orders` (cancel-all). `execution/validate._position_qty` catches it and returns `None` (SELL refused, fail closed). `strategy/executor._cancel_bracket_if_parent_unfilled` (kill switch) catches it and returns `"unknown_state"` (stop/target left alone rather than cancelled on a guess). `strategy/executor_flatten.flatten_positions`/`flatten_preview`/`_cancel_protective_legs` catch it and **abort the flatten for that symbol** (no SELL, no cancel) rather than treating an unverifiable qty as zero. Frontend `useIbkrAccount`/`useClosedOrders` keep the last-good rows and show an explicit error line instead of wiping to empty or (closed orders) silently substituting sample data.
- **Keywords:** IbkrAccountError, get_positions, get_portfolio, open_orders, closed_orders, flatten_positions, kill switch, fail closed, empty account lie, oversell, naked position, 503, last-good

## 2026-07-20 — Vitest "act() environment" warning silently hides real async-update bugs (diagnosed, not yet fixed)

- **Symptom:** `frontend/` Vitest runs of manual-mount tests (e.g. `workingOrderCells.test.tsx`, `closedOrderCells.test.tsx`) print `The current testing environment is not configured to support act(...)` to stderr; tests still pass. The warning is invisible with the default Vitest reporter on passing tests — it only surfaces with `--reporter=verbose` or on failure, which is why it looked like isolated/occasional noise.
- **Cause:** `frontend/vite.config.ts`'s `test` block has no `setupFiles`, and nothing anywhere in the repo sets `globalThis.IS_REACT_ACT_ENVIRONMENT`. React 19's `isConcurrentActEnvironment()` (`react-dom/cjs/react-dom-client.development.js`) treats the flag as unset → prints the "not configured" warning on every `act()`-wrapped `createRoot().render()`/`.unmount()` call. Worse: the *same* unset flag also short-circuits `warnIfUpdatesNotWrappedWithActDEV`, i.e. it disables React's real "update was not wrapped in act(...)" safety warning in **both** directions (wrapped or not) — so this is not purely cosmetic, it silently removes the guardrail that would catch a state update escaping a manual `act()` block (e.g. via `setTimeout`/unresolved promise/effect firing after the synchronous `act()` callback returns). This project has no `@testing-library/react` dependency at all (confirmed absent from `package.json` and `node_modules`) — all 24 `*.test.tsx` files that render JSX use this same hand-rolled `createRoot` + `act` pattern (grep-confirmed), not just the two files reported. Verified via a throwaway probe test + `--reporter=verbose`: flag is `undefined` before/during/after every `act()` call; full-suite run showed 653 instances of the warning across those 24 files (386 tests, 94 files total, all passing).
- **Fix (recommended, not applied — audit only):** Add a tiny shared Vitest setup file (e.g. `frontend/src/testSetup/reactActEnvironment.ts`) that sets `globalThis.IS_REACT_ACT_ENVIRONMENT = true`, and wire it via `test.setupFiles` in `vite.config.ts`. No RTL needed since none is used; this is a one-line env bootstrap, not a tunable constant.
- **Keywords:** IS_REACT_ACT_ENVIRONMENT, act() environment, createRoot, react-dom-client, isConcurrentActEnvironment, warnIfUpdatesNotWrappedWithActDEV, verbose reporter hides console, no testing-library/react, workingOrderCells, closedOrderCells



- **Symptom:** Transport/API failures surfaced as empty scanner/HOD universes with little or no useful log detail; UI looked “frozen” or empty while other tabs still had data.
- **Cause:** Multiple layers treated failure like success: `scan_symbols`/`snapshot_quotes` returned `[]`/`{}` when disconnected; `run_ibkr` default `on_error="empty"`; HOD `set_seed_symbols([])` wiped seeds; FE polls replaced last-good with `[]`; blank `TimeoutError` stringification; empty `.catch(() => {})`.
- **Fix:** Raise `IbkrDiscoveryError` on discovery transport failure; bridge default `on_error="none"` + adapters `"raise"`; refuse empty HOD seed wipe; AH keep last-good; FE last-good on empty polls; maintainer heuristics for `except return []` / empty promise catch; loud `describe_exc` logging.
- **Keywords:** silent error, empty market, IbkrDiscoveryError, run_ibkr, last-good, except return [], fail loud, gappers wipe, HOD seeds

## 2026-07-20 — Empty Gappers looked frozen (silent IBKR bridge wipe)

- **Symptom:** Premarket UI felt frozen; Gappers empty; integrity showed `gappers: 0 rows` as **pass**; logs had `IBKR discovery bridge failed:` with a blank message; Gainers still had ~50 live rows.
- **Cause:** `run_ibkr()` caught bridge timeouts (`TimeoutError` stringifies to `""`), logged a useless warning, and returned `[]`. Discovery then wrote that empty list over `gapper_cache`. Integrity treated recent empty gappers as healthy. Scanner tabs had no integrity banner (only HOD did).
- **Fix:** Loud bridge logging (`type` + `repr` + traceback); `on_error="none"` for scanner adapters; keep last-good gapper/gainer/loser caches on bridge failure; integrity **fails** empty premarket gappers + surfaces `scanner_ibkr_bridge`; integrity banner on all scanner tabs; EmptyState hints to check Gainers.
- **Keywords:** gappers empty, frozen, silent error, IBKR bridge, TimeoutError, run_ibkr, gapper_cache wipe, integrity

## 2026-07-20 — Positions Qty showed 0 for fractional IBKR lot

- **Symptom:** POSITIONS (1) listed IBKR with Qty **0**, Avg Cost ~$93.61, Mkt Price ~$91.60; API had `qty: 0.0642` and ~$5.88 market value.
- **Cause:** Position/order cells used `fmt(qty, 0)` / `toLocaleString` with `maximumFractionDigits: 0`, which rounds fractional shares to zero.
- **Fix:** Shared `formatShareQty` (0–4 decimals, trim trailing zeros) wired into Positions, Working/Closed Orders, executor/journal tables, and Pos/flatten UI copy.
- **Keywords:** fractional shares, Positions Qty 0, formatShareQty, IBKR leftover, Webull S6

## 2026-07-20 — VCIG late Squeeze fired on HOD retest (not new HOD)

- **Symptom:** User: VCIG hit Nova HOD scanner at 08:24:14 ET; Warrior showed true HOD (Former Momo + Low Float High Rel Vol) at 08:02:54 / $1.34, then many Running Up alerts 08:02–08:26 while price was *not* making new HOD.
- **Cause:** (1) Nova first evaluated VCIG ~08:22 ET (`hod_momo.log`; earlier IBKR Error 10089 delayed MD). (2) HOD gate only checked `price ≈ session_high`, so after seeding the ~$1.34 floor, Squeeze 5%/10% re-fired on retests with 5–10m surge — Warrior Running Up semantics on the HOD widget. (3) Alert cache confirms strategies 10/11 at $1.34, not Running Up (12 blocked by `rvol:unknown`).
- **Fix:** Track `session_high_raised_ts`; `fails_hod_gate` requires a fresh new-high within `HOD_MOMO_NEW_HOD_GRACE_SEC` (60s). Initial bars/tick6 seed does not open the window.
- **Keywords:** VCIG, HOD retest, Squeeze, Running Up, session_high_raised_ts, fails_hod_gate, hod:not_new, Error 10089, BA101

## 2026-07-19 — Sample Closed Orders Time Placed milliseconds crawled

- **Symptom:** Sample Closed Orders Time Placed (e.g. `.323`) kept changing on refresh; looked like live stamps were mutable.
- **Cause:** Demo row `9008` in `buildMockClosedOrders` set `submitted_at`/`updated_at` to `new Date().toISOString()` on every rebuild. Sample list rebuilds when account/UI polls, so milliseconds crawled. Banner already said “not from IBKR.”
- **Fix:** Fixed `submitted_at` in `MOCK_CLOSED_TIMES[9008]`; freeze recent-highlight `updated_at` once at module load. Never call `toISOString()` inside the builder.
- **Keywords:** Time Placed, sample preview, mockClosedOrders, 9008, Date.now, milliseconds crawl

## 2026-07-19 — Stock View header showed symbol only (no price / up-down)

- **Symptom:** Header chip for CJMB (and similar) showed only the ticker; price, ▲/▼, and day change missing. Charts still painted.
- **Cause:** `/api/ticker/{symbol}` returned `snapshot: {}`. IBKR path required **both** `price` and `prev_close`; `snapshot_quotes` skipped symbols when `close` was NaN even if `last` was valid. Quote UI lives in the header chip (rail `hidePrice`), so empty snapshot = symbol-only.
- **Fix:** Allow price-only snapshots; keep last when close missing; fall back to live L1 `ticks.last_quotes`, then last 1‑min chart bar close (same feed as charts) when cache/snapshot empty.
- **Keywords:** Stock View header, symbol chip, snapshot empty, prev_close, ticker_ibkr, snapshot_quotes, CJMB, chart bars fallback

## 2026-07-19 — Open Orders Time kept moving / crawling

- **Symptom:** Time column on Open Orders changed as the panel refreshed; felt like a live clock instead of order place time.
- **Cause:** (1) UI used `orderActivityIso` → preferred `updated_at` (last fill / log tick). (2) Sample mocks used `Date.now() - N minutes`, so every rebuild shifted timestamps.
- **Fix:** Open Orders display `submitted_at` only (`orderSubmittedIso`); Closed keep activity time. Mocks use fixed absolute ISO. Contract tests lock filled/remaining/prices/id/time.
- **Keywords:** Open Orders, Time, submitted_at, updated_at, mockWorkingOrders, isoMinutesAgo, crawl

## 2026-07-18 — Paper Gateway could still attach to live (self-heal / port-only)

- **Symptom:** With `IBKR_GATEWAY_MODE=paper`, Nova could still self-heal to port 4001 if paper was down, or treat “paper” as a port label only — risk of live account spend while practicing.
- **Cause:** `gateway_heal` tried either alternate port; `account_mode` reflected env/port, not IB `managedAccounts`; spend gate did not require paper account ids.
- **Fix:** Heal only live→paper; classify managedAccounts (`DU`/`DF`); disconnect + refuse place on paper/live mismatch; `assert_orders_allowed` paper pin.
- **Keywords:** paper pin, self-heal, managedAccounts, DU, IBKR_GATEWAY_MODE, live money, broker_account_kind

## 2026-07-18 — Flatten / market exit ignored extended hours

- **Symptom:** Flatten / exit position after RTH (or on EH working orders) failed or sat until regular hours; felt like Flatten “does not work” outside the session.
- **Cause:** Nova forced `outside_rth=false` on all MKT places and rejected `outside_rth` for non-LMT in both `ibkr.orders` and `execution.validate`.
- **Fix:** Allow MKT + `outside_rth`; auto-set EH in pre/after-market for Flatten / Fill now / exit hotkeys; STP remains RTH-only.
- **Keywords:** Flatten, outside_rth, extended hours, MKT, Fill now, exit_pos, OUTSIDE_RTH_INVALID

## 2026-07-18 — Stock View “Disconnected” while paper Gateway was connected

- **Symptom:** Header showed Disconnected; Gateway Connection Status showed API Server connected; charts/L2 empty. User was on paper trading.
- **Cause:** Gateway listened on paper port **4002**, but `.env` had `IBKR_GATEWAY_MODE=live` so Nova only tried **4001** (ConnectionRefused). Header Paper/Live capsules do not change the port.
- **Fix:** Set mode to paper + reconnect for the incident; added `ibkr/gateway_heal.py` so future preferred **live**-port refuse/timeout can self-heal **to paper** and persist `IBKR_GATEWAY_MODE` (never paper→live; orders still gated). See also paper hard-pin entry above.
- **Keywords:** Disconnected, IBKR_GATEWAY_MODE, 4001, 4002, paper Gateway, self-heal, gateway_self_heal

## 2026-07-18 — Vite HMR “send was called before connect” flooded client-errors

- **Symptom:** Backend log screamed hundreds of `nova.client_errors` WARNINGs (`send was called before connect`, `Cannot read properties of undefined (reading 'send')`) from `/@vite/client` while API routes (gappers, IBKR status) were fine.
- **Cause:** Vite’s HMR/error-overlay WebSocket rejected `send` before connect; Nova’s global `unhandledrejection` reporter POSTed every one to `/api/client-errors`. Multiple tabs (`localhost` vs `127.0.0.1`) amplified the storm.
- **Fix:** Filter Vite tooling noise in `reportClientError` (client) and `routes/client_errors.py` (server). Prefer one origin for the UI in dev.
- **Keywords:** vite, HMR, send was called before connect, client-errors, unhandledrejection, @vite/client

## 2026-07-18 — Gateway chip double-click did nothing (stale API 404)

- **Symptom:** Double-clicking header Gateway chip appeared to do nothing; IB Gateway did not open.
- **Cause:** Running uvicorn process predated `POST /api/ibkr/launch-gateway` → HTTP 404. Feedback was only in the `title` tooltip, so the failure was easy to miss.
- **Fix:** Restart API (route live); show on-chip “opening… / check desktop / launch failed” + visible hint text; Vite-dev fallback `POST /__nova/launch-gateway` when API returns 404.
- **Keywords:** launch-gateway, 404, double-click, Gateway offline, stale uvicorn, Vite fallback

## 2026-07-18 — Dark mode native select menus white-on-white

- **Symptom:** History “Today (Live)” dropdown (and other `<select>`s) opened as a white list with nearly invisible light text; only the hovered row was readable.
- **Cause:** Closed control used transparent/light text; Windows Chromium paints a light native option popup while inheriting app text color. Several menus also fell back to undefined `--bg-secondary` → hardcoded dark hex that broke light theme.
- **Fix:** Theme tokens `--input-bg` / `--menu-bg` / `--bg-secondary`; global `select`/`option` color-scheme + solid backgrounds; history/feed/hotkey/trade selects and Modules/exchange menus updated.
- **Keywords:** select, option, dropdown, white-on-white, color-scheme, history-select, dark mode, menu-bg

## 2026-07-18 — SEC findings: unauth mutating API, config credential leak, webhook SSRF

- **Symptom:** Security audit reported critical/high findings: no API auth (SEC-002/004), `GET /api/config` returning raw Alpaca secrets (SEC-001), CORS `*`, root Docker, missing CI scanners, torch CVEs, alerts webhook SSRF (SEC-008).
- **Cause:** Local-first assumptions never added an auth seam; config echoed env secrets for Settings convenience; webhook URLs were not egress-validated; torch was in the default Railway image for optional FinBERT.
- **Fix:** `backend/auth.py` (`APIKeyHeader` + mutating middleware + `require_auth`); mask config secrets; `alerts/webhook_url.py` SSRF checks; torch → `requirements-ml.txt`; localhost CORS; `USER nova` in Dockerfile; CI scanner jobs.
- **Keywords:** SEC-001, SEC-002, SEC-004, SEC-008, NOVA_API_KEY, X-Nova-Api-Key, SSRF, mask_secret, CORS, Dockerfile USER, torch

## 2026-07-17 — HOD Momo alert queue referenced a dataclass field that never existed

- **Symptom:** `hod_momo_alerts.get_broadcast_queue()` read `state.alert_broadcast_queue`, but `HodMomoState` (`hod_momo_state.py`) never declared that field — the first read on a freshly constructed state would raise `AttributeError`, and the queue's only other use (`hod_momo_trade.py`'s `queue.put_nowait(("pending", alert))` and `flush_consolidated_loop`'s `queue.get_nowait()` drain) never read the queued items or its size anywhere — pure put/drain-only dead machinery.
- **Cause:** Leftover plumbing from an earlier design where broadcast may have gone through the queue; direct WebSocket send (`ws.send_text`) became the real delivery path and nothing was ever wired to observe the queue's size/contents, while the backing state field was dropped from the dataclass at some point without removing the accessor.
- **Fix:** Removed `get_broadcast_queue()`, the `put_nowait`/`get_nowait` calls, and all re-exports (`hod_momo.py`). Alerts still deliver via direct `ws.send_text` in `flush_consolidated_loop`, unchanged.
- **Keywords:** alert_broadcast_queue, get_broadcast_queue, AttributeError, HodMomoState, dead queue, hod_momo_alerts, hod_momo_trade

## 2026-07-17 — End-to-end IBKR scanner trace: AH reshape, cold day_high, dual L1 lines

- **Symptom:** A full code trace of IBKR Gateway → scanner → HOD surfaced several real (not just cosmetic) gaps: After Hours tab sourced from an intraday `TOP_PERC_GAIN`-derived reshape instead of the dedicated AH scan universe; the cold `reqTickersAsync` snapshot path (`apply_table_quotes`) never passed `day_high` into `on_trade_update`, so symbols priced only via cold snapshots (not live L1) stayed HOD-cold-start-blocked longer than necessary; depth's no-L2-entitlement fallback could open a second raw `reqMktData` line for a symbol `ibkr.ticks` already streamed, and `unsubscribe()` unconditionally called `cancelMktData` even when that line might be needed by other owners.
- **Cause:** Each scanner/consumer path (movers, gapper fallback, HOD seed loop, AH tab, depth fallback) was built independently over time without a shared scan-result cache, without threading the day-high field all the way through both quote paths, and without depth's L1 fallback being aware of `ibkr.ticks`' owner-refcounted stream model.
- **Fix:** Added `IBKR_SCAN_CODE_AH_GAINERS` (`TOP_AFTER_HOURS_PERC_GAIN`) as the AH tab's primary source (gainer-reshape stays a fallback only); added a 5s TTL cache in `scan_symbols()` keyed by `(scan_code, num_rows, below_price)`; `snapshot_quotes()` now returns `high` and `apply_table_quotes` passes it as `day_high`; depth's L1 fallback calls `ibkr.ticks.get_ticker()` first and marks the symbol `is_shared_l1` so `unsubscribe()` skips `cancelMktData` for it.
- **Keywords:** TOP_AFTER_HOURS_PERC_GAIN, afterhours reshape, apply_table_quotes, day_high, snapshot_quotes, depth L1 fallback, ibkr.ticks.get_ticker, is_shared_l1, scan_symbols cache, IBKR_SCAN_RESULT_TTL_SEC

## 2026-07-17 — Cold-start false HOD from invented session_highs

- **Symptom:** Symbols appeared "at HOD" / fired HOD strategies when they were not (pullback after earlier day high; mid-session L1 admission; after restart). Quiet-tape re-eval made it worse on flat lasts.
- **Cause:** `hod_momo_trade.on_trade_update` set `session_highs[sym] = price` whenever last exceeded the dict default `0.0`, so the first observed last became HOD. No use of IBKR tick-6 day High or bar highs.
- **Fix:** `hod_momo_high.py` seeds from bar `max(h)` (surge-seed hist fetch) + L1 `ticker.high`; block with `hod:high_unseeded` until seeded; only then raise from last. Removed quiet re-eval; mute→0; burst 10s.
- **Keywords:** HOD, session_highs, cold-start, tick-6, ticker.high, high_seeded, false HOD, mute, consolidation

## 2026-07-17 — TRT sticky flooded: cooled name ranked #15 of 15 (only 8 L1 slots)

- **Symptom:** After sticky L1 shipped, restart left `/debug/symbol/TRT` empty again while DRTS (sticky head) had live L1; sticky file listed 15 soft-block names with TRT last.
- **Cause:** `HOD_MOMO_SESSION_FOCUS_MAX=40` let hot master_rvol soft-blocks accumulate; reserved session_focus slots are only 8. Newest hot stickies took the slots; cooled TRT never subscribed.
- **Fix:** Cap sticky to 8 slots; `_rank_sticky` puts off-mover (cooled) symbols before on-table ones before truncate/priority.
- **Keywords:** TRT, sticky flood, session_focus, cooled-first, HOD_MOMO_SESSION_FOCUS_MAX, empty snap

## 2026-07-17 — TRT empty snap after leaving gainer table (session-focus churn)

- **Symptom:** After PN L1 fix, TRT `/debug/symbol/TRT` empty (no price/rvol/session_high) while Warrior still showed prior Squeeze; TRT not in movers/active/uncovered.
- **Cause:** Session-focus reserved only 2 slots (Former cut) and only `today_alerts` + Former list. TRT never Nova-alerted (soft-block then churn). Once off TOP_PERC_GAIN it left the focus universe and L1. Early sticky-on-every-tick / every-Squeeze-eval flooded the sticky list and evicted TRT.
- **Fix:** `hod_momo_session_focus` day-persisted sticky; remember only on master_rvol soft-block; priority sticky→alerts→Former; `HOD_MOMO_ACTIVE_SESSION_FOCUS_SLOTS=8`.
- **Keywords:** TRT, empty snap, session_focus, sticky L1, master_rvol soft-block, Squeeze churn

## 2026-07-17 — PN Squeeze empty snap despite being on IBKR gainers table

- **Symptom:** Warrior PN Squeeze 5%/10% (~12:54–12:58 @ $4.25–4.49); Nova `/debug/symbol/PN` empty (never evaluated). PN ranked ~36 on `/api/movers` gainers.
- **Cause:** Not a missing scan code — PN was in focus/discovery but uncovered. Active seed_slots took the **head** of HOT_BY_VOLUME-ordered seeds (~150 names before belowPrice TOP_PERC_GAIN). Losers filled ~half of mover slots via `abs(change_pct)`. Former `session_focus` reserved 8 L1 slots. Mid-tier low-volume sub-$20 gainers never got sticky L1.
- **Fix:** `seed_symbols_for_active` / `discovery_for_active` (under-$20 gainer head); `scan_hod_momentum_seeds` belowPrice-first; `ibkr_bridge` omits `loser_rows`; `HOD_MOMO_ACTIVE_FORMER_SLOTS` 8→2.
- **Keywords:** PN, Squeeze, universe_gap, seed_slots, under20, HOT_BY_VOLUME, top_loser, session_focus, empty snap

## 2026-07-17 — CNF Squeeze on Nova but never on Warrior HOD

- **Symptom:** User saw **CNF** alert on Nova HOD Momo (Squeeze 5%/10%); Warrior Small-Cap HOD Momentum never showed CNF.
- **Cause:** (1) Live config had **only** strategies 10/11 enabled — Float / Running Up / 52wk all disabled. (2) Those Squeeze configs had `requires_hod=False`, so a surge alone could fire without a new high of day — Warrior’s HOD widget requires HOD.
- **Fix:** Schema v5 + live repair: Squeeze `requires_hod=True`; re-enable strategies 2–12; Former stays off. Defaults document Squeeze HOD requirement.
- **Keywords:** CNF, nova_only, Squeeze, requires_hod, Warrior HOD Momentum, mass-disabled strategies, schema v5

## 2026-07-17 — Squeeze blocked by master RVOL; microcap squeezes crowded out of seed top-50

- **Symptom:** Live Warrior Squeeze on **TRT** while Nova `would_fire_now` hard-stopped at `master_rvol(0.32<2.0)` with empty strategies. **BTMD** Squeeze never entered Nova (empty snap) despite seed codes including TOP_PERC_GAIN.
- **Cause:** (1) Squeeze 5%/10% defaults intentionally set `min_rvol=0` (surge is the gate), but `passes_master_gate` still applied a global Daily Rate floor of 2.0 before any strategy ran — pace RVOL math for TRT was correct (vol/avg×elapsed ≈ 0.32). (2) IBKR TOP_PERC_GAIN hard-caps at 50 rows; mega-gainers fill the uncapped list so sub-$20 squeezes never enter the HOD seed/watch set.
- **Fix:** Soft-block master RVOL — still evaluate surge-only strategies (`min_rvol<=0` + surge window). Second seed pass: `TOP_PERC_GAIN` with `belowPrice=IBKR_HOD_SEED_BELOW_PRICE` (20). BTMD may still miss when it ranks outside the sub-$20 top-50 (`capacity_expected`).
- **Keywords:** Squeeze, master_rvol, TRT, BTMD, pace RVOL, Daily Rate, belowPrice, TOP_PERC_GAIN, universe_gap, strategy_ignores_master_rvol

## 2026-07-17 — HOD L1 never started — lifespan spawn typo aborted before scanner_l1

- **Symptom:** After uvicorn restart, integrity FAIL (coverage ~42–62%, quote/eval ages climbing to minutes); parity `nova=0`; Warrior Squeeze names (SDOT/TRT) had enrichment snaps but `surge:None` / empty `session_high` (no `on_trade_update`). Log had scan_loop + surge_seed but **zero** `IBKR ticks: subscribed … owner=hod|scanner` and no `lifespan bootstrap complete`.
- **Cause:** `app_lifespan._spawn_runtime_tasks` built a single task list and called `_executor.fills_poll_loop` (plural). Real name is `fill_poll_loop`. `AttributeError` aborted the list mid-build after early tasks (scan/enrichment/surge_seed) were already `create_task`'d but **before** `scanner_l1.reconcile_loop` — so table/HOD L1 never subscribed.
- **Fix:** Wire `fill_poll_loop`; spawn each background task independently (fail one, keep others); start `scanner_l1` + HOD heartbeat/surge-seed first. Regression: `test_app_lifespan_spawn.py`.
- **Keywords:** fills_poll_loop, fill_poll_loop, scanner_l1, lifespan spawn, surge:None, SDOT, Squeeze, L1 coverage, bootstrap complete

## 2026-07-17 — API listens but never serves — lifespan blocked on IBKR connect

- **Symptom:** Nova API listened on :8000 but even `/docs` timed out after restart (no `--reload`); IB Gateway port 4001 was listening.
- **Cause:** `app_lifespan` awaited Alpaca health + `ibkr.client.startup()` / connect path on the same asyncio loop before `yield`, so Starlette never finished startup. `ib_async.connectAsync` can hang past its own timeout when Gateway accepts TCP but the API handshake stalls (common with Error 326 — clientId already in use by a zombie worker on clientId=1).
- **Fix:** Yield HTTP after local restore/DB only; defer ping/IBKR/recovery/background tasks. Hard `asyncio.wait_for` around `connectAsync` (`IBKR_CONNECT_TIMEOUT_SEC`); recreate `IB()` on fail; default `IBKR_CLIENT_ID` 1→17.
- **Keywords:** lifespan hang, /docs timeout, connectAsync, Error 326, clientId, IBKR_CLIENT_ID, Starlette startup, event loop

## 2026-07-17 — API hung CLOSE_WAIT — unbounded L1 qualify under subscribe lock

- **Symptom:** Nova API on :8000 accepted TCP but `/api/ibkr/status` and `/api/integrity` timed out; dozens of CLOSE_WAIT + 100s of ESTABLISHED; hung again ~2min after uvicorn restart.
- **Cause:** `ibkr/ticks.subscribe` awaited `qualifyContractsAsync` with no timeout while holding `_subscribe_lock`. Explore rotation queued many qualifies; Gateway stalls blocked the lock/IB work, starving the asyncio loop so HTTP handlers never finished → clients closed → CLOSE_WAIT pile-up.
- **Fix:** `asyncio.wait_for(..., IBKR_L1_QUALIFY_TIMEOUT_SEC=4)`; cap `IBKR_L1_MAX_SUBSCRIBE_PER_RECONCILE=5`; skip L1-fail-cooldown symbols in scanner_l1; 2s integrity HTTP cache.
- **Keywords:** CLOSE_WAIT, API hung, qualifyContractsAsync, subscribe lock, event loop, L1, uvicorn, integrity timeout

## 2026-07-17 — HOD integrity FAIL from L1-failed explore symbols (coverage 98% / hours-stale ages)

- **Symptom:** Integrity hard-fail with `coverage=85–98%`, sometimes `quote_p95` hours-old / `active_quote_missing` FRE/CRD; `l1_err IBKR L1 subscribe failed for 1 symbol(s)`; session_gate FAIL → parity observe REFUSED while BIYA/LBGJ still on active set and ticks otherwise flowing.
- **Cause:** (1) Rotating discovery explore admitted symbols IBKR cannot qualify/stream as SMART USD (FRE-class) — they occupied an active slot with no L1, dropping coverage below 100%. (2) Coverage hard-required 100%, so one missing symbol failed the whole feed. (3) Demoted-then-re-admitted symbols kept old `_last_quote_ts`, so max age climbed to hours when re-subscribe failed and heartbeat skipped (not subscribed, no cache).
- **Fix:** `note_l1_subscribe_failed` cooldown from `scanner_l1` → skip blocked names in `build_active_set` (except open ticker); purge quote/eval ages on demotion; coverage fail floor 90% (98% → warn). Tool HTTP timeouts 8/10s → 30s to stop false BLOCKED on slow integrity.
- **Keywords:** HOD Momo, integrity, coverage 98%, FRE, L1 subscribe failed, explore, note_quote, session_gate, parity observe, scanner_l1

## 2026-07-17 — Archive cold days had empty `bars_1m` despite tape

- **Symptom:** Cold archive for 2026-07-15/16 had `bars_1m.jsonl` with 0 lines while `tape_ibkr` had tens of thousands of prints; walk/replay could not use bars.
- **Cause:** `archive.capture.record_bar` had no production caller — only tape was wired from `ibkr/tape_stream.py`.
- **Fix:** Added `archive.bar_builder` (minute OHLCV from prints), hooked after `record_tape_print`, backfill tool + re-compact for prior days.
- **Keywords:** bars_1m, archive, tape_ibkr, bar_builder, compact, walk_day, replay

## 2026-07-17 — Execution ledger `update_stages` rejected `symbol=`

- **Symptom:** After routing place/bracket through `execution.service`, happy-path tests and the synthetic latency probe crashed with `TypeError: update_stages() got an unexpected keyword argument 'symbol'`.
- **Cause:** `_send_broker` persisted `symbol=` on send, but `store.update_stages` had no `symbol` parameter (only set at `reserve` time).
- **Fix:** Accept optional `symbol` in `update_stages` and write it when provided; extract broker send helpers to stay under the file-size limit.
- **Keywords:** execution, update_stages, symbol, ADR 007, place_bracket, latency probe

## 2026-07-17 — Stock View right-side gap (Tailwind `.container` max-width)

- **Symptom:** Stock View (header + charts + quote/trade rail) stopped short of the window’s right edge, leaving a large empty black strip. `align-items: stretch` / `width: 100%` / `max-width: none` in feature CSS did not fix it.
- **Cause:** Nova’s shell used `className="container"`. Tailwind v4 scans that name and emits `@media (width>=48rem){ .container { max-width: 48rem } }` (and larger breakpoints) in the `utilities` cascade layer. Utilities beat `features`, so Stock View never went full-bleed.
- **Fix:** Renamed shell to `.nova-shell` / `.nova-shell--ticker-detail` (`App.tsx`, `DashboardPage.tsx`, tokens/stock-view/quote-layout CSS). Kept a `!important` safety reset in `tailwind-overrides.css` for any leftover `.container`.
- **Keywords:** Stock View, gap, max-width, Tailwind container, cascade layers, nova-shell, full bleed

## 2026-07-16 — `markdownlint-cli2 --fix` corrupted bare Python identifiers in prose

- **Symptom:** After running `npx markdownlint-cli2 --fix` on `AGENTS.md`/`gemini.md`/`CHANGELOG.md`/`PROBLEM_LOG.md` to clear MD022/MD032 blank-line violations, a diff review found silently mangled content: `__init__.py` became `**init**.py`, and spaces before underscore-prefixed identifiers were deleted (e.g. `load_state, _session_date` → `load_state,_session_date`, `(IBKR_* constants)` → `(IBKR_*constants)`).
- **Cause:** MD037 (`no-space-in-emphasis`) and MD050 (`strong-style`) autofixers pattern-match `_word` / `__word__` as emphasis/strong markers even when the text is a bare code identifier or filename written without backticks (this repo's CHANGELOG/PROBLEM_LOG/rule docs do this constantly — `_session_date`, `__init__.py`, `IBKR_*`). The fixer "normalizes" what it thinks is malformed emphasis, deleting the preceding space or rewriting `__x__` to `**x**`, destroying the literal text.
- **Fix:** Reverted the specific corrupted spans by hand (verified via `git diff` against HEAD, non-blank-line-only comparison). Disabled `MD037`/`MD050` in `.markdownlint-cli2.jsonc` (same category as the already-disabled MD033/MD034/MD036/MD041/MD060/MD024 — rules structurally incompatible with this project's writing style). Also fixed `**/graphify-out/**` (was only matching root-level, not nested `backend/graphify-out/`) and added `**/.tmp/**` + `**/test-results/**` to ignores.
- **Keywords:** markdownlint-cli2, --fix, MD037, MD050, no-space-in-emphasis, strong-style, autofix corruption, dunder, `__init__.py`, false positive emphasis

## 2026-07-16 — Time & Sales text nearly invisible (`--color-muted` collision)

- **Symptom:** Stock View Time & Sales title/column headers appeared almost invisible (or “wrong color”); module cards looked thematically broken after Tailwind/shadcn.
- **Cause:** `@theme` mapped Tailwind `--color-muted` to `rgba(255,255,255,0.04)` (a *background*). Legacy tape CSS used `color: var(--color-muted)` for text, so computed color was ~4% white. Purple `#22223a` fallbacks and bare global `form`/`button`/`header` selectors compounded the leak.
- **Fix:** Canonical `--nova-text-muted` / `--text-secondary` for domain text; keep `--color-muted` as shadcn muted *surface* only. Move L2/T&S skin to `ibkr/marketData.css`. Scope legacy form selectors. Matched pane headers; remove outer combined title. Maintainer check rejects `color: var(--color-muted)` and bare feature selectors.
- **Keywords:** Time & Sales, --color-muted, token collision, Tailwind, shadcn, Stock View, scanner-l2.css, marketData.css, ADR 006

## 2026-07-16 — Stock View wrongly split L2 from T&S (and moved the drag bar)

- **Symptom:** User reported Level 2 cramped/scrollable, T&S separated into its own stacked module with a horizontal drag between L2 and T&S, and believed Place Order / Unlock Trading had been deleted.
- **Cause:** A prior Stock View layout change treated the "give me a horizontal drag bar" request as a splitter *between* L2 and T&S (`StockViewDepthTape` stacked cards + `STOCK_VIEW_L2_TAPE_SPLIT_*`). The intended control was reallocating height between the *combined* L2+T&S block and the Order Entry card below.
- **Fix:** Restore side-by-side `.depth-and-tape` inside one `StockViewModuleCard`; move `useResizableHeight` + horizontal `ResizeHandle` to `StockViewRail` between depth and Open ticket; keep `TickerTradeActionBar` / `ManualOrderTicket` mounted. Persist `nova.stockView.depthOrderSplitPct` (default 72% depth).
- **Keywords:** Stock View, Level 2, Time & Sales, depth-and-tape, ResizeHandle, Order Entry, ManualOrderTicket, Unlock Trading, horizontal splitter, rail layout

## 2026-07-16 — Full pytest emits TorchVision DLL fatal exception but exits green

- **Symptom:** `py -3 -m pytest backend/tests -q` printed `Windows fatal exception: code 0xc0000139` while `transformers` imported `torchvision` from `news/sentiment.py`; pytest continued and reported 677 passed with exit code 0.
- **Cause:** The local Python 3.13 Torch/TorchVision binary stack is DLL-incompatible. Lazy FinBERT pipeline loading imports Transformers image helpers and therefore TorchVision even though Nova only requests text classification. The broad suite can expose the native-loader failure without converting it into a failing pytest exit.
- **Fix:** No unrelated sentiment runtime change was made in this widget task. The focused IBKR/order suites pass cleanly; the full-suite result is recorded as `677 passed with environment fatal warning`, not an unqualified clean pass. Repair requires aligning the local Torch/TorchVision/Python build or isolating text-only model loading in a dedicated task.
- **Keywords:** pytest, Python 3.13, torchvision, torch, transformers pipeline, FinBERT, c0000139, DLL incompatibility, false green test suite

## 2026-07-16 — Canvas SDK and inferred-union assumptions failed type-check

- **Symptom:** The new `agent-widgets.canvas.tsx` rejected `<TodoList items={...}>`; after adding Widgets Agent to Nova Home, TypeScript also flagged a redundant `a.canvas === "nova-home.canvas.tsx"` comparison after `dashboard_type` had already narrowed the union.
- **Cause:** The Canvas SDK component uses the prop name `todos`, not the guessed `items`. Separately, the generated roster's literal union lets TypeScript prove that the canvas comparison has no overlap after the `home_section` branch.
- **Fix:** Read `canvas/sdk/todo-list.d.ts`, changed the prop to `todos`, and simplified Nova Home dashboard routing to rely on `dashboard_type` alone. Both canvases now pass the authoritative Canvas TypeScript check.
- **Keywords:** Cursor Canvas, TodoList, TodoListProps, items, todos, TypeScript narrowing, literal union, nova-home, Canvas TypeScript check

## 2026-07-16 — HOD Momo table shrunk to one ugly row

- **Symptom:** HOD Momo tab looked nothing like Gappers/Gainers — a single tiny/clipped alert row with a huge empty pane below; numeric values and the intended 30-row window were unreadable ("can't even see the thirty"). Time column also showed "Invalid Date".
- **Cause:** `HodMomoAlertTable` sized its scroll viewport to `min(alerts.length, 30) × 22px`. With one alert that became ~46px total (header + one row). A follow-on CSS pass also forced `table-layout: fixed` + wrapping Strategy/symbol cells. Separately, some live alerts were persisted with empty `timestamp` while `created_ts` was valid, so `new Date("")` rendered "Invalid Date".
- **Fix:** Always reserve `HOD_MOMO_VISIBLE_ROWS` (30) for the viewport; bump row/header heights to Large scanner density (32/30); restore nowrap auto-layout table styling matching `.table-wrapper` scanners; heal empty timestamps from `created_ts` in `alert_to_dict`/`alert_from_dict` and `fmtClock`.
- **Keywords:** HOD Momo, table density, HOD_MOMO_VISIBLE_ROWS, viewportHeight, Gappers, scanner table, ugly layout, Invalid Date, created_ts

## 2026-07-16 — RVOL 700x-11000x blowup + alert spam despite "fixed" prior session

- **Symptom:** Live HOD Momo table showed RVOL (daily) of 743x-11632x for CJMB/TGHL/STAK-class symbols; `/api/hod-momo/alerts` grew ~12-24 rows/30s even on a quiet AH tape, with the same symbol+strategy pair re-firing every 20-36s. Prior session had already claimed pytest/session_gate "fixed" this.
- **Cause:** Three independent bugs, all invisible to unit tests because they only manifest with real live-process state:
  1. **Alert spam:** `backend/.cache/hod-momo-config.json` had `master.cooldown_sec` persisted as `0.0` (a debugging-session leftover), so the `(symbol, strategy_id)` cooldown in `on_trade_update` never blocked a re-fire — every qualifying strategy fired on essentially every trade tick / 5s heartbeat re-eval instead of once per 60s.
  2. **RVOL blowup (multi-day runners):** `evaluate_strategy`'s `request_fundamentals()` callback only fires while `float_shares`/`fifty_two_week_high` are still `None` — once `avg_volume` is populated even once, nothing ever re-requests it. A Former Momo symbol tracked across multiple sessions (CJMB, LBGJ) kept an `avg_volume` frozen at whatever yfinance reported the very first time it was ever fetched (days ago, before its current run), while today's cumulative volume kept growing — pace RVOL = `volume / avg_volume` exploded (CJMB 7016x, LBGJ 1526x) purely from a stale denominator.
  3. **RVOL blowup (same-day movers):** `hod_momo_enrichment.universe_enrichment_loop`'s `discovery=ibkr` branch read `state.avg_volume_cache` (Alpaca `/v2/stocks/bars` on the IEX feed) *before* falling back to yfinance. IEX captures only a sliver of consolidated volume for thin microcaps, so that cache silently understated avg_volume (live: ATPC cached 13,620 vs. yfinance 3,375,816 — 248x off) and, because it runs every 30s, kept re-clobbering any correct yfinance value fix #2 would have supplied.
- **Fix:** (1) Restored `cooldown_sec` to the `HOD_MOMO_COOLDOWN_SEC` default (60.0) live and added a load-time floor guard in `hod_momo_persist._load_configs_from_disk` that self-heals any persisted `cooldown_sec < 1.0` back to default. (2) Added `hod_momo_heartbeat._maybe_refresh_fundamentals`, re-queuing `mark_needs_fundamentals` for every active symbol every `HOD_MOMO_FUNDAMENTALS_REFRESH_SEC` (300s) so `avg_volume` tracks yfinance's live figure instead of freezing at the first-ever fetch. (3) Extracted `hod_momo_enrichment.ibkr_avg_volume()` — yfinance-only, never reads `avg_volume_cache` — and used it in the ibkr branch of `universe_enrichment_loop`, matching the existing (correct) `fundamentals_enrichment_loop` ibkr path and the single-market-data-feed rule.
- **Verified by:** Live before/after via `/api/hod-momo/debug/symbol/{SYM}` on a cleanly-restarted process: CJMB rvol 7016.02→46.49 (avg_volume now 288,855, matching a fresh yfinance query exactly), LBGJ 1526.36→10.38 (avg_volume 308,767), ATPC avg_volume 13,620.44→3,375,816.00. Alert growth measured at 0 new rows/60s once cooldown held and the tape genuinely quieted; `pace_relative_volume`/cooldown/enrichment covered by new tests in `test_hod_momo_persist.py`, `test_hod_momo_heartbeat.py`, `test_hod_momo_enrichment.py`.
- **Keywords:** HOD Momo, RVOL, relative volume, pace_relative_volume, avg_volume, cooldown_sec, alert spam, CJMB, LBGJ, ATPC, yfinance, averageVolume, Alpaca IEX bars, avg_volume_cache, universe_enrichment_loop, mark_needs_fundamentals, single-market-data-feed

## 2026-07-16 — Consolidation dropped Former Momo when Low Float also fired

- **Symptom:** LBGJ decisions showed Former `passed=True` / `would_fire=True`, but alerts only showed Low Float High Rel Vol.
- **Cause:** `flush_consolidated_loop` merged all ready alerts for a symbol into one primary (`ready[-1]`), discarding other strategy_ids.
- **Fix:** Group by `strategy_id` and emit one consolidated alert per strategy; plus session_focus L1 slots + quiet-tape re-eval.
- **Keywords:** HOD Momo, consolidation, Former Momo, LBGJ, strategy_id, flush_consolidated_loop

## 2026-07-16 — Former Momo would_fire PASS but never alerts (off active set)

- **Symptom:** LBGJ debug `would_fire_now` Former/Low Float PASS; Warrior still warrior_only for Former; no new Former alerts.
- **Cause:** Active set filled by top gainers/seeds; LBGJ dropped from L1 so `on_trade_update` stopped while snap/would_fire stayed stale-optimistic.
- **Fix:** Reserved `session_focus` active slots + Former-list-first priority.
- **Keywords:** HOD Momo, active set, session_focus, Former Momo, LBGJ, would_fire, L1 starve

## 2026-07-16 — Integrity p95 ~2.1s false-fail + Former Momo empty vs Warrior

- **Symptom:** After heartbeat, integrity still failed with quote/eval p95≈2.1s; Warrior Former Momo / Squeeze names (BIYA, LBGJ) absent on Nova; parity observe hung after session_gate PASS.
- **Cause:** (1) Heartbeat 1s loop + 1.5s stale gate samples ages just over the 2s SLO. (2) Former Momo list empty and never auto-filled from prior momo fires; `would_fire_now` skipped Former/HOD gates. (3) `/api/hod-momo/alerts` returned full-day 9k rows and stalled observe.
- **Fix:** Heartbeat 0.5s / stale 0.75s; `hod_momo_former` remember+bootstrap; align `would_fire_now`; alerts `limit` query + observe cap; HOD seeds add TOP_PERC_GAIN.
- **Keywords:** HOD Momo, heartbeat, p95, Former Momo, would_fire_now, parity observe, alerts limit, TOP_PERC_GAIN

## 2026-07-16 — HOD Integrity fail: active quote/eval ages ~hours on quiet L1

- **Symptom:** HOD banner Integrity fail with active coverage ~8–15%, quote/eval p95 ~2000–4000s, CJMB shown as (1179 in 2157sec), scanner_gappers cache hours old after open; ~9k alerts today.
- **Cause:** (1) IBKR quote listeners only fire on price *change*, so illiquid AH active symbols never `note_quote`. (2) UI `collapseAlertsBySymbol` summed all-day fires into one Warrior-style badge. (3) Scanner integrity mode-blind on frozen gappers. (4) Alerts route called missing `_current_date_et` → 500.
- **Fix:** `hod_momo_heartbeat` 1Hz refresh from L1 last / cache / subscribed; burst gap 15s in collapse; mode-aware gappers; route uses `current_date_et`; surge_none warn when tape alive; session_gate + parity observe tools.
- **Keywords:** HOD Momo, integrity, note_quote, heartbeat, coverage, CJMB, consolidation badge, gappers offline, session_gate, parity observe

## 2026-07-16 — Scanner "stale · updated Ns ago" despite Connected (IBKR snapshot SLA impossible)

- **Symptom:** Header showed Connected (~258ms) plus `stale · updated 9s ago` on Gainers; table prices froze; `blast.log` flooded with `snapshot timeout (4.0s) for 20 symbols` and occasional `15.0s for 220 symbols`; HOD integrity reported last tick hours ago.
- **Cause:** IBKR completes `reqTickersAsync` only on `tickSnapshotEnd` (~11s). Nova's 1Hz table loop timed out at 4s, discarded partial ticks, and immediately started another batch — structurally impossible for a `<3s` freshness SLA. Concurrent movers/HOD full-universe snapshots amplified Gateway queue saturation. Separately, a pure priority-sort HOD active set let 40 gainers starve IBKR volume-seed runners.
- **Fix:** Bounded persistent `reqMktData` L1 for active scanner tab + reserved HOD pool (`ibkr/scanner_l1.py`, owner-aware `ibkr/ticks.py`); `/ws/scanner` `set_active_tab`; quota-based HOD selection with seed slots; demote `reqTickersAsync` to cold/discovery with ≥12s timeout + snapshot lock; enrichment snapshots only the ≤40 active set; per-row quote age in the UI.
- **Keywords:** stale updated Ns ago, tickSnapshotEnd, reqTickersAsync, reqMktData, scanner_l1, active tab, HOD volume seeds, SCANNER_PRICE_STALE_SEC, single-market-data-feed

## 2026-07-16 — HOD facade dropped test aliases; depth state leaked across tests

- **Symptom:** Close-gate pytest failed with `hod_momo` missing `_effective_min_rvol` / `_save_alerts` / … and smart-depth test saw `len(depth_calls) == 0`.
- **Cause:** Phase 10 facade omitted underscore re-exports tests still call; Phase 2 removed import-time `depth.reset_all()`, so prior subscriptions short-circuit `subscribe_async`.
- **Fix:** Re-export private aliases on `hod_momo.py`; call `reset_all()` in `TestSmartDepthFlag.setup_method`.
- **Keywords:** hod_momo facade, monkeypatch, reset_all, isSmartDepth, close remediation Phase 7

## 2026-07-16 — IBKR discovery discarded when Alpaca keys missing

- **Symptom:** With `discovery=ibkr` and no Alpaca headers, gappers/movers stayed empty even when IBKR returned rows; charts could show synthetic mock candles labelled as an IBKR quote after empty historical bars.
- **Cause:** Discovery returned early on `not headers` after a successful IBKR fetch; movers gated the whole update on Alpaca headers; `useChartBars` always fell back to `buildMockBars` on empty responses.
- **Fix:** Enrichment-only gate on Alpaca headers for IBKR paths; forbid mock bars under IBKR discovery; bind chart/live-trade to `selectedSymbol` with symbol gates.
- **Keywords:** IBKR discovery, Alpaca headers, mock bars, selectedSymbol, single-market-data-feed, close remediation Phase 3

## 2026-07-16 — Maintainer missed tuple except-pass; close metrics overstated swallows

- **Symptom:** Phase 13 claimed zero swallowed exceptions while `except (WebSocketDisconnect, Exception): pass` remained in `routes/hod_momo.py` and `routes/ticker.py`; architecture dep findings were always `baseline=True`.
- **Cause:** `SWALLOW_PY` only matched single-name handlers; cross-feature/`import main` checks hard-coded baseline instead of committed fingerprints.
- **Fix:** Tuple-handler regex + `baselines.json` fingerprints (close remediation Phases 1–2); WS loops now catch disconnect/cancel narrowly and log unexpected failures.
- **Keywords:** swallowed exception, WebSocketDisconnect, maintainer_checks, baselines.json, Phase 11, close remediation

## 2026-07-16 — Swallowed exceptions hid IBKR/cache/Nova OS failures

- **Symptom:** `maintainer_checks.py` reported 11 `SWALLOWED_EXCEPTION` sites in production/tool code (`cache`, `scanner_push`, `tape_stream`, `ticks`, `nova_os/events`, `create_nova_agent`); queue-full and cleanup paths failed silently.
- **Cause:** Defensive `except …: pass` blocks (and a redundant outer swallow around `notify_nova_os_event`, which already logs internally) discarded real OSError/queue-pressure/unsubscribe failures with no log line.
- **Fix:** Narrow exception types, log at debug/warning, drop-oldest on `QueueFull` with visibility; Nova OS receipt notify uses ImportError-only guard; depth/HOD queue leftovers aligned. Regression tests added for cache cleanup, tape/depth queue drop, and Nova OS receipt path.
- **Keywords:** swallowed exception, maintainer_checks, error visibility, Phase 11, QueueFull, tape_stream, cache cleanup, nova_os events

## 2026-07-16 — HOD module extraction exposed stale facade/state aliases

- **Symptom:** HOD tests and consumers patched/read mutable globals on `hod_momo.py`; after extraction, a facade-level monkeypatch did not affect the focused module that held the real callable, and rebinding lists/dicts could leave consumers on stale objects.
- **Cause:** The monolith reassigned `_configs`, `_master`, `_today_alerts`, queues, and session collections directly. Imports/tests depended on module aliases rather than one explicit owner resolved at use time.
- **Fix:** Added `HodMomoState` as the sole owner; all focused modules call `get_state()` and tests patch/replace that owner. Added characterization for persistence, session rollover, queues, WebSocket clients, surge state, consolidation, and config/reset paths.
- **Keywords:** HOD Momo, stale alias, facade monkeypatch, state rebinding, session rollover, persistence, websocket clients, broadcast queue, Phase 10

## 2026-07-16 — Wedged API on port 8000 shows Backend unreachable

- **Symptom:** UI header: Disconnected — Backend unreachable; HOD banner: Integrity unreachable Failed to fetch; health HTTP timed out even though `netstat` showed `LISTENING` on `127.0.0.1:8000`.
- **Cause:** Orphan/wedged `python3.13` (PID listening since overnight) accepted TCP but did not serve `/api/health`. New `run_api.py` failed with WinError 10013 (port busy / access denied), so a second API never bound.
- **Fix:** `Stop-NovaPorts.ps1` for 8000 then restart API. Added header **Start API** button (Vite/Electron). Added outage flags: `API_WEDGED` (health timeout) vs `API_DOWN` (nothing listening); console `[Nova][API_FLAG]`.
- **Keywords:** Backend unreachable, Integrity unreachable, WinError 10013, port 8000, wedged uvicorn, Start API, API_WEDGED, API_DOWN, API_FLAG

## 2026-07-16 — Memory Markdown in `.cursor/agents/` discovered as callable agents

- **Symptom:** `*-memory.md` files under `.cursor/agents/` appeared alongside real agent prompts as if they were invocable Cursor agents, and status facts were duplicated across prompts, memories, and canvases.
- **Cause:** Cursor discovers every `*.md` in `.cursor/agents/` as an agent prompt; memory documents were co-located with prompts and there was no versioned registry/contract separating prompts, memory, and generated dashboards.
- **Fix:** Moved memories to `.cursor/agent-memory/`; added `.cursor/agent-system/contract.json` + `registry.json`; normalized the four agents; added `tools/agent_contract.py` (blocking), `create_nova_agent.py`, `sync_agent_surfaces.py`, specialist routing, and a fail-open lifecycle hook.
- **Keywords:** agent lifecycle, agent-memory, registry, contract, subagentStop, canvas snapshot, create_nova_agent

## 2026-07-16 — Ghost HOD integrity/surge-seed docs vs missing runtime

- **Symptom:** CHANGELOG/constants/CSS claimed fail-loud integrity + Squeeze bar seeding, but `hod_momo_integrity.py`, `integrity_live.py`, `hod_momo_surge_seed.py`, CLI, routes, and UI banner did not exist at master `d3a8985`. Live HOD still cold-started Squeeze and cycled slowly across a large watch set.
- **Cause:** Prior HOD work landed documentation/constants without the runtime modules (or was lost during branch/stash churn); agents treated docs as shipped.
- **Fix:** Implemented integrity evaluators + live builders + CLI/banner; IBKR surge seed loop; capacity-bounded active set with fair reprice batching; uncovered symbols explicit. Corrected changelog with a real ship entry.
- **Keywords:** HOD Momo, integrity, surge seed, active set, reqTickersAsync, HKIT, ghost docs, Warrior parity

## 2026-07-16 — Alert channel Test fire sent empty Discord embeds

- **Symptom:** POST `/api/alerts/test` (and Settings “Test”) delivered Discord embeds with empty `description`; Telegram got a JSON dump instead of the test sentence.
- **Cause:** `format_event_payload` only handled `hod_momo` / `nova_os`. Test events (`type=test` + `text=…`) fell through without copying `text`, so Discord used `payload.get("text", "")` → `""`.
- **Fix:** Formatters now prefer `event["text"]` for test/unknown events; Discord titles distinguish Test vs HOD vs Nova OS. Also sanitized Discord/Telegram/webhook exception return strings so webhook URLs / bot tokens never leak into `/api/alerts/status`.
- **Keywords:** Phase D, alerts, formatters, Discord embed, test channel, empty description, secret redact, telegram

## 2026-07-16 — Tab bar labels mashed (HOD Momo / Trading overlap)

- **Symptom:** Top nav showed overlapping unreadable tab text (e.g. HOD Momo and Trading painted on top of each other) when many modules were visible.
- **Cause:** `.tab` used `flex: 1 1 0` + `min-width: 0`, so equal-width flex items shrank below label width while `white-space: nowrap` let text bleed into neighbors.
- **Fix:** `.tab` → `flex: 1 0 auto` (grow into spare space, never shrink below content); drop `min-width: 0`. Narrow viewports still scroll via `.tab-bar-scroll`.
- **Keywords:** tab-bar, TabNav, overlap, HOD Momo, Trading, flex shrink, min-width, label bleed

## 2026-07-15 — Uncommitted Stock View CSS lost during phase automation

- **Symptom:** Playwright baseline failed: `documentElement must not page-scroll on Stock View`. Working tree no longer had `body:has(.container--ticker-detail)` / portal flex-fill rules even though `TickerChart.tsx` still had `measureChartFillHeight`.
- **Cause:** Stock View viewport-lock CSS lived only as uncommitted `index.css` edits. A phase subagent discarded those working-tree changes (checkout/resolve) while committing its own `index.css` additions — TS half survived, CSS half vanished.
- **Fix:** Re-apply viewport-lock + chart-fill CSS from the prior session; verify Playwright/Vitest/build; commit CSS together with dangling chart/nav work immediately. Lesson: never leave a verified fix uncommitted while parallel agents touch the same files — commit or stash first.
- **Keywords:** Stock View, index.css, uncommitted, phase agent, discarded, 100dvh, page scroll, Playwright baseline

## 2026-07-15 — Stock View double-click opened a browser tab instead of a window

- **Symptom:** Double-clicking a ticker opened Stock View in a new browser tab, not a detached OS window.
- **Cause:** `window.open(url, '_blank')` with no feature string is treated as “open tab” by Chrome/Edge. Only size/`popup` features request a real window.
- **Fix:** Pass `STOCK_VIEW_WINDOW_FEATURES` (`popup=yes`, width/height, …) and a named target `nova-stock-SYMBOL`; still clear `opener` (no `noopener` flag).
- **Keywords:** Stock View, detach, window.open, popup=yes, new tab, double-click

## 2026-07-15 — Stock View chart gaps + page scroll

- **Symptom:** Large empty black bands between the top chart row (1m/5m) and bottom row (full day/15m); Stock View required vertical page scrolling to reach the trade bar.
- **Cause:** (1) `.chart-portal-slot` / `.chart-portal-host` were `display:block` without flex fill, so grid cells did not pass height to `.chart-body`. Charts stayed at `CHART_HEIGHT_GRID` (180px) inside taller cells. (2) Shell used `min-height: 100vh` instead of a locked `100dvh` flex column, and `#root` was not part of the height chain, so content grew past the viewport.
- **Fix:** Viewport-locked Stock View flex shell (`body` / `#root` / `.container--ticker-detail`); portal slot/host + grid card body `flex: 1 1 0`; `measureChartFillHeight` + ResizeObserver on card/host; compact non-sticky trade bar with `max-height: 22vh`.
- **Keywords:** Stock View, chart-grid, CHART_HEIGHT_GRID, portal-host, fillParentHeight, 100dvh, page scroll, ATAI

## 2026-07-15 — tsc -b failed on Vitest ownership tests importing node:fs

- **Symptom:** `npm run build` (`tsc -b`) failed with `TS2591: Cannot find name 'node:fs'` on `tapeFeed.test.ts` / `modules.ownership.test.ts`.
- **Cause:** `tsconfig.app.json` includes all of `src/` with `types: ["vite/client"]` only — Vitest unit tests that import Node builtins are not part of the app compile graph.
- **Fix:** Exclude `src/**/*.test.ts(x)` from `tsconfig.app.json` so Vitest owns those files; app build stays browser-typed.
- **Keywords:** tsc, vitest, node:fs, tsconfig.app.json, exclude, ownership test

## 2026-07-15 — Vitest loaded Playwright e2e specs and failed the unit suite

- **Symptom:** `npx vitest run` failed on `e2e/baseline.spec.ts` with `Playwright Test did not expect test.describe() to be called here`.
- **Cause:** Vitest default include picks up `*.spec.ts`; Playwright specs under `frontend/e2e/` were executed as Vitest files.
- **Fix:** Exclude `**/e2e/**` in `vite.config.ts` `test.exclude`; import `defineConfig` from `vitest/config` so the `test` key type-checks under `tsc -b`.
- **Keywords:** vitest, playwright, e2e, baseline.spec.ts, test.exclude, vitest/config

## 2026-07-15 — Double-click Stock View only worked on scanners / HOD, not Journal / Trading / Debug

- **Symptom:** Double-clicking a HOD (or scanner) row opened Stock View, but Journal trades, Automation staged/open, Trading positions/orders, Decision cards, and HOD debug tables ignored the second click.
- **Cause:** Those surfaces still rendered plain `<tr>` / plain buttons and never received `onOpenTrading` / `selectedSymbol` props from their parents.
- **Fix:** Wrapped symbol rows in `SelectableTableRow` (Decision cards use the same click-vs-double helper), threaded select/open props from `DashboardPage` → Trading / Watchlist / HOD debug, and extracted `ExecutorTables` + `HodMomoDebugTables` so parents stay under file-size limits. Action cells `stopPropagation`.
- **Keywords:** double-click, Stock View, SelectableTableRow, JournalPanel, ExecutorTables, PositionsPanel, DecisionPanel, HodMomoDebugTables, onOpenTrading

## 2026-07-15 — HOD Momo “virtualized” table mounted all 6,603 rows in the populated browser

- **Symptom:** With the user's live HOD Momo dataset at 6,630 alerts, opening the tab remained crash-level slow and produced an effectively endless document. Browser measurement showed 6,603 mounted alert `<tr>` nodes, 137,325 total DOM nodes, a 212,564px-tall `.hod-table-wrapper`, and a 212,971px document.
- **Cause:** `@tanstack/react-virtual` observed `.hod-table-wrapper`, but that element was `flex: 1` in a parent without a constraining height and retained its intrinsic table height. The wrapper expanded to the full table, so the virtualizer considered the full dataset visible and returned every row. Previous verification used an empty alert list, so it could not expose this failure.
- **Fix:** Removed the virtualizer from `HodMomoAlertTable` and made the mounting contract deterministic: render 40 rows initially and exactly 40 more per distinct internal-scroller bottom reach. The wrapper is fixed at 532px with `flex: 0 0 auto`, `min-height: 0`, contained overscroll, and a bottom-event latch.
- **Verified by:** The same populated browser session now reports 40 mounted rows, 964 total DOM nodes, and a 532px wrapper with 6,630 alerts loaded; one bottom reach produces exactly 80 rows and 1,792 DOM nodes while document height stays unchanged. HOD tab open-to-two-animation-frames measured 52.2ms. Browser console is clean; frontend build and all 75 tests pass.
- **Keywords:** HOD Momo, virtualization, 6603 rows, 137325 DOM nodes, flex intrinsic height, endless scroll, render 40, incremental rendering, populated browser verification

## 2026-07-15 — HOD Momo tab still crash-level laggy after three prior "fixes" — every alert was silently duplicated in frontend state

- **Symptom:** User reported the HOD Momo tab was so laggy that opening it felt like it would crash the browser, despite this having been "fixed" repeatedly (virtualization, alert-persistence throttling, batched live prepends — see the three 2026-07-14/15 entries below titled "HOD Momo freezes" / "HOD Momo UI lag"). Browser console (`npx agent-browser console`) showed a continuous flood of React `"Encountered two children with the same key"` errors, one per HOD alert id, for nearly every visible row.
- **Cause:** All three prior fixes addressed *rendering cost* (row virtualization, batching, save throttling) but never looked at *data integrity* of the `alerts` array itself. `frontend/src/hod_momo/useHodMomoStream.ts`'s WebSocket handlers only guarded on a single shared `mountedRef.current` boolean. React 18 `<StrictMode>` (enabled in `main.tsx`, active for every `npm run dev` session) deliberately mounts → cleans up → remounts effects in development: the cleanup set `mountedRef.current = false` and called `ws.close()` on the first socket, but the immediately-following remount flipped `mountedRef.current` back to `true` and opened a second socket *before* the first socket's close handshake and any in-flight messages had fully drained. Any 'alert' broadcast the stale first socket received during that overlap was no longer blocked by the (now-true) `mountedRef` check, so it got pushed into `pendingRef`/state a second time — identical `id` (backend `alert_id = f"{int(ts*1000)}-{symbol}-{strategy_id}"`), identical payload. Verified backend-side: `backend/.cache/hod-momo-2026-07-15.json` had **zero** duplicate ids among 4097+ alerts — the corruption was 100% client-side. This is the exact "ignore events from a non-current WebSocket instance" anti-pattern the `single-market-data-feed.mdc` rule already mandated and other hooks (`useIbkrDepth`, `useIbkrTape`, `useTickerStream`) already implement — `useHodMomoStream` was simply never brought in line with that pattern when it was written, so every dev session doubled (or, after many hot-reloads across a long edit day, multiplied further) the in-memory alert list, and every duplicate-keyed row forced expensive/incorrect React reconciliation on every re-render, compounding as the day's alert count grew into the thousands.
- **Fix:** `useHodMomoStream.ts` now guards every WS handler on `wsRef.current === ws` (per-instance identity) in addition to `mountedRef`, and the cleanup explicitly nulls `onopen/onmessage/onerror/onclose` before calling `close()` so a lingering socket cannot fire into a torn-down instance. Added a persistent `seenIdsRef: Set<string>` (rebuilt only once, from the `initial` payload) so any duplicate `alert.id` — from this bug, a flaky reconnect, or a future backend re-send — is dropped in O(1) before ever reaching state, instead of doing an O(n) full-array rescan per incoming alert.
- **Verified by:** Live-tested against the running dev server with `agent-browser`: before the fix, clicking the tab produced hundreds of duplicate-key console errors within seconds; after the fix and a fresh reload, the tab was watched for 75+ seconds while live alerts grew from ~4097 to 4458 with **zero** console errors. `npm run build` and `npm run test` (73/73) both pass.
- **Keywords:** HOD Momo, duplicate key, React StrictMode, mount cleanup remount, useHodMomoStream, stale WebSocket instance, wsRef, mountedRef race, dedup, seenIdsRef, alert_id, single-market-data-feed, why fixes didn't stick

## 2026-07-15 — Nova OS event-time replay: decide() saw the whole day (hindsight); evening review scored outcome backward from close, not forward from decision

- **Symptom:** The Nova OS hardening audit's section 5 ("implement no-hindsight replay, rewind, ask, and review loop") named this an unimplemented gap. Reading `archive/replay.py::replay_day()` confirmed a concrete bug, not just a missing feature: it loaded every `bars_1m` row for the whole archived day into `by_symbol[sym]` (sorted ascending), then called `decide(candidate, bars, ...)` exactly once per symbol with that *entire* series — the candidate's `price`/`change_pct`/`volume` were built from `bars[-1]` (the day's close) and `bars[0]` (the day's open), and every gate that reads `bars` (`gate_setup`, `first_minute_volume`, `evaluate_setups`) saw the full day too. A "replay" whose decide() call can see the closing price before "deciding" is not a fair simulation of live decision quality — it is hindsight-biased by construction. `evening_review._outcome_for_decision()` had a second, independent bug: it computed `ref = bars[-(horizon_min+1)]` and `fwd = bars[-1]` — always the *last* bars of the whole day, regardless of when a decision supposedly fired, so "outcome N minutes after the decision" was actually "price N minutes before the close vs at the close," with no relationship to any real decision moment.
- **Cause:** `replay_day()` was written as "one decision per symbol per day" with no concept of an as-of point in time — there was no mechanism to slice a symbol's bars to only what existed at some earlier moment, so the whole day was the only option. `evening_review` inherited that same one-decision-per-day shape and, needing *some* timestamp to anchor its "N minutes after" window, fell back to the day's last bar, which is unrelated to when a decision actually happened.
- **Fix:** Added `archive/replay.py::slice_bars_as_of(bars, as_of_ts)` (bars with `ts <= as_of_ts` only) and a shared `_decide_snapshot()` helper used by both `replay_day(as_of_ts=...)`/`replay_at()` (single no-hindsight point-in-time decision) and new `walk_day()` (steps through a day in `ARCHIVE_REPLAY_WALK_STEP_MIN`-minute increments, calling decide() at each step with bars sliced to that step's own `as_of_ts` — the "rewind" timeline). `replay_day()` without `as_of_ts` keeps the old whole-day behavior only for backward compatibility with the existing CLI/route default, and its response now says `"hindsight": True` explicitly so nobody mistakes it for a fair test. `evening_review()` was rewritten on top of `walk_day()`: for each symbol it picks the first real (no-hindsight) BUY decision from the walk — or the final step's decision if none ever fired — then `_outcome_for_decision()` scores it by looking at bars strictly *after* that exact `as_of_ts`, finding the closest one to `as_of_ts + horizon_min*60`. Using bars *after* the decision to grade it is correct (that is how you check whether a decision paid off); the bug was letting decide() see those same bars *before* deciding, which no longer happens. New REST routes (`/api/archive/walk/{day}`, `/api/archive/review/{day}`, `/api/archive/ask`, plus `as_of` on the existing `/replay/{day}`) and CLI subcommands (`at`, `walk`) expose the fix; `ArchiveRewind.tsx` now drives a real scrubber off `/walk` instead of a single whole-day button.
- **Keywords:** hindsight bias, no-hindsight replay, lookahead, replay_day, decide() sees future bars, walk_day, replay_at, slice_bars_as_of, as_of_ts, evening_review, outcome scored backward from close, forward-looking grading vs decision-time information, Nova OS hardening section 5, rewind

## 2026-07-15 — Nova OS archive durability: silent missing-manifest skip + non-atomic cold writes + L2 never bridged

- **Symptom:** The Nova OS hardening audit's section 4 ("persist all feeds and prove crash-safe local/R2 durability") found: (a) `archive/r2.py::upload_day()` and `archive/restore.py::restore_day_to_temp()` both did `if not man_path.is_file(): continue` for a table's missing cold manifest — if `compact_day()` crashed after writing 4 of 5 table manifests, the day could still be marked `verified_remote: True` in R2 (or `ok: True` in a restore drill) as long as the tables that DID get manifests uploaded/restored cleanly; the missing table's data was silently gone with no failure signal. (b) `compact.py`'s `_write_jsonl()` opened the final path directly in `"w"` mode — a crash mid-write left a truncated file on disk while an *old* manifest (from a previous successful run, never rewritten because the crash happened before `write_manifest()`) still claimed the old, now-wrong, row_count/sha256 for it. (c) `archive/capture.py::record_l2_snapshot()` was an unwired, in-memory-only stub (no production caller — confirmed via repo-wide grep) capped at 10k rows and dropped on restart; the counter it bumped looked like evidence L2 depth was being durably captured, when in production nothing called it at all. L2 depth *was* actually being durably captured all along, just by a completely different, older subsystem (`l2/continuous.py` → `l2/db.py`) that the archive package's own P6 stub docstring referenced but never bridged into cold/R2.
- **Cause:** (a) `continue` was written to mean "nothing to upload for this table" instead of distinguishing "genuinely empty" (which `compact_day` always represents with a row_count=0 manifest) from "manifest never got written." (b)/(c) were both write-path integrity gaps: no atomic replace on the jsonl, and a real persistence mechanism (`l2/db.py`) that pre-dated the Nova OS archive package but was never connected to its cold-compaction/R2 pipeline.
- **Fix:** `archive/manifest.py::write_manifest()` and a new `archive/compact.py::write_jsonl_atomic()` (renamed from the old private `_write_jsonl`) now write to a sibling temp file, fsync, then `os.replace()` into the final path — a crash mid-write can never leave the final path holding partial content that doesn't match its manifest. `r2.py::upload_day()` and `restore.py::restore_day_to_temp()` now treat a missing manifest as an explicit `ok: False` failure entry (not a skip), and `upload_day()` additionally calls `manifest.verify_payload()` on the local file against the manifest's recorded sha256 immediately before uploading — a mismatch (stale/corrupted local file) is refused and never reaches R2. New `archive/l2_bridge.py` bridges `l2/db.py`'s `l2_snapshots`/`tape_trades` tables (ts-range queried per America/New_York calendar day, since that db has no `session_date` column) into the same checksummed-JSONL-manifest pattern, with its own R2 upload (`upload_l2_day`), verified index (`_r2_verified_l2.json`, deliberately separate from the primary index so a stalled L2 backup never falsely marks the bars/tape_ibkr day verified or vice versa), and restore drill (`restore_l2_day_to_temp`). Wired into `archive/scheduler.py::run_maintenance_once()` as a best-effort step per finished day (wrapped in its own try/except so an L2 failure never blocks the primary compaction). `capture.py`'s dead stub is left in place (still nothing calls it) but its docstring now explicitly redirects to `l2_bridge` so a future reader doesn't mistake it for the real capture path.
- **Keywords:** archive durability, missing manifest silent skip, upload_day, restore_day_to_temp, atomic write, os.replace, write_jsonl_atomic, l2_bridge, l2.db, l2_snapshots, tape_trades, R2 verified index, sha256 mismatch, Nova OS hardening section 4, persist all feeds

## 2026-07-15 — Nova OS mode-receipt split-brain + unsafe flatten/recovery

- **Symptom:** An audit of Nova OS P2–P7 found (a) every decide() receipt from the scanner and `/api/nova-os/decide*` claimed `mode: "signal"` and `would_execute: false` even while the operator had actually raised control mode to `confirm`/`auto_paper` and orders were staging/placing for real — the audit trail didn't match reality; (b) `flatten_positions()` could SELL after an unfilled parent was cancelled and could leave protective legs working after a position closed; (c) staged-ticket approval and auto_paper placement only checked safety gates once, not at the moment of action, so a kill switch or risk halt seconds later didn't stop an in-flight approval; (d) startup recovery ran before `ibkr.client.startup()` completed, so it always reported "ambiguous — can't verify" for every open position; (e) the loss policy used `consecutive_losses`, which an intervening win resets, instead of a same-day total.
- **Cause:** `strategy/setups_stream.py` and `routes/nova_os.py` hardcoded `mode=NOVA_OS_DEFAULT_MODE` into `decide()` calls instead of reading the real `control_mode.get_mode()`. `flatten_positions()`/`place_from_ticket()`/`staged_tickets.approve()` treated "mode was raised" or "ticket was staged" as a standing permission rather than re-validating at execution time. `app_lifespan.py` called `run_startup_recovery()` before the IBKR client finished connecting. `strategy/risk.py`'s `RiskState` had no independent daily-loss counter.
- **Fix:** Pass the real control mode through `setups_stream._scan_once()` and both `/api/nova-os/decide*` routes (also `record=False` there — they're polling endpoints). Extract `flatten_preview`/`flatten_positions` into `strategy/executor_flatten.py` with real-IBKR-position reconciliation and unconditional protective-leg cancellation. `place_from_ticket()` and `staged_tickets.approve()` re-check kill switch/mode/concurrency/gates/risk immediately before acting, with an explicit `placement_declined`/`approve_blocked` receipt per rejection reason; approval claims the ticket atomically via `dict.pop`. Reorder `app_lifespan.py` so IBKR startup completes before recovery/`risk.reconstruct_from_journal()` run. Add `RiskState.losses_today`, drive `codes.loss_policy_mode()` from it, and rebuild it from the trade journal on restart.
- **Keywords:** would_execute, mode split-brain, decide() hardcoded mode, flatten unsafe sell, staged ticket race, approve atomic, startup recovery ambiguous, consecutive_losses vs losses_today, Nova OS hardening, placement_declined receipt

## 2026-07-15 — Chart Loading stuck: setups_stream starved IBKR historical

- **Symptom:** Open-ticker chart stayed on "Loading…" for 20–30+ seconds (or until timeout) even with Gateway connected.
- **Cause:** `strategy/setups_stream` pulled IBKR `reqHistoricalData` for up to 15 symbols every 15s on the same socket/event loop as the chart. Requests queued; chart hit the 30s timeout while UI spun.
- **Fix:** `ibkr/historical_gate` serializes historical pulls and gives interactive chart priority; throttle setups under ibkr (top 3 / 60s / inter-symbol delay); shorten 1Min lookback to `1 D`; client abort at 25s so Loading cannot hang forever.
- **Keywords:** chart loading, IBKR historical, setups_stream, pacing, reqHistoricalData, TimeoutError, Loading

## 2026-07-15 — Exchange dropdown transparent (missing --card-bg token)

- **Symptom:** Filter Exchanges menu rendered with no background — checkboxes floated over the Settings form behind it.
- **Cause:** `.hod-filter-dropdown` used `var(--card-bg)` / `var(--hover-bg)`, but those CSS variables were never defined in `:root` (only `--panel-bg` existed), so the background resolved to transparent.
- **Fix:** Define `--card-bg: var(--panel-bg)` and `--hover-bg` in `:root`; point the filter dropdown at `--panel-bg` explicitly with a stronger shadow.
- **Keywords:** exchange filter, transparent dropdown, --card-bg, design tokens, Filter Exchanges

## 2026-07-15 — Chart maximize collided with app header; bars blanked then loaded late

- **Symptom:** Maximize chart → Nova header / Symbol Look Up mixed into chart toolbar; candlesticks missing then appeared much later.
- **Cause:** `.side-panel` `container-type: inline-size` made `position: fixed` relative to the panel, not the viewport. Chart `useEffect` listed `maximized` as a dependency, so toggle destroyed and recreated lightweight-charts (empty until refetch).
- **Fix:** Stable portal host reparented to `document.body` while maximized; remove `maximized` from chart create deps; resize in place; Escape to restore.
- **Keywords:** chart maximize, header overlap, container-type, position fixed, side-panel, createPortal, lightweight-charts remount

## 2026-07-15 — HOD Momo alerts wiped on every API restart after 4 AM ET

- **Symptom:** Full-day HOD list (~1000 alerts) shrank to ~90 after restarting the backend; UI scroll ended because the data was gone, not because of virtualization.
- **Cause:** `load_state()` loaded today's snapshot, then `_check_and_reset_session()` saw empty `_session_date` ≠ today and treated it as a rollover, setting `_today_alerts = []`. The next `_save_alerts` overwrote `hod-momo-YYYY-MM-DD.json` with the small new list.
- **Fix:** Initialize `_session_date` without clearing on first boot; archive prior-day alerts on real rollover; add explicit `DELETE /api/hod-momo/alerts` + Clear today UI.
- **Keywords:** HOD Momo, session rollover, restart wipe, persistence, load_state, _session_date, clear alerts

## 2026-07-15 — HOD Momo UI lag at ~1000 alerts despite virtualization

- **Symptom:** Browser extremely laggy on HOD Momo tab with ~1000 alerts today; scrolling/UI felt frozen.
- **Cause:** Hand-rolled windowing + later a custom Prev/Next pager still fought the problem awkwardly; user correctly asked for a standard virtual-scroll library instead.
- **Fix:** Switched the alert table to `@tanstack/react-virtual` (`useVirtualizer`) for continuous scroll with only viewport+overscan rows mounted; removed custom pager/`useWindowedRows`.
- **Keywords:** HOD Momo lag, @tanstack/react-virtual, virtualization, 1000 alerts, HodMomoAlertTable

## 2026-07-15 — reset_config(12) rejected; HOD Momo debug path queued stale fundamentals symbol

- **Symptom (bug 1):** `POST` to the HOD Momo config-reset API for strategy 12 ("Running Up Alert") silently returned `None`/404-equivalent — that one strategy could never be reset to defaults individually, even though `reset_all()` and every other strategy ID worked fine.
- **Cause (bug 1):** `hod_momo.reset_config()` validated the incoming `strategy_id` against a hardcoded `range(1, 12)` (exclusive upper bound → IDs 1–11 only) instead of the `HOD_MOMO_STRATEGY_ID_MAX` constant (=12, inclusive per `HOD_MOMO_STRATEGY_NAMES`/`HOD_MOMO_STRATEGY_DEFAULTS` and per the sibling `_load_configs_from_disk()`, which already used `range(1, HOD_MOMO_STRATEGY_ID_MAX + 1)`). Strategy 12 (Running Up) was added later (schema v3) and this bound was never updated to match.
- **Fix:** `reset_config()` now checks `strategy_id not in range(1, HOD_MOMO_STRATEGY_ID_MAX + 1)`, matching the existing inclusive-bound pattern already used elsewhere in `hod_momo.py`. Added `test_reset_config_resets_strategy_12_running_up` and `test_reset_config_still_rejects_out_of_range_ids` in `backend/tests/test_hod_momo_engine.py`.
- **Symptom (bug 2):** The HOD Momo debug-symbol endpoint (`get_debug_symbol` → `_would_fire_now`) could enqueue the wrong ticker (or nothing useful) into the fundamentals-fetch queue instead of the symbol actually being inspected.
- **Cause (bug 2):** `_would_fire_now(symbol)` called `_evaluate_strategy(..., lambda: mark_needs_fundamentals(_active_symbol()))`, reusing the same callback shape as the live `on_trade_update` path. But only `on_trade_update` sets the module-level `_active_symbol_name` global (to the live symbol on entry, back to `""` on exit) — `_would_fire_now` never set it. Any debug-symbol request that ran between trades (i.e. always, since it's not invoked from inside `on_trade_update`) read a stale leftover symbol (or `""`) via `_active_symbol()`, so `mark_needs_fundamentals()` queued the wrong ticker.
- **Fix:** `_would_fire_now()` now calls `mark_needs_fundamentals(symbol)` directly using its own `symbol` parameter instead of routing through the `_active_symbol_name` global that only `on_trade_update` owns. The live `on_trade_update` path is unchanged. Added `test_would_fire_now_queues_symbol_being_debugged_not_stale_active_symbol` in `backend/tests/test_hod_momo_engine.py`.
- **Keywords:** reset_config, HOD_MOMO_STRATEGY_ID_MAX, off-by-one, strategy 12, Running Up Alert, _would_fire_now, get_debug_symbol, mark_needs_fundamentals, _active_symbol_name, stale symbol, fundamentals queue, hod_momo.py

## 2026-07-15 — Open-ticker detail loop still snapshotting symbols already streaming live

- **Symptom:** Suspected open-ticker (quote panel) lag under load (movers scans + multiple open panels), attributed to the detail refresh being snapshot-based instead of a persistent `reqMktData` stream.
- **Cause:** The open ticker had *already* moved to streaming (`ibkr/ticks.py`, `reqMktData`, added 2026-07-14) — but `ibkr/reprice.py`'s `detail_reprice_loop` "backstop" kept firing a full `reqTickersAsync` snapshot every `IBKR_REPRICE_INTERVAL_SEC` (3s) for **every** open detail symbol regardless of whether its stream was already delivering. That redundant snapshot request queued on the same Gateway connection as `table_reprice_loop`'s 1Hz chunked snapshots — real request-queue contention, just from a duplicate call nobody removed after streaming landed.
- **Fix:** `ibkr/ticks.py` now stamps `last_update_ts` on every `updateEvent` and exposes `is_fresh(symbol, max_age_sec)`. `detail_reprice_loop` / `reprice_detail_symbols` take an optional `is_stream_fresh` callback (wired in `app_lifespan.py` to `ticks.is_fresh(..., IBKR_DETAIL_STREAM_FRESH_SEC)`) and skip the snapshot+broadcast entirely for symbols whose stream is fresh, only backstopping symbols with no/stale stream.
- **Keywords:** open ticker lag, reqMktData already streaming, detail_reprice_loop, reqTickersAsync contention, ibkr/ticks.py, ibkr/reprice.py, IBKR_DETAIL_STREAM_FRESH_SEC, is_fresh, Gateway request queue, table_reprice_loop contention

## 2026-07-15 — Empty "IBKR bars failed for SYMBOL:" in Sentry

- **Symptom:** Sentry/logs showed `IBKR bars failed for AAPL:` / `PYPG:` with nothing after the colon; UI got opaque 503s.
- **Cause:** `reqHistoricalData` timeouts and Gateway cancel (Error 162) often raise exceptions whose `str(exc)` is empty (`TimeoutError()`). Chart path logged/raised with `{exc}` only. Those expected failures were also logged at ERROR, flooding Sentry.
- **Fix:** `ibkr/errors.describe_exc` / `is_transient_historical_failure` / `bars_failure_detail`; transient → warning + clear 503; unexpected → error+traceback. Still no Alpaca candle fallback under ibkr.
- **Keywords:** IBKR bars, chart_bars, TimeoutError, Error 162, Sentry empty message, historical cancelled, PYTHON-FASTAPI-6

## 2026-07-15 — Alpaca WS still connected under discovery=ibkr

- **Symptom:** Backend opened Alpaca market-data WS even when discovery=ibkr (HOD trades already ignored), burning the single connection slot and risking 406 under reload.
- **Cause:** `stream_loop` always connected; prior fix only skipped applying trades, not opening the socket.
- **Fix:** Idle + poll when `not alpaca_trades_drive_hod()`; break inner loop if discovery flips to ibkr mid-session.
- **Keywords:** Alpaca WS, idle, discovery=ibkr, 406, connection limit, stream_loop, ALPACA_WS_IDLE_POLL_SEC

## 2026-07-15 — Alpaca WS still fed HOD Momo under discovery=ibkr

- **Symptom:** HOD alerts / snaps could move on Alpaca IEX prints while scanner/quote prices came from IBKR — dual-feed drift after hours or on thin IEX.
- **Cause:** `handle_trade` already skipped scanner cache overlays under ibkr, but the stream loop still called `_hod_momo.on_trade_update` and `l2.tape.on_alpaca_trade` for every Alpaca trade.
- **Fix:** Early-continue when `not alpaca_trades_drive_hod()`; IBKR `table_reprice` / detail ticks remain the HOD feed.
- **Keywords:** dual-feed, HOD Momo, Alpaca WS, on_trade_update, discovery=ibkr, single-market-data-feed, l2.tape

## 2026-07-14 — Ticker WS used missing main._ibkr_ticks after Phase 4 extract

- **Symptom:** Opening a ticker under discovery=ibkr could fail to subscribe ticks / raise AttributeError if the old route path ran (`m._ibkr_ticks`).
- **Cause:** `routes/ticker.py` still did `import main as m` and called `m._ibkr_ticks.subscribe`, but ticks live in `ibkr.ticks` and were never re-exported on `main` after the router extract.
- **Fix:** Route imports `from ibkr import ticks as _ibkr_ticks`, `alpaca` helpers, and `websocket.mark_resub` directly — no main indirection for tick subscribe.
- **Keywords:** routes/ticker, _ibkr_ticks, AttributeError, websocket ticker, Phase 4 extract

## 2026-07-14 — Strategy bars + catalyst prices mixed Alpaca when discovery=ibkr

- **Symptom:** Strategy endpoints (`/api/strategy/gap-and-go`, `/api/strategy/setups`) always used Alpaca IEX bars regardless of provider; Catalysts tab prices disagreed with IBKR scanner rows. REST `/api/ticker/{sym}` silently served Alpaca snapshot when IBKR snapshot was empty.
- **Cause:** (1) `routes/strategy.py` and `strategy/setups_stream.py` imported `bars.fetch_bars` directly (Alpaca-only) instead of the provider-aware `chart_bars.fetch_chart_bars`. (2) `_run_news_catalyst_scan` always called `_fetch_snapshots` (Alpaca) for prices regardless of `_get_discovery_provider()`. (3) `_build_ticker_detail` explicitly fell back to `_fetch_ticker_snapshot` (Alpaca) when IBKR returned `{}`.
- **Fix:** (1) Strategy routes + setups stream → `chart_bars.fetch_chart_bars(discovery_provider=...)`. (2) Catalyst scan → use `_find_ibkr_cache_row` for prices when `ibkr`, Alpaca path only for `alpaca`. (3) REST ticker — removed Alpaca fallback; logs warning and returns empty snapshot matching WS behavior.
- **Keywords:** strategy bars, setups_stream, catalyst price, _build_ticker_detail, Alpaca fallback, single-market-data-feed, fetch_chart_bars, discovery_provider

## 2026-07-14 — Scanner table prices stale 7–10s (giant reqTickersAsync)

- **Symptom:** Header showed "stale · updated 7s ago" / up to ~10s on Gainers even while Connected; prices felt stuck.
- **Cause:** `table_reprice_loop` called one `reqTickersAsync` for ~100 symbols (gainers+losers+AH+HOD seeds). That call often took 7–10s; skip-if-busy then emitted stale heartbeats until it finished, so the UI age never reset mid-batch.
- **Fix:** Chunk snapshots (`IBKR_TABLE_REPRICE_CHUNK_SIZE=20`) with per-chunk timeout; one chunk per 1Hz tick + rotate; push after each chunk; drop HOD seeds from `_table_reprice_symbols` (scanner rows only).
- **Keywords:** stale updated 7s ago, table reprice, reqTickersAsync, IBKR_TABLE_REPRICE_CHUNK_SIZE, price_patch, scanner

## 2026-07-14 — HOD same-ticker spam (no Warrior consolidation)

- **Symptom:** HOD feed repeated the same ticker row after row (CNEY/TRT/…) instead of one row with "(3 in 5sec)".
- **Cause:** Each queued alert set its own `emit_after = now + consolidation_sec`, so staggered fires in the same burst never landed in one flush bucket.
- **Fix:** First alert opens the window; later same-ticker fires share that deadline; emit newest price + real `consolidation_span_sec`; UI shows `(N in Xs)` under Symbol and collapses leftover consecutive rows.
- **Keywords:** HOD Momo, consolidation, Warrior, N in Xs, same ticker, TRT, AEHR

## 2026-07-14 — HOD Momo freezes with 3k+ alerts (save + UI thrash)

- **Symptom:** UI glitches/freezes with HOD Momo at ~3000 alerts; whole app felt sticky. Follow-up: truncating the live list to 500 hid older alerts users still needed.
- **Cause:** (1) Every emitted alert serialized+wrote the full day list to disk on the asyncio thread. (2) Each live alert re-rendered App. (3) Mounting every `<tr>` (pre-virtualization). Truncating data was the wrong fix for (3).
- **Fix:** Rate-limit alert persistence (5s); keep **all** alerts in memory/WS; virtualize row render only; batch live prepends (150ms); rAF-throttle scroll.
- **Keywords:** HOD Momo freeze, 3000 alerts, _save_alerts, virtualization, useHodMomoStream, do not truncate

## 2026-07-14 — After-hours HOD missed Warrior names (ATHE/TRT/XCUR)

- **Symptom:** Warrior Small Cap HOD AH showed ATHE/TRT/XCUR; Nova HOD showed DYAI squeeze spam; XCUR open in quote but not alerting; After Hours tab ~2 rows.
- **Cause:** (1) AH discovery used Alpaca IEX full-universe scan while `discovery=ibkr` — often 0–2 rows, starving HOD universe. (2) First IBKR AH call raced Gateway connect → 0 rows → **silent Alpaca fallback** locked in a 2-row snapshot for the discovery interval. (3) Enrichment/fundamentals overwrote RVOL with thin yfinance volume. (4) AH scan loop stopped refreshing Top Gainers. (5) `_effective_min_rvol` ignored `afterhours_min_rvol`.
- **Fix:** AH rows reshape from live IBKR `_gainer_cache` every AH cycle (no Alpaca fallback when discovery=ibkr); IBKR focus reprice + HOD snap seed; enrichment/on_trade `ibkr_pace` RVOL; AH loop runs `_run_gainers_update`; master gate uses `afterhours_min_rvol`.
- **Keywords:** after hours, HOD Momo, ATHE, TRT, XCUR, DYAI, IBKR TOP_PERC_GAIN, ibkr_pace, yfinance_pace, afterhours_min_rvol, Alpaca fallback

## 2026-07-14 — HOD Momo ≠ Warrior Day Trade Dash (wrong universe / RVOL / gates)

- **Symptom:** Warrior Small-Cap HOD showed TSSI / YG / FRE with Squeeze and Medium Float strategies; Nova showed CNEY spam (Former Momo + Squeeze) and missed the same names.
- **Cause:** (1) Watch set was only Top Gainer/Gapper shortlist — Warrior scans the tape including volume runners. (2) RVOL was raw daily/avg, not Warrior "Daily Rate" pace RVOL. (3) Master gate required +3% in 5min on *every* strategy, blocking Medium Float HOD grinds. (4) Former Momo with empty list treated every symbol as a former runner.
- **Fix:** IBKR HOT_BY_VOLUME / TOP_VOLUME_RATE / MOST_ACTIVE seeds; pace RVOL via `market.pace_relative_volume`; master surge default 0 + schema v2 migrate; Former Momo requires non-empty list; table reprice includes HOD seeds.
- **Keywords:** HOD Momo, Warrior Trading, Day Trade Dash, pace RVOL, Daily Rate, Former Momo, HOT_BY_VOLUME, master surge, Medium Float

## 2026-07-14 — HOD Momo tab empty (total_trades_seen=0)

- **Symptom:** HOD Momo showed no alerts all session; debug counters had `universe_size≈6022`, `snaps_populated≈6020`, but `total_trades_seen=0` and empty decisions.
- **Cause:** `_refresh_hod_momo_universe` subscribed Alpaca IEX trades to the full common-stock list (~6k). Free IEX does not deliver a usable tape at that scale (probe: 5 top-gainers → trades; 6k subscribe → silence). Ross / Warrior scanners watch a Top Gainer shortlist, not the full tape — already noted in `Scanner-Provider-IBKR-Primary.md`. A follow-on bug shadowed `import hod_momo_universe as _hod_momo_universe` with the `_hod_momo_universe: set` global (`AttributeError: 'set' object has no attribute 'build_focus_universe'`), which broke the scan loop until the import was renamed `_hod_uni`.
- **Fix:** Default `HOD_MOMO_UNIVERSE_MODE=focus` builds watch set from gappers/gainers/losers/AH + open details; chunk Alpaca subscribe; feed IBKR 1Hz table reprice into `on_trade_update` when discovery=ibkr; import alias `_hod_uni`; add universe + engine tests.
- **Keywords:** HOD Momo empty, total_trades_seen, Alpaca IEX, 6000 symbols, Ross shortlist, focus universe, table_reprice, on_trade_update

## 2026-07-14 — Empty Time & Sales; Level 2 cramped beside it

- **Symptom:** Quote panel showed Level 2 and Time & Sales squeezed side-by-side; T&S headers visible but no prints. Data sources still listed Interactive Brokers for both.
- **Cause:** (1) Layout: `DepthAndTape` used a horizontal flex split inside the half-width quote column. (2) Data: the live uvicorn process had not picked up `/ws/ibkr/tape/{symbol}` — unmatched WS paths return HTTP 403, so `useIbkrTape` never got `subscribed`/prints. Empty-state text also collapsed (`flex: 1 1 0` with no min-height).
- **Fix:** Stack L2 + T&S as full-width rows under Watchlist; give `.ts-panel` a min-height; restart API so the tape route loads; surface IB tick-by-tick subscription errors on the WS.
- **Keywords:** Time & Sales empty, Level 2 cramped, DepthAndTape, /ws/ibkr/tape, WebSocket 403, reqTickByTickData, AllLast, Watchlist layout

## 2026-07-14 — Scanner “updated 10–12s ago” / table prices frozen during movers scan

- **Symptom:** Header age climbed to ~10–12+ seconds; Gainers table prices lagged the open quote panel even though both said IBKR.
- **Cause:** `reprice_table_caches` only ran inside `_sleep_with_ibkr_reprice` after `_run_gainers_update` finished. A full IBKR movers scan often takes 20–90s, so table prices and `_gainer_cache_ts` (drives “updated Xs ago”) did not advance during the scan.
- **Fix:** Independent 1Hz `table_reprice_loop` + `/ws/scanner` patches + honest stale UI; contract cache for snapshots; removed mid-sleep table reprice.
- **Keywords:** updated 10s ago, table lag, IBKR_TABLE_REPRICE_INTERVAL_SEC, table_reprice_loop, scan loop starvation, reqTickersAsync, scanner_push, stale

## 2026-07-14 — Level 2 book from prior ticker under new quote (MVO vs ~$7 NXTC)

- **Symptom:** Quote panel showed MVO at $0.80 (+363%) while Level 2 showed bids/asks around $7.14–$7.28 (prior ticker NXTC). Data sources said IBKR for quote/L2 but “Broker listing (Alpaca)” looked like a mixed feed.
- **Cause:** (1) `useTickerStream` kept prior `detail` across symbol changes, so `DepthLadder symbol={detail.symbol}` stayed on the old name while the header/scanner reflected the new selection. (2) SidePanel rendered whenever `detail` was truthy without `detail.symbol === selectedSymbol`. (3) `useIbkrDepth` did not ignore stale WebSocket instances or `msg.symbol` mismatches. Separately, `chart_bars` silently fell back to Alpaca when IBKR failed — a second class of “unaware dual feed” risk.
- **Fix:** Clear detail on switch; gate panel on symbol match; bind L2 to `selectedSymbol` + WS/`msg.symbol` guards; IBKR-mode chart bars hard-fail (no Alpaca fallback); project rule `single-market-data-feed.mdc`; retitle listing as metadata.
- **Keywords:** Level 2 wrong symbol, MVO, NXTC, stale detail, useTickerStream, useIbkrDepth, single source of truth, Alpaca fallback, chart_bars, quote panel gate

## 2026-07-14 — 1Min chart looked wrong vs other tools; live candle not tick-fast (IBKR mode)

- **Symptom:** With `NOVA_DISCOVERY_PROVIDER=ibkr`, the quote price could move (slowly) while the 1-minute chart looked sparse/"weird" vs Webull/other tools, and the forming candle did not update tick-by-tick. Level 2 still felt live.
- **Cause:** (1) Chart bars always came from Alpaca IEX (`bars.fetch_bars`) regardless of discovery provider — thin IEX history vs IBKR live quotes = mismatched candles. (2) Live `trade_update`s were only from 3s `snapshot_quotes` reprice, and broadcasts were scheduled through `_run_ibkr` on the contended IB bridge, so gaps often stretched to ~10–14s. No `reqMktData` last-price stream existed for detail panels (unlike Level 2).
- **Fix:** Added `backend/ibkr/bars.py` + `chart_bars.fetch_chart_bars` (IBKR historical when connected, Alpaca fallback). Added `backend/ibkr/ticks.py` streaming last-price on ticker-detail WS open/close. Reprice broadcasts now `run_coroutine_threadsafe` onto the main loop instead of `_run_ibkr`. Relaxed frontend `CHART_REFETCH_SEC` for 1Min (ticks own the live candle).
- **Keywords:** chart wrong, IEX sparse bars, IBKR historical, reqHistoricalData, trade_update slow, reqMktData ticks, dual data source, chart_bars, ibkr/ticks.py

## 2026-07-14 — Agent shell env var (`NOVA_API_RELOAD`) silently survived across an entire session, made every "stable restart" still use `--reload`

- **Symptom:** Mid-session, an agent set `NOVA_API_RELOAD=1` once to force a hot-reload restart, then later deliberately started the backend "without reload" for stability several times (`py -3 run_api.py`, no flag). Each of those "stable" restarts still printed `WatchFiles detected changes ... Reloading...` on the next file edit and then the whole process silently exited (`exit_code: 0`, no traceback) — looking exactly like a mysterious app crash-on-reload bug, when editing files should not have restarted anything at all.
- **Cause:** The agent's shell tool is a single persistent PowerShell session across the whole conversation. `$env:NOVA_API_RELOAD = 1` (or `[Environment]::SetEnvironmentVariable` / `$env:X=1` in an earlier command) persists for every subsequent command in that session, including ones run much later that never intended to touch it. `run_api.py` reads `NOVA_API_RELOAD` with a "false" default, so it looked safe — but the stale `1` from earlier silently overrode that default on every later restart, and was never printed or checked before declaring "backend restarted, stable, no reload."
- **Fix:** No code change — this is a process discipline issue. Before relying on a shell-scoped env var to be *unset* / at its default, explicitly check it (`$env:NOVA_API_RELOAD`) or explicitly clear it (`Remove-Item Env:\NOVA_API_RELOAD`) rather than assuming a fresh default. When a background process behaves unexpectedly right after a restart in a long agent session, check `Get-ChildItem Env:` for stale overrides before assuming the application code is at fault.
- **Keywords:** NOVA_API_RELOAD, stale env var, persistent shell session, WatchFiles Reloading, silent exit_code 0, uvicorn --reload, agent shell state, false debugging lead

## 2026-07-14 — Detail panel updates every ~30s instead of every tick (IBKR provider)

- **Symptom:** With `NOVA_DISCOVERY_PROVIDER=ibkr`, the ticker-detail panel's `trade_update` WS message (price/volume/prev_close) arrived only once every ~14-90s, not every `IBKR_REPRICE_INTERVAL_SEC` (3s) as intended — everything else in the panel looked frozen except Level 2, which streams independently.
- **Cause:** The fast "reprice between scans" mechanism (`_reprice_ibkr_caches`, called from `_sleep_with_ibkr_reprice` inside `_scan_loop`'s sleep) only got CPU time *after* that iteration's `_run_gainers_update()` finished. For the IBKR provider, `_run_gainers_update` runs a full market scan (`get_gainers()` + `get_losers()`, each doing `scan_symbols()` + `snapshot_quotes()` for up to 50 symbols) *before* the loop ever reaches the sleep/reprice step — that alone routinely took 20-90+ seconds. So even after first separating "reprice the 1-2 detail symbols" from "reprice the whole 100+ symbol table" into two functions, both were still nested inside the same slow scan loop and only got to run once per full (slow) iteration, not every 3s.
- **Fix:** Extracted the reprice logic out of `main.py` into `backend/ibkr/reprice.py` (`reprice_detail_symbols`, `reprice_table_caches`, `detail_reprice_loop`). `detail_reprice_loop` is now started as its **own independent `asyncio.create_task`** in `main.py`'s lifespan, on its own `asyncio.sleep(IBKR_REPRICE_INTERVAL_SEC)` timer, completely decoupled from `_scan_loop` — it can never be blocked by a slow discovery/movers scan. The bulk table reprice (`reprice_table_caches`) stays tied to the scan loop's sleep, since it's a best-effort refresh between full scans, not a per-tick guarantee. Added `backend/tests/test_ibkr_reprice.py` to lock in the separation and the "fall back to cached price when snapshot_quotes() comes back empty" behavior.
- **Keywords:** trade_update, detail panel frozen, _reprice_ibkr_caches, _sleep_with_ibkr_reprice, _run_gainers_update slow, IBKR_REPRICE_INTERVAL_SEC, ibkr/reprice.py, detail_reprice_loop, decoupled async task, scan loop starvation

## 2026-07-14 — Quote panel price/gap % desynced from IBKR scanner row

- **Symptom:** Same symbol (e.g. NXTC) showed scanner Price $9.02 / Gap +313.60% while the quote panel showed big line 2.28 (+16.92%) and Pre: 9.02 +6.74 (+295.46%). User thought React was not updating.
- **Cause:** `/ws/ticker/{symbol}` Phase 1 (`_build_ticker_fast`) always fetched Alpaca snapshots even when `discovery_provider=ibkr`. REST `_build_ticker_detail` already used IBKR. Alpaca `session_close` ≈ $2.28 vs IBKR scanner `prev_close` ≈ $2.18 produced two different gap %. `_fetch_ticker_snapshot_ibkr` also set `session_close` to the live price (wrong for Webull Pre: math). `trade_update` only patched `latest_trade.price`, not `prev_close`. Bid/ask bracketing last is normal L2, not a sync bug.
- **Fix:** `_build_ticker_fast` uses `_fetch_ticker_snapshot_ibkr` when discovery is ibkr; `session_close` = prior close; IBKR UI uses one live-vs-prev_close line; `trade_update` includes `prev_close` and `useTickerStream` patches snapshot accordingly.
- **Keywords:** NXTC, quote panel mismatch, scanner gap %, _build_ticker_fast, Alpaca vs IBKR, session_close, trade_update, useTickerStream, Webull Pre line

## 2026-07-14 — IBKR gappers empty in premarket (TOP_OPEN_PERC_GAIN returns 0)

- **Symptom:** After IB Gateway connected (`/api/ibkr/status` connected:true), `/api/gappers` still returned `[]` during premarket despite real gaps (NXTC +300%, etc. visible via IB `TOP_PERC_GAIN`).
- **Cause:** `get_gappers()` only used scan code `TOP_OPEN_PERC_GAIN` (today's open vs prior close). Before the regular session open, IB often returns 0 rows / error 162 "API scanner subscription cancelled" for that code. Premarket gaps are correctly described by `TOP_PERC_GAIN` (last vs prior close).
- **Fix:** `backend/ibkr/discovery.py` `get_gappers()` now falls back to `TOP_PERC_GAIN` when `TOP_OPEN_PERC_GAIN` is empty, then applies the existing `GAPPER_MIN_GAP_PCT` filter. Added scanner result logging.
- **Keywords:** TOP_OPEN_PERC_GAIN, TOP_PERC_GAIN, premarket gappers, error 162, scanner cancelled, get_gappers, IBKR discovery

- **Symptom:** User reported "nothing is being scanned" and knew real gappers existed, but `/api/gappers`, `/api/movers`, `/api/afterhours` all returned empty lists, and the UI showed the generic "No gappers with a gap of at least X% yet — scan running..." message that implied everything was healthy.
- **Cause:** `.env` has `NOVA_DISCOVERY_PROVIDER='ibkr'`, so scanner discovery is sourced from IBKR (`backend/ibkr/discovery.py`), not Alpaca — but IB Gateway was not logged in. Launching `C:\Jts\ibgateway\1045\ibgateway.exe` alone is not enough: until login (+ weekly 2FA) completes, Gateway opens **no** local API socket, so Nova's reconnect loop gets `ConnectionRefusedError` on `127.0.0.1:4001` forever. `_run_ibkr()` then returns `[]`, which the UI treated as "no gaps yet". Red herring: port `40001` was listening but owned by `Immersed-service` (VR), not IB — TCP connect succeeded then IB API handshake timed out with WinError 64.
- **Fix:** (1) Launch Gateway and bring its login window to the foreground; Nova already retries every ~10s once the API port opens after login. (2) `EmptyState` now takes `discoveryProvider` and, when `ibkr` + Gateway offline, shows `EMPTY_IBKR_DISCONNECTED` instead of the misleading "no gappers yet" copy (`frontend/src/components/EmptyState.tsx`, `constants.ts`).
- **Keywords:** empty gappers, no movers, ConnectionRefusedError, IB Gateway not logged in, NOVA_DISCOVERY_PROVIDER, _run_ibkr, /api/ibkr/status, silent degrade, port 4001, Immersed 40001, EMPTY_IBKR_DISCONNECTED

## 2026-07-14 — Block button in quote panel could not be undone

- **Symptom:** User clicked "Block" on a ticker (LVLU) in the quote panel, then clicked the button again to undo it — nothing happened. The ticker stayed on the HOD Momo blocklist with no way to remove it from that button.
- **Cause:** `TickerDetailContent.tsx`'s block button only ever called `POST /api/hod-momo/blocklist` (add) and set local `blocked` state to `true`, then rendered `disabled={blocked}` — once true, the button could never be clicked again, and there was no code path calling the `DELETE /api/hod-momo/blocklist/{symbol}` endpoint that already existed in `backend/main.py`/`hod_momo.py`. Separately, `blocked` was reset to a hardcoded `false` on every symbol change instead of checking the real blocklist, so an already-blocked symbol misleadingly showed "Block" instead of "Blocked" on first load.
- **Fix:** Fetch the real blocklist on mount/symbol-change and derive `blocked` from it. Replace the one-way `onBlock` with `onToggleBlock`, which `DELETE`s when already blocked (no confirmation — restorative) or shows a `window.confirm()` dialog before `POST`ing to block (per user request: confirm before every block). Button is never `disabled`; label reads "Block"/"Unblock" from the real state.
- **Keywords:** Block button, HOD Momo blocklist, disabled button, unblock, onToggleBlock, TickerDetailContent, quote panel, window.confirm

## 2026-07-14 — Catalyst rows always showed "unknown" source tier

- **Symptom:** Every row on the Catalysts tab classified `source_tier` as `unknown`/`none` and `confirmed_by_official` as `False`, even for headlines from official wires like Business Wire/PR Newswire, and the frontend had no way to show the reader where a catalyst headline actually came from.
- **Cause:** `_run_news_catalyst_scan()` in `backend/main.py` built `symbol_to_article` from the Alpaca `/v1beta1/news` response but only kept `created_at`/`headline`/`url` — it dropped the article's `source` field entirely. Downstream, `enrich_catalyst_row()` (`backend/news/enrich.py`) and the ticker-detail fallback path in `_gather_context()` (`backend/routes/news.py`) both hardcoded `"source": ""` when constructing the article dict passed into `evaluate_news_impact()`, so `classify_source_tier()` had nothing to classify beyond headline/URL keyword matches.
- **Fix:** Capture `article.get("source", "")` into `symbol_to_article` and thread it through as `catalyst_source` on each catalyst row; `enrich_catalyst_row()` and `_gather_context()` now read `row.get("catalyst_source")` instead of a literal `""`. Also added `news/sources.py::best_source_name()` and a new `source_name`/`headline_url` field on `NewsImpactVerdict` so the frontend can show the literal publisher name (not just the tier bucket) next to every headline, in both the Catalysts tab and the quote panel's `NewsImpactPanel`.
- **Keywords:** source_tier, confirmed_by_official, catalyst_source, enrich_catalyst_row, _gather_context, _run_news_catalyst_scan, best_source_name, NewsImpactVerdict, classify_source_tier

## 2026-07-13 — Stock View double-click lost to layout re-render

- **Symptom:** Double-clicking a ticker in Electron did not open Stock View in a new window (Quote Panel updated; no child window). Direct `novaDesktop.openStockView` IPC worked.
- **Cause:** Native `dblclick` requires both clicks on the same target. The first click called `setSelectedSymbol`, re-rendering the row / shifting layout so the second click was not paired as a double-click. Synthetic `dblclick` events still worked, which hid the bug in earlier checks.
- **Fix:** Replace `onDoubleClick` with timed click pairing (`createClickVsDoubleClick`, `SYMBOL_DOUBLE_CLICK_MS`). Second click within the window opens Stock View; single click selects after the delay. Electron child window `show()`/`focus()` after load.
- **Keywords:** Stock View, double-click, dblclick, layout shift, SymbolSelectButton, SelectableTableRow, clickVsDoubleClick, Quote Panel

## 2026-07-13 — Stock View double-click stayed in the same window

- **Symptom:** Double-clicking a ticker (Electron desktop) did not open a new window; Stock View replaced the scanner in the current window.
- **Cause:** `window.open(url, '_blank', 'noopener,noreferrer')` returns `null` when `noopener` is set (by design). `openStockView` treated null as "popup blocked" and called `setStockViewSymbol`, navigating the current tab. Electron also needs an explicit BrowserWindow path — `window.open` alone is unreliable without a trusted IPC open.
- **Fix:** Drop `noopener` from `window.open` (still clear `win.opener` after open). Add `novaDesktop.openStockView(url)` IPC → main creates a child `BrowserWindow`. Prefer IPC when running in the desktop shell.
- **Keywords:** Stock View, double-click, window.open null, noopener, Electron setWindowOpenHandler, nova:openStockView, same window fallback

## 2026-07-13 — LVLU Open 0 / wrong split date on quote card

- **Symptom:** LVLU side panel showed Open `0`, High/Low equal to a stale Previous Close, and Recent Split `1:15` with a calendar day that did not match the Nasdaq trading-effective date (Jul 7, 2025).
- **Cause:** (1) IBKR discovery snapshots omit session OHLC; when a feed sent `0` or the UI formatted a zero open, `fmtPrice(0)` painted `$0.00`. (2) `recent_split` used `datetime.fromtimestamp(epoch)` in the local timezone, so Yahoo’s UTC-midnight epoch for LVLU became `2025-07-06` in US/Eastern.
- **Fix:** Extracted fundamentals to `backend/fundamentals.py` with UTC `_yf_date_str` / `format_recent_split`. Coerce non-positive O/H/L to null in Alpaca `_bar` and IBKR snapshot. Frontend `fmtSessionPrice` / `sessionPriceOrNull` show "—" for missing OHLC.
- **Keywords:** LVLU, Open 0, fmtSessionPrice, recent_split, lastSplitDate, yfinance UTC, OHLC missing, IBKR discovery

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
