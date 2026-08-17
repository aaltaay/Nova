# ADR 010 -- IB loop isolation (connect-loop + hot/cold scheduler)

**Status:** Accepted · **Date:** 2026-08-14
**Builds on:** [[001-modular-monolith]] · [[007-centralized-trading-execution]] · [[008-persistent-ibkr-scanner-rosters]] · [[009-short-entry]]
**Incident:** PROBLEM_LOG 2026-08-14 -- Premarket API_WEDGED banner

## Context

Nova runs IBKR (`ib_async`) on the same asyncio loop as uvicorn HTTP/WS. `ibkr.client.startup()` sets `_loop = asyncio.get_running_loop()` (uvicorn). Lifespan then piles HOD surge-seed historicals, enrichment `snapshot_quotes(40)`, scanner L1 subscribe, charts, integrity, and setups onto that loop.

On 2026-08-14 the Trading prerequisites banner showed **Nova API CRITICAL** / Auto-restarting API mid-premarket. Soak evidence:

- PID 40232 (`python3.13`) kept listening on `127.0.0.1:8000` from 06:05. The process did not die.
- 08:14-08:21: sequential 1Min historicals (~25 names) + unlabeled `run_ibkr(snapshot_quotes(40))` (25s) + mass `reqMktData` + WETO Trader open. `loop_lag` max 50790ms.
- 08:20: `/livez`, `/api/health`, `/api/mode`, `/readyz` all timed out at 8s while the port was LISTENING.
- UI: `GlobalBarStatusBridge` polls `/api/mode` every 5s with a 4s timeout and no grace. Miss -> `diagnoseBackend` (`/api/health`, 2.5s) -> `API_WEDGED` -> `maybeAutoHealBackend` -> `startLocalApi` (kill :8000).

A timeout/grace/auto-heal-only patch would hide the banner and still leave L1 and `placeOrder` on the starved loop. `run_in_executor` around seed already hops `run_coro` **back onto the same loop**, so a thread pool without moving `connectAsync` does not save HTTP.

## Decision

1. **One process, one `IBKR_CLIENT_ID`.** Stay a modular monolith (ADR 001). No second Gateway session. No microservices.

2. **Two event loops in that process.** HTTP/WS stay on uvicorn. All `ib.*` (await, sync `placeOrder`/`cancelOrder`/`reqMktData`/`reqScannerSubscription`, `ib.client.*`, event `+=`) run on a dedicated IB thread whose loop is the `connectAsync` loop. `ib_async` is **connect-loop-only**, not main-thread-only. Wrong-loop use is a hard error. Ban `asyncio.to_thread` around `ib.*` (today `execution/broker_send.py` already wraps `cancel_order_verified` that way).

3. **Cross-loop seam.** `on_ib` / `run_coro` hop HTTP -> IB. `publish_to_http` marshals callbacks. IB thread does not write scanner caches or Starlette/WebSocket objects. ADR 008 apply + `can_commit_roster` + `mark_live` run on the HTTP loop **after** the hop, and are re-fenced. L1 ticks stay lock-protected pending maps; uvicorn flushes at `IBKR_L1_BATCH_FLUSH_SEC` (not a hop per tick).

4. **Honest invariant.** HTTP liveness stays up during IB cold work. IB-loop latency is **bounded** by shrinking and preempting cold work -- not by pretending one Gateway socket can do 25s historicals and L1/acks at once. A slow IB loop blocks the desk honestly. It never auto-kills the process.

5. **`snapshot_quotes` is never HOT.** `scanner_hydrate.hydrate_rows` already calls `discovery.snapshot_quotes` -- the same 40-wide `reqTickersAsync` as HOD enrichment. New names wait for L1 `reqMktData` / tick-6. UI shows loading / empty price, not `0.00`, until the first L1 tick. Classification SSOT: `backend/ibkr/work_class.py`.

