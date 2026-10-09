# Data schema: Performance recorder

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/perf/, backend/gc_policy/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Performance recorder (ADR 026)

Owner `backend/perf/`; always on, read-only (it measures, never throttles or
sheds). One **sample** per second, in memory for `PERF_RING_SEC` (1800 s):

`{schema_version: 1, ts, interval_sec, process: {cpu_pct: number | null,
threads}, loops: {ib | http: {cpu_pct: number | null, delay_max_ms: number |
null, stalled: boolean}}, ops: {NAME: {calls, busy_ms}}, gauges: {NAME:
number}, gc: {collections: [gen0, gen1, gen2], pause_ms, max_pause_ms}}` --
`cpu_pct` is CPU time over wall time (100 = one core; `process` covers every
thread, which share one GIL); `delay_max_ms` is the longest a 50 ms watchdog
callback waited on that loop in the interval (`null` before the watcher runs);
`ops` are the interval's deltas of `op_metrics` operations that ran (a sync
op's `busy_ms` is time on its thread, an async `ws.*` op's is fan-out wall
time; operations nest); `gauges` are queue depths and cumulative drop counters
(`*.dropped` never decreases in a process). A loop whose callback waited more
than `PERF_STALL_MS` is **stalled**; its **stall report** is `{schema_version:
1, id: "<started_ms>-<loop>", loop, started_ts, ended_ts, duration_ms,
samples, truncated, top_frame: string | null, stacks: [{count, frames:
["path:line function", ...]}], before: sample[], after: sample[]}` -- frames
outermost first, `top_frame` the most-sampled innermost frame inside the repo,
`before` / `after` the samples 30 s either side. A **stall summary** is the
report without `stacks` / `before` / `after`, plus `file: string | null`.

`POST /api/perf/client` takes one window's 5 s report (at most
`PERF_CLIENT_MAX_BODY_BYTES`; the sample desk never sends): `{schema_version:
1, window_id, role: "main" | "popout" | "browser" | "electron", visible:
boolean | null, interval_sec, ui_tag: string | null, frames: {count, slow,
p95_ms} | null, long_frames: {count, blocking_ms, max_ms, top: [{source,
invoker, ms}]} | null, sockets: {NAME: {messages, bytes}}, renders: {NAME:
count}, heap_mb: number | null, dom_nodes: number | null, processes: [{type,
window_id, pid, cpu_pct, working_set_mb}] | null, logical_cpus: number |
null}` -- `frames` counts animation frames while visible (`slow` >
`PERF_SLOW_FRAME_MS`), `null` while hidden; `dom_nodes` is the page's element
count (`getElementsByTagName('*')`); `processes` and `logical_cpus` only from
the Electron main process. A process's `cpu_pct` is % of one core (100 = one
core, as in a sample): Electron's `percentCPUUsage` is a share of all logical
CPUs, so the report multiplies it by `logical_cpus` (2026-10-09: a renderer at
112% of one core read 5 on the 24-thread desk PC). A report without
`logical_cpus` (desks before that change, or a machine whose count could not be
read) carries Electron's share unchanged, and `tools/perf_report.py` marks it.
The server stamps `received_ts` and answers `{ok: true}`.

