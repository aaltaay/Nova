# 2026-08-25 — Time & Sales freeze: linger + single-queue fan-out fix

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed (IBKR tape / Time & Sales)
- **Related:** `CHANGELOG.md` 2026-08-25 "Time & Sales no longer freezes..." · `PROBLEM_LOG.md` 2026-08-25 (tape freeze, afterhours crash, pytest cwd-dependent import)

## Task

User reported: "time and sale is stuck... it is just not moving." Diagnose and fix why the IBKR Time & Sales tape freezes for an open Trader tab.

## Goal

The tape for an open symbol keeps printing indefinitely; a StrictMode double-mount (or any transient double-viewer moment) must never silently kill the line or drop prints for the surviving viewer. Prove it with live evidence against the running API and IB Gateway, not just unit tests.

## Why it mattered

A frozen tape with a green "LIVE" badge is worse than an honestly-broken one -- the operator trusts stale prices/prints while trading. `single-market-data-feed.mdc` explicitly requires failing loud, not quiet, for exactly this reason.

## What we changed

- `backend/ibkr/tape_stream.py`:
  - `_schedule_linger`'s deferred release re-checks `viewer_count(symbol) > 0` before cancelling the IB subscription (mirrors depth's `release_when_idle`).
  - `ws_viewer_opened` cancels any pending linger, covering the reattach path that skips `subscribe_async` entirely.
  - `subscribe_async` serializes per symbol via `asyncio.Lock` so two racing callers can't both attach a handler.
  - Queue model changed from one shared `asyncio.Queue` per symbol to one queue per *viewer* (`open_viewer_queue` / `close_viewer_queue`); `_push_queue` broadcasts to every registered queue.
  - `_release_subscription` broadcasts a `{"type":"error","released":true}` notice to any still-open viewer.
- `backend/routes/trading.py`: `ws_tape` now opens/closes its own per-connection queue, passes it to `stream(queue)`, and closes the socket when it sees a `released` notice.
- `backend/afterhours_discovery.py`: `reprice_afterhours_rows_ibkr`'s sort key maps `gap_percent is None` to `-inf` instead of raising `TypeError` when comparing unpriced rows.
- `backend/tests/test_ibkr_tape_stream.py` (+ two archive test files touching the same internals), `backend/tests/test_afterhours_discovery.py`: new/updated regression tests.
- `backend/tests/test_execution_latency_regressions.py`: fixed a `sys.path` gap so the test passes regardless of pytest's invocation directory (found while running the full suite for this change).

## How it works now