6. **One IB-loop scheduler replaces three locks.** Fold `historical_gate` + `discovery._snapshot_lock` + completed-orders lock. Do not add a fourth queue. Interactive chart preempts queued cold work. In-flight historical: wait out **that one** request (Gateway will not cancel cleanly mid-flight); drop the rest of the queue. Cold snapshot batch default: 5 (`IBKR_COLD_SNAPSHOT_BATCH`, Task 3). Orders never enter the scheduler. Mass L1 qualify stays single-flight and paced (`IBKR_L1_SUBSCRIBE_PACE_SEC`, `IBKR_L1_MAX_SUBSCRIBE_PER_RECONCILE`).

7. **Execution lock does not span the hop.** `execution.service` releases `_lock` after persist/validate; `place`/`cancel` hop with no lock held (ADR 007 path unchanged). `OrderWatch` Events live on the HTTP loop. Short-entry gates (ADR 009) unchanged. `auto_live` stays NO-GO.

8. **WEDGED is IB-loop SoT, not a uvicorn probe timeout.** `/livez` is a process pulse only (sync Starlette / AnyIO threadpool). `/api/health` publishes `http_loop_lag_ms` and `ib_loop_lag_ms`. Desk / trading prerequisites block when the IB loop is wedged even if HTTP is 5ms. `API_DOWN` (nothing listening) may spawn/restart. `API_WEDGED` never calls `startLocalApi` or Electron `restartApi`. Auto-heal demotion ships **after** isolation is proven -- it is not the product fix.

9. **HOD integrity matches the drop policy.** Dropped/deferred/`no_history` surge-seed is warn. Fail only for dead L1. Same commit as the scheduler drop policy (Task 3). No Alpaca bar/tick fallback when `discovery=ibkr`.

10. **No half-on feature flag.** Rollback is git revert + process restart. Do not implement Tasks 1-3 against `NOVA_API_RELOAD=1` during a live session.

## Consequences

- HTTP probes stop timing out because they no longer share a loop with `reqHistoricalDataAsync`.
- IB lag remains visible on the desk. A seed storm may still delay L1/acks for at most one in-flight cold request (~12-15s), not 25 sequential historicals.
- `work_class.classify` fails loud on unknown labels so Task 2 cannot silently skip a site.
- `/livez` can still stall briefly under the process GIL if `ib_async` decode is CPU-heavy (accepted P2). That is not auto-heal after Task 4.
- CI covers loop identity, classify, scheduler preempt, and auto-heal flags. Live soak is the only acceptance that seed-storm + place still works.

## Rejected alternatives

