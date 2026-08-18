# 2026-08-18 — IB loop wedge: synchronous archive SQLite writes on the market-data loop

- **Status:** completed (wedge); chart pacing defect named and deferred
- **Agents:** parent
- **Domain:** market-feed / archive
- **Related:** `CHANGELOG.md` 2026-08-18 (archive writes moved off the IB event loop) · `PROBLEM_LOG.md` 2026-08-18 (IB loop wedged 67s) · ADR 010 (IB loop isolation), ADR 012 (local-first chart bars)

## Task

The desk showed a red Trading prerequisites banner: "Nova API (:8000) -- IB loop wedged -- desk blocked. Do not restart the API from this banner." Diagnose why the IB connect-loop was wedged, name the occupying call, and unwedge it by stopping the occupying work -- explicitly **not** by killing the process. Then re-check whether chart live tips resume.

## Goal

Done meant: hard evidence of what call occupied the IB loop (not a hypothesis), a root-cause fix in the correct module, `ib_loop_lag_ms.wedged` back to false under real tape load, and an honest answer on whether charts recovered.

## Why it mattered

The banner blocked a live trading desk during market hours while IB Gateway was connected and READY. Every user-visible freeze this session -- Gainers prices, quote header, chart live tips -- traced to the same starved loop, so the earlier scanner L1 subscription fix could not have been sufficient on its own. Worse, the failure mode is invisible from the HTTP side: uvicorn answered `/api/mode` in 11ms while market data was 45-67 seconds late, so ordinary health checks look green while the desk is blind.

## What we changed

- **New `backend/archive/write_queue.py`** — bounded in-memory deques for tape prints, L1 ticks, and 1m/1d bars, plus a batched writer (`drain_once`, `flush_blocking`, `drain_loop`).
- **`backend/ibkr/tape_stream.py`** — `_on_tape_update` now calls `enqueue_tape_print` and `on_tape_print(..., queued=True)` instead of writing SQLite inside the IB socket callback.
- **`backend/ibkr_bridge.py`** — `_archive_l1_tick` enqueues instead of calling `record_l1_tick`.
- **`backend/archive/bar_builder.py`** — `on_tape_print` / `_flush` take `queued`; the live minute rollover enqueues, offline backfill and rollup keep the direct write.
- **`backend/app_lifespan.py`** — spawns the `archive.write_queue` drain task.
- **`backend/constants_archive_news.py`** — `ARCHIVE_WRITE_QUEUE_MAX`, `ARCHIVE_WRITE_BATCH_MAX`, `ARCHIVE_WRITE_FLUSH_SEC`.
- **Tests** — new `backend/tests/test_archive_write_queue.py`; `test_archive_capture.py`'s tape hook test now pins "enqueue, never write" instead of the old blocking write.

## How it works now

Invariant: **nothing reached from an `ib_async` callback may touch SQLite.** The IB loop is where `reqMktData` L1 ticks, depth, and tape are delivered (ADR 010), so any blocking call there is a market-data outage for the whole desk, not a slow write.

Producers (`enqueue_tape_print`, `enqueue_l1_tick`, `enqueue_bar`) append to bounded deques and hold the lock only for the append -- never across disk I/O. One drain task on the HTTP loop pops batches every second and does the SQLite work in `asyncio.to_thread`, so neither loop blocks: one connection, `executemany`, one commit per batch, and integrity counters bumped once per batch by delta rather than once per row. At the 100,000-row cap the longest queue sheds its oldest row and counts it under `tape_dropped`, so a disk stall degrades visibly instead of growing RAM without bound or wedging the loop again.

`record_tape_print` / `record_l1_tick` / `record_bar` still exist and still write directly. They are the offline path (backfill, rollup, tests) where the caller reads rows back immediately, which is why the live/offline split is a `queued` flag rather than a rewrite of `capture.py`.

## Why this approach

The decisive step was refusing to guess. Three plausible theories were on the table -- `reqHistoricalData` pacing, chart fill storms, and my own soak probes -- and the repo already documented the tool that settles it (`requirements-dev.txt`: `py-spy dump --pid <nova-api-pid>`). Eight of eight stack samples put the IB loop in `archive/capture.py`, which killed all three theories at once. Without that dump the obvious move was another pacing tweak, which would have changed nothing.

Rejected alternatives:

