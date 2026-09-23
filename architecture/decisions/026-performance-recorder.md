# ADR 026 -- Performance recorder: who used the time, not only how late it was

**Status:** Accepted · **Date:** 2026-09-23
**Builds on:** [[010-ib-loop-isolation]] · [[021-desk-self-heal]]

## Context

The operator reports the desk turning laggy and jittery when the market bursts
(the open, a hot runner, several Trader tabs and pop-outs). Nova could say
*that* it was slow -- `loop_lag.py` samples each loop's lateness every 2 s,
`metrics/op_metrics.py` times HTTP routes and IBKR round trips, and the
execution ledger times every order stage -- but not *who* used the time or
how close each worker was to full.

The one freeze diagnosed properly (2026-08-18, the IB loop 67 s behind while
`/api/mode` answered in 11 ms) was found by a hand-run `py-spy dump`: two
SQLite writes per tape print on the IB loop. Nobody is at the desk with
`py-spy` ready when the next burst happens, and a code-read sweep on
2026-09-23 found a dozen plausible suspects on both sides (a per-tick sort of
the hour's volume history, per-tick file logging, a root React context
written on every Level 2 book, per-print React updates in every window) with
no way to rank them.

One constraint shapes the design: CPython runs Python code on one core at a
time (the GIL). ADR 010's two loops are separate threads, which protects each
from the other's **blocking** I/O but not from the other's **CPU** work. A
recorder that reports only per-loop numbers would hide that.

## Decision

An always-on, low-overhead recorder, owner `backend/perf/`, measuring
**utilization** (busy time), **saturation** (queue depth, callback delay) and
**errors** (drops) per worker -- plus the stack that was running whenever a
loop stalled.

1. **Loop CPU.** A coroutine on each loop reads `time.thread_time_ns()` once a
   second; the delta over wall time is that loop thread's CPU %.
   `time.process_time()` gives the whole process (100 = one core). No new
   dependency. Windows' thread clock ticks at ~15.6 ms, so a 1 s reading is
   good to about +/-2%.
2. **Stall catcher.** A daemon thread (`nova-perf-watch`) posts a no-op
   callback onto each loop every 50 ms and times how long it waits
   (`delay_max_ms` per second). When a callback has waited more than
   `PERF_STALL_MS` (200 ms) the loop is stalled: the watcher samples that
   thread's stack (`sys._current_frames()`) every 10 ms until the callback
   runs (cap 30 s), then folds the samples into counted stacks. This is the
   2026-08-18 `py-spy dump`, taken by the process itself at the moment it
   matters. It also catches blocking I/O, which uses no CPU and so never shows
   in (1).
3. **Handler busy time.** `op_metrics` keeps a running total per operation
   (additive `total_ms`), and the hot paths are wrapped with the existing
   timers: `ib.l1`, `ib.l1.scanner`, `volume_boost.observe`, `hod.on_trade`,
   `ib.depth`, `ib.tape`, `hod.save_highs`, `hod.save_alerts`, `l2.flush`,
   and the scanner socket fan-out `ws.scanner.broadcast` (with the HTTP
   routes the middleware already times). Operations nest (`ib.l1` includes
   the listeners it calls); the per-second `busy_ms` of a synchronous op is
   time on that thread, of an async `ws.*` op the wall time of the fan-out
   including waits on slow clients. The setup scanner engine is not timed
   yet (`setup_scanner/engine.py` is over the file-size limit and needs its
   own split first); its time still shows in the HTTP loop's CPU and in any
   stall stack.
4. **Gauges and drops.** Queue depths and drop counters read once a second:
   the archive write queue, the depth / tape viewer queues (their silent
   drop-oldest now counts), the setup scanner inbox, `run_coro` calls in
   flight, scanner socket clients, the L2 batch backlog.
5. **Garbage collection.** `gc.callbacks` time every collection per
   generation; a gen-2 pause freezes every thread and no other number shows it.
6. **The desk's windows report too.** Each window posts a 5 s summary to
   `POST /api/perf/client`: frame pacing while visible, long animation frames
   (Chromium's `long-animation-frame` entries name the script), messages and
   bytes per socket, render counts of the hot providers and pages, JS heap and
   DOM size. The Electron main process posts `app.getAppMetrics()` -- CPU and
   memory per window process. The sample desk sends nothing.
7. **Kept, bounded, off the loops.** One sample per second in memory (30 min).
   A writer thread (`nova-perf-writer`) appends a 5 s aggregate, every client
   report and every stall summary to `<cache_dir>/perf/YYYY-MM-DD.jsonl`
   (Eastern date), each line `schema_version: 1`; full stall reports, with 30 s
   of samples either side, go to `<cache_dir>/perf/stalls/<id>.json` (at most
   `PERF_STALL_FILES_PER_HOUR` an hour; the rest are counted). Files older than
   `PERF_RETENTION_DAYS` are removed at start and at day rollover; a day file
   stops taking samples and window reports past `PERF_DAY_FILE_MAX_MB`.
   Nothing is written from either loop.
8. **Surfaces.** `GET /api/perf/live`, `GET /api/perf/stalls[/{id}]`, a
   **Performance** group in `/api/diagnostics`, and `tools/perf_report.py`,
   which reads a day file and prints the worst minute, the busiest handlers,
   the stalls with their stacks, queue drops and per-window jank.

Thresholds (warn at 60% CPU, fail at 85%; warn at 5% slow frames) are first
guesses; the burst rig (phase 2) replaces them with measured limits.

## Consequences

- The recorder's own cost is budgeted at under 1% of IB-loop CPU at
  500 ticks/s; a test pins the per-call overhead of the timers (measured
  0.54 us a call on the operator's machine, against a 5 us budget).
- A stall inside C code that holds the GIL cannot be sampled until it lets go;
  the report still carries the full duration and the frame that called it.
- The stall's `top_frame` skips the recorder's own frames: a GC collection
  caught in progress shows `perf/gc_watch.py` in the stack, and the named line
  is the Nova code that triggered it.
- Production bundles keep function names (Rolldown `output.keepNames`; Vite 8
  ignores `esbuild.keepNames` in builds) so long-frame attribution names code.
  Measured cost: all JS +9.8% raw, +5.9% gzipped, loaded from local disk.
- Code-read suspects are not fixed here; they wait for a recorded open to rank
  them. The one exception is what the recorder measured on its first run
  (2026-09-23): `second_factor.current_state()` started PowerShell
  (`Get-Process ibgateway`, about 250 ms) **before** reading the IBC log, on
  the HTTP loop, on every `/api/ibkr/status` poll (every 5 s per window) and
  every `/api/diagnostics` read -- a quarter-second freeze of every socket the
  HTTP loop serves, several times each 5 s. The log now decides first; the
  process is checked only while the log shows an open 2FA prompt. Same answer
  in every case. A second measured stall -- `port_diagnostics.probe_port`,
  a synchronous TCP probe of both Gateway ports on the HTTP loop, up to 0.35 s
  each -- runs only while Nova is disconnected and is left to its own issue.

## Rejected

- **Continuous `py-spy record`** -- needs a separate process, admin rights on
  some machines, and produces flame graphs nobody reads after the open. Kept as
  the manual deep-dive tool.
- **asyncio debug mode / `slow_callback_duration`** -- slows every callback and
  names only the callback, not the line inside it.
- **psutil for per-thread CPU** -- a new dependency for what
  `thread_time_ns()` already answers from the thread itself.
- **React Profiler** -- a no-op in production builds; render counters plus
  long-frame attribution answer the same question in the build the operator
  runs.