`GET /api/perf/live?seconds=N` (default 300) -> `{schema_version, generated_at,
recorder: {running, since, dir, write_dropped, stall_files_skipped,
write_error}, samples[],
stalls: summary[], clients: {window_id: report}}`. `GET /api/perf/stalls` ->
`{schema_version, stalls: summary[]}` (this process, newest first); `GET
/api/perf/stalls/{id}` -> the report (404 unknown). Kept under
`<cache_dir>/perf/`: `YYYY-MM-DD.jsonl` (Eastern date), one JSON object per
line with `schema_version` and `kind: "sample" | "client" | "stall" | "heap" |
"ib_notice" | "tape_silence"` -- a
`sample` line aggregates `PERF_PERSIST_EVERY_SEC` (5) seconds (ops and gc
summed, `cpu_pct` averaged, `delay_max_ms` maxed, gauges last); an `ib_notice`
line is one IBKR farm or line notice and a `tape_silence` line one tape line
turning dead or silent, both shaped in `architecture/schema/market-data.md`
("When one tape line goes silent", #722), kept here because they outlive the
API log -- and
`stalls/<id>.json`; both removed after `PERF_RETENTION_DAYS`. A reader skips
and counts a line of unknown `schema_version`, never guesses. `/api/diagnostics`
adds group `performance` (rows `perf_process_cpu`, `perf_ib_loop`,
`perf_http_loop`, `perf_stalls`, `perf_queues`, `perf_windows`,
`perf_handlers`; one `unknown` row while the recorder has no samples).

**The longest stalls keep their stacks (#619).** The hourly full-report cap keeps
the longest `PERF_STALL_FILES_PER_HOUR` stalls, rather than the first ones. A
strictly longer report replaces the shortest kept report; ties keep the earlier
report. Replaced files are removed by the writer, and live summaries' `file`
fields follow the retained set (null after eviction). Ordinary day summaries
remain. The cap is per report's start hour, with bounded current/previous-hour
bookkeeping; a late report outside that window is counted and declined. GC
thresholds, startup freezing and trading behavior are unchanged.

**L1 timestamp evidence (#667).** With the existing performance recorder on,
`perf/l1_timestamps.py` queues the L1 updates delivered to quote listeners and
price-setting AllLast facts; a bounded off-loop drain writes
`<perf>/l1_timestamps/YYYY-MM-DD.jsonl`. Each line is `{schema_version: 1,
kind: "l1_timestamp", symbol, instance, price, price_ts, arrival_ts,
last_timestamp, rt_time, seed, quote_quality, native_price_received,
timestamp_receipt: {tick_type: 45 | 88, stamp, received_at, with_price} | null,
tape_candidates: [{price, exchange_ts, arrival_ts, delta_sec}],
candidates_truncated}`. Native wrapper callbacks establish receipt: cached
`ticker.ticks` cannot say whether a string tick arrived. `with_price` means a
native last tick and timestamp receipt were in the same dispatch, never a seed.
Nearby same-price prints are candidates, not proof they are the same trade.
Correlation requires the same IB instance and recent arrival times; bounded
rings, queue, rate and per-day file size count omissions in perf gauges. Files
follow `PERF_RETENTION_DAYS` retention and unknown schema versions are refused
by readers. Missing receipt/correlation stays null/empty. Evidence never
changes trigger age, minute bucketing, warm-up protection or the sampled-L1
source; #667 still needs recorded-market diagnosis before those decisions.

**Heap census (#619).** A full (gen-2) garbage collection stops every thread
while it walks every tracked object. On 2026-09-29 the backend ran about one a
minute all day, and the median one took ~430 ms; only ~60 ms of that was
imported code. The census says what the rest is (owner `perf/heap.py`):

`GET /api/perf/heap` -> `{schema_version: 1, generated_at, elapsed_ms, tracked,
allocated_blocks, gc: {thresholds, counts, frozen, stats}, process:
{private_bytes, working_set_bytes, peak_working_set_bytes, page_faults},
types: [{type, count}], holders: [{name, kind, items, nested_items}], cached}`.

- **`tracked`** counts the objects the collector walks. `types` are the most
  common, at most `PERF_HEAP_TOP`. `allocated_blocks` is
  `sys.getallocatedblocks()`. After the freeze below, the frozen objects are
  not walked and not counted here; `gc.frozen` counts them.
- **`process`** is the OS's figures. A field is null where the platform does
  not report it: on Linux only the peak and the page faults.
- **`holders`** are the backend's biggest containers, each counted once:
  - its modules' globals;
  - the containers on module-level objects (a state singleton's dicts) and on
    its classes, named `module.name.attr`;
  - its `lru_cache`s (`kind: "lru_cache"`, `items` the cache's size).

  `nested_items` sums the containers one level down, and the containers on the
  objects there, reading at most `PERF_HEAP_SCAN_CAP` values.

Taking a census walks the heap too, so it pauses the process about as long as
one full collection. Two things limit it:
- The route answers the last census (`cached: true`) while it is younger than
  `PERF_HEAP_MIN_GAP_SEC`.
- The recorder takes one `PERF_HEAP_FIRST_AFTER_SEC` after it starts, then every
  `PERF_HEAP_EVERY_SEC`, never in `PERF_HEAP_QUIET_ET` (09:25-09:45) on a
  weekday.

Every census taken, scheduled or asked for, is written to the day file as `kind: "heap"`.

**GC policy (#619, owner `gc_policy/`).** The first census on the live backend (2026-09-29,
minutes after a start) found 732,138 tracked objects in 7,037 modules; the objects were mostly
code, classes and module state. 1,434 of those modules were torch and transformers, imported by
the FinBERT warm-up, which failed on every start on the desk.
- **FinBERT is off** unless `NOVA_NEWS_SENTIMENT=1`; its label reads `unavailable`, as it
  already did.
- **The heap is frozen once.** `GC_FREEZE_AFTER_SEC` after start, the backend collects what is
  garbage and freezes everything still alive (`gc.freeze()`), so full collections walk only what
  was created since. A frozen object is still freed when nothing refers to it; one that later
  dies in a reference cycle is never reclaimed. That leak is bounded, since the freeze runs once
  per process. `NOVA_GC_FREEZE=0` turns it off.

