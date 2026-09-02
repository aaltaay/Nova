# 2026-09-02 -- HTTP ready before Sentry and cache restore

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-09-02 HTTP ready before Sentry · `PROBLEM_LOG.md` 2026-09-02 init_sentry blocked yield · `DEFERRED_LOG.md` D-006

## Task

Close D-006: daily start declared the API dead because `init_sentry` + cache/DB restore ran before FastAPI `yield`, so :8000 stayed dark for ~94s.

## Goal

`/livez` can answer as soon as uvicorn binds. Sentry, snapshot restore, and SQLite init run after that, off the HTTP event loop.

## Why it mattered

Daily start's health wait expired in that hole and painted Start API. A click then risks killing a live PID. The 2026-08-28 soak parked the patch because the operator API was `reload=true` after 09:30.

## What we changed

- `app_lifespan.lifespan` yields after sync tick/L1 wiring only.
- New `_local_startup()` (`init_sentry`, `_restore_caches`, `_init_databases`) runs via `asyncio.to_thread` at the top of `_bootstrap_runtime`.
- Logs per-step milliseconds (`sentry=` / `cache=` / `db=`).
- Regression: `backend/tests/test_app_lifespan_http_ready.py`.

## How it works now

HTTP listen is not gated on Sentry or disk. `/livez` is alive during local startup. `/readyz` stays 503 until `_bootstrap_complete` (network + loops). Cache/DB writes happen on a worker thread before IBKR dial; loops still start only after restore. Early scanner reads may see empty caches for those milliseconds -- empty at 04:00 is already the honest cold start.

## Why this approach

Yield-then-sync-on-the-loop would still freeze `/livez` for the Sentry RTT (67s on the soak). `asyncio.to_thread` is allowed here -- this is not `ib.*`. Keeping restore *before* IBKR/loops preserves the old invariant that HOD `load_state` and snapshot tables exist before background tasks read them. Rejected: leaving restore before yield (27s still dark). Rejected: a second "armed" readiness flag beyond existing `/readyz`.

## Verification

- `python3 -m pytest tests/test_app_lifespan_http_ready.py tests/test_app_lifespan_spawn.py tests/test_observability.py tests/test_routes_health_live_ready.py -q` -- 13 passed.
- Test proves yield while `init_sentry` is blocked, event loop still sleeps 50ms, then restore/db run, then `_mark_nova_api_health`.

## Follow-ups

Operator still needs `NOVA_API_RELOAD=0` on daily start (already the launcher default). This PR does not restart a live desk. D-005 (orphaned API lock) remains open.

## Keywords

D-006, init_sentry, lifespan yield, HTTP ready, to_thread, HealthWaitSec, /livez, /readyz
