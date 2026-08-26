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

- Consider moving `IBKR_TAPE_LINGER_SEC` / `IBKR_TAPE_RESUBSCRIBE_GUARD_SEC` out of `tape_stream.py` module-locals into `constants_ibkr.py` (per `centralized-constants.mdc`), matching `IBKR_DEPTH_RELEASE_GRACE_SEC`'s facade-read pattern so tests can keep monkeypatching them.

## Addendum (same session) -- Level 2 depth given the same fan-out fix, preemptively

The "Follow-ups" section above originally named `ibkr/depth/state.py` as unreopened, unproven scope creep. The user explicitly asked to fix it anyway, immediately, rather than wait for a real report -- so it was done in the same session while the pattern was fresh.

**What changed:** `backend/ibkr/depth/state.py`, `backend/ibkr/depth/stream.py`, `backend/ibkr/depth/__init__.py`, `backend/routes/trading.py` (`ws_depth`), plus `backend/tests/test_depth_stability.py`, `backend/tests/test_ibkr_depth_state.py`, `backend/tests/test_ibkr_safety.py`.

**Scope difference from tape:** depth only needed the fan-out half of the fix. Its `release_when_idle` already re-checks `viewer_count` inline (synchronously, in the closing connection's own `finally`, not a fire-and-forget background task like tape's linger) before releasing, and `subscribe_async` already serializes through one global `get_subscribe_lock()`. Neither of tape's first two bugs (linger-cancels-a-watched-line, unserialized concurrent subscribe) existed in depth. Only the single-shared-`_queues[symbol]`-per-symbol competing-consumer defect was identical, and got the identical fix: `_viewer_queues: dict[str, list[asyncio.Queue]]`, `open_viewer_queue`/`close_viewer_queue`, `push_book` broadcasting to every registered queue, `stream()` taking a queue directly instead of a symbol. `has_queue` renamed `is_subscribed` (now backed by `_subscriptions`, decoupled from queue lifecycle) since queues no longer exist at subscribe time.

**Deliberately not touched:** `evict_for_capacity`'s force-eviction path (in `subscribe.py`) can silently kill an active viewer's depth line to free a slot at `IBKR_MAX_DEPTH_SYMBOLS` cap, with no notification to that viewer -- an orthogonal, pre-existing behavior unrelated to the fan-out bug. Not in scope for this pass; named here so it isn't rediscovered as a surprise.

**Verification:** `pytest backend/tests/test_depth_stability.py backend/tests/test_ibkr_depth_state.py backend/tests/test_ibkr_safety.py` (47 passed) + full backend suite (1343 passed). Live: restarted the local API with IB Gateway connected live; opened two concurrent WebSocket viewers to `/ws/ibkr/depth/DAIC`, held both open 15s -- both received an identical 15 book updates each (not a competing split), confirming fan-out.

## Follow-ups (updated)

- (Resolved below.) `evict_for_capacity`'s force-eviction of a "busy" (non-idle) depth slot at cap previously had no notification to the orphaned viewer.

## Addendum 2 (same session) -- Depth cap eviction notification + a test-isolation bug found while fixing it

Asked directly: "did you see other clear bugs?" Two, both found by inspection immediately after the depth fan-out fix, in the same files just touched -- not from a broader audit.

**Bug A -- silent eviction:** `evict_for_capacity`'s force-evict branch (`ibkr/depth/subscribe.py`) picks a victim by `others[0]` when no idle slot exists, on the assumption its `viewer_count` is a "possible leak." That's a guess, not a guarantee. If it was a real, active viewer, their line died with zero notification -- same failure shape as the tape freeze, just via a different trigger (capacity pressure instead of a StrictMode race).

**Fix A:** Extracted `push_book`'s broadcast loop into a shared `_broadcast(symbol, payload)` in `state.py`; added `push_error(symbol, message, evicted=True)` on top of it. `evict_for_capacity` calls it before `unsubscribe()` in the force-evict branch only (the idle branch has no live viewer to notify by definition). `ws_depth`'s message loop previously wrapped every non-heartbeat queue item as `{"type": "book", "data": item}` unconditionally -- it now checks `item.get("type") == "error"` first (a plain book dict has no `"type"` key, so this is backward compatible), forwards the error, and closes the socket when `evicted` is set so the frontend's existing reconnect backoff takes over.

**Bug B -- test cross-contamination:** Writing a regression test for Bug A (`test_force_evict_notifies_any_open_viewer_queue`) initially failed intermittently on *which* symbol got evicted, depending on test execution order within `TestDepthCap`. Root cause: `importlib.reload(depth_mod)` in `setup_method` only re-executes the **facade** module (`ibkr/depth/__init__.py`); `ibkr.depth.state`'s module-level dicts are a separately-loaded module already sitting in `sys.modules`, never re-executed by that reload, so `_subscriptions`/`_ws_viewers`/`_viewer_queues` silently persisted and accumulated across every test method in five of six classes in `test_ibkr_safety.py`. One class (`TestSmartDepthFlag`) already had the fix, with a comment noting "Import-time reset was removed (Phase 2)" -- it was never propagated to the other five when that removal happened.

**Fix B:** Added `depth_mod.reset_all()` to all five affected `setup_method`s (one `StrReplace` with `replace_all`, since the code block was byte-identical across all five).

**Why this approach:** Reused the exact `_broadcast` pattern from the tape/depth fan-out fix rather than inventing a new notification mechanism -- one shape for "tell every viewer queue something happened," used for both normal book pushes and out-of-band eviction/error notices. For Bug B, fixed the root cause (missing `reset_all()`) rather than just hardcoding my new test to tolerate any victim -- test order-dependency in a shared-state test class is a real bug that will bite the next person who adds a test to that file, not just a quirk of my one test.

**What was deliberately not done:** No broader audit of the rest of the codebase for similar test-isolation gaps was performed -- this fix is scoped to the one file and six classes actually touched this session. If a similar pattern exists elsewhere (any `setup_method` that reloads a facade module without resetting its backing submodule state), it wasn't searched for here.

**Verification:** New `test_force_evict_notifies_any_open_viewer_queue`; full `tests/test_ibkr_safety.py` (34 passed, order-independent now); full backend suite (1353 passed). Live: restarted the local API with IB Gateway connected live; confirmed normal single-viewer `/ws/ibkr/depth/DAIC` still streams book updates correctly through the restructured message loop (no regression from the `item.get("type")` branch added to `ws_depth`).

## Follow-ups (updated again)

- No further known gaps from this session. Scope was: tape freeze (linger + fan-out), afterhours crash, pytest sys.path, depth fan-out (preemptive), depth eviction notification + test isolation (found on inspection, not audit).

## Keywords

time and sales stuck, tape frozen, IBKR_TAPE_LINGER_SEC, StrictMode double-mount, competing consumers, single shared queue, fan-out, viewer_count, afterhours reprice, apply_quote failed, gap_percent None, ADR 010, pytest sys.path, Level 2 depth, push_book, open_viewer_queue, has_queue, is_subscribed, preemptive fix, evict_for_capacity, force-evict, push_error, importlib.reload does not reset submodules, test isolation, TestDepthCap
