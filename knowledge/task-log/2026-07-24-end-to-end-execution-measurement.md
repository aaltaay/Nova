# 2026-07-24 — End-to-end execution measurement

- **Status:** completed
- **Agents:** daddy, execution, widgets, tester, maintainer
- **Domain:** trading execution telemetry
- **Related:** `CHANGELOG.md` § 2026-07-24 — Add clock-safe end-to-end execution measurement and dashboard · `PROBLEM_LOG.md` § 2026-07-24 — HTTP 200 execution rejections were timed as browser successes; § Fill-leg telemetry pushed the execution callback owner over its file limit; § Cancel failures were hidden and latency imports bypassed the feature API; § Mixed benchmark SLA and bracket-child fills corrupted parent metrics; § Cancel/replace reused stale order acknowledgment and produced negative latency; § Frontend latency tests initially missed browser/test runtime boundaries · ADR 007

## Task

Implement the explicitly authorized user-action-through-fill measurement and modular frontend dashboard without placing orders, adding IBKR requests, changing polling cadence, or weakening execution gates.

## Goal

Provide honest browser/backend timing boundaries, complete callback/fill evidence, slippage, bounded segmented metrics, and CI-safe regressions while preserving `execution.service.execute`, idempotency, persist-before-send, adapter exclusivity, and `auto_live` NO-GO.

## Why it mattered

The prior ledger proved backend receive→ack and complete fill but could not tell a dashboard where browser time ended, distinguish partial fills or callback provenance, or quantify fill quality. Worse, old cancel/replace rows contained negative ack deltas that were silently omitted rather than diagnosed.

## What we changed

- Extended ADR 007 before code with same-clock-only arithmetic, provenance-preserving fill evidence, bounded API, and population-segregation rules.
- Captured backend ingress in the existing ASGI timing middleware and added an optional paired browser action/request contract to execution HTTP routes.
- Added bounded SQLite fill evidence for `execDetails`, `orderStatus`, and cached reconciliation observations, including exchange/callback stamps, partial/complete state, prices/qty, and side-aware slippage.
- Added p50/p95/p99/max/count/error/exclusion/sufficiency rollups segmented by population, mode, operation, source, and provenance.
- Split order execution routes from `routes/trading.py`, order-row mapping from `ibkr/orders.py`, and cached reconciliation evidence from `execution/telemetry.py`; all touched source files remain under 400 lines.
- Bound each `OrderWatch` to one execution and reset watches for cancel/replace, fixing stale ack reuse on IBKR's reused order ids.
- Added `frontend/src/execution_latency/` as an ADR-005 feature slice: parser, polling hook, bounded browser timing ring, dashboard tables, explicit uncertainty states, representative fixtures, and RTL/Vitest coverage.
- Added Account → Latency navigation without adding business logic to `App.tsx`. Extracted the account section nav and manual-order footer so touched React components remain under 300 lines.
- Wired paired body/header timing into established manual place, cancel, flatten, Fill now, cancel-all, and Nova Action clients. Response→visible is the second animation frame after response, measured only in browser `performance.now()`.
- Corrected maintainer findings: normalized population now controls mixed/SLA status, and bracket parent/target/stop evidence carries explicit role, side, reference source, and parent-aggregate eligibility.
- Closed frontend maintainer warnings: Account/Stock View cancel failures now use a shared visible-alert path with polling recovery, and all sibling features import execution-latency contracts through its public barrel.
- Corrected browser outcome classification: place, per-order cancel, and cancel-all parse body-level `ok` before completing timing; Flatten, Fill now, and Nova Actions inherit the same verdict.

## How it works now

Widgets may send action and request-dispatch wall plus `performance.now()` stamps. Nova computes action→dispatch only in browser monotonic time. The backend computes ingress→validation/persist/send/ack/fill/response-ready only with the current process's `perf_counter_ns`. A wall observation between browser and backend is present only as clock-offset-plus-transport uncertainty.

Each callback/poll observation is stored independently and bounded. First and complete fill are derived from those rows; old same-boot `filled_ns` remains labeled legacy-stage evidence rather than being invented into a callback provenance. Legacy, cross-boot, missing, and negative timings are retained but excluded with counts/reasons.

Aggregate execution percentiles are diagnostic-only when normalized populations mix; aggregate `sla_pass` becomes null and each population segment exposes its own SLA status and insufficiency. Bracket target/stop evidence remains visible with SELL side and target/stop reference when known, but only parent/single-leg evidence can set parent stages or enter parent-entry fill/slippage/provenance rollups. Legacy evidence without leg attribution is excluded rather than guessed.

