# 2026-07-29 -- Fix cold-Gateway event-loop wedge

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed | ibkr-ops
- **Related:** `CHANGELOG.md` 2026-07-29 · `PROBLEM_LOG.md` 2026-07-29 API_WEDGED cold IBKR READY

## Task

The user pushed back on "throttle IBKR cold-start work" and asked for the **root cause** of why an IBKR reconnect floods the API until the event loop wedges, then to fix it.

## Goal

`/api/health` and `/livez` must stay responsive while IBKR snapshot/scanner calls time out on a cold Gateway; no more `API_WEDGED` every morning.

## Why it mattered

Every morning after Gateway login, the FastAPI loop wedged for a minute or more (`loop_lag` 3s -> 65s) so the app was unusable right when the user wanted to trade. It looked like "the API is down" but the process was alive -- a hard, recurring, user-visible failure.

## What we changed

- `backend/ibkr/discovery.py`: `snapshot_quotes` finally block now cancels the snapshot `reqMktData` lines it opened via new `_cancel_snapshot_tickers` (pops reqId from `wrapper.ticker2ReqId["snapshot"]` and sends `client.cancelMktData(reqId)`).
- `backend/ibkr/scanner_stream.py`: `in_ready_quiet_window()` true for `IBKR_SCANNER_WARMUP_QUIET_SEC` and until each desired table has a shadow roster batch.
- `backend/scan_loop.py`: `_ibkr_one_shot_paused()` defers one-shot discovery to the persistent stream during that window.
- `backend/constants_ibkr.py`: `IBKR_SCANNER_WARMUP_QUIET_SEC` = 120s (was proposed 20s).
- `backend/tests/test_ibkr_discovery_fail_loud.py`: new test asserting a snapshot timeout cancels the snapshot reqId.

## How it works now

Two invariants on a cold Gateway:

1. **No zombie snapshot reqIds.** Any snapshot batch that is timed out locally also has its IB-side `reqMktData` lines cancelled, so nothing keeps streaming onto the shared uvicorn loop after we gave up waiting. Snapshot tickers live under tickType `"snapshot"` -- plain `ib.cancelMktData` looks under `"mktData"` and no-ops, so the cancel must go through the `"snapshot"` map.
2. **One discovery owner while warming.** The ADR 008 persistent `scanner_stream` is the sole discovery owner after READY (for the quiet window and until its tables hydrate). One-shot `scan_loop` discovery defers, so a cold Gateway faces a single discovery pipeline instead of two racing ones.

## Why this approach

Root cause was two compounding defects, and both had to be fixed:

- The `wait_for` around `reqTickersAsync` cancelled only the *await*, not the IB-side subscriptions. That is the actual leak; throttling alone would never have fixed it. First attempt with `ib.cancelMktData(contract)` failed because ib_async registers snapshot tickers under the `"snapshot"` tickType, so the correct cancel is the direct `client.cancelMktData(reqId)` from the `"snapshot"` map. This is why the first live re-test still wedged.
- Throttling / a global IB work queue (the attached plan's step 3) was **rejected as unnecessary once the leak + dual-owner race were fixed.** The wedge came from unbounded zombie streams and two discovery pipelines racing, not from honest bounded concurrency. Adding a process-wide serializer would couple unrelated IB work and risk head-of-line blocking for interactive quotes for no benefit once the leak is closed.

## Verification

- `py -3 -m pytest backend/tests/` -- 1018 passed.
- Truly cold API restart: peak `loop_lag` 28.8ms, **0** `/api/health` timeouts over 150s (previously 60s+ wedge). `/api/gappers` 46 + `/api/movers` 50 rows, IBKR connected.

## Follow-ups

- The "global IB work queue" (attached plan step 3) is deliberately **not** built; keep as a documented fallback only if a genuinely different wedge reappears.
- If a future reconnect still spikes, check `loop_lag` + whether `_cancel_snapshot_tickers` found reqId 0 (would mean a new tickType or a different leak source).

## Keywords

API_WEDGED, loop_lag, cold start, IBKR READY, reqTickersAsync, cancelMktData, snapshot, zombie reqId, scanner_stream, one-shot discovery, event loop
