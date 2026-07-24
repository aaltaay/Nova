# 2026-07-23 — Per-operation latency measurement

- **Status:** completed
- **Agents:** execution → market-feed → tester → widgets → tester → market-feed → docs
- **Domain:** observability / execution / market feed / frontend attribution
- **Related:** `CHANGELOG.md` § 2026-07-23 — Add bounded per-operation latency measurement and harden timing correctness · `PROBLEM_LOG.md` § 2026-07-23 — Per-operation latency review found reconnect, lock-scope, cross-boot, attribution, and probe-isolation defects

## Task

Implement the attached Per-Operation Latency Measurement plan across existing execution, IBKR market-data, HTTP, WebSocket, and header paths. Complete the work without adding broker requests, per-tick samples, live orders, or an `auto_live` unlock.

## Goal

Provide low-overhead, source-honest latency evidence for individual operations; make execution fill timing and benchmark runs trustworthy; and close review findings that could lose callbacks, block urgent sends, corrupt monotonic deltas, or mislabel an Alpaca probe as generic API/IBKR latency.

## Why it mattered

Aggregate process health could not answer which operation was slow, while some existing timing assumptions were unsafe. A replacement IB instance could miss telemetry handlers, an acknowledgment wait could monopolize the global execution lock for up to five seconds, persisted `perf_counter_ns` values could be compared across process boots, and the header could imply that an Alpaca account HTTP round trip represented the IBKR market-data path.

## What we changed

- Added a process-local operation metrics core with a 512-sample ring per operation, `perf_counter_ns` timing, async/sync helpers, and p50/p95/p99/max/count/error-count/age rollups. Central constants own the ring size and health-source identifiers; thin `GET /api/metrics/ops` returns the snapshot.
- Timed existing outbound IBKR boundaries only: connect, historical bars, one-shot and persistent scanners, snapshots, hydration/pipeline work, account reads/refreshes, and depth/tape subscriptions. No request was added and no market-data tick is sampled individually.
- Added route-template HTTP timing and scanner WebSocket first-buffer-to-broadcast timing, avoiding raw-symbol cardinality.
- Added execution send→fill and ack→fill rollups. Synthetic and paper probes now use a unique run prefix so summaries cannot mix older ledger rows.
- **HIGH:** changed process-global telemetry wiring to once-per-IB-instance wiring so replacement clients after reconnect receive order-status, execution, and error callbacks.
- **HIGH:** moved broker acknowledgment waiting outside the global send lock while retaining reservation, validation, persistence, and synchronous broker send inside the protected section.
- **MEDIUM:** added `boot_id` to the execution ledger, a legacy-schema migration, and same-boot callback/rollup filters so process-local monotonic timestamps are never combined across restarts.
- **MEDIUM:** exposed health/latency/market-data source fields. The header allowlists `alpaca_account_http` as “Alpaca account RTT” and suppresses unknown or legacy latency sources.
- **LOW:** isolated every benchmark run with a unique idempotency prefix and retired obsolete `table_reprice` integrity counters in favor of honest `scanner_l1` age. The retired loop was not revived.
- During verification, removed the unused `WORKING_AAPL` test fixture and an obsolete ESLint suppression around the already-correct React act setup. The underlying act-environment diagnosis remains the existing `PROBLEM_LOG.md` entry dated 2026-07-22.
- Orchestration sequence: execution implemented the metrics/execution slice; market-feed instrumented existing IBKR, HTTP, WebSocket, and integrity paths; tester ran focused/full safety gates; widgets removed the dead Orders Today fixture while tester removed the stale act suppression; tester reran final lint/focused gates; market-feed verified the current route in an isolated fresh process; docs wrote these aggregate logs. The attached external plan was read-only throughout and was never edited.

## How it works now

Each named operation records elapsed monotonic nanoseconds into a bounded in-memory ring. The metrics endpoint reports recent percentile distribution plus process-lifetime counts and sample age; restart naturally resets these operational samples. HTTP names use matched route templates, scanner WebSocket timing starts with the first buffered row and ends after broadcast, and IBKR timing wraps calls the application already makes.