The frontend fetches both read-only metric endpoints and renders process-local operation age, end-to-end backend hops, first/complete fill stages, paper/live/benchmark populations, operation/source/mode segments, provenance, exclusions, and browser-local action timing. Mixed aggregate SLA is visibly suppressed and population rows own Pass/Fail/Insufficient status. Fill-leg rows display side-aware slippage while marking child target/stop legs excluded from parent execution aggregates. It does not fetch raw execution identifiers or infer unavailable per-evidence exclusion reasons.

Browser timing outcome is the conjunction of transport and execution result. HTTP 200 with `{ok:false}`, non-2xx with any body, malformed JSON, and network failure all complete as errors. Returned body failures remain ordinary typed results for existing UI handling; parse/network failures still throw.

## Why this approach

One universal timestamp subtraction would look simpler but would be false: browser `performance.now()` and backend `perf_counter_ns` have unrelated origins, and wall clocks can be offset. Separate clock domains preserve what can actually be measured. A bounded evidence table was chosen over a JSON blob so partial fills and provenance remain queryable without unbounded API payloads. Existing callbacks and cached trade mapping were instrumented instead of adding broker requests or tightening poll loops. Fresh per-mutation watches fix the order-id reuse root cause at correlation ownership rather than hiding negative values in the rollup.

The maintainer fixes use normalized population instead of mode/source because benchmark transport is part of the measurement population, not an account mode. Child bracket evidence is retained rather than dropped, but aggregate eligibility is explicit: this preserves the audit trail while preventing an exit leg from rewriting the meaning of the parent-entry execution.

The dashboard is nested under Account because this is operator execution evidence, not another scanner tab. The browser ring is process-local and reload-reset by design, matching the backend operation rings' operational nature. A second animation frame is used as the visible boundary so React state queued by the request continuation can commit before observation; it remains labeled as a browser frame, not a backend-to-paint duration.

Cancel feedback uses one IBKR-owned helper rather than duplicating alert state across Account and Stock View. Refreshing in `finally` preserves last-good polling recovery for success, broker rejection, and network failure. A feature public barrel was chosen over relocating timing to generic shared utilities because the types and ring remain execution-observability concepts, not business-agnostic infrastructure.

The body-aware completion rule lives in one public response helper because every higher-level action eventually delegates to place, cancel, or cancel-all. Fixing those three request boundaries avoids duplicated timing decisions in Flatten, Fill now, and Nova Actions while preserving their current errors and safety gates.

## Verification

- Final focused CI-safe execution/order/metrics pytest after maintainer fixes: 102 passed, covering browser/backend timing, partial→complete fill, evidence bounds, exchange/callback stamps, BUY/SELL and parent/target/stop slippage, reconciliation provenance, mixed benchmark suppression, restart/clock exclusions, stale cancel ack regression, routes, metrics, and no-bypass AST.
- Complete backend pytest: 974 passed. The known Windows TorchVision DLL diagnostic printed during optional sentiment import but did not fail the run.
- Tester re-ran 60 focused execution/metrics tests after extracting cached reconciliation mapping from the 407-line telemetry module; Ruff passed and the maintainer scan no longer reports an execution-scope file-size finding.
- Ruff on changed files, `py -3 tools/agent_contract.py`, and `git diff --check` pass.
- Frontend focused body-outcome tests: 39 passed; complete frontend suite: 458 passed.
- Frontend ESLint and production build/typecheck passed. All touched/new React components are below 300 lines and TypeScript modules below 400.
- No latency probe was run because the user prohibited order-producing probes while Gateway is live.

## Follow-ups

- Browser verification used populated representative GET fixtures and covered Account → Latency, stale/error/recovery states, corrected mixed-population/SLA/fill-leg labels, rapid navigation, and console cleanliness (0 console errors, 0 page errors, 0 mutation requests). The final body-outcome helper change was then covered by eight focused tests plus the 458-test frontend suite.
- Phase B remains 0/5 and active; this work does not advance it. Future latency evidence must come from normal operator activity—never an agent-generated live or paper order.

## Keywords

execution latency, browser performance.now, perf_counter_ns, partial fill, slippage bps, execDetails, orderStatus, reconciliation poll, negative ack, cancel replace, ADR 007
