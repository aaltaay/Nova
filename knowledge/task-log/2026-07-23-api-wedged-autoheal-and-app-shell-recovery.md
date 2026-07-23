# 2026-07-23 — API_WEDGED dedicated scan pool + auto-heal + app-shell auto-recover

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed (backend scan pool) | docs/frontend (auto-heal, app-shell recovery)
- **Related:** `CHANGELOG.md` §2026-07-23 "Prevent API_WEDGED", "Auto-heal API_WEDGED / API_DOWN", "App shell auto-recover on provider/context crashes" · `PROBLEM_LOG.md` §2026-07-23 "API_WEDGED: health timeout, Start API was click-only" and "useWorkspace outside WorkspaceProvider"

## Task

Three back-to-back incident-response fixes from the same outage arc: (1) `/api/health` timing out while scan_loop's IBKR bridge waits saturated asyncio's default thread pool ("API_WEDGED"), (2) the only recovery being a manual "Start API" click, and (3) a separate Vite-HMR context-skew crash (`useWorkspace must be used within WorkspaceProvider`) leaving users on a dead Retry screen.

## Goal

Health checks stay responsive under scanner load; the UI recovers from a WEDGED/DOWN API and from a fatal provider/hook crash without requiring a manual reload.

## Why it mattered

Users saw a header stuck on `API_WEDGED`/`API_DOWN` or a blank crashed shell with no automatic path back, even though the underlying process was often recoverable (a restart, or a reload past a stale HMR module graph) — every occurrence cost a manual intervention instead of self-healing.

## What we changed

- `backend/scan_executor.py` (new): dedicated `ThreadPoolExecutor` (2 workers) for `scan_loop`'s blocking IBKR/Alpaca calls, separate from asyncio's default executor that `/api/health` (and other `async def` routes) implicitly share.
- `backend/scan_loop.py`: every `loop.run_in_executor(None, ...)` call switched to `loop.run_in_executor(scan_pool, ...)`.
- `frontend/src/utils/backendAutoHeal.ts` (new) + `BackendStartButton.tsx`: `maybeAutoHealBackend()` fires `startLocalApi()` automatically the first time the header flag is `API_WEDGED`/`API_DOWN` in a browser session (dev/Electron only — no spawn path in prod web), gated by a `sessionStorage` flag so it can only try once per session.
- `frontend/src/components/AppErrorBoundary.tsx` + `appErrorRecovery.ts` (new): classifies fatal shell errors (`useWorkspace must be used within…`, invalid hook call) and triggers one hard `window.location.reload()` via a `sessionStorage` guard; non-fatal errors still soft-remount via a `key` bump. `App.tsx` adds an outer `app-shell` boundary around `<AppShell />` so provider-level failures that a page-level boundary never sees are still caught.
- `backend/tests/test_scan_executor.py`, `frontend/src/utils/backendAutoHeal.test.ts`, `frontend/src/components/appErrorRecovery.test.ts`, `frontend/src/components/AppErrorBoundary.test.tsx` (all new).

## How it works now

`/api/health` (and `/livez`/`/readyz` added later the same day) never blocks on the same executor `scan_loop` uses for `run_in_executor(None, ...)` work, so a slow/hung IBKR bridge call cannot itself make liveness probes time out. If the header still diagnoses `API_WEDGED` or `API_DOWN`, `BackendStartButton` auto-calls the existing manual "Start API" path exactly once per session; the manual button remains for retries. Separately, `AppErrorBoundary` distinguishes "fatal" shell-identity errors from ordinary render errors: fatal → one automatic full reload with a `sessionStorage` guard against reload loops (second occurrence falls back to a manual "Reload Nova" button); anything else → soft retry via remount key.

## Why this approach

- **Dedicated pool over `asyncio.to_thread`/one-off fixes:** a named, bounded (2-worker) executor keeps scan work from starving *any* default-pool consumer (health today, anything else tomorrow) without changing the blocking call sites themselves — the alternative (making every IBKR call natively async) is the larger `IbkrRuntime` rewrite explicitly deferred by the later lifecycle-hardening plan.
- **Auto-heal is session-once, not a retry loop:** an unconditional auto-restart-on-every-poll would fight a legitimate `uvicorn --reload` cycle or mask a real crash loop; one attempt per session plus the still-present manual button keeps a human in the loop if the first auto-heal doesn't stick.
- **Reload over "smarter" HMR recovery:** the root cause (Vite duplicating a context module across HMR boundaries) is a dev-time class of bug with no clean runtime fix from inside React; a guarded one-shot reload is the correct backstop rather than trying to detect and patch the specific module-duplication case.
- **Rejected:** teaching `AppErrorBoundary` to distinguish *which* context/provider failed and selectively remount just that subtree — too fragile against the actual failure mode (duplicated module identity), and a full reload is cheap and already guarded against looping.

## Verification

- `py -3 -m pytest backend/tests/test_scan_executor.py -q`
- `npx vitest run` (includes `backendAutoHeal.test.ts`, `appErrorRecovery.test.ts`, `AppErrorBoundary.test.tsx`)
- Full combined regression re-run this session: backend `py -3 -m pytest` (893 passed, 1 pre-existing unrelated flaky failure in `test_hod_momo_universe.py`), frontend `npx vitest run` (434/434) and `npm run build`.

## Follow-ups

- The later same-day `api_ibkr_lifecycle_hardening_24083047.plan.md` work (session-state machine, cancellable bridge, single restart supervisor) builds on top of this and further tightens `useScannerData.ts` with a consecutive-failure grace count so a normal reload blip can no longer arm auto-heal mid-restart.
- No further action planned unless loop-lag/readiness telemetry (from the later hardening pass) shows the scan pool itself becoming a bottleneck.

## Keywords

API_WEDGED, API_DOWN, scan_executor, ThreadPoolExecutor, auto-heal, maybeAutoHealBackend, AppErrorBoundary, useWorkspace, WorkspaceProvider, HMR context skew, sessionStorage guard, one-shot reload
