# 2026-08-14 -- Premarket API_WEDGED soak (loop starve, not a restart)

- **Status:** in progress (soak running; first incident diagnosed)
- **Agents:** parent
- **Domain:** market-feed / ibkr-ops (continuity only this session; no specialist hop)
- **Related:** `PROBLEM_LOG.md` §2026-08-14 -- Premarket API_WEDGED banner · prior API_WEDGED 2026-07-23 / 2026-07-29 / 2026-07-30

## Task

User saw Trading prerequisites "Nova API CRITICAL / Auto-restarting API" with no action. Asked to investigate by soaking -- wait for the next fire and work from data, not a quick guess.

## Goal

Name what actually restarts (or does not), what starves `/api/health`, and keep a 1Hz external record through the rest of the session.

## Why it mattered

A false or real API kill mid-premarket blanks scanners, charts, and the order path. The banner looks like a crash. Killing a live IB session to "heal" a slow loop is worse than a stale chip.

## What we changed

- No product code this turn.
- External soak: `C:\Users\aalta\.nova\soak\soak_api_wedge.py` (outside `backend/` so `--reload` cannot see it).
- Incident notes: `C:\Users\aalta\.nova\soak\incident-2026-08-14-0816.md`.

## How it works now

The banner is a **client diagnosis**. `GlobalBarStatusBridge` polls `/api/mode` every 5s with a 4s abort and **no grace count**. One miss calls `diagnoseBackend` (`/api/health`, 2.5s). Timeout => `API_WEDGED` => `BackendStartButton` auto-heals once (kill :8000).

The 08:16 event was **not** a process restart. PID 40232 / instance `1866c7cd0078` stayed up from 06:05:57. `NOVA_API_RELOAD=1` but no WatchFiles lines. Port kept LISTENING while `/livez` and `/api/health` timed out at 8s (08:20:44). Same loop recovered by 08:21:41 (probes 2-30ms). `lag_max_ms` remains 50790.

Trigger burst on the shared uvicorn+ib_async loop (08:14:00-08:15:58):

1. HOD surge-seed sequential 1Min historicals for ~25 names.
2. HOD enrichment `run_ibkr(snapshot_quotes(40))` -- unlabeled `[ibkr]` 25s bridge.
3. Mass scanner `reqMktData` subscribe.
4. WETO Trader open: several bar timeframes + depth + tape.

Then `run_coro` timeouts stacked; `loop_lag` 7s / 30s / 50s; circuit breaker (`IBKR_RUN_CORO_MAX_INFLIGHT_WHEN_WEDGED=2`) only after streak 3 x 5s -- after the UI already armed a kill.

## Why this approach

Soak first. A code patch now (raise probe timeout, disable auto-heal, drop enrichment snapshots) would hide the next wave. Rejected restarting the API to "clear" the banner -- that would destroy the PID/instance evidence. Rejected blaming uvicorn `--reload` without WatchFiles lines. Rejected treating empty TOP_OPEN_PERC_GAIN as the root cause -- that log is a gappers-empty derive, an amplifier at most.

## Verification

- `GET /livez|/api/health|/api/mode|/readyz` at 08:20:44: all TimeoutError ~8s; netstat LISTENING 40232.
- Log extract: 2973 lag samples today in the tail window; 197 >= 2s; max 50790ms; 8 `run_coro` timeouts 08:15:58-08:19:34.
- Soak baseline 08:21:41+: same pid/instance, `reload=true`, health 2-30ms, `lag_wedged=false`, `lag_max_ms=50789.8`.

## Follow-ups

- Keep soak through RTH open. Do not click Start API / refresh the UI session if we want the next hang without an auto-kill (slot is session-once).
- Likely fix candidates after more waves: move HOD surge-seed and enrichment snapshots off the IB loop or serialize them; give `/mode` the same grace as scanner polls; do not auto-kill on a single 2.5s health miss while `loop_lag.wedged` is still false; open `run_coro` circuit earlier than streak 3.
- `auto_live` still NO-GO.

## Keywords

API_WEDGED, loop_lag, run_coro, HOD surge seed, snapshot_quotes, auto-heal, soak
