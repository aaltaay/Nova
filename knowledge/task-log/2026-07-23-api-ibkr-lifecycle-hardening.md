# 2026-07-23 — API/IBKR lifecycle hardening: readiness, cancellation, single supervisor

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops / market-feed (backend lifecycle) + general (frontend dev-launcher)
- **Related:** `CHANGELOG.md` "API/IBKR lifecycle hardening…" (2026-07-23) · `PROBLEM_LOG.md` "API restart cascade…" (2026-07-23) · plan `api_ibkr_lifecycle_hardening_24083047.plan.md`

## Task

User asked why Nova's API kept restarting during a dev session, then asked for a root-cause investigation of the resulting `TimeoutError`, then explicitly asked to implement the attached remediation plan (`api_ibkr_lifecycle_hardening_24083047.plan.md`) end to end, working through its five pre-created todos without stopping.

## Goal

1. Correct the prior (disproven) incident diagnosis and add real telemetry instead of inference.
2. Make IBKR readiness explicit so no consumer can act on a half-initialized broker session.
3. Make the sync→async IBKR bridge cancel on timeout and reject stale-session results.
4. Replace arbitrary port-killing dev restarts with one locked, ownership-aware supervisor.
5. Verify the above with automated tests plus a live smoke check.

## Why it mattered

The original PROBLEM_LOG entry blamed a shared thread pool between `/api/health` and `scan_loop` — false, since Starlette/AnyIO and asyncio use separate pools. Meanwhile two real defects were live: `ibkr.client.get_ib()` handed out the IB instance the instant the socket connected, before account-kind validation or cache warm-up finished, so 19+ background tasks could act on a half-ready session; and `run_coro()` never cancelled a timed-out bridge future, so stale coroutines kept running against an old session after a reconnect. Separately, the dev restart path could kill any process on :8000 with no lock, which is how `WinError 10048` happened when auto-heal raced a manual restart.

## What we changed

- **`backend/ibkr/session_state.py` (new):** 5-state machine (`DISCONNECTED/CONNECTING/SYNCHRONIZING/READY/DEGRADED`) plus a monotonic generation counter bumped on every transition into `READY`.
- **`backend/ibkr/client.py`:** `get_ib()` now returns the client only when `is_ready()` (session `READY` *and* socket connected) — added `is_ready()`, `current_generation()`, `session_snapshot()`. `run_coro()` cancels its `run_coroutine_threadsafe` future on timeout and raises the new `StaleIbkrSessionError` if the generation changed mid-call. `reconnect_loop()` drives the state machine and passes the freshly-connected `_ib` directly into warm-up calls (bypassing the very gate those calls exist to satisfy).
- **`backend/ibkr/account.py`:** `refresh_positions_cache()` / `refresh_completed_orders_cache()` accept an optional `ib` to avoid a `get_ib()` deadlock during warm-up.
- **`backend/ibkr/discovery.py`:** local `asyncio.wait_for` timeouts around `reqScannerDataAsync` (`IBKR_SCAN_REQUEST_TIMEOUT_SEC`) and the batch `qualifyContractsAsync` inside `snapshot_quotes()` (new `IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC`) — same wedge pattern `ibkr/ticks.py` already guarded for single-symbol L1 qualify, now closed on the discovery/table-reprice batch path too.
- **`backend/ibkr_bridge.py`:** `run_ibkr()` now forwards its `label` into `run_coro()` so cancellation/staleness logs are attributable per caller.
- **`backend/instance_identity.py`, `backend/loop_lag.py` (new):** per-process instance id/PID/reload-flag and an event-loop-lag sampler.
- **`backend/app_lifespan.py`:** waits on `is_ready()` (not raw socket) before declaring IBKR bootstrap-connected; spawns the loop-lag sampler; exposes `is_bootstrap_complete()`.
- **`backend/routes/health.py`:** `/api/health` now includes `loop_lag_ms` + instance identity; new `/livez` (pure liveness, no IBKR/cache dependency) and `/readyz` (bootstrap + IBKR session snapshot, 503 until bootstrap-complete).
- **`frontend/scripts/vite-nova-start-api.ts`:** file-based cross-process lock (`acquireLock`/`releaseLock`, staleness-aware) so a concurrent restart request gets HTTP 409 instead of racing `Stop-NovaPorts`/`Start-NovaApi`; restart success now requires HTTP 200 + valid JSON + a genuinely *new* `instance_id`.
- **`frontend/electron/sidecar.mjs`:** same HTTP-200-plus-schema tightening for the Electron sidecar's health wait.
- **`scripts/Stop-NovaPorts.ps1`:** `Test-NovaOwnedProcess` inspects the process command line before killing; only Nova-owned (`run_api.py`/`uvicorn`/`vite`) or unverifiable processes on Nova's dedicated dev ports get force-stopped — anything else is left alone with a loud warning.
- **`frontend/src/hooks/useScannerData.ts` + `frontend/src/constantGroups/chart_api.ts`:** new `SCANNER_HEALTH_FAIL_GRACE_COUNT` — the scanner poll now requires 2 *consecutive* fetch failures before flipping health to disconnected/WEDGED, so a single missed poll during a normal `uvicorn --reload` blip can no longer arm `BackendStartButton`'s auto-heal and fight the reload.
- Corrected the disproven shared-thread-pool comment in `backend/constants_scanner.py`.
- New/updated tests: `test_ibkr_session_state.py`, `test_ibkr_client_readiness.py`, `test_instance_identity.py`, `test_routes_health_live_ready.py`, additions to `test_ibkr_account.py` and `test_ibkr_discovery_fail_loud.py`, and `frontend/scripts/vite-nova-start-api.test.ts`.