- **Restart the API.** Explicitly forbidden, and correctly so: loop starve is not a dead process. A restart would have cleared the symptom for minutes and destroyed the evidence, and the wedge would have returned on the next high-volume runner. (The one restart in this task came *after* the patch existed, to load it -- not as the remedy.)
- **Disable tape archiving.** Fastest unwedge, but it trades a data-integrity guarantee (Nova OS P6 loss-aware capture) for a latency problem that has a correct fix.
- **Reuse one long-lived connection instead of `get_connection()` per call.** Removes the connect + 3 PRAGMAs but leaves an INSERT and a `commit` (an fsync-class operation) on the IB loop per print. That is a constant-factor win on a path that must be O(0) on that loop. It also silently changes `archive/db.py` semantics for every other caller.
- **`asyncio.to_thread` at each call site.** Non-blocking, but it spawns a thread hop and a transaction per print -- thousands per second under load -- and SQLite writer contention would then serialise them anyway. Batching is what actually makes the work cheap; the queue is what makes it non-blocking.
- **Unbounded queue.** Simpler, but converts a disk stall into unbounded memory growth with no signal. The bound plus a drop counter keeps the failure loud, matching the archive module's existing "non-fatal for live UI, never silent" policy.

Bounding the queue by total rows across all four streams (shedding the *longest* queue) means one noisy tape symbol cannot evict another stream's rows -- a per-queue cap would let tape volume alone decide what L1 history survives.

## Verification

- `py -3 -m pytest backend/tests/test_archive_write_queue.py backend/tests/test_archive_capture.py -q` — 21 passed.
- `py -3 -m pytest backend/tests -q -k "archive or tape or bar_builder or bars or l2 or lifespan or loop_lag"` — 177 passed.
- Red-first evidence: producer tests assert **zero** SQLite connections opened while enqueueing 500 prints / 250 ticks; the drain test asserts 50 prints + 20 ticks cost exactly **one** connection (previously 140); overflow test asserts oldest-dropped and `tape_dropped == 4`.
- Live before: `ib_loop_lag_ms` `last 45,094ms -> 48,453ms`, `max 67,091ms`, `wedged=true`, `high_streak 17 -> 35`, while `http_loop_lag_ms.last_ms` was 11.2ms and `/api/ibkr/status` reported `connected: true`, `session_state: ready`.
- Live after: `last 6.1ms`, `max 120ms`, `wedged=false`, `high_streak 0`.
- Under load (`.tmp/wedge_load.py`, 8,515 tape prints across PFSA/IPST/AIXC/CAST in 150s, ~57 prints/sec): IB lag stayed in the 0.6-15.9ms band across 25 consecutive samples, never wedged.
- `py-spy dump` after: IB loop idle in `select()` on 6/6 samples (0/8 before).
- Archive integrity intact: `tape_ibkr` +28 and `l1_ticks` +97 rows in 20s, counters advancing, `tape_dropped` unset.

## Follow-ups

- **Charts are only partly recovered — separate defect, not fixed here.** The unwedge was necessary but not sufficient, and the sequence is worth keeping:
  - While the pacing debt was outstanding (15:27-15:29), `/api/ticker/CAST/bars` returned 10Sec `bars=0` and 1Min five minutes behind wall clock, `filling=True`, and the log shed every fill: `historical fill shed CAST 1Min: pacing wait 297.6s` decaying ~1s/s with no sends.
  - Once the debt drained (15:34), the fill landed: 10Sec `bars=0 -> 1441`, `complete_through=19:33:00Z`, `filling=False`. That fill never completed while the loop was wedged.
  - But the right edge then **stopped advancing**: at both 15:34 and 15:35 the 10Sec and 1Min last bar stayed `19:33:00Z` while the wall clock moved on, with `filling=True` again — the next fills were shed by pacing.
  - So the pane's lag equals "time since the last fill that pacing allowed." Root cause is IBKR historical pacing budget, where `priority=open_chart` is shed on the same terms as `priority=background` HOD surge seeds, so the pane the operator is looking at loses to background work. The fix is a pacing-budget reservation (or strict priority preemption) for `open_chart`, plus a live-append/`bars_patch` path for 10Sec so the tip does not depend on a refetch at all. Not another sleep.
- Some of this session's pacing debt was self-inflicted: the chart soak probes (`bars_check.py`, `tf_soak.py`, `tensec_poll.py`, `chart_soak.mjs`) each scheduled `open_chart` fills. That inflated the debt but did not create the wedge — the wedge predates those probes and is fully explained by the tape write path.
- `archive/db.get_connection()` still opens a connection and re-runs three PRAGMAs per call. Now that the hot path batches, this is only a cold-path cost, but any future per-event caller will reintroduce the same class of bug. Consider making that cost explicit in the function's docstring or gating it behind a "cold path only" helper.
- Worth a maintainer sweep: grep for other `record_*` archive calls reachable from `ib_async` callbacks before they become the next wedge.

## Keywords

IB loop wedged, ib_loop_lag_ms, API_WEDGED, desk blocked, py-spy dump, record_tape_print, bump_counter, sqlite on event loop, tcpDataProcessed, tape_stream, record_l1_tick, archive write queue, batched writes, reqMktData starved, ADR 010, historical pacing debt, open_chart priority, charts frozen
