# 2026-08-14 -- ADR 010 IB loop isolation (runtime)

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` 2026-08-14 -- ADR 010 IB loop isolation (runtime) · `PROBLEM_LOG.md` 2026-08-14 -- API_WEDGED mid-trade

## Task

Ship the long-term IB loop isolation so a seed/enrichment/chart burst cannot time out HTTP probes or auto-kill a live trading PID.

## Goal

HTTP liveness stays up during IB cold work. IB lag is visible and blocks the desk. WEDGED never calls `startLocalApi`. One scheduler replaces three IB locks.

## Why it mattered

08:14 ET the desk flashed CRITICAL / Auto-restarting while PID 40232 still listened. Mid-trade kill of a wedged-but-alive API is worse than a slow IB loop.

## What we changed

- `loop_supervisor`: dedicated IB thread; `on_ib` / `call_on_ib` / `publish_to_http` / `assert_ib_loop`.
- `client.startup` + reconnect run on that loop; `run_coro` targets it; circuit-break keys off IB lag.
- Dual lag on `/api/health` and `/api/mode`.
- `ib_scheduler` replaces `historical_gate` + snapshot lock + completed-orders lock; snapshot batch=5.
- Execute `_lock` released before `send_broker`.
- Auto-heal `API_DOWN` only; prerequisites false when `ib_loop_lag.wedged`.
- HOD `hod_surge_buffer` warn on dropped seeds.

## How it works now

One process, one clientId, two loops. `ib.*` on the connect-loop. HTTP handlers yield via `on_ib`. Cold work is single-flight and droppable when a chart is interactive. A slow IB loop blocks trading honestly and never kills the process.

## Why this approach

Two OS processes / second clientId rejected (ADR 001, Gateway slot). Timeout-only rejected (hides the banner). Feature flag rejected (half-migrated `_loop`). In-flight historical waits one request (Gateway will not cancel cleanly). Task 4 shipped in the same slice after isolation so cutover cannot auto-kill.

## Verification

- `pytest` supervisor + cold-queue + historical_gate + health + client readiness + execution + integrity (focused; 68 then 100 then 7).
- Vitest `backendAutoHeal` + `tradingPrerequisites` + `startLocalApi` -- 14 passed.

## Follow-ups

Confirm live `/livez` p99 after the running API reloads this code. Do not treat a GIL hitch on `/livez` as auto-heal.

## Keywords

ADR 010, loop_supervisor, ib_scheduler, on_ib, API_WEDGED, auto-heal, ib_loop_lag
