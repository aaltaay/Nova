# 2026-08-31 — IBKR session watchdog: self-heal a frozen dialer

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed (IBKR connection lifecycle)
- **Related:** `CHANGELOG.md` 2026-08-31 -- IBKR session self-heals from a frozen dialer · `PROBLEM_LOG.md` 2026-08-31 -- IBKR session frozen 7h · `DEFERRED_LOG.md` D-008 (unrelated pre-existing test failures found while verifying)

## Task

User reported: "im clicking this and still not attaching itself properly. whats going on? we fixed this a billion time" -- Trading prerequisites showed "log into IB Gateway" and clicking "Open live Gateway" did nothing, while the attached screenshot showed IB Gateway itself healthy and logged in (green "API Client: connected").

## Goal

Find why the session was actually stuck (not guess), then make it so this class of freeze (a) recovers on its own without a click, and (b) the click is never a no-op even if recovery is somehow incomplete.

## Why it mattered

The user was blocked from trading at 7:27am, ~2 hours before the open, and this was reported as a recurring problem ("we fixed this a billion times") -- meaning prior fixes patched symptoms of this same class without closing the actual gap: nothing outside the dialer task could tell the dialer itself had died.

## What we changed

- New `backend/ibkr/session_watchdog.py` -- independent sibling IB-loop task (spawned via `loop_supervisor.spawn_ib`, next to `observability.ib_loop_lag`). Two checks every 5s: stuck-unusable-with-transport-up (moved out of `session_reconnect.handle_transport_up_unusable`), and dead/frozen dialer via a new heartbeat (`session_reconnect.dialer_heartbeat_age_sec()`, stamped at the top of every `_reconnect_once`).
- `backend/ibkr/client.py`: `reconnect_task()` / `restart_reconnect_task()` accessors so the watchdog can inspect and respawn the dialer; `session_snapshot()` gained `earn_in_flight` / `ib_cold_inflight` / `dialer_alive` / `dialer_heartbeat_age_sec`.
- `backend/ibkr/ib_scheduler.py`: `cold_slot()` lock acquire now bounded by `IBKR_COLD_SLOT_ACQUIRE_TIMEOUT_SEC` (20s), raising `ColdSlotTimeout` instead of awaiting forever.
- `backend/ibkr/session_usable.py`: `earn_usable()`'s warm-up phase wrapped in an overall `IBKR_EARN_USABLE_TIMEOUT_SEC` (45s) deadline; aborts (does not promote to READY) on timeout.
- `backend/routes/trading.py`: `/api/ibkr/status` exposes the same new diagnostics; `/api/ibkr/launch-gateway` checks `is_ready()` after an `already_listening` result and calls `force_reconnect()` (`action: "rebuild_session"`) instead of leaving the button a no-op.
- `frontend/src/ibkr/tradingPrerequisites.ts`: `gatewayPortOpenButSessionDown()` no longer requires `ibkrTransportConnected !== true` -- the port being open is sufficient once the caller already knows `!connected`. Detail line now surfaces `session_state`.
- `frontend/src/ibkr/TradingPrerequisitesGate.tsx`: `onLaunchGateway` now calls `refreshIbkrStatusNow()` immediately (previously waited up to 5s for the next poll).
- New constants in `backend/constants_ibkr.py`: `IBKR_SESSION_WATCHDOG_INTERVAL_SEC`, `IBKR_DIALER_HEARTBEAT_STALE_SEC`, `IBKR_COLD_SLOT_ACQUIRE_TIMEOUT_SEC`, `IBKR_EARN_USABLE_TIMEOUT_SEC`.

## How it works now

The dialer (`session_reconnect.reconnect_loop`) is the only task that ever mutates the IB session, but it is no longer the only thing that can *notice* it is broken. A sibling task on the same IB loop -- proven to survive a frozen dialer because the loop-lag sampler is exactly this shape and kept ticking through the whole 7-hour freeze -- polls two independent signals every 5s and, on either one, discards the current `IB()` object, resets session state to disconnected, and (for a dead/frozen dialer) cancels and respawns the dialer task itself. Two of the awaits that could freeze the dialer (a cold-work lock acquire, and the overall warm-up phase) are now bounded on top of their existing per-request timeouts, so most freezes never even reach the watchdog's threshold. The Gateway launch button no longer trusts "port is open" as proof that Nova's side is fine -- it checks Nova's own readiness and rebuilds the session when it is not.

## Why this approach

The old design put the stuck-unusable timer *inside* `session_reconnect.handle_transport_up_unusable` -- the same task doing the connecting. That is structurally unable to fire once that task is the thing that's frozen, no matter how the timeout constant is tuned. The alternative of only adding more inner timeouts (bounding `cold_slot` and `earn_usable`, which we also did) does not cover the case where the freeze is inside `ib_async` itself and does not honor `Task.cancel()` -- a real possibility here, since `py-spy` showed the IB-loop OS thread genuinely idle (not blocked in a syscall), meaning the stuck coroutine was parked on an asyncio-level Future that never got set or cancelled cleanly. Only a task-level supervisor (cancel the whole `Task`, not just an inner `await`) is guaranteed to recover regardless of which layer actually froze. We deliberately did not try to diagnose *which* await was stuck at runtime -- a fresh `IB()` object plus a fresh dialer task is the one remedy correct under every hypothesis, and it never touches the Gateway process itself (no risk to a real 2FA session in flight). Rejected: adding a client-side auto-restart of the whole API process on a stuck session -- too blunt (loses in-memory HOD/scanner state) when a scoped IBKR-only reset is sufficient and faster.

## Verification

- `py -3 -m pytest -q` (backend, full suite): 1446/1447 passed; the 1 failure is pre-existing and unrelated (see DEFERRED_LOG D-008), confirmed via `git status --porcelain` showing zero local changes to that test's files.
- New/updated tests: `test_ibkr_session_watchdog.py` (9), `test_ibkr_session_usable.py` (3), `test_ibkr_cold_queue.py` (+2), `test_ibkr_client_readiness.py` (+2, 1 rewritten), `test_routes_trading.py` (+4).
- `ruff check` clean on every touched backend file.
- `npx vitest run src/ibkr` (frontend): 215/215 passed, including a new regression test reproducing the exact incident state (`transport_connected=true`, `preferred_port_reachable=true`, `connected=false`).
- `npx tsc --noEmit` and `npm run build`: clean.
- Live: captured a `py-spy` stack dump of the frozen process (PID 25544) before restarting, confirming the IB-loop thread was idle rather than blocked. Restarted the API with the new code; `/readyz` reached `state: ready`, and `/api/ibkr/status` / `/readyz` both report `dialer_heartbeat_age_sec` in the low single digits against the live Gateway session.

## Follow-ups

None blocking. A future session could add a light integration test that actually starts `loop_supervisor` + a fake dialer task and lets `session_watchdog.run()` execute for a few iterations against a real event loop, rather than calling `_check_stuck_unusable` / `_check_dialer_heartbeat` directly -- current tests validate the decision logic but not the `spawn_ib` wiring end-to-end (that wiring was instead verified live, once, on this real restart).

## Keywords

IBKR session frozen, earn_usable, cold_slot, session_watchdog, dialer heartbeat, reqCompletedOrdersAsync, py-spy, already_listening, rebuild_session, gatewayPortOpenButSessionDown, Trading prerequisites, ADR 010