## How it works now

`ibkr.client.get_ib()` is the single choke point every consumer (`discovery`, `account`, `orders`, `ticks`, `depth`, `tape_stream`, `bars`, `listing_flags`, `executor`) already null-checks — it now only returns non-`None` once Nova's own session state (not the raw socket) says `READY`. Every `READY` transition bumps a generation counter; `run_coro()` captures that generation before bridging a coroutine onto the IBKR event loop from a worker thread and raises `StaleIbkrSessionError` if a reconnect happened before the result came back, and it cancels the future outright on timeout instead of abandoning it. `/livez` never touches IBKR/cache state so it can't hang; `/readyz` reports bootstrap completion plus the live IBKR session snapshot without gating on the broker (an Alpaca-only or intentionally-disabled broker must not block process readiness). The Vite dev launcher's file lock plus the frontend's 2-consecutive-failure grace period together mean a normal `uvicorn --reload` blip no longer looks identical to a genuine hang and no longer triggers a competing restart.

## Why this approach

- **Readiness gate at `get_ib()`, not at every call site:** every consumer already null-checked `get_ib()` and failed loud/no-op'd on `None` (a pre-existing pattern from "disconnected" handling). Tightening the *meaning* of that single function's return value gave every consumer the fix for free instead of touching a dozen files individually.
- **Generation counter instead of cancelling every in-flight coroutine on disconnect:** simpler and race-free — the counter can only increase, so a stale comparison never un-stales itself, and callers already have a natural checkpoint (`run_coro`'s return) to check it.
- **File lock + strict instance-id check over a full explicit state-machine enum:** the plan asked for `healthy → stopping → stopped → starting → healthy` coalescing; a disk lock achieves the same effect (second POST gets 409, so at most one restart in flight) with far less surface area, and it works across separate Vite processes, not just within one.
- **Client-side consecutive-failure grace period over a backend "reloading" flag:** a `RELOADING` signal from the backend itself is unavailable *during* the reload (the process is briefly not answering at all), so the only place that can absorb a WatchFiles blip is the poller that already tolerates transient misses — 2 consecutive failures (5–10s of real wall time at current poll intervals) comfortably covers a normal reload without meaningfully delaying real-outage detection.
- **Deferred: full `IbkrRuntime` actor rewrite.** The plan's explicit scope boundary defers this unless the new loop-lag/readiness telemetry keeps showing contention — premature given the readiness/cancellation fixes above address the two *confirmed* defects directly.

## Verification

- Backend: `py -3 -m pytest` — 892/893 passed (one pre-existing, unrelated failure in `test_hod_momo_universe.py::test_build_focus_universe_empty_inputs`, confirmed to fail identically on `master` in isolation with none of this session's files touched — local cache-file state pollution, not caused or fixed here).
- Frontend: `npx vitest run` — 434/434 passed across 103 files; `npm run build` (tsc -b + vite build) clean.
- Live smoke test against the developer's already-running, Gateway-connected dev API (non-destructive — did not restart it): `GET /livez`, `/readyz` (`ibkr.state="ready"`, `generation=1`, `mode="live"`), and `/api/health` (`loop_lag_ms.max_ms` showed real ~20s contention concurrent with this session's own heavy pytest/npm runs on the same machine — the telemetry correctly surfaced it instead of hiding it).
- Deliberately **not** performed (would have disrupted the user's live connected Gateway session): firing concurrent restart POSTs against the running Vite server, a full WatchFiles rapid-write soak, and Electron-packaged load testing. The lock/grace-period logic is covered at the unit level instead (`vite-nova-start-api.test.ts`'s `acquireLock`/`releaseLock` coalescing tests).

## Follow-ups

- Run the deferred live-only checks (concurrent restart race, WatchFiles soak, Electron no-reload load test) in a session where disrupting the active Gateway connection is acceptable.
- The unrelated `test_hod_momo_universe.py` failure should get its own PROBLEM_LOG entry if a future session tracks down the cache-file pollution source.
- If loop-lag telemetry keeps showing sustained (non-test-induced) contention in normal operation, escalate to the plan's deferred `IbkrRuntime` actor phase.

## Keywords

API_WEDGED, hot reload, WatchFiles, WinError 10048, ibkr session readiness, run_coro cancellation, stale generation, StaleIbkrSessionError, instance_id, loop_lag, livez, readyz, single supervisor lock, qualifyContractsAsync timeout, SCANNER_HEALTH_FAIL_GRACE_COUNT