Execution ledger timing is durable only as raw evidence from its originating boot. `boot_id` fences callback updates and rollups to the process whose `perf_counter_ns` clock produced them. The send lock protects the safety-critical reserve/validate/persist/send sequence, then releases before waiting for broker acknowledgment. Fill rollups remain separate from the acknowledgment SLA. Header RTT appears only when its backend source is explicitly recognized.

## Why this approach

- **Bounded local metrics over a new telemetry service:** a 512-sample ring gives useful tail latency without unbounded memory, database writes, network export, or a new dependency. Process-lifetime counts preserve volume/error context while percentiles describe a recent bounded window.
- **Existing boundaries over active probes:** wrapping current request/subscription calls proves real application-path latency without spending IBKR request capacity or changing broker behavior. Per-tick timing was rejected because it would create high-volume overhead and distort the hot path.
- **Route templates and fixed operation names over raw URLs/symbols:** low-cardinality keys keep snapshots bounded and avoid leaking ticker- or identifier-specific paths into metric names.
- **Monotonic time plus boot fencing over wall-clock deltas:** `perf_counter_ns` is correct for duration measurement but has process-local scope. Replacing it with wall time would reintroduce clock-adjustment error; retaining legacy rows but excluding cross-boot deltas preserves audit history without manufacturing latency.
- **Narrow lock scope over either extreme:** holding the lock through acknowledgment serialized urgent cancels behind a broker wait; removing the lock entirely would weaken idempotency and send safety. Protecting reserve/validate/persist/send and waiting afterward keeps both guarantees.
- **Unique prefixes over clearing the ledger:** deleting old benchmark rows would destroy audit evidence and race with concurrent readers. Prefix-scoped queries isolate runs deterministically while preserving history.
- **Explicit attribution over inference:** the frontend only labels the known Alpaca account source. Reusing a generic “API RTT” or guessing that legacy latency was IBKR would preserve the original user-facing lie.
- **Fresh-process verification without a second Gateway session:** the running API was stale and returned 404 for the new route despite a live IBKR connection. Starting another broker-enabled process would risk a conflicting Gateway session and add requests, so live outbound broker metrics were deliberately not exercised. Code/test correctness was verified safely; the deployed/local runtime must be restarted before operational samples can appear.

## Verification

- Focused backend latency/safety suites: 118 passed; fresh-process market-feed probe slice: 13 passed.
- Full backend: 961 passed. Full frontend: 441 passed. Header: 4 passed.
- Final frontend lint: 0 errors and 0 warnings. Build/typecheck passed. `git diff --check` was clean apart from informational line-ending warnings.
- Two isolated fake-broker runs used 8 samples each; each independently returned 16 rows, 8 acknowledgments, and 8 send→fill plus 8 ack→fill samples. No order/confirmation flag or execution arm was used.
- Fresh `TestClient` calls returned 200 for `/api/health` and `/api/metrics/ops`; the snapshot contained `http.GET./api/health`, `clock=perf_counter_ns`, and `ring_size=512`.
- Browser verification showed no unlabeled RTT in the header and a clean console. `agent_contract` passed.
- Known non-failing diagnostics remained: the TorchVision DLL message occurred although pytest exited 0 with all tests passed, and Vite reported its existing large-chunk warning.
- Safety remained unchanged: `auto_live` is still NO-GO, and no live or paper orders were placed.

## Follow-ups

- Restart the local API after deployment so the running process loads `/api/metrics/ops`; then normal application activity can populate outbound IBKR operation samples without adding requests.
- Do not claim live Gateway latency from this run. Exercise it only through normal post-restart traffic or a separately approved safe session.
- The attached plan remains external and read-only; do not edit it as part of completion logging.

## Keywords

per-operation latency, op_metrics, perf_counter_ns, ring 512, p95, IBKR timing, HTTP route template, scanner WebSocket, send to fill, ack to fill, boot_id, reconnect telemetry, execution lock, Alpaca account RTT, benchmark isolation, scanner_l1 age
