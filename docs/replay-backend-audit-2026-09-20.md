# Replay backend audit and measurements — 2026-09-20

Scope: [#324](https://github.com/aaltaay/Nova/issues/324), backend half of
[#341](https://github.com/aaltaay/Nova/issues/341), download truth
[#303](https://github.com/aaltaay/Nova/issues/303), and progress for
[#321](https://github.com/aaltaay/Nova/issues/321). This is an offline, reproducible
engine/API audit. The separate browser report measures the UI with routed fixture
responses; those responses are not the 250,000-print backend measurements below.

## Fixture and method

- Baseline revision: `17e2f3e5124819f7eeb5bf1c966b4b7e5578817c`; baseline captured
  before editing history code. After: this PR's immutable-selection implementation.
- Windows 11 `10.0.26200`, Python 3.13.14, psutil 7.2.2. One paired run, no CPU
  affinity or machine-idle guarantee. All data is synthetic, no Gateway required.
- BENCH, 2026-09-18, 04:00–09:30 Eastern; 250,000 ordered prints, exactly 50,000
  unreported; 230,000 evenly distributed prints plus 50 bursts of 400 prints.
  Retained candle store contains 330 one-minute candles. Prior close is absent,
  deliberately exercising the old repeated negative-lookup path.
- `POST /api/sim/history/select` and snapshots use FastAPI TestClient: serialization
  and ASGI/thread-pool overhead are included; TCP/network transport is not.
  Candle timings call the same playback function directly, excluding HTTP encoding.
- Playheads: 04:01, 06:45, 09:30 ET, paused. Each p95 uses 40 samples after one
  separately reported cold call; nearest-rank p95. Concurrent measurements run
  four threads, each making 20 snapshot-then-bars iterations (80 combined samples).
- RSS is the process working set delta after GC, measured around selection, not
  a retained-object accounting or a hard capacity estimate. SQL/OS caches remain
  warm across measurements. Independent fresh-fixture runs vary materially.

Reproduce from the repository root with development dependencies installed:

```powershell
py -3 backend/tests/replay_benchmark.py after
# Prove the fixture can start from an absent directory:
py -3 backend/tests/replay_benchmark.py fresh --directory .tmp/replay-bench-fresh
```

The committed harness is `backend/tests/replay_benchmark.py`. It creates only its
selected scratch directory and overrides both history and bars archives. Use the
same harness against each revision. Scratch SQLite files and generated JSON are
ephemeral; this report is the durable measurement record.

## Results

All latencies below are milliseconds, before → after.

| Measurement | Early | Mid | Late |
|---|---:|---:|---:|
| Snapshot HTTP p95 | 17.522 → 8.413 | 19.979 → 8.072 | 30.197 → 8.601 |
| Snapshot HTTP cold | 38.187 → 9.524 | 16.522 → 7.074 | 22.528 → 9.517 |
| Bars function p95 | 4.407 → 0.003 | 8.064 → 0.019 | 10.649 → 0.042 |
| Bars function cold | 142.868 → 115.779 | 6.875 → 0.825 | 9.750 → 0.101 |
| Four concurrent snapshot+bars loops p95 | 69.854 → 26.869 | 87.900 → 28.336 | 147.051 → 31.011 |
| Four-loop total wall time (80 iterations) | 1163.750 → 474.768 | 1547.853 → 493.826 | 2489.513 → 525.415 |

Select HTTP took **1235.745 → 897.854 ms**. Selection RSS delta was
**220.305 → 222.699 MiB**; after all warm calls it was **211.734 → 215.285 MiB**.
This does **not** demonstrate a memory reduction. Packed numeric indexes reduce
Python index objects, but full print dictionaries still dominate memory.

Neither baseline nor after snapshot p95 exceeded the 1000 ms polling interval.
The hypothesized backend-caused request pile-up was **not reproduced** on this
fixture and machine. Contention and disk work were measurable, and warm repeated
bar requests improved; the first timeframe aggregation still has a cold cost.
A separate fresh-directory smoke run returned snapshot p95 13.436 / 14.689 /
10.591 ms and select 1223.357 ms, showing why the paired run is not an SLA claim.

Compact source values (ms, MiB):

```json
{"before":{"select":1235.745,"rss":220.305,"snapshot_p95":[17.522,19.979,30.197],"bars_p95":[4.407,8.064,10.649],"concurrent_p95":[69.854,87.900,147.051]},"after":{"select":897.854,"rss":222.699,"snapshot_p95":[8.413,8.072,8.601],"bars_p95":[0.003,0.019,0.042],"concurrent_p95":[26.869,28.336,31.011]}}
```

## Eight backend leads from #341

| Lead | Finding and disposition |
|---|---|
| Disk while holding playback lock | Confirmed in baseline: every bars poll opens both stores; missing prior close causes two more reads per snapshot. Selection now loads off the global lock, then publishes one immutable reference. Selected-symbol archives for all supported intraday timeframes and previous close are loaded before publication. Hot snapshots/bars are tested with disk reads forbidden. |
| Unbounded materialization | Confirmed. Selection now queries at most 500,001 rows and refuses above 500,000 with a narrow-window error, retaining the previous selection. No truncation/decimation of downloaded prints. One load at a time bounds simultaneous transient builds; an old selection can remain live during its replacement. This is a playback memory guard, not storage retention. |
| Per-poll recomputation | Full trade buckets were already cached in baseline; claiming they rebuilt on every poll was inaccurate. Partial bucket aggregation, retained/shared archive reads, merges, sorting and summaries still repeated. Bounded event-second/timeframe/limit caches eliminate repeated candle work. Rewind changes the key; reload replaces all selected-symbol source data. Snapshot sums over at most 2000 candles remain, a small bounded operation. |
| Missing vs downloaded-empty | Distinct: `download_status=missing, job_id=null, trade_count=0` versus an existing failed/queued job id with count zero. Empty mid-window responses now fail resumably with cursor/count unchanged; resume retries that cursor. Mismatched-symbol snapshots return `active=false` and null quote data; other-symbol chart fallback remains restricted to completed bars on the replay date. |
| Clock/window coupling | Market-hour windows retain correct UTC offsets across both DST transitions. Same-window reload preserves playhead/pause, changed windows start at their own open, and custom 19:00–22:00 playback reaches 21:00 without clamping at 20:00. Return to SIM1 keeps Eastern time of day and pause. Explicit weekend/holiday selection stays that date and reports missing data; defaults skip known closed days. Holiday-year coverage limitation is recorded below. |
| Concurrency | An in-flight select no longer blocks snapshots; a later clear/select fences obsolete loads. WAL plus a 30s connection busy timeout isolates writer transactions. A newly reproduced begin race left a refused request's queued orphan; active check, row creation and reservation are now one SQLite transaction, tested with simultaneous reservations. A held capture load is also fenced by later historical selection in `test_capture_selection.py`. |
| Error paths | Invalid inputs use JSON 422; selecting outside Sim uses 409; corrupt/unsupported/unreadable archives return a logged, sanitized JSON 503. Integer SQLite schema v1 migrates known legacy v0; DDL/WAL setup runs once per file identity, and replacement invalidates that proof. Timeout/empty-page failures preserve the durable checkpoint. Logical partial pages cannot be committed without their cursor. |
| Test gaps | Added API edge cases, schema/replacement/corruption, isolated resume ETA, concurrent admission, immutable-cache mutation protection, off-lock load/clear fencing, bounded selection, stable print ordinals, and explicit reload tests. Existing rewind/identical prints/reported-volume/closed-candle/calendar/return-to-SIM tests pass. Real entitlements, pacing rejections, sparse-market coverage and production-machine performance still need operator evidence. |

Other-symbol candle caches are bounded and filled lazily; their first access
fixes that cached series until eviction/reload. Selected-symbol source series
remain fixed until reload. New downloads are deliberately displayed only after
**Load again**, matching the product's immutable selection contract.

## Adversarial and operational probes

- End-before-start, apparent cross-day dates, 24:00, future dates and path-like
  tickers: JSON 422. Whitespace/lowercase tickers normalize. A syntactically valid
  unknown ticker can select an empty archive; downloading still requires unique
  IBKR contract qualification. No unknown ticker was submitted to a real Gateway.
- Weekend/holiday explicit dates and the 16-hour window: accepted as an explicit
  empty historical selection, not silently remapped. Summer/winter and transition
  adjacent trading-day windows have correct offsets.
- Two simultaneous reservations: one running job, one refusal, no queued orphan.
  Existing worker/paused/in-flight-page tests cover pause preservation and atomic
  resume of identical prints.
- No Gateway: the real read-only adapter was pointed only at a reserved-then-closed
  localhost test port. It returned failed/unreachable in **2190.657 ms**, cursor
  unchanged. This verifies connection refusal and cleanup, not behavior of a
  logged-out, blackholed, or connected Gateway; bounded timeout has a separate test.
- Restart: a parent Python process loaded RESTART; a fresh Python child sharing
  its scratch archive reported `selection=null, jobs=1`. A stale-running job test
  reports interrupted/stale with no ETA. A full desktop restart was not performed;
  the existing Sim/Live restart-policy decision remains [#302](https://github.com/aaltaay/Nova/issues/302).

## File audit coverage and remaining findings

- `sim/history_playback.py`, `history_cache.py`, `history_store.py`,
  `history_schema.py`, `history_download.py`, `history_progress.py`,
  `history_routes.py`: acquisition, ownership, bounded caches, storage and errors
  covered above. No execution API was introduced.
- `sim/session_clock.py`, `sim/trading_day.py`: paused/scrubbed versus wall time,
  selected date/window, DST offsets and holiday defaults inspected and tested.
  The holiday table currently covers 2026 only. `is_trading_day(date(2025,7,4))`
  returns true and `last_trading_day(date(2025,7,4))` returns July 4. This can miss
  the prior close for July 7, 2025. Tracked as [#386](https://github.com/aaltaay/Nova/issues/386); calendar behavior is unchanged in this PR.
- `sim/chart_replay.py`: closed interval and UTC calendar-date gates retain
  no-lookahead fallback; only the selected capture may supply capture bars.
  Historical routes and ticker bars routes are synchronous FastAPI handlers,
  so their disk work runs in the thread pool. Historical selection adds no
  event-loop disk reads.
- `sim/replay.py`, `sim/capture_player.py`: compatibility selection and historical
  clearing inspected; parallel capture work adds atomic immutable publication,
  generation fencing, no-feed loading state, schema refusal, diagnostics and
  off-loop L2 loading. See `architecture/capture-fidelity.md` and
  `test_capture_fidelity.py` / `test_capture_selection.py` for its evidence.
- `sim/market.py` and `market.py`: synthetic SIM1 generation and live market clock
  remain separate. Historical tick fan-out bypasses synthetic fills; quote/depth
  availability is not inferred from historical trade prints. Capture projections now live in `sim/market_views.py` under ADR 001 and
  preserve missing bid/ask, sizes, prior close and daily OHLC as null. Recorded
  quote prices/sizes use canonical ticker fields; capture loading/failure never
  falls through to synthetic SIM1 facts. Remaining broad exception handlers
  outside those projections were not rewritten.
- `ibkr/replay_history_gateway.py`: separate read-only connection, StartupFetch(0),
  live-port-first fallback, unique contract qualification, bounded requests and
  trade flags inspected; closed-loopback failure tested as above.
- `archive/replay.py`, `hod_momo_replay.py`: **confirmed separate lookahead defect**,
  tracked as [#385](https://github.com/aaltaay/Nova/issues/385). Both admit a final
  minute bar by its opening timestamp rather than its closing boundary. This PR
  records the finding without changing the Nova OS/HOD audit engines. Their
  current tests pass because they assert timestamp-start inclusion.

Minimal #385 reproduction: at `1789738205`,
`archive.replay.slice_bars_as_of([{'ts':1789738200,'h':200,'c':99,'v':1000}], as_of)`
returns the complete 09:30 candle 55 seconds before close. The equivalent
`hod_momo_replay.prime_symbol` probe seeds high 200 and close 99 from that bar
five seconds after open. `archive/bar_builder.py` confirms stored timestamps
are minute starts. HOD cumulative base volume uses the same `ts <= first_ts` rule.

## Combined source-transition review

Independent review found two interactions that per-engine generation tests had
missed. Capture clock alignment called market fanout while holding its selection
lock; fanout could re-enter historical status while historical publication held
its lock and waited to clear capture. Initial capture history-clear and intent
registration also had a gap in which newer history publication could be followed
by an older capture clock assignment.

Source-intent registration is now a short atomic history-to-capture transition;
clock mutation under publication locks suppresses notifications, and external
fanout afterward checks the capture generation. No disk loading runs inside this
transition. Quote/ticker projections pin one immutable snapshot per call.
Deterministic barrier tests force both overlaps, assert completion and latest-source
clock ownership, and reject stale tape fanout. Independent re-review found no
remaining blocking interaction. Final targeted capture/clock/history/market/ticker
verification passed 145 tests; recorder/worker/fanout neighbors had passed in the
preceding 191-test run.

## Verification

The initial broader run passed **85 tests in 72.27s**, including historical replay,
API/download/audit, chart replay, archive decision replay and HOD replay suites.
After the concurrent-admission fix, the affected historical suites passed
**54 tests in 3.39s**. Ruff passes all historical source/tests and the committed
benchmark. Capture selection/fidelity and browser evidence are recorded by the
other parts of this PR. These results establish the tested boundaries; they do
not claim live IBKR coverage or an exhaustive clean bill of health.

## Linux CI follow-up

PR #387 merged after the Windows-focused evidence above. Its Linux backend CI
passed 978 tests before the file-recreation regression failed: the filesystem
reused the same device/inode and did not expose birth time, so a new empty SQLite
file incorrectly inherited the prior schema proof. Each connection now checks
`PRAGMA user_version` before accepting a matching cached identity. Version zero
migrates even after inode reuse; unknown versions refuse even on a warmed path.
Valid version-one connections still avoid repeated DDL/WAL transitions. New
portable tests force identical device/inode and missing birth time for both empty
and legacy replacements. This extends the original audit's platform coverage;
the paired performance measurements above remain the original observed runs.