- Raise 2.5s / 4s probes or add grace only (hides the banner; leaves the starve).
- Two OS processes / second clientId (ADR 001, Gateway slot, split-brain state).
- `run_in_executor` around seed without moving `connectAsync` (today's shape).
- Disable surge-seed entirely (HOD Squeeze goes blind).
- Treat hydrate as HOT and `snapshot_quotes(40)` as COLD (contradiction; 08:14 was this burst).
- Alpaca bars/ticks for seed or charts when `discovery=ibkr`.
- A new global event bus.
- Feature-flag two-loop half-migration (worse than today: `_loop` identity split).

## Related

- `backend/ibkr/work_class.py` -- HOT/COLD SSOT (this ADR, Task 0)
- `backend/ibkr/loop_supervisor.py` -- IB thread (Task 1, not yet)
- `backend/ibkr/ib_scheduler.py` -- one cold scheduler (Task 3, not yet)
- `.cursor/rules/single-market-data-feed.mdc` -- two-loop + hot/cold rule
- `frontend/src/utils/backendAutoHeal.ts` -- WEDGED must not kill (Task 4)
- Soak notes: `C:\Users\aalta\.nova\soak\incident-2026-08-14-0816.md`

## Appendix -- `ib.*` inventory (Task 2 must empty this)

Every production touch. Tests omitted. Kind: await / sync / `ib.client.*` / event `+=` / `to_thread`.

| Site | Kind | Class | Notes |
|------|------|-------|-------|
| `ibkr/client_connect.py` `connectAsync` / `disconnect` | await / sync | HOT | Must live on IB thread. Task 1 ship-blocker. |
| `ibkr/client.py` `reqMarketDataType` / `disconnect` | sync | HOT | READY + delayed fallback. |
| `ibkr/client_ops.py` `disconnect` | sync | HOT | |
| `ibkr/session_reconnect.py` `disconnect` | sync | HOT | |
| `ibkr/session_errors.py` `errorEvent +=` | event | HOT | No IB **requests** from the handler (existing rule). |
| `ibkr/scanner_stream.py` `reqScannerSubscription` / `cancel*` / `updateEvent +=` / `ib.client.cancelScannerSubscription` | sync / client / event | HOT | `_on_batch` copies symbols only. Do not `mark_live` on IB thread. |
| `ibkr/ticks.py` `qualifyContractsAsync` / `reqMktData` / `cancelMktData` / `updateEvent +=` | await / sync / event | HOT | Qualify is single-flight + paced. |
| `ibkr/scanner_l1.py` | via ticks | HOT | Mass subscribe uses `IBKR_L1_MAX_SUBSCRIBE_PER_RECONCILE`. |
| `ibkr/depth/subscribe.py` `qualify` / `reqMktDepth` / `reqMktData` / `cancel*` | await / sync | HOT | |
| `ibkr/depth/handlers.py` `updateEvent +=` / `errorEvent +=` / `reqMktData` / `cancelMktDepth` | event / sync | HOT | |
| `ibkr/tape_stream.py` `qualify` / `reqTickByTickData` / `cancel*` / `updateEvent +=` / `errorEvent +=` | await / sync / event | HOT | |
| `ibkr/orders.py` `placeOrder` / `cancelOrder` / `openTrades` / `trades` | sync | HOT | |
| `execution/broker_send.py` `to_thread(cancel_order_verified)` | to_thread | HOT | Ban; hop `on_ib` instead. |
| `execution/telemetry.py` `orderStatusEvent` / `execDetailsEvent` / `errorEvent +=` | event | HOT | `OrderWatch` waiters on HTTP loop. |
| `execution/service.py` `get_ib` | lookup | -- | Release `_lock` before hop. |
| `ibkr/account.py` `positions` / `portfolio` | sync | HOT | Cheap cache read; still IB-loop. |
| `ibkr/account.py` `accountSummaryAsync` / `reqPositionsAsync` / `reqCompletedOrdersAsync` | await | COLD | Completed-orders lock folds into scheduler. |
| `ibkr/bars.py` `qualifyContractsAsync` / `reqHistoricalDataAsync` | await | COLD | Interactive preempts. |
| `ibkr/discovery.py` `reqScannerSubscription` (one-shot) / `errorEvent` / `cancel*` / `ib.client.*` / `wrapper.requests` | sync / client / event | COLD | One-shot path; persistent stream is authoritative. |
| `ibkr/discovery.py` `qualifyContractsAsync(*)` / `reqTickersAsync` | await | COLD | `snapshot_quotes`. Never HOT. |
| `ibkr/scanner_hydrate.py` | via snapshot_quotes | COLD | Roster commit after HTTP hop + re-fence. |
| `hod_momo_enrichment.py` `run_ibkr(snapshot_quotes)` | bridge | COLD | |
| `hod_momo_surge_seed.py` / `chart_bars.py` `run_coro` historicals | bridge | COLD | |
| `ibkr/reprice.py` `run_ibkr(snapshot_quotes)` / `run_in_executor` | bridge | COLD | |
| `ibkr/listing_flags.py` `qualify` / `reqContractDetailsAsync` / `reqMktData` tick 236 | await / sync | COLD qualify + HOT mkt data | Shortability line is a dedicated `reqMktData`; keep on IB loop. |
| `ticker_ibkr.py` `run_coro(snapshot_quotes)` | bridge | COLD | |
| `journal/ibkr_import.py` `ib.fills()` | sync | HOT | IB-loop read. |
| `strategy/executor.py` `ib.fills()` | sync | HOT | IB-loop read. |
| `scanner_runners/afterhours.py` `run_ibkr` | bridge | COLD | |
| `adapters/ibkr_scanner.py` `run_ibkr` | bridge | COLD | |
| `ibkr_bridge.py` `run_ibkr` -> `run_coro` | bridge | -- | Target loop becomes supervisor. |

Task 2 is not done until every row is either on the IB loop with `assert_ib_loop()` or deleted.