Each open `/ws/ibkr/tape/{symbol}` connection owns exactly one `asyncio.Queue`, registered in `_viewer_queues[symbol]` for the life of that connection. Every IB tick-by-tick print (`_push_queue`) fans out to every queue in that list -- viewers no longer compete for a single reader. The 16s "linger" (kept so a fast remount reuses the live IB line instead of hitting IB's 15s same-instrument resubscribe guard) only actually tears down the line if, 16 seconds later, `viewer_count(symbol)` is still zero; a reattach in that window cancels the pending release outright. If the line does get released while a queue is still open (should not happen in the normal flow, but is now handled instead of silently orphaning), that viewer's queue gets a `released` notice, its socket closes, and the frontend's existing WebSocket backoff reconnects it cleanly.

Separately (found live, not by design): `ibkr/scanner_l1.py`'s `apply_l1_quote` calls into `afterhours_discovery.reprice_afterhours_rows_ibkr` on every quote tick; that function's sort crashed the moment any afterhours row was a name-only admission (`price=None`, `gap_percent=None` per ADR 010) sitting next to a priced row. Fixed with a `None`-safe sort key.

## Why this approach

- **Re-check viewer count instead of removing the linger:** the linger exists for a real reason (IB's 15s same-instrument `reqTickByTickData` guard -- PROBLEM_LOG 2026-07 "Resubscribing in 10s"). Removing it would reopen that older bug. Depth already solved the identical race with `release_when_idle`; copying that shape kept the fix minimal and consistent with existing precedent instead of inventing a new mechanism.
- **Per-viewer queues over a single broadcast object:** considered keeping one shared queue and just fixing the linger, but a live soak against the running API proved that alone is insufficient -- 1,902 archived prints during a 24s window delivered zero to the surviving viewer, because the discarded socket's server-side task kept winning the race to drain the queue and then failed to actually send (its own transport was already closed). A single-consumer queue cannot serve N readers correctly; per-viewer queues are the standard fix and match how a pub/sub fan-out is normally built. Rejected alternative: a `asyncio.Condition`-based broadcast primitive shared across viewers -- more moving parts for the same result once each viewer already needs its own bounded queue for backpressure/drop-oldest anyway.
- **Left `ibkr/depth/state.py` untouched despite the identical shape:** depth's queue holds full book *snapshots*, where a dropped intermediate update is superseded by the next one (much lower severity than tape's append-only, non-supersedable prints), and it has not been reported as frozen. Fixing it now would be scope creep on an unproven symptom in a shared, safety-sensitive module (`single-market-data-feed.mdc` L2 rules) -- named as a follow-up instead of silently rewritten alongside tape.
- **Fixed the afterhours crash and the pytest cwd bug in the same session:** both were discovered directly in the verification path for the primary fix (the crash was spamming the very log being read to confirm the tape fix; the pytest failure blocked running the full suite from `backend/`). Per repo convention ("fix bugs you see on your way"), both got root-caused and regression-tested rather than skipped or logged as "pre-existing, ignored" again.

## Verification

- `pytest backend/tests/test_ibkr_tape_stream.py backend/tests/test_ibkr_tape_side.py backend/tests/test_archive_capture.py backend/tests/test_archive_write_queue.py backend/tests/test_depth_stability.py backend/tests/test_ibkr_safety.py backend/tests/test_afterhours_discovery.py backend/tests/test_execution_latency_regressions.py` -- all passed.
- Full backend suite from `backend/`: 1342 passed (0 failed).
- `npm run build` (frontend): clean, unrelated to this change.
- Live, with IB Gateway connected in `live` mode: restarted the local API twice (once per fix layer) and, using a raw WebSocket client against the running `/ws/ibkr/tape/DAIC`, reproduced the exact StrictMode double-mount race (open socket A, open socket B, close A immediately, hold B open 24s spanning the 16s linger mark):
  - Pre-linger-fix baseline (reproduced from `blast.log` timestamps): `unsubscribed DAIC` exactly 16.0s after the double-subscribe, archive `tape_ibkr` shows zero prints for any symbol after that timestamp.
  - Post-linger-fix, pre-fan-out-fix: line survived (no `unsubscribed`), but B received 0 of 1,902 archived DAIC prints during the window -- proved the second bug.
  - Post-fan-out-fix: B received 1,148 prints matching the archive's concurrently-recorded count for the same window, zero errors, socket stayed open throughout.
  - Afterhours crash: confirmed present (`apply_quote failed for DAIC`, `TypeError` in `afterhours_discovery.py:112`) before the fix, and absent across 20+ minutes of continuous afterhours L1 ticks after restarting with the fix in place.

## Follow-ups

- `ibkr/depth/state.py` has the same single-queue-per-symbol shape as tape's pre-fix design. Not reopened here (see Why this approach) -- give it a dedicated pass if multi-viewer Level 2 delivery is ever reported stale.
- Consider moving `IBKR_TAPE_LINGER_SEC` / `IBKR_TAPE_RESUBSCRIBE_GUARD_SEC` out of `tape_stream.py` module-locals into `constants_ibkr.py` (per `centralized-constants.mdc`), matching `IBKR_DEPTH_RELEASE_GRACE_SEC`'s facade-read pattern so tests can keep monkeypatching them.

## Keywords

time and sales stuck, tape frozen, IBKR_TAPE_LINGER_SEC, StrictMode double-mount, competing consumers, single shared queue, fan-out, viewer_count, afterhours reprice, apply_quote failed, gap_percent None, ADR 010, pytest sys.path
