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
"ib_notice" | "tape_silence" | "tape_recovery" | "memory"` -- a
`sample` line aggregates `PERF_PERSIST_EVERY_SEC` (5) seconds (ops and gc
summed, `cpu_pct` averaged, `delay_max_ms` maxed, gauges last); an `ib_notice`
line is one IBKR farm, line or connectivity (1100 / 1101 / 1102, since 2026-10-14) notice, a
`tape_silence` line one tape line turning dead or silent, and a `tape_recovery` line one Reconnect
Data attempt (`sent`, then `verified`), all shaped in `architecture/schema/market-data.md`
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

**Memory watch (operator report 2026-10-11).** "nova keeps driving the ram higher and higher": the PC sat
at 72 of 80 GB committed, the API held 1.9 GB and the desk 1.3 GB, and nothing said whose the rest was (a
day-file reader under test in another session, 8.3 GB and growing, and other programs).
The sample's `working_set_mb` could not say either: Windows trims a working set under pressure, and the API's
read 211 MB while it held 1.9 GB. Owner `perf/memory_watch.py`, started with the recorder: 20 s after start,
then every `PERF_MEMORY_EVERY_SEC` (60 s), on a worker thread (a scan of ~500 processes takes ~100 ms), one
reading, written to the day file and kept for the `pc_memory` diagnostics row (`desk-ops.md`, "PC memory"):

`{kind: "memory", schema_version: 1, ts, pc: {load_pct, ram_total_mb, ram_free_mb, commit_limit_mb,
commit_used_mb} | null, nova: {total_mb, parts: {api, children, desk, gateway}, processes: [{role, pid, name,
private_mb}]}, others: [{name, count, private_mb, largest_pid, largest_mb}], others_total_mb, unreadable}`

- Sizes are **private bytes** in MB, the memory a process committed for itself: what a leak grows, never
  trimmed. `load_pct` is Windows' own RAM in use (Task Manager's Memory %); an allocation fails, in any
  process, once `commit_used_mb` reaches `commit_limit_mb` (RAM plus the page file).
- **Nova is counted by pid, never by a name.** One part per process, the first that claims it: `gateway`
  (IB Gateway and IBC's loop, as the priority keeper found them), `api` (this process), `children` (what the
  API started -- a Sim import), `desk` (the Electron processes in desk window reports younger than
  `PERF_MEMORY_CLIENT_FRESH_SEC`, and what they started; the packaged desk starts the API, which stays
  `api`). Windows reuses pids and keeps a child's parent pid after the parent exits, so a child counts only
  when it was created after its parent.
- `others` groups every other process by image name, the biggest `PERF_MEMORY_TOP` (5) kept;
  `others_total_mb` is all of them. A process Windows will not open (a protected one) is counted in
  `unreadable`, never as 0. No command line is read.
- The API log warns once per episode when RAM in use or the commit charge reaches `PERF_MEMORY_PRESSURE_PCT`
  (90%; the episode ends under `PERF_MEMORY_REARM_PCT`, 85%), with Nova's parts and the other programs' total
  -- never their names, since an issue dump prints the log -- and once per run when a Nova part passes its
  leak line (`PERF_MEMORY_API_LEAK_MB`, `PERF_MEMORY_DESK_LEAK_MB`). It measures and never acts.

**Port watch (operator report 2026-10-14).** The desk PC ran out of network ports: 16,400 TCP connections
against Windows' 16,384 dynamic ports, 15,300 of them still `ESTABLISHED` under 755 process ids that no longer
existed (mostly to Google, from a stream reader restarted all morning), leaking since the boot four days
before. Every new connection then failed (`WinError 10048` / `52`): IB Gateway's, the desk's, and the API
guard's own probe, which stopped a serving API 19 times. Nothing on the desk had said the ports were going.
Owner `perf/port_watch.py`, started with the recorder: 20 s after start, then every `PERF_PORTS_EVERY_SEC`
(60 s), on a worker thread, one reading of Windows' TCP tables (IPv4 and IPv6, `GetExtendedTcpTable`, a few
ms) beside the process list, written to the day file and kept for the `pc_ports` diagnostics row
(`desk-ops.md`, "PC network ports"):

`{kind: "ports", schema_version: 1, ts, range: {start, count, source: "netsh" | "default"}, in_use,
in_use_by_family: {ipv4, ipv6}, pct, closed: {connections, pids}, top: [{name, count}]}`

- `in_use` counts connections, not listeners, whose local port lies in the dynamic range (`netsh int ipv4
  show dynamicport tcp`, read once per process; Windows' default 49152 + 16,384 when it cannot be read).
  IPv4 and IPv6 count against that one range: on 2026-10-14 IPv4 connects to 127.0.0.1 failed with ~3,600
  IPv4 and ~12,800 IPv6 connections open, so Windows handed both families ports from one pool (two separate
  pools would have left ~12,000 IPv4 ports). `in_use_by_family` keeps each family's share of `in_use`.
- `closed` counts connections whose owning process id is in no process list now -- a closed program's
  connection Windows has not let go of. They are freed only by a restart of the PC.
- `top` is the living programs holding the most connections, by image name, the biggest `PERF_PORTS_TOP`
  (3). No address, port or command line is kept.
- The API log warns once per episode when `pct` reaches `PERF_PORTS_PRESSURE_PCT` (70%; the episode ends
  under `PERF_PORTS_REARM_PCT`, 60%) or `closed.connections` reaches `PERF_PORTS_CLOSED_WARN` (500), with the
  counts only. It measures and never acts.

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

