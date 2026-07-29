# Change log (agent-maintained)

This file is a running narrative of **what changed in this repo and why**, so future agent and human sessions can get oriented in minutes without digging through diffs.

- **Scope:** code behavior, module boundaries, public APIs, constants, tooling, rules, user-visible UI changes.
- **Out of scope:** pure typo fixes, formatting-only edits, local scratch files.

Bug fixes should **also** be logged in `PROBLEM_LOG.md` (symptom / cause / fix). This file answers "what does the codebase do now and why"; `PROBLEM_LOG.md` answers "what went wrong and how was it diagnosed."

## How agents update this file

1. **When:** After completing any task that changes logic, public behavior, a module boundary, constants, config, build, or rules. Skip pure cosmetics.
2. **Where:** Prepend a new `##` section **immediately below** the `<!-- ENTRIES_START -->` marker (newest entries at the top).
3. **Commit together:** The changelog entry ships in the **same commit** as the code it describes. Do not push code without an entry.
4. **Keep it short:** A few lines per field. No secrets, tokens, or personal data.

Entry template (copy and fill in):

```markdown
## YYYY-MM-DD — Short descriptive title

- **What:** 1–2 sentences on what changed (user-visible + internal).
- **Why:** Trigger for the change (user request, bug class, performance, cleanup).
- **Files touched:** Key files only, e.g. `backend/scanner.py`, `frontend/src/App.tsx`.
- **How it works now:** The mental model a future agent needs — the "oh, got it" paragraph.
- **Verified by:** How you confirmed it works (built + ran, test name, manual click path).
- **Follow-ups:** (optional) anything deferred.
- **Related:** (optional) commit SHA, PROBLEM_LOG entry date, issue link.
```

<!-- ENTRIES_START -->

## 2026-07-28 -- Fix G1 zombie L1 subs + G4 session errorEvent handler

- **What:** On every READY transition, Nova clears all L1 ownership maps and installs a session-level IB `errorEvent` handler for connectivity (1100/1101/1102), data-farm (2104/2106/2108), max-tickers (101), and delayed-data (10167) codes.
- **Why:** Capture audit findings G1/G4 -- zombie `_subs` after reconnect silently starved HOD; classic IB connectivity/farm codes were unhandled.
- **Files touched:** `backend/ibkr/ticks.py` (`clear_all_subscriptions`), `backend/ibkr/client.py` (`_on_session_ready`), `backend/ibkr/session_errors.py` (new), `backend/ibkr/scanner_l1.py` (`note_capacity_error`), `backend/constants_ibkr.py`, tests.
- **How it works now:** READY -> clear zombie L1 maps -> install error hook. Reconnect then re-issues `reqMktData` on the next reconcile. Error 1100 marks session DEGRADED; 101 surfaces on L1 subscription error; 10167 sets `is_delayed_data()` for Phase 3 UI.
- **Verified by:** `pytest tests/test_hod_pipeline_fake_feed.py tests/test_ibkr_session_errors.py tests/test_scanner_l1.py` -- 17 passed (former G1 xfail now passes).
- **Related:** PROBLEM_LOG 2026-07-28 zombie L1; audit doc G1/G4.

## 2026-07-28 -- Constitution single-sourced to AGENTS.md (gemini.md becomes alias)

- **What:** `AGENTS.md` is now the sole constitution text. `gemini.md` is a thin legacy alias whose only content is `@AGENTS.md`. The ADR 007 execution-command schema (which existed only in `gemini.md`) was ported into `AGENTS.md` §3 first; stale agent-table/canvas prose unique to `gemini.md` was superseded by the newer `AGENTS.md` versions and not ported. Pointer wording updated in `.cursor/rules/constitution.mdc` and `.cursor/rules/self-annealing.mdc`.
- **Why:** User question -- why mirror two constitution files at all? The mirror had already failed in practice: the files drifted by ~48 lines (ADR 007 block + 2026-07-18 fleet rows missing from one side). Two copies guarantee drift; one source + an alias does not.
- **Files touched:** `AGENTS.md` (title, ADR 007 port, embedded constitution copy, §9 pointer, §11 row), `gemini.md` (now an alias), `.cursor/rules/constitution.mdc`, `.cursor/rules/self-annealing.mdc`.
- **How it works now:** Read/edit the constitution ONLY in `AGENTS.md`. Tools that open `gemini.md` (Gemini CLI, the constitution.mdc pointer) resolve the `@AGENTS.md` import to the same text -- the same mechanism `CLAUDE.md` already used. Any future "update the constitution" edit happens in one place.
- **Verified by:** `git diff --no-index gemini.md AGENTS.md` showed the drift (19+/29-); post-change, `gemini.md` contains only the alias + import; no other repo references to `gemini.md` as the edit target remain except historical CHANGELOG/memory entries.
- **Related:** `CHANGELOG.md` § 2026-07-28 Constitution: Co-Pilot Coaching Footer (same session).

## 2026-07-28 -- Constitution: Co-Pilot Coaching Footer (§5)

- **What:** New behavioral rule in `gemini.md` + `AGENTS.md` §5: every substantive assistant reply must end with a short **Better ask:** coaching paragraph -- honest feedback on how the user's request could have been clearer/better, plus one thing worth teaching. Trivial exchanges are skipped at the agent's judgement.
- **Why:** User directive -- they want direct judgment on their prompting so they become a better co-pilot, not flattery.
- **Files touched:** `gemini.md`, `AGENTS.md` (§5 rule + §11 maintenance log rows).
- **How it works now:** Substantive replies end with a `**Better ask:**` paragraph (max ~5 sentences, plain language). One-word pings, tiny confirmations, and pure status checks may skip it.
- **Verified by:** Rule text present in both constitution mirrors; maintenance log rows added; no code changes.
- **Related:** User request 2026-07-28; `CHANGELOG.md` § 2026-07-28 HOD scanner capture audit (preceding task in same session).

## 2026-07-28 -- HOD scanner capture audit + mock replay harness

- **What:** New offline verification stack for the HOD Momo scanner: a committed fixture day (real 2026-07-17 tape/bars/alert log), a deterministic replay driver that feeds archived prints through the production engine with an injected clock, golden + parity tests, and a fake IBKR feed that drives the real `ticks.py` -> `scanner_l1` -> `ibkr_bridge` -> engine path. Plus a written capture audit at `docs/audits/2026-07-28-hod-scanner-capture-audit.md`. No product-code behavior changes.
- **Why:** User asked for an audit of whether the scanner captures what happens in the market, with mock tests on sample data, focused on IBKR API-layer accuracy.
- **Files touched:** `tools/export_hod_replay_fixture.py`, `backend/hod_momo_replay.py`, `backend/tests/conftest.py` (new), `backend/tests/fixtures/hod_replay/*` (new), `backend/tests/test_hod_momo_replay.py`, `backend/tests/fakes/fake_ibkr_feed.py`, `backend/tests/test_hod_pipeline_fake_feed.py`, `backend/tests/test_hod_momo_engine.py` (reset delegates to conftest), `docs/audits/2026-07-28-hod-scanner-capture-audit.md`.
- **How it works now:** `py -3 tools/export_hod_replay_fixture.py --date <d>` exports a committed fixture from the local archive; `py -3 backend/hod_momo_replay.py --date <d>` replays it through the real engine (pins `time.time` + `market.now_et` to replay time, reconstructs cumulative volume + day-high series, mirrors the consolidation flush without disk/WS). Replay-vs-production parity for 2026-07-17: dense-tape movers (SDOT/BIYA/CJMB) reproduce strategies 11/12; quiet symbols stay silent; thin-tape production alerts (CNF/WZRD/SLND/KLRS) are unreproducible because the L1 tick stream is never archived -- the audit's headline data finding.
- **Verified by:** `pytest tests/test_hod_momo_replay.py` (8 passed), `tests/test_hod_pipeline_fake_feed.py` (4 passed + 1 strict xfail proving the zombie-L1 reconnect gap), full HOD + L1 suite 109 passed/1 xfailed.
- **Follow-ups:** Ranked fix list in the audit doc (P0: archive L1 ticks for active-set symbols; P0: clear/re-establish L1 subs on reconnect; P1: reqMarketDataType + delayed-data labeling; P1: persist session_high_raised_ts).
- **Related:** PROBLEM_LOG 2026-07-28 (zombie L1, delayed-data blindness, L1 archive gap).

## 2026-07-24 — Dashboard “Reload backend” control

- **What:** Added a **Reload backend** button in the header status cluster (next to API/Gateway chips) when the local API is up. Confirms, then kill-restarts uvicorn via the same path as **Start API** (Vite dev middleware or Electron sidecar).
- **Why:** After backend-only fixes (e.g. HOD session reconcile), users needed a one-click way to restart the API without closing Run Nova.bat windows manually.
- **Files touched:** `frontend/src/components/BackendReloadButton.tsx`, `HeaderConnectionStatus.tsx`, `utils/startLocalApi.ts`, `constantGroups/chart_api.ts`, `styles/tokens-shell.css`.
- **How it works now:** Visible only when `canReloadLocalBackend()` (dev or desktop). Hidden on production web deploys where the UI cannot spawn processes. On success, triggers the existing `onBackendStarted` refresh (scanner refetch).
- **Verified by:** Vitest (`BackendReloadButton.test.tsx`, `HeaderConnectionStatus.test.tsx`, `startLocalApi.test.ts`); `npm run build`.

## 2026-07-24 — HOD Momo session boundary + honest tab counts

- **What:** HOD Momo "today" now uses the same 04:00 ET-anchored session key as scanner/cache files. Stale prior-session alerts are archived on load instead of appearing under Today (Live). Tab badge and header show collapsed symbol count (with raw fire count when higher).
- **Why:** Yesterday evening alerts (e.g. 6:43 PM Thu) were counted in today's badge (96) while the table showed ~20 collapsed rows; a midnight–4 AM restart could skip rollover and leave prior-session alerts in the live feed.
- **Files touched:** `backend/hod_momo_session.py`, `backend/hod_momo_persist.py`, `frontend/src/pages/DashboardPage.tsx`, `frontend/src/hod_momo/HodMomoSection.tsx`, `frontend/src/hod_momo/HodMomoTab.tsx`, `frontend/src/hod_momo/RunningUpTab.tsx`.
- **How it works now:** `current_date_et()` delegates to `session_key_et()`. On startup, `reconcile_loaded_alerts_to_session()` archives alerts whose timestamps belong to a prior session. Tab `(N)` matches visible symbol rows; header adds "· M alerts" when raw fires exceed symbols.
- **Verified by:** `py -3 -m pytest backend/tests/test_hod_momo_persist.py -q` (17 passed).
- **Related:** PROBLEM_LOG 2026-07-24 — HOD Momo session bleed.

## 2026-07-24 — Header Prices chip scoped to scanner tabs only

- **What:** The header **Prices** freshness chip (last `/ws/scanner` `price_patch` age) now appears only on tabs whose module `feedDeps` include `scanner` (Gappers, Gainers, Losers, After Hours, Catalysts). It is hidden on HOD Momo, Running Up, Dashboard, Watchlist, and Account tabs.
- **Why:** On HOD Momo the UI sends `set_active_tab: none`, so the backend stops forwarding scanner `price_patch` messages while IBKR L1 for the HOD pool keeps flowing — the chip falsely read **stale** even though alerts and ticks were live.
- **Files touched:** `frontend/src/workspace/registry.ts` (`tabUsesScannerPricePatch`), `frontend/src/pages/DashboardPage.tsx`, registry + header tests.
- **How it works now:** `DashboardPage` gates `secondsAgo` / `pricesStale` through `tabUsesScannerPricePatch(activeTab)`; `HeaderConnectionStatus` omits the chip when `secondsAgo` is null. HOD integrity freshness stays on the HOD Integrity banner (`hod_active_quote_age`, etc.), not the scanner-table chip.
- **Verified by:** `npm run test -- --run src/workspace/registry.test.ts src/components/HeaderConnectionStatus.test.tsx` (15 passed).
- **Follow-ups:** Optional future HOD-scoped header chip tied to `/ws/hod-momo` or integrity metrics if product wants tab-local freshness there too.

## 2026-07-24 — Remove daddy dispatcher; zero-hop specialist routing

- **What:** Deleted the `daddy` top-of-fleet dispatcher agent (spec, memory, dashboard canvas, registry entry) and flipped Nova's agent routing default from "auto-dispatch a specialist" to **zero-hop**: the parent Auto session classifies and does multi-domain work in-session by default. All other specialists (router, ibkr-ops, market-feed, hod-momo, tester, maintainer, security, docs, warrior, widgets, execution, news, backtester, hotkeys) remain registered but are now **opt-in only** — invoked when the user explicitly names one. Also added a "Pragmatic patterns & loops" section to `engineering-standards.mdc` reviewing refactoring.guru's GoF catalog and the loop-library loop collection against this repo, adopting only a small named-pattern vocabulary for shapes already present in the code plus a future pre-commit test guard, and rejecting the rest as unneeded ceremony for a solo-maintained, functional (non-OOP) codebase.
- **Why:** Every `Task(subagent)` call is a full extra agent turn (new context, tools, Lifecycle report). `daddy` nested an extra nested-Task hop on top of that for the highest-frequency routing paths ("just get this done", casual `daddy, …` address), making normal requests structurally slower and more expensive with no product benefit — investigation found no backend/frontend code depends on it.
- **Files touched:** Deleted `.cursor/agents/daddy.md`, `.cursor/agent-memory/daddy-memory.md`, `agent-daddy.canvas.tsx`. Edited `.cursor/agent-system/registry.json`, `.cursor/rules/specialist-routing.mdc`, `.cursor/rules/task-log.mdc`, `.cursor/rules/problem-log.mdc`, `.cursor/rules/engineering-standards.mdc`, `knowledge/obsidian/00-System/Agent-Fleet-Map.md`, `AGENTS.md`, `docs/agent-operations.md`, `.cursor/agents/router.md`, `.cursor/agents/hotkeys.md`, `.cursor/agent-system/agent-template.md`, `tools/sync_agent_surfaces.py`, `tools/session_brief_hook.py`, `tools/test_agent_contract.py`, `tools/test_agent_fleet.py`, `tools/agent_dream_lib/bridges.py`, `knowledge/task-log/_template.md`, `knowledge/task-log/README.md`, `nova-home.canvas.tsx`, `agent-router.canvas.tsx`.
- **How it works now:** Default path for any request (including multi-domain work) is the parent working in the current session — no automatic `Task(...)` calls. A hop only happens when the user explicitly names a specialist (e.g. "Use the ibkr-ops subagent…"). Fleet crack index prefers the deterministic `py -3 tools/agent_fleet.py` (no LLM cost) over invoking `router`. `Agent-Fleet-Map.md`'s "Fleet dispatch / orchestration" domain is now owned by `parent` instead of `daddy`. Specialist specs/memories/continuity rules remain as ownership/knowledge references the parent should still follow even when not invoking the agent.
- **Verified by:** `py -3 tools/agent_contract.py` (PASS, 14 agents); `py -3 -m pytest tools/test_agent_contract.py tools/test_agent_fleet.py -q` (19 passed); `py -3 tools/agent_fleet.py --session-brief` shows no daddy reference; regenerated canvas snapshots via `py -3 tools/sync_agent_surfaces.py --write`.
- **Follow-ups:** None planned — specialist fleet stays available opt-in; no loop-runner framework or pre-commit hook was added in this pass (reviewed and deferred, see `engineering-standards.mdc`).
- **Related:** `PROBLEM_LOG.md` § 2026-07-24 — `hotkeys` agent missing from contract test's expected set · `knowledge/task-log/2026-07-24-remove-daddy-zero-hop-routing.md`

## 2026-07-24 — Loud IB Gateway login banner + reconnect warm-up empty state

- **What:** Added a non-dismissible red **ACTION REQUIRED — IB Gateway login** banner above scanner tabs when discovery is IBKR and Gateway is disconnected, with an **Open IB Gateway** CTA. After reconnect, empty Gainers/Losers show a bounded warm-up message instead of “no rows in the feed.”
- **Why:** Offline Gateway looked like empty markets; the only UX was a tiny header chip plus plain empty-state text buried under Integrity fail.
- **Files touched:** `frontend/src/ibkr/GatewayDisconnectedBanner.tsx`, `frontend/src/ibkr/useIbkrReconnectWarmup.ts`, `frontend/src/ibkr/gatewayUxConstants.ts`, `frontend/src/components/EmptyState.tsx`, `frontend/src/pages/DashboardPage.tsx`, `frontend/src/styles/scanner-l2.css`, tests.
- **How it works now:** Banner uses existing `useWorkspace()` connection fields and `launchIbGateway()`. Warm-up is a client-side 45s window after a false→true connect transition (`useIbkrReconnectWarmup`), only for Gainers/Losers market empty state. Tunables live in `ibkr/gatewayUxConstants.ts` so `market_ui.ts` does not grow further.
- **Verified by:** Focused Vitest 7 passed; full frontend suite 465 passed earlier in session; ESLint clean; production build passed; ReadLints clean; maintainer shows no new module over-limits from this work; browser confirmed banner absent while Gateway connected LIVE.
- **Related:** `PROBLEM_LOG.md` § 2026-07-24 — Gateway offline looked like empty scanners · `knowledge/task-log/2026-07-24-ibkr-gateway-login-ux.md`

## 2026-07-24 — Add clock-safe end-to-end execution measurement and dashboard

- **What:** Added optional paired browser action/request stamps, backend ingress/response-ready stamps, bounded per-fill evidence, first/complete-fill timing, exchange/callback observations, side-aware slippage, and population/provenance-segregated execution rollups. Added Account → Latency as a modular frontend dashboard with operation, hop, fill-stage, provenance, population, and browser-visible timing; cancel failures now surface visibly while account polling refreshes. Split execution HTTP routes/order-row mapping into focused modules and added a public frontend feature barrel while preserving ADR 007's sole mutation path.
- **Why:** Operators and Widgets need audit-grade action→ack→fill evidence without invalid cross-host clock arithmetic. Review found cancel/replace could reuse an original order ack; maintainer follow-up also found mixed synthetic/paper benchmarks could suppress the mixed warning, bracket child exits could corrupt parent-entry slippage, and HTTP 200 body rejections were mislabeled as successful browser outcomes.
- **Files touched:** `backend/execution/`, `backend/routes/trading_execution.py`, `backend/routes/trading.py`, `backend/ibkr/order_rows.py`, `backend/ibkr/orders.py`, metrics middleware/route, `frontend/src/execution_latency/`, established frontend trading clients, focused tests, ADR 007, and execution validation docs.
- **How it works now:** Browser monotonic deltas stay in the browser; backend stages stay same-boot `perf_counter_ns`; wall deltas are explicitly uncertain. Manual place, cancel, flatten, Fill now, and Nova Actions send paired action/request stamps without changing `execution.service`; the browser records request→response and response→second-animation-frame locally in a bounded, reload-reset ring. A shared response parser completes browser timing only after combining HTTP transport status with body-level `ok`, so handled HTTP 200 rejections record `outcome=error`; Flatten, Fill now, cancel-all, and Nova Actions inherit that verdict from the same place/cancel clients. Failed cancel HTTP/body/network outcomes use Nova's danger alert and always refresh account polling afterward. Cross-feature consumers import timing/dashboard contracts only through `execution_latency/index.ts`. Fill observations retain `execDetails`/`orderStatus`/existing-poll provenance and partial/complete state, capped at 64 per execution. `/api/ibkr/execution-latency` and `/api/metrics/ops.execution` cap reads at 500 and segment normalized population, operation, source, provenance, and bracket leg. Mixed populations expose diagnostic aggregate percentiles but suppress aggregate SLA; population segments own SLA verdicts. Fill-leg rows show side-aware slippage while labeling target/stop children excluded from parent aggregates. Cached reconciliation mapping lives in `execution/reconciliation.py`, keeping the callback/watch owner under its file limit without changing its public compatibility entry. Cancel/replace watches bind to one execution id, so old acks cannot leak forward.
- **Verified by:** Implementer focused execution/order/metrics run: 102 passed; tester focused execution/metrics run after the reconciliation split: 60 passed; complete backend suite: 974 passed. Frontend focused body-outcome run: 39 passed; complete frontend suite: 458 passed; frontend lint and production build passed; changed-file Ruff, `agent_contract`, and diff checks passed. Maintainer no longer reports an execution-scope file-size finding. No broker probe and no order placed. `auto_live` and spend gates unchanged.
- **Follow-ups:** Tester should restart the local API, intercept both read-only metric endpoints with `frontend/src/execution_latency/testFixtures.ts`, and browser-check Account → Latency plus cancel-error feedback. Parent/Daddy owns the final aggregate commit.
- **Related:** `PROBLEM_LOG.md` § 2026-07-24 — HTTP 200 execution rejections were timed as browser successes; § Fill-leg telemetry pushed the execution callback owner over its file limit; § Cancel failures were hidden and latency imports bypassed the feature API; § Mixed benchmark SLA and bracket-child fills corrupted parent metrics; § Cancel/replace reused stale order acknowledgment and produced negative latency; § Frontend latency tests initially missed browser/test runtime boundaries · `knowledge/task-log/2026-07-24-end-to-end-execution-measurement.md`

## 2026-07-23 — Add bounded per-operation latency measurement and harden timing correctness

- **What:** Added bounded process-local per-operation metrics (512-sample rings using `perf_counter_ns`) with p50/p95/p99/max/count/error-count/age rollups and thin `GET /api/metrics/ops`. Existing IBKR, HTTP route-template, scanner pipeline/WebSocket, and execution fill paths are measured without new requests or per-tick samples; the header now labels only source-attributed “Alpaca account RTT.”
- **Why:** Operators needed operation-level latency evidence, and review found reconnect telemetry, execution lock scope, cross-restart monotonic timestamps, RTT attribution, and benchmark-window defects that could make results incomplete, blocking, corrupt, or misleading.
- **Files touched:** `backend/metrics/`, `backend/constants_metrics.py`, `backend/routes/metrics.py`, existing `backend/ibkr/` and `backend/execution/` owners, health/integrity wiring, `frontend/src/components/HeaderConnectionStatus.tsx`, `frontend/src/components/headerConnectionStatusModel.ts`, focused tests, ADR/validation docs, and `tools/execution_latency_probe.py`.
- **How it works now:** Named operations record durations in bounded in-memory rings; HTTP uses route templates and scanner WS measures first buffer→broadcast. Execution callbacks wire once per IB instance, the global lock protects reserve/validate/persist/send but not the up-to-5-second ack wait, ledger `boot_id` prevents cross-process `perf_counter_ns` deltas, and probe summaries filter by a unique run prefix. Fill timing is reported separately as send→fill and ack→fill. Retired `table_reprice` counters were replaced by honest `scanner_l1` age without reviving the loop.
- **Verified by:** Focused backend 118 passed plus fresh-process market-feed probe 13 passed; full backend 961 passed; full frontend 441 passed; header 4 passed; lint 0 errors/0 warnings; build/typecheck passed; two isolated 8-sample fake-broker runs each produced 16 rows, 8 acks, and 8 samples for both fill rollups; fresh `TestClient` `/api/health` and `/api/metrics/ops` returned 200 with `http.GET./api/health`, `clock=perf_counter_ns`, and ring 512; browser header/console, `agent_contract`, and diff checks passed.
- **Follow-ups:** Restart the stale local API process after deployment so it loads the new route. Live outbound IBKR metrics were intentionally not exercised because the existing process was connected live but stale (metrics 404), and a second Gateway session/new requests would have been unsafe. Known non-failing TorchVision DLL and Vite chunk diagnostics remain. `auto_live` stays NO-GO; no orders were placed.
- **Related:** `PROBLEM_LOG.md` § 2026-07-23 — Per-operation latency review found reconnect, lock-scope, cross-boot, attribution, and probe-isolation defects · `knowledge/task-log/2026-07-23-per-operation-latency-measurement.md`

## 2026-07-23 — Block fractional Flatten + treat Error 10243 / Cancelled as hard fail

- **What:** Manual Flatten / place now refuses non-whole share qty before IBKR submit (`QTY_FRACTIONAL_API`). If a place still gets broker-cancelled with no fill (classic Error 10243), the execution receipt is `ok: false` with a clear desktop-close message instead of a silent success.
- **Why:** Live Flatten of `0.0642 IBKR` was submitted then cancelled by IBKR API; the UI could treat that Cancelled ack as success.
- **Files touched:** `backend/constants_ibkr.py`, `backend/execution/validate.py`, `backend/execution/telemetry.py`, `backend/execution/broker_send.py`, `frontend/src/ibkr/exitPosition.ts`, tests.
- **How it works now:** Whole-share preflight on place validation + FE exit builder. Order watches record `errorEvent`; `finish_place` fails terminal reject statuses without a fill. Closing true fractionals still requires TWS / Gateway desktop (IBKR API limit).
- **Verified by:** `pytest tests/test_execution_validate.py tests/test_execution_finish_place_reject.py`; Vitest `exitPosition` / `closeFullPosition`.
- **Related:** PROBLEM_LOG 2026-07-23 Error 10243 · task-log fractional-flatten-error-10243

## 2026-07-23 — Reset Former Momo watchlist (strategy 1) to default, freeing HOD active-set slots

- **What:** Reset strategy 1's `former_momo_list` from 433 symbols back to the intended default `["SPRC"]` via `POST /api/hod-momo/config`.
- **Why:** Former Momo entries get priority admission into the 40-slot HOD active set in file order; 433 entries meant only the first ~39 (by list order) ever won a slot, permanently crowding out live movers from Gainers/Gappers/Afterhours (`uncovered` was 417/457 discovery symbols). User chose "reset to default" after being shown the mechanism and options.
- **Files touched:** `backend/.cache/hod-momo-config.json` (runtime data, not git-tracked).
- **How it works now:** With the list at 1 entry, `hod_active.build_active_set()` immediately has 39 free slots for table-ranked live movers. Verified live: `hod_active_set` check's `uncovered` metric dropped from 417 → 23 within ~5s of the config POST, with no backend restart required — confirms the same-day active-set cache removal fix is working (a config-only change with no scanner-table mutation reached the active set instantly).
- **Verified by:** `GET /api/hod-momo/debug/integrity` before/after; `GET /api/hod-momo/debug/symbol/WLDS` now shows a populated `session_high` and live decision snapshot.
- **Follow-ups:** None — `update_config()`'s existing 40-symbol capacity guard prevents this from silently recurring through the UI.
- **Related:** `knowledge/task-log/2026-07-23-ah-sticky-bridge-error-and-former-momo-bloat.md` (Resolution section).

## 2026-07-23 — Fix AH scanner sticky bridge-error banner never clearing

- **What:** `run_afterhours_discovery_scan()` and `run_afterhours_focus_scan()` (`backend/scanner_runners/afterhours.py`) now clear `state.ibkr_bridge_last_error` on every successful IBKR-sourced scan, matching the pattern already used by `movers.py`/`discovery.py`.
- **Why:** The Integrity banner kept showing `scanner_ibkr_bridge: IBKR discovery bridge error (Ns ago): afterhours: TimeoutError` with the age climbing indefinitely, even while AH discovery scans kept succeeding every cycle — the `afterhours` label was never included in the existing clear-on-success fix for `movers`/`gappers`.
- **Files touched:** `backend/scanner_runners/afterhours.py`, `backend/tests/test_scanner_runners_afterhours.py` (new).
- **How it works now:** Any successful AH discovery or focus/reprice scan resets the sticky error immediately, so the banner reflects current bridge health instead of the oldest unresolved timeout of the session.
- **Verified by:** New regression tests (`test_run_afterhours_discovery_scan_clears_sticky_bridge_error`, `test_run_afterhours_focus_scan_clears_sticky_bridge_error`); full backend suite (931 tests) green.
- **Related:** PROBLEM_LOG 2026-07-23 — "AH scanner sticky ibkr_bridge_last_error never cleared".

## 2026-07-23 — Fix HOD active-set stale cache (WLDS-style lockout) + persist session highs across restarts

- **What:** `refresh_hod_active_set()` (`backend/ibkr_bridge.py`) no longer memoizes HOD's tracked symbol pool — it always recomputes from the live Gappers/Gainers/Afterhours caches + pinned Former Momo symbols on every tick. HOD session-high truth (`session_highs`/`day_highs`/`session_high_source`/`session_high_seeded`) is now persisted to a dated JSON cache file and restored on startup for the current ET trading session, so a backend restart no longer wipes highs already caught today. A silent one-shot historical-seed failure now logs at `WARNING` instead of a suppressed `DEBUG`.
- **Why:** WLDS was rolling in after-hours (+104%, RVOL 5743x) but never reached `hod_momo.on_trade_update` — the active-set cache's `id()`+`len()` signature stopped changing the moment all three scanner tables froze for the day (ADR 008), so the function returned a permanently stale snapshot for the rest of the session, and any symbol admitted after that point was silently locked out. Separately, every dev `--reload` restart threw away in-memory session highs the engine had already correctly seeded minutes earlier.
- **Files touched:** `backend/ibkr_bridge.py`, `backend/hod_momo_session_focus.py`, `backend/hod_momo_surge_seed.py`, `backend/hod_momo_high.py`, `backend/hod_momo_state.py`, `backend/hod_momo_persist.py`, `backend/hod_momo_alerts.py`, `backend/hod_momo.py`, `backend/cache.py`, `backend/constants_hod_momo.py`, `backend/app_lifespan.py`, `backend/tests/test_ibkr_bridge.py`, `backend/tests/test_hod_momo_session_focus.py`, `backend/tests/test_hod_momo_persist.py`, `backend/tests/test_cache_error_visibility.py`.
- **How it works now:** `build_active_set()` is a pure in-memory merge/rank/dedupe over ~40-70 small dict rows — cheap enough to run on every L1 tick with no memoization, so it can never go stale again. `hod_momo_high.apply_session_high()` calls a new throttled `hod_momo_persist.save_highs()` (same dirty-flag + rate-limit pattern as alert saves) on every high update; `load_persisted_state()` restores those four fields from `backend/.cache/hod-momo-highs-YYYY-MM-DD.json` if the stored date matches today's 04:00-ET-anchored session (a genuinely new day still starts fresh via the existing session-rollover reset).
- **Verified by:** Full backend suite (929 tests) green, including a new regression test proving a symbol appended in-place to an unchanged-`id()` table cache is still admitted, and highs-survive-a-restart / stale-prior-day-ignored persistence tests. Live: `/api/hod-momo/debug/integrity` shows the active set freshly recomputed every tick (`active=40/40`, quote age p95 0.6s) instead of frozen.
- **Follow-ups:** WLDS is still excluded from the active set right now — not by this cache bug (confirmed fixed) but because the manually-curated Former Momo priority list currently holds 39/40 slots, crowding out live table-ranked admission. Separate decision needed (prune list / raise capacity / reserve slots for top movers) — not part of this fix.
- **Related:** PROBLEM_LOG 2026-07-23 — HOD active-set stale cache permanently excluded symbols admitted after freeze (WLDS lockout)

## 2026-07-23 — Stop HOD consolidation test from writing fake alerts into live cache

- **What:** `test_hod_momo_consolidation` now stubs `save_alerts` / notify so fixture LBGJ `$2.40` / `+30%` rows cannot overwrite `backend/.cache/hod-momo-*.json`. Cleared today’s polluted alerts from the running API.
- **Why:** User saw a 5:59 PM LBGJ alert that looked like a real +30% HOD catch; it was pytest fixture data persisted by an unpatched flush loop during ADR verification.
- **Files touched:** `backend/tests/test_hod_momo_consolidation.py`, `PROBLEM_LOG.md`.
- **How it works now:** Consolidation unit test keeps in-memory assertions only; live alert files are untouched by that test.
- **Verified by:** Inspected `hod-momo-2026-07-23.json` (exact fixture match); live snap showed LBGJ ~$0.03 / session_high `$0.0608`; re-ran consolidation test after monkeypatch.
- **Related:** PROBLEM_LOG 2026-07-23 — Fake LBGJ $2.40

## 2026-07-23 — Chart time axis / crosshair use AM/PM instead of 24-hour

- **What:** Stock View / ticker charts now show 12-hour times with AM/PM on the x-axis ticks and crosshair label (e.g. `5:02 PM` / `23 Jul '26 5:02 PM`) instead of 24-hour `17:02`.
- **Why:** User request — 24-hour labels on the after-hours chart were harder to read at a glance.
- **Files touched:** `frontend/src/chart/chartTimeFormat.ts` (+ test), `frontend/src/chart/useChartInstance.ts`, `frontend/src/components/TickerChartOscillatorPanes.tsx`.
- **How it works now:** `formatChartCrosshairTime` / `formatChartTickMark` are passed into lightweight-charts `localization.timeFormatter` and `timeScale.tickMarkFormatter`. Times stay ET wall-clock (same ET-as-UTC encoding as `isoToEtTime`).
- **Verified by:** `npx vitest run src/chart/chartTimeFormat.test.ts`.
- **Follow-ups:** Reload the UI (or wait for HMR) to see the new labels on an open chart.

## 2026-07-23 — ADR 008 follow-up: fix frozen-table mutation leak, diff-based hydration, session-aware integrity, Frozen-at UI

- **What:** A self-review of the ADR 008 persistent-scanner work found and fixed four gaps: (1) `ibkr_bridge.apply_l1_quote`/`apply_table_quotes` now skip repricing any table whose `TableState` is frozen for the current session — previously HOD's reserved L1 pool could mutate a "frozen" table's cache via retained symbols; (2) `ibkr/scanner_l1.flush_loop` now tags `price_patch` batches by the symbols actually subscribed under `OWNER_SCANNER` (the live active tab), not by "whichever tab a client happens to be viewing" — HOD-only ticks for symbols outside the active tab are dropped instead of leaking into a frozen table's displayed row; (3) `ibkr/scanner_hydrate.hydrate_rows` now diffs against a per-table/session known-rows cache and cold-quotes only newly admitted symbols, preserving unchanged rows as the plan specified; (4) `evaluate_scanner_integrity` now accepts per-table `*_frozen` flags (sourced from `ibkr.scanner_session.is_table_frozen`) and passes a frozen table cleanly instead of failing/warning as its cache age grows by design. Also wired the previously-dead `frozenTableLabel()`/`tableMeta` plumbing into a visible "Frozen at HH:MM ET" badge above each scanner tab panel.
- **Why:** User asked for a detailed review of the just-completed ADR 008 work; the review found the immutability contract ("a frozen table's membership, rank, values, metadata, and timestamp cannot change") was violated at the backend-cache level and could leak through the WS relay, plus two functional gaps that were reported done in the earlier changelog entry but weren't actually wired up.
- **Files touched:** `backend/ibkr/scanner_session.py` (new `is_table_frozen`), `backend/ibkr_bridge.py`, `backend/ibkr/scanner_l1.py`, `backend/ibkr/scanner_hydrate.py`, `backend/integrity_live.py`, `backend/hod_momo_integrity_scanner.py`; frontend `ScannerTabPanels.tsx`, `TabModuleHost.tsx`, `DashboardPage.tsx`, `styles/scanner-l2.css`; tests: `test_ibkr_bridge.py`, `test_scanner_l1.py`, `test_scanner_session_adr008.py`, `test_hod_momo_integrity.py`, `test_integrity_live_builders.py`.
- **How it works now:** `ibkr.scanner_session.is_table_frozen(state, table)` is the single source of truth for "may this table's cache be mutated right now?" — shared by the one-shot runners (already gated), `ibkr_bridge`'s L1/snapshot reprice paths (newly gated), and integrity's freshness checks (newly bypassed when frozen). `scanner_l1.py` maintains `_active_tab_symbols` (updated every reconcile from the final `plan["tab"]`) and `flush_loop` filters `_pending` against it before tagging/pushing — a symbol only reaches the WS as a named table's row when it is actually subscribed there. `scanner_hydrate._known_rows[table]` persists hydrated rows across batches, reset whenever the session key changes; only symbols not already in that map get a cold `reqTickersAsync` call.
- **Verified by:** `py -3 -m pytest` (924 passed, incl. 8 new regression tests: frozen-cache-not-mutated / live-cache-still-reprices / flush_loop-drops-HOD-only-ticks / hydrate-preserves-unchanged / hydrate-drops-stale-symbols / hydrate-resets-on-rollover / frozen-integrity-passes / unfrozen-integrity-still-warns); `npx vitest run` (435 passed); `npm run build` (green).
- **Related:** PROBLEM_LOG 2026-07-23 — ADR 008 review found frozen-table mutation leak + three under-delivered plan items.

## 2026-07-23 — ADR 008 persistent scanner stream (shadow), freeze boundaries, table-scoped WS

- **What:** Landed the remaining Session-Owned Scanner Rosters plan: persistent IBKR `reqScannerSubscription` manager (`ibkr/scanner_stream.py` + hydrate/session helpers), 04:00-anchored freeze/rollover enforcement, table-scoped `/ws/scanner` events (`roster_replace` / `table_state` / `price_patch.table`), Error-322 recovery that skips desired persistent leases, and frontend consumers that stop IBKR structural REST polls once `IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=true`.
- **Why:** Finish ADR 008 after the HOD-narrowing checkpoint — replace poll inventiveness with push subscriptions while keeping one-shot caches authoritative until live Gateway shadow evidence is recorded.
- **Files touched:** `backend/ibkr/scanner_stream.py`, `scanner_session.py`, `scanner_hydrate.py` (new); `discovery.py` (lease-aware recover); `scan_loop.py`; `scanner_push.py`; `app_lifespan.py`; `scanner_runners/{discovery,movers,afterhours}.py`; `ibkr_bridge.py` / `scanner_l1.py`; `constants_ibkr.py`; `routes/health.py`; `frontend` scanner hooks + workspace config; `tests/test_scanner_session_adr008.py`.
- **How it works now:** With `IBKR_SCANNER_PERSISTENT_ENABLED=true` (default) the lifespan starts `scanner_stream.manager_loop` in **shadow** mode: it opens ≤2 persistent leases by session period, hydrates new symbols via cold `reqTickersAsync`, fences commits by READY generation + epoch + session key + live window, logs parity vs one-shot caches every 60s, and never writes authoritative caches until `IBKR_SCANNER_PERSISTENT_AUTHORITATIVE` (env) is flipped. Independently, `scan_loop` + runners refuse writes to frozen tables (Gappers @09:30, Gainers/Losers @16:00, AH @20:00) and rollover clears prior-session rows at the new 04:00 session key. `/ws/scanner` bootstrap includes per-table meta; L1 `price_patch` carries the dominant tab so a live Gainers tick cannot mutate a frozen Gappers row. Cutover is intentionally not flipped in this change.
- **Verified by:** `py -3 -m pytest` (916 passed); `npx vitest run` (435 passed); `npm run build` green; focused ADR tests in `test_scanner_session_adr008.py`.
- **Follow-ups:** Record live Gateway shadow evidence (batch cadence, membership delta, slot occupancy, reconnect), then set `IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=true` and confirm UI drops the 5s membership poll.
- **Related:** ADR 008; prior CHANGELOG groundwork entry same day.


- **What:** Implementing the "Session-Owned Scanner Rosters and HOD Eligibility" plan. This entry covers the foundational + HOD-narrowing phases: (1) recorded ADR 008 and updated `single-market-data-feed.mdc` + HOD docs with the session-owned persistent-scanner-roster model; (2) added per-table session metadata (`TableState`: `state`/`session_key`/`revision`/`roster_ts`/`quote_ts`/`frozen_at`) to `runtime_state`; (3) split Gainers/Losers on-disk persistence into independent `gainers-*.json` / `losers-*.json` files (was one combined `movers-*.json`) so one table's freeze/update can never advance the other's revision; (4) removed HOD's volume-seed scan (`hod_momo_seed.py`, `HOT_BY_VOLUME`/`TOP_VOLUME_RATE`/`MOST_ACTIVE`), the second `belowPrice=20` Gainers pass, open-ticker priority, Losers, and the rotating "explore" tail from HOD admission — `hod_momo_active.build_active_set()` is now a deterministic function of manual Former Momo (guaranteed) + round-robin across ranked Gappers/Gainers/Afterhours only; (5) HOD session-high now seeds from the symbol's *full current session* (04:00 ET forward, ~1000 one-minute bars) instead of the same 15-bar window used for the 5m/10m surge buffer; (6) advanced `HOD_MOMO_CONFIG_SCHEMA_VERSION` to 7 and repaired a historical bug where Squeeze strategies #10/#11 could persist with `surge_pct=0` while `surge_window_min` still matched the strategy default (a silent no-op filter); (7) fixed HOD UI jank — memoized `partitionScannerAlerts()`, extracted the HOD Momo / Running Up tab body into a `React.memo`'d `HodMomoSection` so the dashboard's 1Hz scanner-age clock can no longer force it to re-render, and coalesced the alert table's scroll handler to one windowing update per animation frame.
- **Why:** User-directed implementation of the finalized "Session-Owned Scanner Rosters and HOD Eligibility" plan (`session_scanner_rosters_8c8337bc.plan.md`). The scanner polling cadence constants were never an IBKR requirement (see ADR 008); HOD eligibility had grown a large invisible side-channel (volume seeds, sub-$20 pass, open-ticker priority) that the plan retires in favor of "HOD sees exactly what the user sees in a scanner tab, plus their own curated Former Momo list."
- **Files touched:** `architecture/decisions/008-persistent-ibkr-scanner-rosters.md` (new); `.cursor/rules/single-market-data-feed.mdc`; `docs/hod_brainstorming.html`, `docs/HOD-requirements.html`; `knowledge/obsidian/03-Nova-Decisions/IBKR-Scanner-HOD-Architecture.md`; `backend/runtime_state/state.py`; `backend/cache.py`; `backend/market.py` (new `session_key_et()`); `backend/websocket.py`, `backend/scan_runners.py`, `backend/scanner_runners/movers.py` (split gainer/loser persistence); `backend/hod_momo_active.py` (rewritten), `backend/hod_momo_universe.py` (rewritten), `backend/universe.py`, `backend/ibkr_bridge.py`, `backend/ibkr/discovery.py`, `backend/app_lifespan.py`, `backend/integrity_live.py`, `backend/hod_momo_integrity_hod.py`, `backend/routes/hod_momo.py`, `backend/hod_momo_admin.py` (Former Momo capacity guard), `backend/constants_ibkr.py`, `backend/constants_hod_momo.py`; deleted `backend/hod_momo_seed.py`; `backend/hod_momo_surge_seed.py` (full-session seed split from surge tail); `backend/constants_hod_momo.py` (schema v7), `backend/hod_momo_persist.py`; `frontend/src/pages/DashboardPage.tsx`, `frontend/src/components/TabModuleHost.tsx`, `frontend/src/hod_momo/HodMomoSection.tsx` (new), `frontend/src/hod_momo/HodMomoAlertTable.tsx`.
- **How it works now:** `hod_momo_active.build_active_set(gapper_rows, gainer_rows, afterhours_rows, priority_symbols, capacity)` admits manual Former Momo first (every registered symbol guaranteed — `hod_momo_admin.update_config` now rejects a `former_momo_list` longer than `HOD_MOMO_ACTIVE_SET_CAPACITY` outright instead of letting admission silently drop entries), then round-robins one symbol at a time across ranked Gappers/Gainers/Afterhours queues until capacity is full. `ibkr_bridge.refresh_hod_active_set()` rebuilds only when a version fingerprint (`id()`+`len()` of each scanner cache list, plus the Former Momo tuple) changes, not on a 30s timer. `hod_momo_surge_seed.surge_seed_loop` fetches one full-session bar set per admitted symbol (`HOD_MOMO_FULL_SESSION_BAR_LIMIT=1000`, filtered to the 04:00 ET session key via `market.session_key_et()`), seeds `session_high` from the max of the whole filtered set, and slices only the last 15 bars into the surge buffer — so a runner whose actual high happened 30+ minutes before joining the active set gets the correct floor instead of a falsely-low one. `runtime_state.TableState` (state/session_key/revision/roster_ts/quote_ts/frozen_at) exists on `gapper_table`/`gainer_table`/`loser_table`/`afterhours_table` but is not yet written by any producer — that wiring is the next phase (`enforce-freeze`/`build-scanner-manager`). `cache.save_gainer_snapshot`/`save_loser_snapshot` are now the write path; `load_movers_snapshot()` still exists and prefers the split files, falling back to the legacy combined `movers-*.json` only for whichever side has no independent file yet.
- **Verified by:** `py -3 -m pytest` (909 passed, 0 failed — previously-flaky `test_build_focus_universe_empty_inputs` order-dependency also disappeared once the retired seed test file was removed); `npx tsc -b && vite build` (frontend build green); `npx vitest run` (434 passed, including an updated RAF-aware scroll-virtualization test).
- **Follow-ups:** Build the persistent `ibkr/scanner_stream.py` manager, wire session rollover/freeze into `runtime_state.TableState`, extend `/ws/scanner` with typed roster/table-state events, update frontend hooks to consume them, then shadow-compare against the current one-shot path before cutover (remaining plan sections 2–4 and 7).
- **Related:** `architecture/decisions/008-persistent-ibkr-scanner-rosters.md`; plan `session_scanner_rosters_8c8337bc.plan.md`.

## 2026-07-23 — Clarify scanner-table windows and retained HOD rosters

- **What:** Revised the HOD requirements ledger so Gappers, Gainers, Afterhours, and manually registered Former Momo are the only allowed HOD provenance sources. Added explicit, non-overlapping table update windows: Gappers 04:00–09:30 ET, Gainers 04:00–16:00 ET, and Afterhours 16:00–20:00 ET; each table freezes at its end boundary.
- **Why:** The draft persistent-subscription schedule incorrectly kept Gappers live during RTH and Gainers live during afterhours, contradicting the original requirement to preserve completed morning/RTH scanner snapshots.
- **Files touched:** `docs/hod_brainstorming.html`; implementation plan `hod_top_gainers_only_17f4fd86.plan.md`.
- **How it works now:** The specification distinguishes frozen table state from HOD evaluation. Membership, rank, displayed price/change/volume, and cache timestamp stop changing at 09:30/16:00/20:00 respectively, while retained symbols may still receive separate HOD-owned L1 inside the bounded active pool without mutating the frozen table.
- **Verified by:** Python HTML parse plus browser render of `hod_brainstorming.html`; requirement/UML search found no remaining “Gainers-only” or “Gappers excluded” contradictions.
- **Follow-ups:** Runtime subscription ownership, freeze gates, and WebSocket roster delivery remain pending in the active HOD scanner plan.
- **Related:** `REQ-HOD-001`, `REQ-HOD-002`, `REQ-HOD-003`, `REQ-HOD-007`.

## 2026-07-23 — Integrity self-heals on Gateway reconnect; Error 322 recovers + retries instead of going silently empty

- **What:** Two additions on top of the earlier Error-322 leak fix: (1) reconnecting to IB Gateway now clears any sticky `ibkr_bridge_last_error` left over from the disconnect window as soon as the session reaches READY, and a successful movers refresh clears it on losers landing rows too (not just gainers); (2) IBKR Error 322 (scanner slot exhausted) is now detected via `errorEvent` and triggers one surgical recovery-and-retry instead of silently resolving to an empty result.
- **Why:** After a brief Gateway drop + reconnect, gainers/losers were already fresh but the Integrity banner stayed red — the sticky bridge error from the outage never got cleared, and previously required a full API process restart to clear. Separately, `ib_async` defaults to `RaiseRequestErrors=False`, so a live Error 322 during a scan looked identical to "market has 0 rows" — no signal existed to recover the leaked slot without a Gateway/API restart.
- **Files touched:** `backend/ibkr/client.py`, `backend/scanner_runners/movers.py`, `backend/ibkr/discovery.py`, `backend/ibkr/errors.py`, `backend/constants_ibkr.py`, `backend/tests/test_ibkr_client_readiness.py`, `backend/tests/test_scan_runners.py`, `backend/tests/test_ibkr_discovery_fail_loud.py`.
- **How it works now:** `ibkr/client.py._clear_sticky_bridge_error_on_ready()` runs at both `session_state.set_ready()` call sites in `reconnect_loop()`. `discovery._one_shot_scanner()` registers a scoped `errorEvent` listener that flags Error 322 for the matching reqId and raises `IbkrScannerSlotExhaustedError` (new, in `ibkr/errors.py`) instead of trusting the future's `[]` result; `scan_symbols()` catches it once via `_scan_once_with_recovery()`, calls `discovery.recover_scanner_slots(ib)` (cancels tracked in-flight reqIds + any `ScanDataList` entry in `ib.wrapper.reqId2Subscriber`, never mktData/order subscribers, never disconnects), and retries the scan once under the same `_scan_lock`. A second consecutive Error 322 surfaces as a normal `IbkrDiscoveryError`.
- **Verified by:** `py -3 -m pytest backend/tests/test_ibkr_discovery_fail_loud.py backend/tests/test_ibkr_discovery.py backend/tests/test_ibkr_client_readiness.py backend/tests/test_scan_runners.py` (40 passed) + full `backend/tests` suite (910 passed, 1 pre-existing unrelated failure — `test_build_focus_universe_empty_inputs`, local cache pollution, not touched by this change).
- **Follow-ups:** `_inflight_scan_reqids` is not cleared on a full IB reconnect (new socket session invalidates old reqIds) — low-risk since a fresh `IB()` instance also gets a fresh `wrapper.reqId2Subscriber`, but worth revisiting if a future change reuses the tracked set across reconnects.
- **Related:** PROBLEM_LOG 2026-07-23 "Integrity banner stayed red after Gateway re-login; Error 322 silently returned empty instead of raising".

## 2026-07-23 — Fix IBKR scanner subscription leak (Error 322 root cause)

- **What:** One-shot IBKR market scans now always cancel their scanner subscription, including on timeout. Concurrent one-shots are serialized so Nova does not occupy more than one of IBKR's 10 API scanner slots.
- **Why:** Live logs showed continuous `Error 322: Only 10 simultaneous API scanner subscriptions are allowed` — the Integrity fail / empty losers / empty volume seeds were symptoms of leaked subscriptions after `asyncio.wait_for` abandoned `reqScannerDataAsync` before its cancel ran.
- **Files touched:** `backend/ibkr/discovery.py`, `backend/tests/test_ibkr_discovery.py`, `backend/tests/test_ibkr_discovery_fail_loud.py`.
- **How it works now:** `_one_shot_scanner()` opens with `reqScannerSubscription`, waits with a local timeout, and cancels in `finally`. A process-wide scan lock serializes callers (movers, gapper fallback, HOD seeds). After deploy, restart the API (or reconnect Gateway) once to clear any slots already leaked by the old process.
- **Verified by:** `py -3 -m pytest tests/test_ibkr_discovery.py tests/test_ibkr_discovery_fail_loud.py` (22 passed), including timeout-must-cancel regression.
- **Related:** PROBLEM_LOG 2026-07-23 "IBKR Error 322: scanner subscription leak on wait_for timeout".

## 2026-07-23 — Stop sticky TOP_PERC_GAIN timeout from painting Integrity fail all day

- **What:** A recovered Top Gainers feed no longer leaves a permanent red Integrity fail banner. Successful movers refresh clears sticky `ibkr_bridge_last_error`; scanner integrity demotes leftover bridge errors to warn when gainer cache is fresh; empty/stale losers alone cannot fail the merge when gainers are live.
- **Why:** User screenshot still showed `scanner_ibkr_bridge ... TOP_PERC_GAIN timed out` ~173s later (plus `scanner_losers` empty) after REQ-HOD-004 fixed alert mute but left the banner on the flat merged status.
- **Files touched:** `backend/scanner_runners/movers.py`, `backend/hod_momo_integrity_scanner.py`, `backend/tests/test_scanner_integrity_mode.py`, `backend/tests/test_scan_runners.py`, `docs/hod_brainstorming.html`.
- **How it works now:** RTH gainers success clears the sticky bridge error the same way premarket gappers success already did. Integrity only hard-fails `scanner_ibkr_bridge` when the error is still set *and* gainer cache is empty/stale. Losers are treated as a secondary UI list when Top Gainers is healthy.
- **Verified by:** `py -3 -m pytest tests/test_scanner_integrity_mode.py tests/test_scan_runners.py` (15 passed).
- **Related:** PROBLEM_LOG 2026-07-23 "Sticky scanner_ibkr_bridge Integrity fail banner after TOP_PERC_GAIN timeout"; REQ-HOD-004 (alert mute already shipped).

## 2026-07-23 — HOD requirements ledger (REQ-HOD-004/005/006): scope integrity suppress to HOD, Former Momo manual-only

- **What:** Three related HOD Momo fixes captured as requirements in `docs/hod_brainstorming.html` (Requirements ledger + REQ-HOD-004/005/006) and shipped end-to-end: (1) `integrity_fail_suppress` is now scoped to HOD-only integrity status, so an unrelated scanner-tab bridge failure can no longer mute HOD alerts; (2) Former Momo's `former_momo_list` is now strictly manual (no more auto-add-on-any-alert-fire or bootstrap-from-alert-history on every restart); (3) Former Momo members get guaranteed HOD active-set admission (live L1 + tracking) via the same `build_active_set()` pipeline every Top Gainer already flows through, seeded with a one-time default of `["SPRC"]`.
- **Why:** User-driven HOD requirements pass — narrowing HOD focus to Top Gainers (Losers/Gappers/volume-seeds excluded, tracked separately as REQ-HOD-001/002/003) surfaced that (a) the integrity suppress gate was flat-merged across unrelated scopes (see PROBLEM_LOG 2026-07-23 "HOD alerts muted by scanner-bridge TimeoutError"), and (b) Former Momo was silently mutating itself instead of being the user-curated watchlist it was meant to be.
- **Files touched:** `backend/integrity_live.py` (new `hod_integrity_is_failing()`), `backend/hod_momo_trade.py`, `backend/hod_momo_former.py`, `backend/hod_momo_persist.py`, `backend/ibkr_bridge.py`, `backend/universe.py`, `backend/constants_hod_momo.py` (`HOD_MOMO_FORMER_MOMO_DEFAULT_LIST`, schema v6), `backend/hod_momo_models.py` (copy mutable per-strategy defaults instead of sharing one list object), `docs/hod_brainstorming.html`, tests below.
- **How it works now:** `hod_momo_trade.on_trade_update`'s suppress check calls `integrity_live.hod_integrity_is_failing()` (reads only the cached `hod` partition of the merged report) instead of the flat `integrity_is_failing()` — a scanner-only fail no longer blocks strategy fires; a genuine `hod`-scope fail still does. `hod_momo_former.former_momo_priority_symbols()` returns strategy 1's `former_momo_list` (order-preserving, dedup'd) and is now the single input to both `ibkr_bridge.refresh_hod_active_set()`'s `priority_symbols` and `universe.refresh_hod_momo_universe()`'s `extra_symbols`, replacing `hod_momo_session_focus.session_focus_active_priority()`/`session_focus_extra_symbols()` (alert-history + sticky-memory — the sticky half was already dead code in production). `remember_former_momo()` and `bootstrap_former_momo_from_alerts()` are deleted; the list only changes via the strategy-1 config API. A one-time schema v6 migration seeds `["SPRC"]` if the persisted list is still empty (never overwrites a customized list). `hod_momo_session_focus.py` itself is untouched and still unit-tested, just no longer called from the active-set build path.
- **Verified by:** `py -3 -m pytest` — full backend suite: 895 passed, 1 pre-existing unrelated failure (`test_hod_momo_universe.py::test_build_focus_universe_empty_inputs`, confirmed failing identically on `git stash`-ed pre-change code — local cache-file pollution, not this change). New/updated tests: `test_hod_momo_former.py` (`former_momo_priority_symbols` manual-only), `test_hod_momo_engine.py` (`integrity_fail_suppress_blocks_on_hod_scope_fail` / `_ignores_scanner_only_fail`), `test_integrity_live_builders.py` (`hod_integrity_is_failing_scoped_to_hod_partition`).
- **Related:** PROBLEM_LOG 2026-07-23 "HOD alerts muted by scanner-bridge TimeoutError (integrity_fail_suppress)" and "Former Momo silently auto-grew forever + re-seeded from alert history on every restart".

## 2026-07-23 — API/IBKR lifecycle hardening: honest readiness, cancellable bridge calls, single restart supervisor

- **What:** Corrected the earlier "shared thread pool" diagnosis for the 10:18–10:19 restart cascade (it was a dev hot-reload race, not a health/scan pool conflict — see PROBLEM_LOG below). Added an explicit IBKR session-readiness state machine, made the sync→async IBKR bridge cancel on timeout and reject stale-generation results, added instance/liveness/loop-lag telemetry, and replaced arbitrary port-killing in the dev API launcher with an owned, locked restart flow.
- **Why:** Two real defects let background IBKR work run against a half-initialized or already-replaced broker session, and the dev restart path could kill an unrelated process or race a second API start on :8000. Full plan: `api_ibkr_lifecycle_hardening_24083047.plan.md`.
- **Files touched:** `backend/ibkr/session_state.py` (new), `backend/ibkr/client.py`, `backend/ibkr/account.py`, `backend/ibkr/discovery.py`, `backend/ibkr/errors.py`, `backend/ibkr_bridge.py`, `backend/instance_identity.py` (new), `backend/loop_lag.py` (new), `backend/app_lifespan.py`, `backend/routes/health.py`, `backend/constants_ibkr.py`, `backend/constants_scanner.py`, `frontend/src/types/health.ts`, `frontend/scripts/vite-nova-start-api.ts`, `frontend/electron/sidecar.mjs`, `scripts/Stop-NovaPorts.ps1`, plus new/updated backend and frontend tests.
- **How it works now:** `ibkr.client.get_ib()` returns the live `IB` instance only once Nova's own session state reaches `READY` (transport connected *and* account-kind validated *and* positions/completed-orders caches warmed) — not merely "socket connected." Every transition into `READY` bumps a monotonic generation counter; `run_coro()` captures the generation before bridging a coroutine onto the IBKR loop and raises `StaleIbkrSessionError` if a reconnect happened mid-call, and it now cancels the underlying future on timeout instead of abandoning it. `reqScannerDataAsync` and the batch `qualifyContractsAsync` inside `snapshot_quotes()` each carry their own bounded timeout inside the outer bridge ceiling, so a hung scanner/qualify call is attributable and cancellable rather than indistinguishable from any other bridge timeout. `/api/health` now reports per-process `instance_id`/pid/reload state and event-loop lag; `/livez` is a minimal loop-liveness probe and `/readyz` reports bootstrap + IBKR session readiness (503 until ready). The Vite dev plugin acquires a file-based lock before starting/killing the API, requires HTTP 200 + a valid JSON body + a *new* `instance_id` before declaring a restart successful, and `Stop-NovaPorts.ps1` only force-stops processes it can identify as Nova-owned (`run_api.py`/`uvicorn`/`vite`), warning instead of killing anything else.
- **Verified by:** `py -3 -m pytest backend/tests/test_ibkr_session_state.py backend/tests/test_ibkr_client_readiness.py backend/tests/test_instance_identity.py backend/tests/test_routes_health_live_ready.py backend/tests/test_ibkr_account.py backend/tests/test_ibkr_discovery_fail_loud.py backend/tests/test_ibkr_discovery.py` (all pass) and a full `py -3 -m pytest` run (892 passed, 1 pre-existing unrelated failure in `test_hod_momo_universe.py` from local cache-file pollution, untouched by this change).
- **Follow-ups:** The plan's scope boundary explicitly defers a full `IbkrRuntime` actor rewrite unless the new loop-lag/readiness telemetry later shows continued contention. `frontend/scripts/vite-nova-start-api.test.ts` covers the lock-staleness helper only; full restart-coalescing/reload-detection behavior still needs a manual Windows soak per the plan's step 5 (concurrent restarts, WatchFiles rapid-write, IBKR reconnect mid-call).
- **Related:** PROBLEM_LOG 2026-07-23 "API restart cascade" correction entry; `api_ibkr_lifecycle_hardening_24083047.plan.md`.

## 2026-07-23 — PROBLEM_LOG mandatory for every agent

- **What:** Bug-fix logging is now an explicit constitution-level requirement for every agent (parent + specialists). Lifecycle footers must declare `problem_log=`; the subagentStop hook reminder and contract regex enforce the footer shape.
- **Why:** User asked to make PROBLEM_LOG mandatory project-wide; it was rule-guided before but easy to skip without a Lifecycle field.
- **Files touched:** `.cursor/rules/problem-log.mdc`, `constitution.mdc`, `self-annealing.mdc`, `specialist-routing.mdc`, `task-log.mdc`, `contract.json`, agent prompts, `docs/agent-operations.md`, `gemini.md` / `AGENTS.md`, `PROBLEM_LOG.md` header, hook + tests.
- **How it works now:** Fix a bug → prepend `PROBLEM_LOG.md` same session → Lifecycle `problem_log=<YYYY-MM-DD title>` (or `skipped`/`n/a` only when no bug). Missing full Lifecycle (including `problem_log=`) triggers one fail-open reminder for Nova specialists.
- **Verified by:** `py -3 -m pytest tools/test_subagent_lifecycle_hook.py -q`; `py -3 tools/agent_contract.py --ci`.
- **Related:** task-log `knowledge/task-log/2026-07-23-mandatory-problem-log.md`.

## 2026-07-23 — Prevent API_WEDGED (async health + dedicated scan pool)

- **What:** `/api/health` is async (never parks on the default thread pool). `scan_loop` IBKR/Alpaca work runs on a dedicated `scan_executor` (2 workers) so 25s bridge waits cannot starve health.
- **Why:** WEDGED was not “API dead” — default executor was saturated by scan `run_coro` waits, so health probes timed out.
- **Files touched:** `routes/health.py`, `scan_executor.py`, `scan_loop.py`, `constants_scanner.py`, `app_lifespan.py`, tests.
- **How it works now:** Liveness stays responsive while scanners may still time out / keep last-good. Auto-heal remains a backstop.
- **Verified by:** pytest `test_scan_executor.py`.

## 2026-07-23 — Auto-heal API_WEDGED / API_DOWN (Start API once)

- **What:** When the header diagnoses `API_WEDGED` or `API_DOWN`, `BackendStartButton` auto-calls `startLocalApi` once per browser session (dev / Electron). Manual Start API still works.
- **Why:** Hung uvicorn (IBKR bridge timeouts starving the event loop) left users on a click-only "Start API" screen even though Vite can kill+restart port 8000.
- **Files touched:** `backendAutoHeal.ts`, `BackendStartButton.tsx`, `chart_api.ts` hints, tests.
- **How it works now:** First WEDGED/DOWN → auto-restart via `/__nova/start-api` or Electron sidecar; sessionStorage prevents loops. Prod web (no spawn) stays manual.
- **Verified by:** Vitest `backendAutoHeal.test.ts`.

## 2026-07-23 — App shell auto-recover on provider/context crashes

- **What:** `AppErrorBoundary` detects fatal shell errors (`useWorkspace must be used within…`, invalid hook call) and hard-reloads once (sessionStorage guard). Soft Retry remounts with a key for other errors; fatal Retry = full reload. Outer `app-shell` boundary wraps `AppShell`.
- **Why:** Vite HMR context skew left users on a dead Retry screen with no recovery.
- **Files touched:** `AppErrorBoundary.tsx`, `appErrorRecovery.ts`, `App.tsx`, tests.
- **How it works now:** Fatal → “Recovering — reloading Nova…” once; second failure shows “Reload Nova” (no loop). Non-fatal → soft remount.
- **Verified by:** Vitest `appErrorRecovery.test.ts`, `AppErrorBoundary.test.tsx`.

## 2026-07-23 — IBKR-only scanner discovery (retire Alpaca soft-toggle)

- **What:** Locked scanner discovery to IBKR. Defaults/options are `ibkr` only; Settings no longer offers Alpaca as Scanner Source (read-only Gateway line); `/api/config` coerces/persists `ibkr` even if a client sends `alpaca`. Header aux chip renamed `News` so green OK cannot be read as scanner feed. Attribution + rules updated.
- **Why:** Product invariant — Alpaca must never be a scanner source. Soft-toggle left defaults at `alpaca`, a boot race that showed `FEED: Alpaca IEX`, and a Settings save path that could overwrite `.env`.
- **Files touched:** `constants_ibkr.py`, `alpaca.py`, `routes/health.py`, `SettingsPanel.tsx`, `DashboardTab.tsx`, `useSettingsForm.ts`, `workspaceConfig.ts`, `dataSourceMap.ts`, `market_ui.ts`, `HeaderConnectionStatus.tsx`, `single-market-data-feed.mdc`, decision note, tests.
- **How it works now:** Scanner/quote/chart/L2/T&S = IBKR. Alpaca = news + listing metadata only. Stale `NOVA_DISCOVERY_PROVIDER=alpaca` coerces to `ibkr` at runtime and on Settings save.
- **Verified by:** pytest `test_discovery_provider_lock.py`; Vitest header/workspace/dataSourceMap/SettingsWorkspace.
- **Follow-ups:** Residual honesty copy cleaned (Volume/RVOL label, TradingTab, HOD YF title, `.env.example`, data-sources hint) after explore inventory.
- **Related:** `knowledge/obsidian/03-Nova-Decisions/Scanner-Provider-IBKR-Primary.md`.

## 2026-07-23 — Daily auto-start (Gateway + Nova API/UI)

- **What:** Added `scripts/Start-NovaDaily.ps1` (idempotent morning bootstrap: IBC Gateway → API → UI → browser) plus `scripts/Install-NovaDailyTask.ps1` to register a Windows Scheduled Task (default: daily 6:00 AM + AtLogon). Convenience launcher `Start Nova Daily.bat`.
- **Why:** User does not want to manually start Nova/Gateway every trading day.
- **Files touched:** `scripts/Start-NovaDaily.ps1`, `scripts/Install-NovaDailyTask.ps1`, `Start Nova Daily.bat`, `docs/ibc-gateway-setup.md`.
- **How it works now:** Run `.\scripts\Install-NovaDailyTask.ps1` once. Task runs `Start-NovaDaily.ps1`, which skips already-healthy ports/processes. IBC credentials stay under `%USERPROFILE%\.nova\ibc\`. Log: `backend/logs/daily-start.log`. 2FA on phone may still be required.
- **Verified by:** Script syntax load; task register path documented; IBC launcher paths already present on this machine.
- **Follow-ups:** User must run Install once (or ask agent to). Wake timers needed if PC sleeps through 6am.
- **Related:** `docs/ibc-gateway-setup.md` § Daily auto-start.

## 2026-07-22 — Quiet Sentry noise (IBKR benign logs + Object is disposed)

- **What:** Extended `IBKR_BENIGN_LOG_ERROR_CODES` / message needles so ib_async ERROR spam (300, 10089/10189/354, open/completed-orders timeouts, Gateway port/ConnectionRefused reconnect chatter) downgrades to WARNING before Sentry. Client intake ignores TradingView `Object is disposed`. Left Error 101 (max tickers) as ERROR — real capacity signal.
- **Why:** Sentry `python-fastapi` was yelling with tens of thousands of expected Gateway/reconnect/chart-dispose events, drowning real issues.
- **Files touched:** `backend/constants_ibkr.py`, `backend/routes/client_errors.py`, `backend/tests/test_ibkr_log_filters.py`, `backend/tests/test_client_errors.py`.
- **How it works now:** Same `BenignIbkrErrorFilter` path as 162/365; new codes/needles match live issues PYTHON-FASTAPI-C/-F/-PN/-SW/-SN/-2S. `Object is disposed` never mirrors to Sentry. Restart API to load filters.
- **Verified by:** pytest log-filter + client-errors tests; Sentry triage of last-24h unresolved.
- **Follow-ups:** Error 101 max-tickers still needs HOD/scanner subscription budgeting (not silenced).
- **Related:** PYTHON-FASTAPI-126 (`closedFilterFromToday`) was a one-shot HMR crash during Orders Today refactor — already fixed in `7c95889`.

## 2026-07-22 — Vitest: enable React 19 act() environment

- **What:** Vitest now loads a tiny setup file that sets `globalThis.IS_REACT_ACT_ENVIRONMENT = true` so React 19 treats tests as an act-capable environment. Follow-up: `WorkspaceContext.test.tsx` defers the mocked `/api/config` fetch so defaults can be asserted while pending, then releases under `await act` (and flushes config before symbol updates).
- **Why:** Without the flag, every hand-rolled `createRoot` + `act()` test printed `The current testing environment is not configured to support act(...)`, and React also disabled the real “update was not wrapped in act(...)” safety net (audit 2026-07-20). After the flag, the deferred WorkspaceProvider config `setState` still needed an act flush.
- **Files touched:** `frontend/src/testSetup/reactActEnvironment.ts` (new), `frontend/vite.config.ts` (`test.setupFiles`), `frontend/src/workspace/WorkspaceContext.test.tsx`.
- **How it works now:** `vite.config.ts` registers `./src/testSetup/reactActEnvironment.ts` as the only Vitest setup file. That module sets the React 19 global before any test runs. Product code / `constants.ts` / `App.tsx` are untouched. Manual-mount tests keep using `createRoot` + `act` (no RTL). WorkspaceProvider tests hold config fetch until after the defaults assertion, then drain under `act`.
- **Verified by:** `npx vitest run --reporter=verbose` → 99 files / 422 tests passed; zero “not configured to support act” and zero “was not wrapped in act(...)” warnings.
- **Follow-ups:** none for act warnings.
- **Related:** PROBLEM_LOG 2026-07-22 fixed entry; diagnosed 2026-07-20; task-log `knowledge/task-log/2026-07-22-vitest-act-environment-fix.md`.

## 2026-07-22 — Orders (Today): warm completed orders + honest badge/empty

- **What:** Closed Orders now warms from IBKR `reqCompletedOrdersAsync` after every Gateway connect (same lifecycle as positions). Orders (Today) badge counts symbol-scoped **working + real closed** for the active filter; empty copy distinguishes “no completed orders from Gateway yet” vs “no orders for this symbol in this filter.”
- **Why:** Positions could show an open long while Orders (Today) stayed empty — Closed Orders only saw fills witnessed on the current API socket, never Gateway’s completed-order stream. Badge was working-only; empty gate ignored symbol filter.
- **Files touched:** `backend/ibkr/account.py` (`refresh_completed_orders_cache`, single-flight + timeout), `backend/ibkr/client.py`, `backend/ibkr/orders.py` (`closed_orders_async`, Filled-qty inference), `backend/routes/trading.py`, `backend/constants_ibkr.py` (`IBKR_COMPLETED_ORDERS_TIMEOUT_SEC`); `frontend/src/orders_today/*`, `frontend/src/stock_view/StockViewOpenOrdersDock.tsx`, `stockViewDockPersist.ts`, `constantGroups/chart_api.ts`.
- **How it works now:** Connect → `reqPositionsAsync` + `reqCompletedOrdersAsync(False)` under a lock and 10s ceiling. ib_async merges completed trades into `ib.trades()`; `closed_orders()` filters terminal statuses as before. First empty `GET /api/ibkr/orders/closed` retries one warm. Trades that arrive as `Filled` with zero fill counters get `filled_qty = qty`. UI badge uses `ordersTodayBadgeCount` (never closed sample rows).
- **Verified by:** pytest `test_closed_orders` / `test_ibkr_account` (timeout + single-flight); Vitest orders_today + dock badge; live log `completed-orders cache refreshed after connect`; `GET /orders/closed` returns promptly. **No live trades placed.** Remaining fractional IBKR position with empty closed list is consistent with IBKR having no *session* completed orders for today.
- **Follow-ups:** If a same-day fill is still missing after Read-Write API is confirmed, check Gateway completed-order retention for that fill — not a silent empty disguise.
- **Related:** PROBLEM_LOG 2026-07-22 completed-orders hang; task-log `knowledge/task-log/2026-07-22-orders-today-completed-orders.md`.

## 2026-07-22 — Closed Orders "Time Filled" column (real broker fill clock)

- **What:** Closed Orders now has a dedicated first column, **Time Filled**, showing IBKR's real fill clock (max `Trade.fills[].execution.time`) separate from the existing audit-grade **Time Placed** (`submitted_at`, unchanged). Shows `—` for orders that never filled (straight cancel/reject); shows the real fill time for filled and partial-then-cancelled rows.
- **Why:** Users had no way to see when an order actually filled — only when it was placed. Time Placed intentionally never updates on fills (to stay audit-grade / non-crawling), so the real fill moment was invisible in the UI even though IBKR already reports it per-fill.
- **Files touched:** `backend/ibkr/order_times.py` (`extract_trade_times` now returns a 3-tuple `(submitted_at, updated_at, filled_at)`), `backend/ibkr/orders.py` (`_trade_to_order_row` adds `filled_at`), `backend/tests/test_order_times.py`; `frontend/src/ibkr/types.ts` (`IbkrOrder.filled_at`), `frontend/src/ibkr/orderTableColumns.ts` (`ClosedOrderColumnId`, `CLOSED_COLUMN_META`, `DEFAULT_CLOSED_ORDER_COLUMNS`), `frontend/src/ibkr/orderDisplay.ts` (`orderFilledIso`, `orderFilledTimeTitle`), `frontend/src/ibkr/orderTableSort.ts` (sortable, defaults desc like Time Placed), `frontend/src/closed_orders/closedOrderCells.tsx`, `frontend/src/closed_orders/mockClosedOrders.ts`, `frontend/src/constantGroups/chart_api.ts` (`ORDER_TABLE_COLUMNS_STORAGE_KEY` bumped `v4`→`v5`, `ORDER_TABLE_DATA_SORT_KEYS` gains `filled_at`).
- **How it works now:** `extract_trade_times` computes `filled_at` as the ISO UTC of the latest fill execution time only (never falls back to log/cancel time — that stays `updated_at`'s job), so `filled_at` is `null` whenever `fills` is empty. Closed Orders defaults to `['filled_at', 'time', 'type', 'symbol', 'qty', 'status', 'filled', 'limit', 'avg_fill', 'order_id']` — Time Filled first, Time Placed second, everything else unchanged. Working Orders columns are untouched (non-goal). The storage-key bump means existing users' saved Closed Orders column order picks up the new first column instead of silently omitting it.
- **Verified by:** New pytest cases in `test_order_times.py` (filled → `filled_at` set; cancelled-no-fills → `filled_at is None`) plus updated `test_trade_to_order_row_*` assertions; full backend suite green (850/851, one pre-existing unrelated flaky HOD-universe test isolated and confirmed failing identically on `master` before this change). New/updated Vitest coverage in `orderTableColumns.test.ts`, `orderTableSort.test.ts`, `closedOrderCells.test.tsx`; full frontend suite green (415/415). Live browser check on the running dev app (Stock View → AAPL → Orders (Today) → sample Closed Orders): Time Filled renders first showing the correct ET fill time for Filled/partial-cancel rows and `—` for zero-fill Cancelled/Inactive rows, while Time Placed is unchanged.
- **Follow-ups:** Companion fix for "Orders (Today) empty despite an open position" (warm `reqCompletedOrdersAsync`, honest badge/empty-state) tracked separately in the same plan.

- **What:** HOD Momo / Running Up rows no longer move or re-stamp when a symbol re-fires — each collapsed row's `id`/`timestamp`/position are now pinned to the ticker's first catch of the day, ordered by first-catch time (newest catch on top), while price/rvol/change%/badges still update live from the newest fire. Separately, `HodMomoAlertTable` now uses true fixed-window virtualization (mounts only the visible viewport + a small overscan buffer, ~54 rows) instead of an unbounded "load more on scroll" batch-append, so a full day with thousands of alerts stays a flat DOM footprint.
- **Why:** User report: rows were "not coming like a record… they're moving, they're just getting re-ordered." Root cause was `collapseAlertsBySymbol` anchoring each collapsed row's identity to whichever occurrence it happened to encounter first while walking the newest-first alert feed — since a re-fire is always newest, it kept becoming that row's new "first occurrence," yanking the row's position and stamp forward every time. Separately, the old scroll-triggered batch table only ever grew (`renderedCount += 40`, never shrank), risking browser lag on long sessions with thousands of alerts.
- **Files touched:** `frontend/src/hod_momo/collapseAlertsBySymbol.ts` (+ test), `frontend/src/hod_momo/HodMomoAlertTable.tsx` (+ new `HodMomoAlertTable.test.ts`, `HodMomoAlertTable.render.test.tsx`), `frontend/src/hod_momo/HodMomoAlertRow.tsx`, `frontend/src/hod_momo/hodMomo.css`, `frontend/src/constantGroups/chart_api.ts` (`HOD_MOMO_OVERSCAN_ROWS`, `HOD_MOMO_MAX_INLINE_STRATEGY_PILLS`; removed `HOD_MOMO_RENDER_BATCH_SIZE` / `HOD_MOMO_LOAD_MORE_THRESHOLD_PX`).
- **How it works now:** `collapseAlertsBySymbol` still merges strategy tags/burst badges/live snapshot fields exactly as before, but after that merge it finds each ticker's oldest (first-catch) occurrence in the full-session `alerts` array and overrides the collapsed row's `id`/`timestamp`/`created_ts` with it, then sorts rows by that anchor descending. `HodMomoAlertTable` tracks `scrollTop` and derives `{startIndex, endIndex}` via the pure `computeVisibleRowRange(scrollTop, total, rowHeight, viewportHeight, overscan)` helper, rendering only `alerts.slice(startIndex, endIndex)` plus two spacer `<tr>`s sized to keep the scrollbar honest for the full list. Row height is enforced uniform (32px) by capping inline strategy pills to `HOD_MOMO_MAX_INLINE_STRATEGY_PILLS` with a "+N" overflow chip (full list still in the `title` tooltip), which the fixed-height windowing math depends on.
- **Verified by:** New/updated Vitest coverage (`collapseAlertsBySymbol.test.ts`, `HodMomoAlertTable.test.ts` for the windowing math, `HodMomoAlertTable.render.test.tsx` mounting a real 5,000-row synthetic feed and asserting mounted `<tr class="hod-alert-row">` count stays bounded before/after a deep scroll); full frontend suite (412 tests) + `npm run build` + ESLint all green; live browser check against the running IBKR-connected session confirmed exactly 42 rows mounted at `scrollTop=0` (matches `30 visible + 12 overscan`), no new console errors, and rows still sorted newest-catch-first with intact "(N in Xsec)" burst badges.
- **Related:** `PROBLEM_LOG.md` 2026-07-21 entry.

## 2026-07-21 — Drop misleading "paper by default" from IBKR order disclosure

- **What:** Flatten / place-order dialogs and the trading action bar no longer say orders are "(paper by default)". Copy is now: "Orders go through Interactive Brokers only. Alpaca scanning stays read-only."
- **Why:** On a live session the static disclaimer sat above a correct "on the LIVE account?" line and looked like a silent downgrade to paper. It was never mode-aware — only an architecture reminder.
- **Files touched:** `frontend/src/constantGroups/chart_api.ts` (`TICKER_TRADE_ORDER_DISCLOSURE`).
- **How it works now:** Disclosure always states IBKR-only + Alpaca read-only. Per-order account mode still comes from the dynamic `${mode.toUpperCase()} account` line (and header Live/Paper badge). Spend gates unchanged.
- **Verified by:** String grep confirms no remaining "paper by default"; constant readback; callers still import the same constant.

## 2026-07-21 — Bidirectional IBKR Gateway auto-detect (paper↔live heal)

- **What:** When the preferred Gateway port is hard-refused but the alternate port answers, Nova now self-heals in **either** direction (live→paper or paper→live), persists `IBKR_GATEWAY_MODE`, and shows online with the logged-in account kind. Session acceptance requires `accounts_match_mode` for both paper and live. Spend gates unchanged.
- **Why:** Operator expectation — Gateway chip should reflect whether IBKR is logged in (and paper vs live), not stay “offline · PAPER” while a live Gateway is already up. The old one-directional paper pin was a display/context guard for Phase B, not order safety.
- **Files touched:** `backend/ibkr/account_kind.py`, `client.py`, `gateway_heal.py`, `client_connect.py`, related tests; `.cursor/rules/ibkr-gateway-login-warning.mdc`, `docs/ibc-gateway-setup.md`, `Nova-Roadmap-Status.md`.
- **How it works now:** Preferred port refused → try alternate → classify managedAccounts → accept only if kind matches the mode being established → persist mode. Intentional capsule switches still suppress heal mid-switch. Timeouts / Error 326 still not heal-eligible. Orders still require `IBKR_ORDERS_ENABLED` + live confirm for live spends.
- **Verified by:** `pytest tests/test_gateway_heal.py tests/test_ibkr_account_kind.py tests/test_gateway_mode_switch.py tests/test_port_diagnostics.py` (28 passed); manual `/api/ibkr/status` with live-only Gateway; header badge check.
- **Follow-ups:** Phase B shadow days remain operator discipline (prefer paper Gateway logged in); not a hard software block anymore.

## 2026-07-20 — Root-cause fix: execution/executor/routes-trading tests leaked real env + real bootstrap

- **What:** Paper-simulating test helpers (`test_execution_service.py`, `test_executor.py`, `test_routes_trading.py`) now pin `IBKR_GATEWAY_MODE=paper` explicitly instead of relying on the developer's real `.env`; `test_routes_trading.py` also isolates `journal.db` / `nova_os.events_db` cache dirs and stubs `app_lifespan._bootstrap_runtime` (real IBKR ping + risk/journal reconstruction) so its module-level `TestClient(app)` can't fire a real background bootstrap against real files; `strategy.risk.reset_day()` added to the shared autouse fixtures.
- **Why:** 18 backend tests started failing after `.env`'s `IBKR_GATEWAY_MODE` was manually flipped to `live` earlier the same day — `ibkr/safety.py::assert_orders_allowed()` reads that env var directly, a path none of the "paper" test helpers ever mocked. Self-annealing investigation (not a symptom patch) traced it to a real test-isolation gap, not flaky infra.
- **Files touched:** `backend/tests/test_execution_service.py`, `test_executor.py`, `test_routes_trading.py`.
- **How it works now:** Any test that arms "paper" gates via `_arm_paper()` / `_arm_ibkr_execution()` / `_arm_paper_gates()` is now fully isolated from the real environment and real on-disk journal/cache — safe regardless of what `IBKR_GATEWAY_MODE` the developer's `.env` currently targets.
- **Verified by:** `pytest tests/test_execution_service.py tests/test_executor.py tests/test_routes_trading.py` → 59 passed (was 18 failed / 41 passed); full backend `pytest` → 847 passed, 1 pre-existing unrelated failure (`test_hod_momo_universe.py::test_build_focus_universe_empty_inputs`, out of scope).
- **Related:** PROBLEM_LOG 2026-07-20 "18 execution/executor/routes-trading tests failed after switching Gateway to live".

## 2026-07-20 — TradingTab nests Reports (`initialSection` prop) — fixes broken `npm run build`

- **What:** `TradingTab` now accepts an optional `initialSection: 'overview' | 'reports'` prop and renders a small Overview/Reports toggle at the top of the Account view; selecting Reports renders the existing `ReportsTab` (P&L calendar) in place of the trading layout.
- **Why:** `frontend/src/workspace/registry.ts` already nests the `reports` module under Account (`showInTabNav: false`, "Nested under Account (header)") and `TabModuleHost.tsx` already passed `initialSection={activeTab === 'reports' ? 'reports' : 'overview'}` into `TradingTab`, but `TradingTabProps` never declared that prop and never rendered anything for it — a `tsc` build error (`TS2322`) blocking `npm run build` and leaving `ReportsTab` orphaned (imported nowhere).
- **Files touched:** `frontend/src/ibkr/TradingTab.tsx`, `frontend/src/ibkr/tradingTab.css`.
- **How it works now:** `TradingTab` owns a local `section` state seeded from `initialSection`; a two-button toggle switches between the normal trading layout and `<ReportsTab />` without leaving the Account view.
- **Verified by:** `npm run build` (was `tsc` error, now clean); `npx vitest run src/ibkr src/stock_view` → 154 passed.

## 2026-07-20 — IBKR disconnect foresight (sticky intent + port diagnostics)

- **What:** Honest disconnect diagnostics on `/api/ibkr/status` (port reachability + `disconnect_hint`); sticky intentional Paper/Live intent (no ~18s suppress timer); live→paper self-heal only on hard refuse (not timeout); reconnect wake on switch; Stock View actionable mismatch copy + 404 restart-API hint; mode-aware empty IBKR copy.
- **Why:** Paper Nova + live-only Gateway stays disconnected by design (never auto paper→live). Operators saw bare “Disconnected” / silent heal-back after a failed Live switch; same split-brain class as the flatten qty bug — connection intent was scattered globals + a timer.
- **Files touched:** `backend/ibkr/gateway_heal.py`, `client.py`, `client_connect.py`, `port_diagnostics.py`, `routes/trading.py`; `frontend/src/ibkr/disconnectCopy.ts`, `StockViewHeader.tsx`, `StockViewTradingChrome.tsx`, `EmptyState.tsx`; `ibkr-gateway-login-warning.mdc`, `docs/ibc-gateway-setup.md`.
- **How it works now:** One sticky `intentional_gateway_mode` blocks silent live→paper heal until the user switches again or Live connects. Status exposes which port is up. UI CTA: “Nova targets Paper (4002)… Live is up — Switch to Live?” Stale API 404 → “Restart Nova API”.
- **Verified by:** pytest `test_gateway_heal`, `test_gateway_mode_switch`, `test_port_diagnostics`, status route hint; Vitest disconnectCopy + capsule 404/CTA.
- **Related:** PROBLEM_LOG 2026-07-20 disconnect foresight; task-log `2026-07-20-ibkr-disconnect-foresight.md`.

## 2026-07-20 — Paper/Live capsule stays clickable when disconnected

- **What:** Paper/Live no longer greys out when IBKR is disconnected. Selection falls back to `gateway_mode` (env target) so you can retarget 4001/4002 while offline.
- **Why:** After a Live login on 4001 with Nova still on paper/4002, self-heal cannot flip paper→live (by design). Operators were stuck: Disconnected + disabled capsule.
- **Files touched:** `StockViewTradingChrome.tsx`, `StockViewHeader.tsx`, `StockViewPage.tsx`, tests.
- **How it works now:** Capsule uses connected `mode` when linked, else `gateway_mode`; clicks always allowed except while a switch is in flight.
- **Verified by:** Vitest capsule “clickable when disconnected” + status now `connected:true mode:live` after pointing Nova at 4001.

## 2026-07-20 — Global pretty app dialogs (replace native popups)

- **What:** Replaced every `window.confirm` / `window.alert` / `window.prompt` / bare `alert()` in the frontend with a single styled dialog system. Live Gateway switch, Flatten, Stop Automation, blocklist, HOD clear, alert-channel delete, settings errors, Nova Actions, Fill now, etc. all use the same Nova-themed modal (title + message + Cancel/Confirm, danger/warning tones).
- **Why:** Native browser “localhost:5173 says” popups broke the trading UI look and felt like a system error rather than an in-app confirm.
- **Files touched:** `frontend/src/ux/{appDialogApi,AppDialogHost,appDialog.css,index}.ts(x)`, `App.tsx` (`AppDialogHost` root), `constantGroups/ux.ts`, and every former native-popup call site under `stock_view/`, `ibkr/`, `strategy/`, `hod_momo/`, `closed_orders/`, `hotkeys/`, `components/`, `hooks/`, `modules/`.
- **How it works now:** Call `confirmApp` / `alertApp` / `promptApp` from anywhere (React or pure helpers). `AppDialogHost` (mounted once in `App`) owns a queue and renders shadcn `AlertDialog` with Nova chrome. `promptApp({ expectedValue })` keeps Confirm disabled until the typed token matches (used for Nova OS flatten). Place-order’s existing `PlaceOrderConfirmDialog` is unchanged (already custom).
- **Verified by:** Vitest `src/ux/AppDialogHost.test.tsx` + updated capsule/header/flatten tests; full frontend suite 399 passed.
- **Follow-ups:** None.
- **Related:** Intentional Paper↔Live Gateway switch (same session).

## 2026-07-20 — Intentional Paper ↔ Live Gateway switch

- **What:** The Stock View header's Paper/Live capsule is now a real switch, not a status mirror. Clicking Live/Paper (after a strong confirm) calls `POST /api/ibkr/gateway-mode`, which persists `IBKR_GATEWAY_MODE` to `.env`, disconnects, and lets the background reconnect loop dial the new Gateway port. Live never sets `IBKR_LIVE_TRADING_CONFIRMED` — spend stays `locked_live_unconfirmed` until armed separately. A refused/timed-out live port surfaces an honest inline error under the capsule instead of self-heal silently flipping back to Paper. If the live port answers with a paper account (`DU…`/`DF…`), Nova disconnects and refuses to pretend Live.
- **Why:** Live click previously only showed a `window.confirm` explaining the control did nothing — there was no way to actually switch Nova's target Gateway port from the UI.
- **Files touched:** `backend/ibkr/client.py` (`request_gateway_mode`), `backend/ibkr/gateway_heal.py` (`suppress_self_heal`/`self_heal_suppressed`), `backend/routes/trading.py` (`POST /api/ibkr/gateway-mode`), `frontend/src/stock_view/StockViewTradingChrome.tsx`, `frontend/src/ibkr/useIbkrStatus.ts` (`refreshIbkrStatusNow`), `constantGroups/chart_api.ts`, `docs/ibc-gateway-setup.md`, tests.
- **How it works now:** `request_gateway_mode(mode)` persists+applies the target env var, suppresses the live→paper self-heal for one connect attempt (so a refused live port doesn't quietly reappear as Paper), disconnects, and polls `is_connected()` for up to `IBKR_CONNECT_TIMEOUT_SEC + 3s` while the reconnect loop (the sole connector — ib_async doesn't support concurrent `connectAsync` on one `IB()`) dials the new port. The route is a thin delegate; the frontend capsule shows `…` while switching, calls `refreshIbkrStatusNow()` (a window-event broadcast so every mounted `useIbkrStatus()` polls immediately) when done, and renders the backend's error text inline on failure.
- **Verified by:** `pytest backend/tests/test_gateway_mode_switch.py backend/tests/test_gateway_heal.py backend/tests/test_routes_trading.py` (30 passed); `vitest run src/stock_view/StockViewTradingChrome.test.tsx` (4 passed) + full frontend suite (396 passed).
- **Follow-ups:** None — auto-login/credential storage and `auto_live` unlock remain explicit non-goals.
- **Related:** `.cursor/plans/live_gateway_switch_731cc270.plan.md`, `.cursor/rules/ibkr-gateway-login-warning.mdc`.

## 2026-07-20 — Paper trading CTA + hot banner

- **What:** When IBKR Gateway mode is `paper`, the manual ticket primary button reads **Place Paper order** (orange) instead of blue **Place an order**. A hot orange banner (`PAPER TRADING — orders go to your IBKR paper account, not live money.`) shows at the top of Stock View and the Trading tab. Live/disconnected keep the prior blue Place an order label and no banner.
- **Why:** Operators asked for unmistakable paper vs live cues before clicking Place.
- **Files touched:** `frontend/src/ibkr/ManualOrderTicket.tsx`, `PaperTradingBanner.tsx`, `paperTradingBanner.css`, `tradeTicket.css`, `TradingTab.tsx`, `stock_view/StockViewHeader.tsx`, `constantGroups/chart_api.ts`, tests.
- **How it works now:** Banner and orange CTA key only off `mode === 'paper'` from IBKR status — not spend_status alone.
- **Verified by:** Vitest `StockViewHeader` banner + `ManualOrderTicket.paperLabel` tests.
- **Follow-ups:** None.

## 2026-07-20 — IBKR long_qty SSOT + BuyingPower fail-closed

- **What:** Unified broker long qty on `account.long_qty()` (`ib.positions()` only) for validate anti-short, Nova OS flatten reconcile/preview, and `GET /api/ibkr/positions` **qty** (MTM/PnL joined from portfolio; never invent longs from portfolio-only rows). Split reason codes `POSITION_UNAVAILABLE` vs `NO_POSITION`. `get_account_summary` / `refresh_account_summary` now raise `IbkrAccountError` on `accountValues` failure (route `/api/ibkr/account` → 503); priced BUY refused with `BUYING_POWER_UNKNOWN`. FE disables Flatten / exit Nova Actions when `useIbkrAccount.error` is set. Positions cache refreshed via `reqPositionsAsync` after connect.
- **Why:** UI showed SPY from portfolio while Flatten/`source=manual` SELL used empty `positions()` → false `NO_POSITION`. Swapping validate to portfolio was rejected (false-allow short). Same swallow class left BuyingPower fail-open on LMT BUY.
- **Files touched:** `backend/ibkr/account.py`, `client.py`, `execution/validate.py`, `strategy/executor_flatten.py`, `routes/trading.py`, FE Positions/TickerTrade/Nova Actions/`useIbkrAccount`, tests, ADR 007 / trading-execution note, task-log.
- **How it works now:** One SSOT — `long_qty` / `positions()`. UI qty follows that SSOT; portfolio is mark/PnL join only. Read failure ≠ flat (`POSITION_UNAVAILABLE` / flatten abort). Summary read failure ≠ skip BP check. UI Flatten stays `source="manual"`. `source=flatten` still skips validate anti-short (reconcile uses `long_qty`).
- **Verified by:** `pytest` focused suite 89 passed (`test_ibkr_account`, `test_execution_validate`, `test_execution_service`, `test_executor`, `test_orders_api_contract`, `test_routes_trading`); Vitest ClosePositionButton + closeFullPosition 7 passed.
- **Follow-ups:** Optional paper buy-1 → Flatten e2e when Gateway up. Kill/recovery claim model still separate.
- **Related:** PROBLEM_LOG 2026-07-20 "positions vs portfolio dual-source + BuyingPower fail-open"; plan `flatten_sell_refusal_14e16b28`; audit task-log `2026-07-20-flatten-dual-source-daddy-audit.md`.

## 2026-07-20 — Fail-loud remainder: IBKR positions/orders + maintainer swallow policy

- **What:** Closed the two follow-ups from the global fail-loud pass. (A) `ibkr/account.get_positions`/`get_portfolio` and `ibkr/orders.open_orders`/`closed_orders` now raise `IbkrAccountError` on disconnect/API failure instead of returning `[]`; `/api/ibkr/positions`, `/api/ibkr/orders`, `/api/ibkr/orders/closed` return HTTP 503 on that error, `DELETE /api/ibkr/orders` returns a structured `{ok:false,error}`; `execution/validate._position_qty`, the kill-switch's bracket-unfilled check, and `flatten_positions`/`flatten_preview`/protective-leg cancel all fail closed (refuse SELL / abort flatten / leave stops alone) instead of treating a failed read as "flat"/"no working orders". Frontend `useIbkrAccount`/`useClosedOrders` keep last-good rows and surface an error line instead of wiping panels to empty or (closed orders) silently falling back to sample data. (B) `tools/maintainer_checks.py` no longer scores `tools/` scripts or test files against the swallow heuristics, and path-allowlists 5 modules whose empty-on-error behavior is already deliberate (disk/JSON loaders, `managedAccounts()` paper-pin fail-closed, idempotent tick/listener cleanup, already-loud Alpaca degrades).
- **Why:** The account/orders empty-on-error path was the one real "flat account" lie left: a transient IBKR read failure during a deliberate flatten could skip the market SELL and still cancel the protective stop/target (read failure indistinguishable from "genuinely flat"). The maintainer's swallow heuristic was separately flagging its own `tools/` scripts, tests, and 5 already-safe modules, drowning out real findings.
- **Files touched:** `backend/ibkr/{errors,account,orders}.py`, `backend/routes/trading.py`, `backend/execution/validate.py`, `backend/strategy/{executor,executor_flatten}.py`, `frontend/src/ibkr/{useIbkrAccount,PositionsPanel,WorkingOrdersPanel,TradingTab}.tsx/.ts`, `frontend/src/closed_orders/{useClosedOrders,ClosedOrdersModule,ClosedOrdersPanel}.ts/.tsx`, `tools/maintainer_checks.py`.
- **How it works now:** `IbkrAccountError` is the typed signal for "could not verify" on account/order reads. Anything safety-critical (SELL sizing, kill-switch stop preservation, flatten) treats that error as "unknown — do not guess", never as zero/empty. UI hooks track a separate `error` string alongside their last-good state and never overwrite good rows with `[]` on a failed poll. `maintainer_checks.check_swallowed_errors` skips `tools/`+test paths entirely and consults `EXCEPT_RETURN_EMPTY_ALLOWLIST`/`SWALLOWED_EXCEPTION_ALLOWLIST` (documented in `.cursor/agent-memory/maintainer-memory.md` "Swallow heuristic policy") before flagging a Python except/return-empty or swallow.
- **Verified by:** `pytest backend/tests/test_ibkr_account.py test_ibkr_orders.py test_orders_api_contract.py test_execution_validate.py test_executor.py test_closed_orders.py` + full backend suite (800 passed, 18 pre-existing/unrelated failures confirmed identical on clean `master`); `npx vitest run` for the touched IBKR/closed-orders panels; `py -3 -m pytest tools/test_maintainer_checks.py` (25 passed); `py -3 tools/maintainer_checks.py --json` (0 swallow-heuristic findings, down from 7).
- **Related:** PROBLEM_LOG 2026-07-20 "IBKR positions/orders empty-on-error lie"; follows up on the 2026-07-20 global fail-loud pass entry below.

## 2026-07-20 — Global fail-loud pass (silent empty markets)

- **What:** Stopped IBKR discovery/bridge/AH/HOD-seed paths from turning transport failures into successful `[]`/`{}` that wipe UI caches. Scanner polls keep last-good rows; maintainer heuristics flag `except: return []` and empty `.catch(() => {})`.
- **Why:** Empty Gappers with live Gainers proved a class of bugs: exception → blank log/`[]` → overwrite last-good → “app frozen” with no honest error.
- **Files touched:** `ibkr/discovery.py`, `ibkr/errors.py`, `ibkr_bridge.py`, `adapters/ibkr_scanner.py`, `hod_momo_universe.py`, `hod_momo_seed.py`, `scanner_runners/afterhours.py`, `scanner.py`, `useScannerData.ts`, `tools/maintainer_checks.py`, FE catch sites.
- **How it works now:** `scan_symbols` / `snapshot_quotes(require_success=True)` raise `IbkrDiscoveryError` on disconnect/timeout/API fail. Scanner adapters use `run_ibkr(..., on_error="raise")`. Bridge default is `on_error="none"` (return `None`, keep last-good). HOD seeds refuse empty wipes. AH discovery/focus keep last-good on bridge fail. FE scanner poll ignores wipe-signature `[]` when prior rows exist. Integrity already fails empty premarket gappers (prior fix).
- **Verified by:** `pytest` discovery + fail_loud + bridge_loud + integrity + maintainer_checks (all green).
- **Follow-ups:** Remaining maintainer `except_return_empty` on account/orders (logged but still return `[]`); Alpaca-only scanner paths; benign ticks `list.remove` swallows.
- **Related:** PROBLEM_LOG 2026-07-20 silent IBKR bridge wipe + this global pass.

## 2026-07-20 — Shared money formatter (formatMoney)

- **What:** Extracted the duplicated dollar-formatting helper (`fmt`/`fmtDollar`, copy-pasted identically in 5 files) into one shared `formatMoney` utility.
- **Why:** Same single-source-of-truth gap `formatShareQty` closed for qty — a rounding/thousands-separator fix in one copy would silently miss the other four.
- **Files touched:** `frontend/src/utils/formatMoney.ts` (new), `PositionsPanel.tsx`, `workingOrderCells.tsx`, `closedOrderCells.tsx`, `TickerTradeActionBar.tsx`, `StockViewHeader.tsx`.
- **How it works now:** `formatMoney(n, decimals = 2)` — `$` + `toLocaleString` with matching min/max fraction digits, `'—'` for null/non-finite. 2-decimal default covers Positions/Orders price columns; `formatMoney(n, 0)` covers account-total badges (Net Liq / BP). `fmtPrice` in `quoteFormat.ts` (no thousands separator, per-share quote price) is a distinct, correctly-scoped helper and was left untouched.
- **Verified by:** Vitest `formatMoney` + existing working/closed order cell contracts (25 passed); `npm run build` clean (no orphaned imports).
- **Follow-ups:** Did not merge the three per-table cell renderers or fold Executor/Journal tables into the IBKR order-table system — column sets and data shapes (`IbkrPosition`/`IbkrOrder`/`ClosedOrder`) diverge enough that a shared renderer would add indirection without removing real duplication.
- **Related:** `knowledge/task-log/2026-07-20-shared-money-formatter.md`

## 2026-07-20 — Fail-loud IBKR scanner bridge (no silent gapper wipe)

- **What:** IBKR discovery bridge timeouts no longer wipe Gappers/Losers to empty with a blank log line. Integrity fails empty premarket gappers; scanner tabs show the integrity banner.
- **Why:** User saw “frozen” empty Gappers while Gateway was connected and Gainers were live — classic silent `[]` on bridge timeout.
- **Files touched:** `backend/ibkr_bridge.py`, `adapters/ibkr_scanner.py`, `scanner_runners/discovery.py`, `scanner_runners/movers.py`, `hod_momo_integrity_scanner.py`, `integrity_live.py`, `ScannerTabPanels.tsx`, `EmptyState.tsx`.
- **How it works now:** Bridge failures log `TimeoutError: …` (etc.), record `ibkr_bridge_last_error`, and keep the last good cache. Premarket 0 gappers with IBKR up is integrity **fail**, visible on Gappers/Gainers/Losers tabs.
- **Verified by:** pytest `test_ibkr_bridge_loud` + `test_scanner_integrity_mode` (17 passed).
- **Follow-ups:** Restart API to load; open **Gainers** if Gappers still empty until next successful discovery.
- **Related:** PROBLEM_LOG 2026-07-20 empty Gappers / bridge wipe

## 2026-07-20 — Fractional share qty in trading tables

- **What:** Positions, Working/Closed Orders, executor/journal Qty (and related Pos/flatten copy) show fractional shares instead of rounding to whole numbers.
- **Why:** Live IBKR leftover (0.0642 shares) rendered as Qty **0** while POSITIONS (1) still counted the row — Webull-style fractional display.
- **Files touched:** `frontend/src/utils/formatShareQty.ts`, `PositionsPanel.tsx`, `workingOrderCells.tsx`, `closedOrderCells.tsx`, `ExecutorTables.tsx`, `JournalPanel.tsx`, trade bar / Close Position copy, `docs/webull-widget-parity.md`.
- **How it works now:** Shared `formatShareQty` uses up to `TICKER_TRADE_QTY_DECIMALS` (4) with no forced trailing zeros — `100` stays `100`, `0.0642` stays `0.0642`.
- **Verified by:** Vitest `formatShareQty` + working/closed order cell contracts (21 passed).
- **Related:** PROBLEM_LOG 2026-07-20 · `knowledge/task-log/2026-07-20-fractional-share-qty-display.md`

## 2026-07-20 — Separate Running Up tab from HOD Momo

- **What:** Added a top-level **Running Up** tab. HOD Momo no longer shows strategy #12 or the “Running Up only” chip; each tab gets its own partitioned feed and badge count.
- **Why:** Warrior treats Running Up as a sibling alert scanner (no new HOD required). Mixing it into HOD Momo caused confusion (e.g. VCIG Squeeze retests looking like HOD).
- **Files touched:** `frontend/src/hod_momo/RunningUpTab.tsx`, `scannerPartition.ts`, `HodMomoTab.tsx`, `HodMomoAlertTable.tsx`, `workspace/registry.ts`, `TabModuleHost.tsx`, `DashboardPage.tsx`, `SampleDashboardPage.tsx`.
- **How it works now:** One backend WS (`/ws/hod-momo`) still evaluates all strategies. UI partitions `strategy_id === 12` → Running Up tab; everything else → HOD Momo. Clear-today still hits the shared alert store (honest confirm copy). Warrior Day Trade Dash never feeds Nova’s engine.
- **Verified by:** Vitest `scannerPartition` + `registry` tests; `npm run build` / targeted vitest.
- **Follow-ups:** Optional separate clear/history API; audio routing per tab.

## 2026-07-20 — HOD strategies require a fresh new high (not retest)

- **What:** `requires_hod` strategies (Squeeze / Float / etc.) now pass the HOD gate only when the session high was *raised* recently (observed print or post-seed tick-6) within `HOD_MOMO_NEW_HOD_GRACE_SEC` (60s), while price stays near that high. Mere retests of a bars/tick6 floor no longer fire HOD Momentum.
- **Why:** VCIG hit Nova Squeeze at 08:24:14 ET / $1.34 after Warrior’s true HOD alerts at 08:02:54; Nova had treated “at session high + surge” as HOD, which is Warrior Running Up semantics.
- **Files touched:** `backend/hod_momo_high.py`, `hod_momo_filters.py`, `hod_momo_trade.py`, `hod_momo_admin.py`, `hod_momo_state.py`, `hod_momo_session.py`, `constants_hod_momo.py`, HOD unit tests.
- **How it works now:** Initial bars/tick6 seed sets the floor without opening the alert window. A later last (or tick-6 raise above that floor) stamps `session_high_raised_ts`. Running Up (strategy 12, `requires_hod=False`) is unchanged. Restart API to load the gate.
- **Verified by:** `pytest` `test_hod_momo_high` / `filters` / `engine` / `persist` / `consolidation` — 45 passed; live VCIG evidence in `hod_momo.log` + `hod-momo-2026-07-20.json`.
- **Follow-ups:** Parent restart uvicorn; Warrior handoff if fresh Running Up snapshot needed; consider separate Running Up UI widget (Warrior has a sibling scanner).
- **Related:** PROBLEM_LOG 2026-07-20 VCIG late Squeeze; task-log `knowledge/task-log/2026-07-20-vcig-hod-retest-gate.md`.

## 2026-07-20 — Gateway chip shows PAPER vs LIVE

- **What:** Header Gateway status now reads `connected · PAPER` or `connected · LIVE` (LIVE uses a distinct orange chip). Wired session `mode` / `gateway_mode` from `/api/ibkr/status` through Workspace → AppHeader.
- **Why:** "Gateway connected" alone hid whether Nova was on paper (4002) vs live (4001) — a serious operator safety gap when the desktop Gateway was live but Nova stayed paper-pinned.
- **Files touched:** `HeaderConnectionStatus.tsx`, `AppHeader.tsx`, `WorkspaceContext.tsx`, `DashboardPage.tsx`, `market_ui.ts`, `tokens-shell.css`, tests.
- **How it works now:** Chip label follows IBKR session `mode` (fallback: configured `gateway_mode` when offline). Tooltip states paper vs live money path. Orders remain gated by spend flags even on LIVE.
- **Verified by:** Vitest HeaderConnectionStatus paper/LIVE cases; local reconnect to `mode=live` / `gateway_mode=live`.
- **Follow-ups:** Clear IB Error 10089 market-data subscriptions so live scanner quotes populate; do not commit local `.env` mode flips.
- **Related:** `knowledge/task-log/2026-07-20-gateway-paper-live-badge.md`

## 2026-07-19 — Dual listing flags + aux API chips + Alpaca RVOL label

- **What:** Quote panel shows Alpaca vs IBKR listing flags side-by-side (tradable / short type / margin — never one merged Yes/No). Header adds aux chips (Alpaca, OpenAI, yfinance, Archive) under IBKR discovery instead of implying Alpaca IEX is the price feed. Scanner Volume/RVOL cells and quote Rel Vol are labeled as Alpaca-sourced so runs can study accuracy; RVOL source swap deferred.
- **Why:** Operator asked to compare broker metadata honestly, see every aux API, and watch Alpaca RVOL during sessions without replacing the denominator yet.
- **Files touched:** `listing_compare.py`, `ibkr/listing_flags.py`, `integrations_health.py`, `routes/health.py`, `routes/scan.py`, `ticker_detail.py`, `TickerBrokerGrid.tsx`, `HeaderConnectionStatus.tsx`, `ScannerTable.tsx`, `market_ui.ts`, quote/fundamentals panels.
- **How it works now:** Ticker `listing` payload has separate `alpaca` + `ibkr` objects; WS `detail_update` merges IBKR after slow fetch. `/api/health` and scanner `health` include `integrations`. Under `discovery=ibkr`, Gateway remains the price chip; Alpaca chip = news/listing/RVOL aux only.
- **Verified by:** `pytest` listing/integrations tests; Vitest HeaderConnectionStatus + TickerBrokerGrid.
- **Follow-ups:** Optional IBKR/yfinance RVOL warmer (user deferred).
- **Related:** task-log dual-listing-aux-chips.

## 2026-07-19 — Nova OS dock tab readable type

- **What:** Enlarged typography in the Trader **Nova OS** dock panel (verdict, gates, news, ticket, reason codes) so it is readable at normal viewing distance.
- **Why:** User could barely read the dense ~0.62–0.72rem compact styles after the panel moved into the dock.
- **Files touched:** `traderNovaOsBrain.css`
- **How it works now:** Dock Nova OS body uses ~0.88–0.95rem for content (section titles ~0.85rem); no micro-type overrides on gates/news/ticket.
- **Verified by:** CSS review against prior compact sizes; reload Trader → Nova OS tab.
- **Related:** prior entry “Nova OS judgment moved to Stock View dock tab”

## 2026-07-19 — Nova OS judgment moved to Stock View dock tab

- **What:** The Trader Nova OS panel (BUY/WAIT/NO_BUY, gates, news impact, ticket) no longer sits under the header. It is a third bottom-dock tab next to Positions and Orders (Today).
- **Why:** User asked to move the judgment strip into the tab bar so charts reclaim vertical space.
- **Files touched:** `StockViewPage.tsx`, `StockViewOpenOrdersDock.tsx`, `chart_api.ts` (`StockViewDockSurface` + `STOCK_VIEW_MODULE_NOVA_OS_TITLE`), `traderNovaOsBrain.css`, Vitest.
- **How it works now:** Dock surfaces are `positions` | `orders` | `nova_os` (persisted). Selecting **Nova OS** mounts `TraderNovaOsBrain` in the dock body; decide polling runs only while that tab is open. Signal-only behavior unchanged.
- **Verified by:** Vitest `StockViewOpenOrdersDock` (Nova OS tab) + `TraderNovaOsBrain`.
- **Related:** task-log `2026-07-19-nova-os-dock-tab.md`; prior `2026-07-19-trader-nova-os-brain.md`

## 2026-07-19 — Isolated Sample data route (header switch)

- **What:** Header **Sample data** toggle opens `?view=sample` — a hard-gated shell with populated gappers, gainers, losers, after-hours, catalysts, HOD Momo, watchlist, decide, and sample Trader. Live dashboard never mounts in that route.
- **Why:** Need a full UI populated for demos/QA without mixing fixtures into live IBKR/scanner feeds.
- **Files touched:** `App.tsx`, `AppHeader.tsx`, `SampleShell` / `SampleDashboardPage`, `frontend/src/sample_data/*`, hook short-circuits (`useTickerStream`, decide/signals/executor/journal/IBKR), CSS + Vitest.
- **How it works now:** On → `SampleDataProvider` + fixtures only (banner + Exit). Off → live `DashboardPage`. Sample Trader uses `?view=sample&symbol=`. Hooks under the provider skip network; live shell never wraps the provider.
- **Verified by:** Vitest `sampleNav`, `sampleFixtures`, `SampleDashboardPage` (no `/gappers` fetch).
- **Related:** task-log `2026-07-19-sample-data-route.md`

## 2026-07-19 — Trader always-on Nova OS judgment (ratings + news)

- **What:** Opening Trader (`?view=stock`) now shows a persistent Nova OS band under the header: live BUY/WAIT/NO_BUY, gate trail, catalyst `news_impact` (class/confidence/reasons), ticket, and exit note when holding. Watchlist Decision reuses the same detail component.
- **Why:** User asked to see how the OS rates a name (including news score) before trusting Automation — Trader had no decide wiring.
- **Files touched:** `TraderNovaOsBrain.tsx`, `useNovaOsDecideSymbol.ts`, `NovaOsVerdictDetail.tsx`, `novaOsNewsImpact.ts`, `DecisionPanel.tsx`, `StockViewPage.tsx`, `market_ui.ts`, CSS + Vitest.
- **How it works now:** Trader polls `GET /api/nova-os/decide/{symbol}` every `NOVA_OS_TRADER_DECIDE_POLL_MS` (2s), clears on symbol switch, surfaces 404 loudly. Signal-only — nothing places; Automation path unchanged. News comes from soft gate `catalyst` → `evidence.news_impact` (no API change).
- **Verified by:** Vitest for news_impact render, symbol-switch clear, Trader brain + 404.
- **Follow-ups:** Optional deep-link CTA into Watchlist Automation tab (no URL param today).
- **Related:** task-log `2026-07-19-trader-nova-os-brain.md`

## 2026-07-19 — Remove Modules menu from tab bar

- **What:** Removed the **Modules** control from the scanner tab bar. Tabs are fixed registry entries; no in-app show/hide/reorder menu.
- **Why:** User does not need the power-user Modules UI.
- **Files touched:** `TabNav.tsx`, `DashboardPage.tsx`, e2e `module-registry` / `layout-store` (localStorage-only checks).
- **How it works now:** Tab bar = scanner tabs only. Layout/visibility stores remain for defaults and any prior localStorage; `ModulesMenu.tsx` is unused by the shell.
- **Verified by:** Typecheck path via edited files; e2e expectations updated.
- **Follow-ups:** Delete `ModulesMenu.tsx` later if nothing imports it.
- **Related:** None.

## 2026-07-19 — Fix sample Closed Orders Time Placed crawl

- **What:** Sample Closed Orders row 9008 no longer calls `new Date().toISOString()` on every `buildMockClosedOrders` rebuild. Time Placed is a fixed ISO; recent-highlight activity is frozen once per module load.
- **Why:** User saw milliseconds tick on sample Time Placed — sample rebuilds on poll made stamps look mutable.
- **Files touched:** `closed_orders/mockClosedOrders.ts`, `mockClosedOrders.test.ts`.
- **How it works now:** All sample `submitted_at` values come from `MOCK_CLOSED_TIMES`. Real IBKR rows were already immutable; only the sample preview was crawling.
- **Verified by:** Vitest `mockClosedOrders.test.ts`.
- **Follow-ups:** None.
- **Related:** Time Placed audit work earlier today.

## 2026-07-19 — Account header replaces Trading tab

- **What:** Removed Level 2 Order Book + Order Ticket from the old Trading tab. Renamed the surface to **Account**, moved it to the AppHeader next to **Today (Live)**, and nested **Reports** as an Account section (Overview | Reports). Trading/Reports no longer appear in the scanner tab bar.
- **Why:** User wants Account for balances/habits learning; order entry stays on Trader (double-click), not a duplicate left rail.
- **Files touched:** `TradingTab.tsx`, `AppHeader.tsx`, `DashboardPage.tsx`, `TabModuleHost.tsx`, `registry.ts`, `features.ts` constants, `tradingTab.css`, `settings-workspace.css`, e2e baseline, registry tests.
- **How it works now:** Header **Account** → `activeTab=trading` → Overview (positions/working/closed) or Reports (`ReportsTab`). Registry ids stay `trading` / `reports` with `showInTabNav: false`. Place orders from Trader window.
- **Verified by:** `tsc -b`; Vitest registry; e2e baseline Account click expectation.
- **Follow-ups:** None.
- **Related:** task-log `2026-07-19-account-header-replaces-trading.md`.

## 2026-07-19 — Orders Time Placed (audit-grade)

- **What:** Order tables rename **Time → Time Placed**. Column always shows `submitted_at` (place time), never last fill/cancel. Place path stamps Nova wall-clock UTC (µs) at send, prefers IBKR trade.log time when present, and emits `IBKR_ORDER_AUDIT` logs. Display shows milliseconds when the ISO carries a fraction; `<time dateTime>` keeps raw UTC.
- **Why:** User needs auditable place times with no drift from fill/status updates.
- **Files touched:** `ibkr/order_times.py`, `ibkr/orders.py`, `orderDisplay.ts`, `orderTableColumns.ts`, Working/Closed cells + panels, sort, tests.
- **How it works now:** Time Placed = broker log[0] else Nova `remember_nova_placed`. Hover still shows last activity. Recent-row highlight still uses fill/cancel (`updated_at`). Sample preview rows remain non-IBKR fixtures.
- **Verified by:** pytest `test_order_times` + `test_open_orders_row` (12); Vitest order display/cells/sort/panels (36).
- **Follow-ups:** Persist Nova place stamps across API restarts if long-lived audit DB is required.
- **Related:** task-log `2026-07-19-orders-time-placed-audit.md`.

## 2026-07-19 — Rename Stock View window to Trader

- **What:** User-facing label for the detached single-symbol terminal is now **Trader** (was Stock View). Document title, Electron child-window title, Quote Panel open button, and double-click tooltips updated.
- **Why:** User asked to rename the Stock View window to Trader.
- **Files touched:** `constantGroups/chart_api.ts` (`STOCK_VIEW_TITLE` / `OPEN_LABEL` / `OPEN_TITLE`), `StockViewHeader.tsx`, `SelectableTableRow.tsx`, SidePanel + table tooltips, `electron/main.mjs`, e2e baseline/workspace specs.
- **How it works now:** Internal module/ids stay `stock_view` / `StockView*` / `?view=stock`. Visible copy and window chrome say Trader. Header shows Nova / Trader brand.
- **Verified by:** Vitest + Playwright e2e string updates; browser check of Trader header/button when UI is up.
- **Follow-ups:** None.
- **Related:** Prior Stock View dock / terminal work.

## 2026-07-19 — Stock View Positions table in bottom dock

- **What:** Stock View footer dock adds a **Positions** tab (WID-019) beside **Orders (Today)** — qty, avg cost, mkt price/value, unrealized P&L, Flatten when paper/live connected. Dock mounts even while ticker charts/rail are still loading.
- **Why:** User asked for a Positions table of current holdings in Stock View.
- **Files touched:** `StockViewOpenOrdersDock.tsx`, `PositionsPanel.tsx` (`compact` / `hideTitle`), `StockViewPage.tsx`, constants, tests, e2e.
- **How it works now:** Dock surface `positions` | `orders` persists in `nova.stockView.dock.surface`. Positions uses the same IBKR account feed as Trading tab; compact mode omits nested Working Orders + account strip. Charts/rail still wait on `detail.symbol` match.
- **Verified by:** Vitest dock Positions tab + stock-view terminal gate test; Playwright Positions + Open/Closed orders e2e.
- **Follow-ups:** None.
- **Related:** WID-019.

## 2026-07-19 — Stock View Eastern market clock

- **What:** Stock View header shows a live `HH:MM:SS ET` clock with session chip (Premarket / RTH / After-hours / Closed).
- **Why:** User asked for a clock on the terminal.
- **Files touched:** `StockViewMarketClock.tsx`, `marketClock.ts`, `StockViewHeader.tsx`, `chart_api.ts`, CSS, tests.
- **How it works now:** Ticks every 1s; session from the same ET bounds as chart session highlighting.
- **Verified by:** Vitest `marketClock.test.ts` + header test.
- **Follow-ups:** None.
- **Related:** Stock View header.

## 2026-07-19 — Stock View header quote when prev_close missing

- **What:** IBKR ticker snapshots no longer require `prev_close` to show last price in the header chip; live L1 stream used as fallback. `snapshot_quotes` keeps `last` when `close` is NaN.
- **Why:** User saw only “CJMB” in the header — price/▲▼/change live there but snapshot was `{}`.
- **Files touched:** `ticker_ibkr.py`, `ibkr/discovery.py`, tests, PROBLEM_LOG.
- **How it works now:** Header chip still owns last + ▲/▼ + day change (rail quote card keeps `hidePrice`). Lookup order: scanner cache → L1 stream → 1‑min chart close → slow IBKR snapshot; prior close from daily bars when needed. Chip shows `—` placeholders while quote is missing.
- **Verified by:** `pytest backend/tests/test_ticker_ibkr_snapshot.py` + discovery last-only case.
- **Follow-ups:** If still `—` under IBKR pacing, wait for bars/L1; check market-data entitlements.
- **Related:** PROBLEM_LOG 2026-07-19 header symbol-only.

## 2026-07-19 — Order tables: rich click-to-sort headers

- **What:** Working / Closed order column headers sort rows on click (Type, Session, Time, Quantity, Status + filled/remaining/prices/id). Shift+click stacks multi-sort; Time defaults newest-first; status/type/session use semantic ranks. Sort persists per table.
- **Why:** User asked to switch top↔bottom view by clicking headers for those fields, with rich features.
- **Files touched:** `orderTableSort.ts`, `useOrderTableSort.ts`, `OrderTableColumnHeader.tsx`, Working/Closed panels, `chart_api.ts`, CSS, tests.
- **How it works now:** Click cycles asc/desc/off (Time: desc first). Shift+click adds levels (superscript 1/2…). Drag (≥6px) still reorders columns; Alt/⌘+double-click clears sort; double-click alone resets column order.
- **Verified by:** Vitest `orderTableSort.test.ts`.
- **Follow-ups:** None.
- **Related:** Orders (Today).

## 2026-07-19 — Stock View: two columns top-to-bottom

- **What:** Stock View is two full-height columns: left = charts + Orders (Today); right = trading rail. Orders no longer span under the rail as a page-wide footer.
- **Why:** User asked for a 2-column top-to-bottom layout (orders were a full-width bottom strip).
- **Files touched:** `StockViewPage.tsx`, `stockViewTerminal.css`, `StockViewRail.tsx` comment.
- **How it works now:** Body grid remains charts|handle|rail; Orders dock moves inside `stock-view-main` under charts with the existing vertical splitter (`--sv-main-pct`).
- **Verified by:** Layout structure + existing dock Vitest/e2e still target dock testids.
- **Follow-ups:** None.
- **Related:** Orders (Today) segmented dock.

## 2026-07-19 — Orders (Today) Webull-style segmented dock

- **What:** Stock View footer is now **Orders (Today)** with a contiguous segmented control: Working | Filled | Canceled | Partial Filled | All (replacing Open / Closed tabs). New `orders_today/` feature slice hosts the filters + view.
- **Why:** User pointed at Webull’s Orders (Today) filter bar as the target UX for active session orders.
- **Files touched:** `orders_today/*`, `StockViewOpenOrdersDock.tsx`, `ClosedOrdersPanel` (`hideFilters` / `statusFilter`), `chart_api.ts`, e2e/dock tests, `webull-widget-parity.md`.
- **How it works now:** One dock title; segment picks working table and/or closed table (closed Cancelled excludes partial — Partial Filled owns those). Filter persists in `nova.stockView.ordersToday.filter` (legacy open→working, closed→all).
- **Verified by:** Vitest filter + dock tests; Playwright orders e2e.
- **Follow-ups:** Optional single merged table for All; WID-020 CSV.
- **Related:** WID-026 / WID-027.

## 2026-07-19 — Closed Orders: highlight just-completed rows

- **What:** Closed Orders rows whose completion time (`updated_at`) is within the last 60 seconds get an amber pulse highlight (`ibkr-order-row--recent`) and tooltip “Completed within the last minute.” Sample preview includes one just-completed demo row.
- **Why:** User asked to visually mark extremely recent fills/cancels while actively trading.
- **Files touched:** `closedOrderRecency.ts`, `ClosedOrdersPanel.tsx`, `closedOrders.css`, `SelectableTableRow.tsx`, `chart_api.ts`, mocks/tests.
- **How it works now:** Recency uses `orderActivityIso` vs `Date.now()` with a 5s tick so the class drops after the minute window. Buy/sell row tint remains; recent pulse sits on top.
- **Verified by:** Vitest `closedOrderRecency` + `ClosedOrdersPanel` recent-row test.
- **Follow-ups:** None.
- **Related:** WID-027.

## 2026-07-19 — Filled column tooltips (active fill progress)

- **What:** Confirmed Working/Closed **Filled**, **Remaining**, **Average fill**, Partially filled status, and **Fill now** already ship; added header/cell tooltips so fill progress is obvious while an order is working.
- **Why:** User asked for the “actively trade / filled” field after Open/Closed status-matrix work — verify completeness, do not invent TurboTrader (WID-015).
- **Files touched:** `orderTableColumns.ts`, `workingOrderCells.tsx`, `closedOrderCells.tsx`, tests, `docs/webull-widget-parity.md`, widgets memory/task-log.
- **How it works now:** Open Orders shows Filled + Remaining + Average fill (Stock View dock non-compact). Hover Filled → “X of Y shares filled”. Fill now markets remaining after cancel (live rows only; sample preview hides actions). Closed Orders keeps Filled for full and partial-cancel rows.
- **Verified by:** Vitest order/fill cell + panel tests; pytest `test_open_orders_row` + `test_orders_api_contract`.
- **Follow-ups:** WID-015 TurboTrader still missing (separate capability); WID-020 CSV export.
- **Related:** task-log `2026-07-19-filled-active-trade-verify.md`; WID-026 / WID-027.

## 2026-07-19 — Mock full Open/Closed IBKR status matrix

- **What:** Open sample rows now include `PreSubmitted`, `ApiPending`, and partial-`PreSubmitted` (plus existing Submitted/PendingSubmit). Closed samples add `Inactive` (Failed) and zero-fill `ApiCancelled`; fixed closed timestamps. E2E fixtures/assertions expanded. Banner no longer hardcodes “5 rows”.
- **Why:** Status coverage was incomplete vs `formatOrderStatus` / `IBKR_CLOSED_ORDER_STATUSES`.
- **Files touched:** `mockWorkingOrders.ts`, `mockClosedOrders.ts`, `orderDisplay.test.ts`, e2e fixtures/spec, `chart_api.ts`.
- **How it works now:** Sample Open covers Submitted/PendingSubmit/PreSubmitted/ApiPending; Closed covers Filled/Cancelled/ApiCancelled/Inactive. Tests assert every status appears and maps to a known UI label.
- **Verified by:** Vitest mock + orderDisplay; `npm run test:e2e:orders`.

## 2026-07-19 — Orders testing pyramid (L1–L4)

- **What:** Full orders pyramid: L1 Vitest (`test:orders-pyramid`), L2 `test_orders_api_contract.py`, L3 Playwright `e2e/open-closed-orders.spec.ts` with mocked IBKR APIs (hard-ban place/cancel), L4 human `docs/paper-orders-field-checklist.md`. Tester recipe + routing wired.
- **Why:** Prevent Open/Closed qty/time regressions without agents placing paper orders.
- **Files touched:** `orderQtyMath.ts`, API contract test, e2e fixtures/spec, `package.json`, `tester.md`, paper-shadow link.
- **How it works now:** Run L1→L3 for code changes; humans run L4 on live paper Gateway. Remaining prefers broker remaining when present; Closed accepts remaining=0 after cancel.
- **Verified by:** `npm run test:orders-pyramid`; pytest contract + open_orders_row; `npm run test:e2e:orders`.

## 2026-07-19 — Remaining column uses same math as Fill now

- **What:** Open Orders Remaining cell now uses `remainingShares()` (qty − filled when broker remaining is null) — same derivation as Fill now / action enable.
- **Why:** Tester found Remaining could show "—" while Fill still worked.
- **Files touched:** `workingOrderCells.tsx`, tests; backend null-remaining mapper case.
- **How it works now:** Display and Fill share `orderQtyMath`; null IB remaining no longer blanks the column.
- **Verified by:** Vitest Remaining null-derivation; pytest null remaining row.

## 2026-07-19 — Order qty math extracted + invariant tests

- **What:** Shared `orderQtyMath` (`remainingShares` / `remainingSharesWhole` / coherence). Fill now + Working panel use it. Added math + Closed cell contract tests; backend asserts filled+remaining=qty.
- **Why:** User asked whether all order-column math was tested — display was covered; remaining derivation was not isolated.
- **Files touched:** `orderQtyMath.ts`, `WorkingOrdersPanel.tsx`, `fillWorkingOrderImmediately.ts`, tests.
- **How it works now:** Broker supplies filled/remaining/avg/limit/stop; Nova only derives remaining when missing and floors for Fill now. Tests lock invariants.
- **Verified by:** Vitest `orderQtyMath` / closedOrderCells / fillWorkingOrderImmediately; pytest `test_open_orders_row`.

## 2026-07-19 — Closed Orders default columns mirror Open (Time first)

- **What:** Closed Orders default is Time → Type → Symbol → Qty → Status → Filled → Limit → Avg fill → Order ID (Open Order layout minus session/remaining/stop). Storage key `v4`.
- **Why:** User asked Closed to copy Open as much as possible, Time first.
- **Files touched:** `orderTableColumns.ts`, `chart_api.ts`.
- **How it works now:** Fresh load / hard refresh uses the mirrored default.
- **Verified by:** Vitest `orderTableColumns`.

## 2026-07-19 — Open Orders Status column after Quantity

- **What:** Default Open Orders order is now Time → Session → Type → Symbol → Quantity → **Status** → Filled → … Storage key `v3`.
- **Why:** User asked Status after Quantity.
- **Files touched:** `orderTableColumns.ts`, `chart_api.ts`.
- **How it works now:** Fresh load uses the new default; hard refresh picks up `v3`.
- **Verified by:** Vitest `orderTableColumns`.

## 2026-07-19 — Open Orders Time is submitted snapshot + column contract tests

- **What:** Open/Working Orders **Time** now uses `submitted_at` only (never `updated_at`). Sample mocks use fixed ISO times (not `Date.now()`-relative). Added contract tests for filled, remaining, limit, stop, avg fill, order id, and time. Zero IB prices map to null.
- **Why:** Time was crawling — UI preferred last-activity, and mocks rebuilt “minutes ago” on every poll.
- **Files touched:** `orderDisplay.ts`, `WorkingOrdersPanel.tsx`, `workingOrderCells.tsx`, `mockWorkingOrders.ts`, `orders.py`, tests.
- **How it works now:** Open Orders Time = place-time snapshot; Closed Orders still use last fill/cancel via `orderActivityIso`. Hover title says the time is fixed at place.
- **Verified by:** Vitest workingOrderCells / orderDisplay / mockWorkingOrders / WorkingOrdersPanel; pytest `test_open_orders_row`.
- **Related:** PROBLEM_LOG 2026-07-19 open-orders time crawl.

## 2026-07-19 — Open Orders default column order (Time first)

- **What:** Default Open/Working Orders columns are now Time → Session → Status → Type → Symbol → Qty → Filled → Remaining → Limit → Stop → Avg fill → Order ID. Storage key bumped to `v2` so prior drag layouts reset.
- **Why:** User-requested left-to-right scan order for live open orders.
- **Files touched:** `orderTableColumns.ts`, `chart_api.ts` (`ORDER_TABLE_COLUMNS_STORAGE_KEY`), tests.
- **How it works now:** Fresh load / new key uses the new default; double-click header still resets; drag+persist still works under `nova.ibkr.orderTable.columns.v2`.
- **Verified by:** Vitest `orderTableColumns`.

## 2026-07-18 — IBKR paper hard-pin (no accidental live)

- **What:** Paper mode can no longer self-heal onto the live Gateway; after connect, IB `managedAccounts` must classify as paper (DU/DF) or the session is dropped and place is refused. Status exposes `broker_account_kind`.
- **Why:** Port/`IBKR_GATEWAY_MODE` alone is not proof of paper — heal paper→live or a live login on the wrong port could spend real money.
- **Files touched:** `ibkr/account_kind.py`, `ibkr/client.py`, `ibkr/safety.py`, `ibkr/gateway_heal.py`, `ibkr/orders.py`, `execution/validate.py`, `nova_os/control_mode.py`, `routes/trading.py`, tests, `.env.example`.
- **How it works now:** Self-heal is live→paper only. Spend gate when `IBKR_GATEWAY_MODE=paper` requires connection mode paper **and** `broker_account_kind=paper`. Live still needs `IBKR_LIVE_TRADING_CONFIRMED`.
- **Verified by:** pytest `test_ibkr_account_kind`, `test_gateway_heal`, `test_ibkr_safety` paper-pin cases; `/api/ibkr/status` after reload.
- **Related:** PROBLEM_LOG 2026-07-18 paper hard-pin; prior gateway self-heal entry (now narrowed).

## 2026-07-18 — Larger Open/Closed Orders typography (esp. Time)

- **What:** Bumped Open/Closed Orders tab titles, column headers, body cells, and Time column (was ~0.78em of a tiny base).
- **Why:** Headers and timestamps were hard to read under stress.
- **Files touched:** `tradingTab.css`, `stockViewTerminal.css`, `closedOrders.css`.
- **How it works now:** Headers ~0.8rem, body ~0.85rem, Time ~0.9rem; dock tabs ~0.88rem.
- **Verified by:** CSS-only visual hard-refresh.

## 2026-07-18 — Draggable order/position columns with localStorage memory

- **What:** Open Orders, Closed Orders, and Positions headers are drag-reorderable (dnd-kit). Order persists in `nova.ibkr.orderTable.columns.v1`. Double-click a header row to reset that table. Actions/Close stay pinned.
- **Why:** User asked to rearrange columns and remember the layout.
- **Files touched:** `orderTableColumns.ts`, `useOrderTableColumnOrder.ts`, `OrderTableColumnHeader.tsx`, Working/Closed/Positions panels.
- **How it works now:** Drag finishes → immediate localStorage write; refresh keeps the layout. Compact Open Orders still hides Remaining/Stop/Session.
- **Verified by:** Vitest `orderTableColumns` + WorkingOrdersPanel.

## 2026-07-18 — Order side as color (no Side column)

- **What:** Open Orders, Closed Orders, and Positions drop the Buy/Sell text column; side is green (buy/long) / red (sell/short) on symbol + qty, with a full-row tint (`ibkr-order-row--buy` / `--sell`).
- **Why:** Fewer columns; faster scan under stress.
- **Files touched:** `orderDisplay.ts`, `WorkingOrdersPanel.tsx`, `ClosedOrdersPanel.tsx`, `PositionsPanel.tsx`, `tradingTab.css`.
- **How it works now:** Entire row is tinted; hover title still says Buy/Sell (or Long/Short); wire `side` unchanged.
- **Verified by:** Vitest `orderDisplay` + `WorkingOrdersPanel`.

## 2026-07-18 — Fill now + EH market flatten + Cancel+Flatten hotkey

- **What:** Working Orders get **Fill now** (cancel resting + market remaining same side). Flatten / exit hotkeys and Fill now set `outside_rth` in pre/after-market (backend now allows MKT EH; STP still RTH-only). New Nova Action **Cancel + Flatten** (`cancel_and_exit`, Ctrl+Shift+Backspace) plus existing Cancel-symbol (Shift+Backspace).
- **Why:** Panic path when a working/partial order will not finish; Flatten previously forced RTH-only MKT so EH exits failed.
- **Files touched:** `fillWorkingOrderImmediately.ts`, `extendedSession.ts`, `WorkingOrdersPanel.tsx`, `closeFullPosition.ts`, `runNovaAction.ts`, `novaActionDefaults.ts`, `backend/ibkr/orders.py`.
- **How it works now:** Fill now ≠ Flatten (order remainder vs full position). Cancel+Flatten = cancel-all symbol then position MKT. Sample Open Orders still disable mutation buttons.
- **Verified by:** pytest `test_ibkr_orders`; Vitest fill/close/extendedSession/WorkingOrdersPanel/novaActionDefaults.
- **Follow-ups:** Per-order Fill now hotkey needs a selected-order concept (not added).

## 2026-07-18 — Exact order times + partial-fill rehearsal mocks

- **What:** Open and Closed Orders show an exact Eastern **Time** column (seconds). Wire adds `submitted_at` / `updated_at` (ISO UTC from IBKR trade log / last fill). Status labels call out **Cancelled (partial fill)**. Sample mocks cover working partials and cancel-after-partial.
- **Why:** User needs precise timestamps and offline rehearsal of partial-fill edge cases before relying on this in live ops.
- **Files touched:** `backend/ibkr/order_times.py`, `backend/ibkr/orders.py`, `orderDisplay.ts`, `WorkingOrdersPanel.tsx`, `ClosedOrdersPanel.tsx`, `mockWorkingOrders.ts`, `mockClosedOrders.ts`.
- **How it works now:** Time = last fill or last status change, tooltip shows submitted vs updated. Closed filter **Partial cancel** isolates cancel-after-partial rows. Partials still on Working show **Partially filled**; after cancel they move to Closed as **Cancelled (partial fill)** with filled qty kept.
- **Verified by:** `pytest` order_times/open_orders_row/closed_orders; Vitest `orderDisplay` + `filterClosedOrders`.
- **Follow-ups:** Confirm live Gateway always populates trade.log/fills; multi-day History remains WID-020.

## 2026-07-18 — Orders table column alignment (Type under Type)

- **What:** Working/Closed order tables use matching header+cell alignment (`ibkr-col--type` centered, nums right, text left) so “Limit Order” / “Market Order” sit under **Type**, not under Filled.
- **Why:** User screenshot showed headers stretched right while type values clustered left.
- **Files touched:** `tradingTab.css`, `ClosedOrdersPanel.tsx`, `WorkingOrdersPanel.tsx`, `closedOrders.css`.
- **How it works now:** `table-layout: fixed` + role classes; Type/Side/Status centered together.
- **Verified by:** Visual hard-refresh of Closed Orders tab.

## 2026-07-18 — Closed Orders on Stock View footer + Trading offline preview

- **What:** Stock View orders dock tabs **Open Orders | Closed Orders** (Closed mounts isolated `closed_orders` module). Trading shows Closed Orders sample even when Gateway is disconnected.
- **Why:** User could not see Closed Orders (was Trading-only while connected) and asked to refresh + push.
- **Files touched:** `StockViewOpenOrdersDock.tsx`, `TradingTab.tsx`, `ClosedOrdersModule.tsx`, dock CSS/constants/tests.
- **How it works now:** Stock View → expand bottom bar → **Closed Orders**. Trading account column / offline guide preview. Live rows via `GET /api/ibkr/orders/closed` after API reload.
- **Verified by:** Vitest dock closed-tab test + closed_orders suite.
- **Related:** WID-027; prior Closed Orders widget entry.

## 2026-07-18 — Closed Orders widget (WID-027) + Flatten SSOT

- **What:** Isolated `frontend/src/closed_orders/` feature slice (session filled/cancelled orders, Modules hide/show) plus Positions **Flatten** via shared `closeFullPosition` (same ADR 007 place path as hotkeys `exit_pos`). New `GET /api/ibkr/orders/closed`.
- **Why:** Daddy-authorized Webull Closed/History parity + full-position close, without baking into Stock View monolith or inventing a second broker path.
- **Files touched:** `closed_orders/*`, `ibkr/closeFullPosition.ts`, `PositionsPanel.tsx`, `TradingTab.tsx`, `TickerTradeActionBar.tsx`, `workspace/registry.ts`, `ibkr/orders.py`, `routes/trading.py`, `docs/webull-widget-parity.md`.
- **How it works now:** Working Orders (WID-026) = cancel only. Closed Orders (WID-027) = terminal session rows + All/Filled/Cancelled filters. Flatten = market exit of entire position through `POST /api/ibkr/order`. CSV/multi-day export remains WID-020. `auto_live` untouched.
- **Verified by:** pytest `test_closed_orders.py`; Vitest `closed_orders/*`, `closeFullPosition.test.ts`, registry (tester owns full UI gates).
- **Follow-ups:** WID-020 CSV export (Stock View Closed tab shipped).
- **Related:** task-log `knowledge/task-log/2026-07-18-closed-orders-wid027.md`.

## 2026-07-18 — IBKR Gateway paper/live port self-heal

- **What:** If the configured Gateway port refuses or times out but the other API port (paper 4002 ↔ live 4001) accepts, Nova flips `IBKR_GATEWAY_MODE`, persists `.env`, and reconnects. Status exposes `gateway_self_heal*`. Disable with `IBKR_GATEWAY_SELF_HEAL=false`.
- **Why:** Paper Gateway on 4002 while `.env` said `live` left Stock View “Disconnected” until a manual edit — user asked for self-heal next time.
- **Files touched:** `ibkr/gateway_heal.py`, `ibkr/client.py`, `routes/trading.py`, `constants_ibkr.py`, `.env.example`, gateway login rule, tests.
- **How it works now:** Reconnect loop tries preferred port → on refuse/timeout tries alternate → on success records heal + persists mode. Orders stay locked via `safety.py`. Neither port up → still a login/IBC warning.
- **Verified by:** pytest `test_gateway_heal.py` + connect tuple tests.
- **Related:** PROBLEM_LOG same date (port mismatch Disconnected).

## 2026-07-18 — Open Orders: Webull-clean labels (no PreSubmitted / LMT)

- **What:** Working / Open Orders table spells out Type (Limit Order, Market Order, Stop Order), Side (Buy/Sell), Session (Regular / Extended hours), and maps IBKR statuses to Webull labels: Working, Pending, Partially filled, Filled, Cancelled, Failed. Cancel button says “Cancel”; raw IBKR status stays in a tooltip only.
- **Why:** User found PreSubmitted / LMT opaque; asked for Webull-style clean copy with no abbreviations.
- **Files touched:** `orderDisplay.ts`, `WorkingOrdersPanel.tsx`, `tradingTab.css`, WID-026 note, tests.
- **How it works now:** Wire data unchanged; `formatOrderStatus` / `formatOrderType` own display. Partial fills on Submitted → Partially filled.
- **Verified by:** Vitest `orderDisplay` + WorkingOrdersPanel label tests.
- **Related:** WID-026; widgets research S15/S17.

## 2026-07-18 — Stock View: drag to resize chart rows and Open Orders

- **What:** Horizontal drag handles between the top/bottom chart rows and between the charts+rail workspace and the Open Orders dock. Sizes persist; double-click resets.
- **Why:** User asked to change heights of those panels (same pattern as L2 vs Trade ticket).
- **Files touched:** `ChartGrid.tsx`, `StockViewPage.tsx`, `StockViewOpenOrdersDock.tsx`, `useResizableHeight` constants, `stockViewTerminal.css`, tests.
- **How it works now:** Chart grid is two flex rows + handle. Expanded Open Orders sits under a workspace handle (`--sv-main-pct`); collapsed dock hides that handle and charts reclaim height.
- **Verified by:** Vitest ChartGrid row-split test + existing Stock View / dock tests.

## 2026-07-18 — Open Orders bar: full-width click to expand

- **What:** Clicking anywhere on the Open Orders header strip (including the middle / “Expand open orders” area) toggles the dock — not only the left title.
- **Why:** User could not open the dock by pressing in the middle of the bar.
- **Files touched:** `StockViewOpenOrdersDock.tsx`, `stockViewTerminal.css`, dock test.
- **How it works now:** Toggle button stretches across the bar; bar click also toggles (sample Hide/Show still isolated).
- **Verified by:** Vitest click-on-hint toggle test.

## 2026-07-18 — Open Orders sample preview (5 mock rows)

- **What:** When Stock View has no real working orders for the symbol, Open Orders shows 5 paper-style sample rows (limit/stop/market, partial fills) tagged **Sample** — not from IBKR. Hide/Show sample controls + banner.
- **Why:** User asked to preview the open-orders table without Gateway paper fills.
- **Files touched:** `mockWorkingOrders.ts`, `StockViewOpenOrdersDock.tsx`, constants, CSS, tests.
- **How it works now:** Empty → auto sample for current symbol (e.g. SDOT); real IBKR orders replace it; Hide sample persists in localStorage.
- **Verified by:** Vitest mock builder + dock sample test.

## 2026-07-18 — Stock View Open Orders dock (collapsible footer)

- **What:** Moved symbol working/open orders from the Stock View rail into a full-width **Open Orders** strip under the chart+rail workspace. User can collapse/expand; preference persists; auto-expands after place / when orders exist.
- **Why:** User marked the bottom of Stock View for the open-order widget (Webull-style), not the trade rail.
- **Files touched:** `StockViewOpenOrdersDock.tsx`, `StockViewPage.tsx`, `StockViewRail.tsx`, `stockViewTerminal.css`, `chart_api.ts` constants, tests, WID-026 note.
- **How it works now:** Footer bar shows count + ▸/▾ toggle. Expanded body reuses `WorkingOrdersPanel` (full columns). Trading tab panel unchanged.
- **Verified by:** Vitest dock + rail composition tests.
- **Related:** WID-026; task log working-orders panel.

## 2026-07-18 — Working Orders panel (Webull WID-026)

- **What:** Post-place / working-orders UI: `WorkingOrdersPanel` on Trading
  (highlight just-placed id) and Stock View rail (symbol-scoped card under
  Trade). `GET /api/ibkr/orders` rows now include filled/remaining/avg fill.
- **Why:** User needs Webull-like order status after placement without unlocking
  `auto_live` or Webull feeds.
- **Files touched:** `backend/ibkr/orders.py`, `frontend/src/ibkr/WorkingOrdersPanel.tsx`,
  `PositionsPanel.tsx`, `TradingTab.tsx`, `StockViewRail.tsx`, `StockViewPage.tsx`,
  `docs/webull-widget-parity.md` (WID-026 + S17 + column map).
- **How it works now:** Place → refresh open orders → highlight row on Trading;
  Stock View shows Working Orders when the open symbol has working rows. Cancel
  only; history/export remains WID-020.
- **Verified by:** Vitest `WorkingOrdersPanel` + `stockViewTerminal`; pytest
  `test_open_orders_row`.
- **Follow-ups:** Filled/cancelled history tabs + CSV export (WID-020); order
  modify deferred.
- **Related:** WID-026, `knowledge/task-log/2026-07-18-working-orders-panel.md`

## 2026-07-18 — Fix shortcuts-menu rebind (StrictMode cancel)

- **What:** Double-click / Edit rebind now stays open. Cleanup uses TanStack `stopRecording` instead of `cancelRecording` (cancel was clearing the session via `onCancel` under React StrictMode). Added per-row **Edit** button and a clearer listening banner.
- **Why:** Keyboard shortcuts menu double-click appeared to do nothing — remount cleanup immediately dismissed rebind.
- **Files touched:** `ShortcutRebindSession.tsx`, `ShortcutsMenuOverlay.tsx`, `settings-workspace.css`, overlay test.
- **How it works now:** Edit or double-click → “Press the new shortcut now · Listening…” → press chord (Esc / Cancel to abort).
- **Verified by:** Vitest overlay Edit/dblclick; Playwright Edit → Listening.

## 2026-07-18 — Silence Vite HMR noise in client-error logs

- **What:** `POST /api/client-errors` no longer logs Vite HMR failures (`send was called before connect`, `@vite/client` stacks). Frontend reporter drops the same noise before POSTing.
- **Why:** Dev HMR WebSocket races flooded the API log with hundreds of WARNING lines that looked like the app was crashing.
- **Files touched:** `frontend/src/utils/reportClientError.ts`, `backend/routes/client_errors.py`, matching tests.
- **How it works now:** Real product errors still POST + log; Vite overlay/HMR internals return `{ok:true, ignored:true}` (or never leave the browser).
- **Verified by:** Vitest `reportClientError.test.ts` + pytest `test_client_errors_ignores_vite_hmr_noise`.
- **Related:** PROBLEM_LOG §2026-07-18 Vite HMR client-error flood.

## 2026-07-18 — Gateway double-click: visible feedback + Vite fallback

- **What:** Fixed “double-click does nothing”: stale API returned 404 with no visible error. Chip now shows opening/check desktop/launch failed + a hint line; Vite `POST /__nova/launch-gateway` covers 404 in local dev.
- **Why:** User double-clicked Gateway offline and saw no effect.
- **Files touched:** `launchIbGateway.ts`, `HeaderConnectionStatus.tsx`, `vite-nova-launch-gateway.ts`, `vite.config.ts`.
- **How it works now:** Prefer `POST /api/ibkr/launch-gateway`; on 404 try Vite middleware. Restart Vite once so the new plugin loads.
- **Verified by:** Live POST launch-gateway → 200 after API restart; Vitest launchIbGateway fallback test.
- **Related:** PROBLEM_LOG §2026-07-18 Gateway chip double-click.

## 2026-07-18 — Double-click Gateway chip opens IB Gateway

- **What:** Double-clicking the header **Gateway** status chip calls `POST /api/ibkr/launch-gateway`, which starts IB Gateway (or the local IBC script) or brings an existing Gateway window to the front.
- **Why:** User asked to summon Gateway from the offline chip to reduce hunting the desktop app.
- **Files touched:** `ibkr/launch_gateway.py`, `routes/trading.py`, `HeaderConnectionStatus.tsx`, `launchIbGateway.ts`, constants.
- **How it works now:** Prefer `%USERPROFILE%\.nova\ibc\start_gateway.ps1` if present; else `IBKR_GATEWAY_EXE` / newest `C:\Jts\ibgateway\*\ibgateway.exe`. Does not store passwords or bypass 2FA — user still logs in.
- **Verified by:** pytest `test_launch_gateway.py`; Vitest `launchIbGateway.test.ts`; live resolve found `C:\Jts\ibgateway\1045\ibgateway.exe`.
- **Follow-ups:** Complete Gateway login + 2FA after launch so the chip flips to connected.

## 2026-07-18 — Rebind shortcuts on the go (TanStack recorder)

- **What:** In the shortcuts menu, **double-click** any row to capture a new chord via `@tanstack/react-hotkeys` `useHotkeyRecorder`. Duplicates blocked with TanStack-normalized conflict checks. Automation six + menu chord persist on the hotkey profile (schema v3).
- **Why:** User wanted change-on-the-go rebinding without hand-rolling a capture/conflict stack.
- **Files touched:** `ShortcutRebindSession.tsx`, `tanstackChord.ts`, `shortcutConflicts.ts`, `effectiveBindings.ts`, `HotkeyDispatchContext.tsx`, `hotkeyStorage` schema v3, `package.json` (`@tanstack/react-hotkeys`).
- **How it works now:** Dispatcher still owns execution; TanStack only records. Conflicts say “Already used by …”. Esc cancels capture. Profile fields: `automationBindings`, `shortcutsMenuKey`.
- **Verified by:** Vitest `src/hotkeys` + `useHotkeys` (51 passed); `tsc -b` PASS.
- **Related:** Ctrl+M menu; hotkeys-continuity rebind invariant.

## 2026-07-18 — Theme-aware select / menu surfaces

- **What:** Fixed native `<select>` option lists (and custom dropdown panels) that rendered light text on a white popup in dark mode. Defined `--input-bg`, `--menu-bg`, `--bg-secondary`, `--bg-elevated` for both themes; global `select`/`option` rules force readable contrast.
- **Why:** History date menu (and other selects) were nearly illegible — OS popup stayed light while app text stayed light.
- **Files touched:** `tokens-shell.css`, `settings-workspace.css`, `scanner-misc.css`, `scanner-l2.css`, `tradeTicket.css`.
- **How it works now:** Closed selects and open `<option>` lists use solid theme menu/input surfaces. Exchange filter + Modules menus use `--menu-bg` instead of hardcoded dark hex.
- **Verified by:** Browser history-select option styles + dark/light theme toggle.
- **Related:** PROBLEM_LOG §2026-07-18 select white-on-white.

## 2026-07-18 — Theme toggle icon by brand

- **What:** Replaced the header “Light/Dark” text button with a sun/moon icon and moved it next to the brand + market-mode badge (out of Look Up / Settings).
- **Why:** User disliked the text control location in the actions cluster.
- **Files touched:** `ThemeToggle.tsx`, `AppHeader.tsx`, `tokens-shell.css`.
- **How it works now:** Dark mode shows a sun (switch to light); light mode shows a moon (switch to dark). Circular icon button by the logo.
- **Verified by:** Browser header check.

## 2026-07-18 — Header connection status cluster (API / Gateway / Prices)

- **What:** Replaced the ambiguous green “Connected” header status with three labeled chips: **API** (Nova backend), **Gateway** (IBKR when discovery=ibkr) or **Feed** (Alpaca), and **Prices** (last tick age, humanized e.g. `16h ago`).
- **Why:** Users saw “Connected” while IB Gateway was offline and prices were ~16h stale — those are different signals that looked like one.
- **Files touched:** `HeaderConnectionStatus.tsx`, `AppHeader.tsx`, `DashboardPage.tsx`, `formatScanAge.ts`, `tokens-shell.css`, tests.
- **How it works now:** Hover tooltips explain each chip. API up ≠ Gateway connected. Stale prices use a warn tone; Gateway offline uses a bad tone. No bare “Connected” label on the API chip.
- **Verified by:** Vitest `formatScanAge` + `HeaderConnectionStatus`; browser check of header cluster when UI is up.
- **Related:** single-market-data-feed honesty; IB Gateway login warning.

## 2026-07-18 — Ctrl+M shortcuts cheat-sheet (peek / pin)

- **What:** Global **Ctrl+M** overlay lists Automation six + enabled Nova Actions + the menu itself. Single press peeks (closes on release); double-tap pins until Esc / Ctrl+M / backdrop click.
- **Why:** User asked for a quick way to see all bound Nova shortcuts without opening Settings.
- **Files touched:** `shortcutsMenuState.ts`, `shortcutsCatalog.ts`, `ShortcutsMenuOverlay.tsx`, `HotkeyDispatchContext.tsx`, `features.ts` constants, `settings-workspace.css`, hotkeys continuity rule.
- **How it works now:** Same shell dispatcher handles Ctrl+M before Automation/Nova Actions. Catalog is built live from `HOTKEY_DEFAULTS` + enabled profile actions.
- **Verified by:** Vitest shortcuts menu/catalog (+ hotkeys suite); Playwright peek/pin path when UI up.
- **Related:** Phase G3 dispatcher; Settings → Hotkeys still owns editing.

## 2026-07-18 — Apple-inspired light/dark appearance tokens

- **What:** Theme-only redesign: HIG-like light + dark palettes, system font stack, calmer header (no purple hero), logo uses accent `currentColor`, header **Light/Dark** toggle persisted as `nova.theme`.
- **Why:** User asked for an Apple-brand vibe without changing infrastructure; keep both appearances.
- **Files touched:** `frontend/src/styles/tokens-shell.css`, `tailwind-theme.css`, `theme/themePrefs.ts`, `ThemeToggle.tsx`, `AppHeader.tsx`, `index.html` FOUC script, `constantGroups/theme.ts`.
- **How it works now:** `data-theme="light"|"dark"` on `<html>` drives all `--bg-color` / `--panel-bg` / `--accent-color` tokens. Default dark. Toggle in header; early apply in `index.html` + `main.tsx`. Trading bid/ask greens/reds retained.
- **Verified by:** Vitest `src/theme/themePrefs.test.ts` (5 passed); Playwright toggle dark→light (`bg` `#f5f5f7`, `nova.theme=light`).
- **Follow-ups:** Gradually replace remaining hard-coded hex in feature CSS with tokens.
- **Related:** ADR 006 CSS tokens.

## 2026-07-18 — Phase G3 verified (Map-to-Nova-Action + browser)

- **What:** Closed G3 leftovers: **Map to Nova Action** (DAS row → disabled typed action; TriggerOrder rejected); HotkeyManager + Vitest coverage; tester browser pass on Settings → Hotkeys and Stock View quick-bar. Roadmap G3 marked `[x]`.
- **Why:** Banner promised Map UX; phase could not be verified until import/map never hit order APIs and UI was exercised live.
- **Files touched:** `frontend/src/hotkeys/mapDasToNovaAction.ts`, `MapDasToNovaDialog.tsx`, `HotkeyManager.tsx`, `HotkeyItemActions.tsx`, tests, `settings-workspace.css`, `Nova-Roadmap-Status.md`, `tester.md` routing note.
- **How it works now:** Select a DAS import row → Map to Nova Action → confirm → appends a **disabled** Nova Action (enable later). Raw `.htk` still never registers with the dispatcher. Use `http://127.0.0.1:5173` for local UI (not `localhost` when another app binds `::1`).
- **Verified by:** Vitest `src/hotkeys` (28 passed); tester browser checklist PASS (console clean; no orders).
- **Follow-ups:** P3 risk-dollar / OTO; server-synced profiles.
- **Related:** task log `knowledge/task-log/2026-07-18-phase-g3-nova-actions.md`; prior open commit `ce1da59`

## 2026-07-18 — Phase G3 Nova Actions + hotkeys specialist

- **What:** Scaffolded `hotkeys` specialist (Owned); Settings → Hotkeys gains editable **Nova Actions**; Trading quick-bar buttons; typed cancel / exit / Ask±/Bid± through the manual order path; `DELETE /api/ibkr/orders?symbol=`; one shell-level hotkey dispatcher with `event.repeat` guard.
- **Why:** Reach DAS-grade trading hotkeys without executing raw `.htk` scripts; Continuity-only G/G2 had no steward for executable work.
- **Files touched:** `.cursor/agents/hotkeys.md`, `hotkeys-continuity.mdc`, `frontend/src/hotkeys/*`, `frontend/src/hooks/hotkeyUtils.ts`, `useHotkeys.ts`, `App.tsx`, `backend/routes/trading.py`, `Nova-Roadmap-Status.md`, fleet map / routing / `AGENTS.md`.
- **How it works now:** System 1 (Automation six) registers with `HotkeyDispatchProvider`; System 2 Nova Actions use PIN/spend-lock/confirm and L2 top-of-book for Ask/Bid. Imported DAS rows stay inactive until mapped. `auto_live` remains NO-GO.
- **Verified by:** `pytest backend/tests/test_trading_cancel_all.py`; Vitest `src/hotkeys` + `useHotkeys` + `exitPosition`; `npm run build`; `agent_contract.py` PASS (15 agents).
- **Follow-ups:** (closed in G3 verify entry) Map UX + tester browser.
- **Related:** Phase G2 `645761b`; task log `knowledge/task-log/2026-07-18-phase-g3-nova-actions.md`

## 2026-07-18 — Nova agent dreaming (full mission)

- **What:** Fleet dream CLI now covers light/REM/deep **plus** LLM REM (key-gated), Obsidian decision hygiene/stamps, Pinecone re-ingest hook, Claude Auto Dream + OpenClaw MEMORY bridges, and `--commit`/`--push`.
- **Why:** Finish the mission — earlier “out of scope” cuts were safety deferrals, not permanent exclusions.
- **Files touched:** `tools/agent_dream.py`, `tools/agent_dream_lib/*`, tests, `Agent-Dreaming.md`, docs/ops, `.claude/settings.json` (via `--bridges`).
- **How it works now:** `py -3 tools/agent_dream.py --full-mission` dry-runs all surfaces; `--write --full-mission --commit --push` applies and ships. Strategy Chosen/rules are not rewritten — hygiene + footers only.
- **Verified by:** `pytest tools/test_agent_dream.py`; `agent_contract.py --ci`; live `--write --full-mission` when shipping.

## 2026-07-18 — Durable task log (`knowledge/task-log/`)

- **What:** Added an append-only task-log folder plus always-on rule so every completed job records what was asked, what changed, and **why that approach** (tradeoffs). Wired into Lifecycle (`task_log=`), daddy/docs, agent-operations, and `tools/task_log_new.py`. Seeded SEC-001–008 remediation narrative.
- **Why:** User requirement — CHANGELOG/PROBLEM_LOG alone do not preserve fix reasoning across agents/sessions.
- **Files touched:** `knowledge/task-log/*`, `.cursor/rules/task-log.mdc`, `tools/task_log_new.py`, specialist-routing, daddy/docs prompts, `docs/agent-operations.md`, contract Lifecycle example.
- **How it works now:** End of material work → scaffold/write `knowledge/task-log/YYYY-MM-DD-*.md` → prepend INDEX → Lifecycle `task_log=<path>`. Skip only for typo/status-only with `skipped`/`n/a`.
- **Verified by:** `py -3 -m pytest tools/test_task_log_new.py tools/test_subagent_lifecycle_hook.py -q`; `py -3 tools/agent_contract.py --ci`.
- **Related:** `knowledge/task-log/2026-07-18-task-log-system.md`.

## 2026-07-18 — Remediate SEC-001–SEC-008 security findings

- **What:** Closed all eight open security findings: API-key guard on mutating `/api/*`, masked Alpaca secrets on `GET /api/config`, webhook SSRF validation, optional FinBERT/torch, localhost CORS default, non-root Docker user, and CI gitleaks/osv-scanner/semgrep jobs. Frontend sends `X-Nova-Api-Key` via `novaFetch` when `VITE_NOVA_API_KEY` is set.
- **Why:** Daddy vuln search found critical unauth executor/API routes, credential leak, and webhook SSRF; user asked to fix them.
- **Files touched:** `backend/auth.py`, `backend/routes/{health,executor}.py`, `backend/alerts/{webhook_url,channels_store,generic_webhook,discord}.py`, `backend/constants_scanner.py`, `backend/requirements.txt`, `backend/requirements-ml.txt`, `Dockerfile`, `.github/workflows/deploy.yml`, `frontend/src/api/novaFetch.ts`, Settings hooks/panels, `security/findings-registry.json`.
- **How it works now:** Loopback without `NOVA_API_KEY` stays open for desktop; public bind or a set key requires `X-Nova-Api-Key`. Config GET never returns plaintext Alpaca keys. Webhooks must be https to non-private hosts (optional host allowlist). Torch is opt-in via `requirements-ml.txt`.
- **Verified by:** `pytest` for auth/config/webhook/alerts + updated `tools/test_security_audit.py` builtin regression (clean).
- **Follow-ups:** Set `NOVA_API_KEY` + `VITE_NOVA_API_KEY` for any non-loopback deploy; tighten CI `continue-on-error` when scanner noise is low.
- **Related:** PROBLEM_LOG 2026-07-18 SEC remediation; Security-Status.md; `knowledge/task-log/2026-07-18-sec-001-008-remediation.md`.

## 2026-07-18 — Daddy orchestration contract (parallel vs sequence)

- **What:** Documented that specialists do not peer-chat — daddy is a hub. Added parallel-safe / sequential / write-conflict rules to `daddy.md` and a durable **Orchestration** table in `Agent-Fleet-Map.md`; daddy reports now label `[parallel]` vs `[after: …]`. Canvas `agent-daddy` shows the same matrix.
- **Why:** Need a clear way to communicate which agents can run together vs which must wait or would conflict on the same files.
- **Files touched:** `.cursor/agents/daddy.md`, `knowledge/obsidian/00-System/Agent-Fleet-Map.md`, `agent-daddy.canvas.tsx`.
- **How it works now:** Audit/research agents (`maintainer`, `security`, `execution`, `router`, `warrior`) may run in parallel. Implementers that share paths (`market-feed`/`hod-momo`/`widgets`) must sequence. Gateway work (`ibkr-ops`) usually runs before feed agents. Tester runs after implementers.
- **Verified by:** Spec + fleet-map review; `py -3 tools/agent_contract.py`.

## 2026-07-18 — Daddy casual shorthand (`daddy, …`)

- **What:** You can address daddy naturally — `daddy, diagnose and tell me what to do next.` — without the formal “Use the daddy subagent…” phrase. Wired via always-apply `specialist-routing.mdc` (Daddy shorthand = highest priority), expanded `daddy.md` description for Cursor proactive match, and casual invoke phrases in the registry.
- **Why:** Day-to-day use should feel like talking to the dispatcher, not reciting a template.
- **Files touched:** `.cursor/agents/daddy.md`, `.cursor/rules/specialist-routing.mdc`, `.cursor/agent-system/registry.json`, `AGENTS.md`, `docs/agent-operations.md`.
- **How it works now:** Parent chat sees a leading `daddy` address → must Task(`daddy`) with the remainder as the prompt. Daddy still classifies and launches/sequences specialists (or emits a Dispatch Plan). Formal invoke phrase remains valid.
- **Verified by:** `py -3 tools/agent_contract.py`.
- **Follow-ups:** First real casual invoke should record `dispatch_mode` in daddy memory.

## 2026-07-18 — Standardize agent names (plain role ids)

- **What:** Renamed five agents to a consistent plain-role scheme: `nova-router`→`router`, `nova-agent`→`docs`, `security-sentinel`→`security`, `widgets-agent`→`widgets`, `news-catalyst`→`news`. Aligned canvases (`agent-execution`, `agent-news`). Reordered registry (daddy → domain specialists → meta). Added Mode column to `Agent-Fleet-Map.md` (Dispatch / Audit / Implement / Research).
- **Why:** Mixed naming dialects (`nova-*`, `*-agent`, `*-sentinel`) made the roster harder to scan and invoke.
- **Files touched:** `.cursor/agents/{router,docs,security,widgets,news}.md` (+ memories), registry, contract `home_exception_agents`, routing/docs/AGENTS/CHANGELOG, fleet map, sync titles, canvases under Cursor projects folder.
- **How it works now:** Invoke with `Use the <id> subagent to …`. Dashboard rule: dedicated = `agent-<id>.canvas.tsx` (docs keeps `nova-home`). Product API paths like `/api/news-catalysts` are unchanged.
- **Verified by:** `py -3 tools/agent_contract.py` (14 agents); tools pytest; `agent_fleet.py`.
- **Follow-ups:** Cursor Task `subagent_type` enum may lag until the IDE reloads custom agents — use the new invoke phrases from the registry.

## 2026-07-18 — Fleet gap-fill: 5 domain specialists + daddy dispatcher

- **What:** Closed every previously Unowned fleet domain and the orphan VectorBT skill cluster by scaffolding six agents: `execution` (audit-only + new `execution-continuity.mdc`, reusing `agent-execution-validation` canvas), `ibkr-ops`, `backtester` (Phase E product + 5 VectorBT skills), `market-feed` (merged general L1 + quote/L2/T&S coherence), `news`, and top-of-fleet `daddy` (dispatch/sequence/aggregate; never implements product code). Flipped `Agent-Fleet-Map.md` ownership; updated routing, AGENTS.md, agent-ops docs, `AGENT_TITLES`, and contract tests to 14 agents.
- **Why:** Unowned domains and orphan skills were intentional cracks after the Agent Fleet Router shipped — the gap-fill was the deferred Phase 3 / follow-up specialists work, plus the user’s request for a literal top-of-fleet owner named `daddy`.
- **Files touched:** `.cursor/agents/{execution,ibkr-ops,backtester,market-feed,news,daddy}.md`, matching memories, `.cursor/rules/execution-continuity.mdc`, `.cursor/rules/specialist-routing.mdc`, `.cursor/agent-system/registry.json`, `knowledge/obsidian/00-System/Agent-Fleet-Map.md`, `tools/sync_agent_surfaces.py`, `tools/agent_fleet.py`, `tools/test_agent_contract.py`, `docs/agent-operations.md`, `AGENTS.md`, canvases `agent-{ibkr-ops,backtester,market-feed,news,daddy}.canvas.tsx` + updated `agent-execution.canvas.tsx`.
- **How it works now:** `daddy` is the action-oriented front door (“dispatch this”); `router` stays the pure classification/crack-index tool. Domain specialists own their slices with explicit handoffs (`market-feed` ↔ `hod-momo`/`widgets`; `execution` does not absorb Nova OS strategy/executor). `agent_fleet.py` should report zero Unowned domains and zero Orphan skills from the map (Continuity-only roadmap phases remain informational cracks).
- **Verified by:** `py -3 tools/agent_contract.py`; `py -3 tools/sync_agent_surfaces.py --write`; `py -3 tools/agent_fleet.py`; targeted pytest on execution/backtest + tools suite.
- **Follow-ups:** Confirm whether nested Task works inside `daddy` on first real invoke (record `dispatch_mode` in daddy memory). Heartbeat Cursor Automation still deferred. Continuity-only roadmap domains (alerts/reports/hotkeys/archive/Nova OS) remain without dedicated specialists by design.
- **Related:** prior entry “Agent Fleet Router” (same day); plan `fleet_gap-fill_5_new_specialists_998441a0.plan.md`.

## 2026-07-18 — Agent Fleet Router: crack index + router triage dispatcher

- **What:** Added a durable domain/skill ownership matrix (`knowledge/obsidian/00-System/Agent-Fleet-Map.md`); a read-only cross-agent crack index (`tools/agent_fleet.py` + `tools/test_agent_fleet.py`) that unions stale snapshots, open blockers, unowned/continuity-only domains, orphan skills, unmanaged canvases, and missing `AGENT_TITLES`; a "Fleet cracks" rollup on Nova Home; a new report-only `router` specialist (dashboard `agent-router.canvas.tsx`) that emits a Routing card naming the right specialist(s)/skill(s) before implementation starts; and a `sessionStart` hook (`tools/session_brief_hook.py`) that leads every new chat with the top-3 fleet cracks + roadmap NEXT. Fixed a real gap: `hod-momo` was missing from `sync_agent_surfaces.AGENT_TITLES`.
- **Why:** Cracks (unowned domains, stale dashboards, orphan skills) were only discoverable by opening seven separate agent memories one at a time; there was no auto-dispatch when a task didn't obviously map to one specialist.
- **Files touched:** `tools/agent_fleet.py`, `tools/test_agent_fleet.py`, `tools/session_brief_hook.py`, `tools/test_session_brief_hook.py`, `tools/sync_agent_surfaces.py`, `tools/test_agent_contract.py`, `.cursor/agent-system/registry.json`, `.cursor/agents/router.md`, `.cursor/agent-memory/router-memory.md`, `.cursor/hooks.json`, `.cursor/rules/specialist-routing.mdc`, `knowledge/obsidian/00-System/Agent-Fleet-Map.md`, `docs/agent-operations.md`, `AGENTS.md`, canvases `agent-router.canvas.tsx` (new) + `nova-home.canvas.tsx` (Fleet cracks section).
- **How it works now:** `py -3 tools/agent_fleet.py --json` is the single command that answers "what's in the cracks?" — it reads the registry, each agent's memory snapshot/backlog, the fleet map, and the canvases directory, but never mutates any of them. `router` is invoked for ambiguous/multi-domain/unowned-domain tasks per `specialist-routing.mdc`; it never edits product code. The `sessionStart` hook calls the same tool and injects `additional_context` with the top-3 cracks — fail-open, so a hook error never blocks a session. Ownership changes get recorded first in `Agent-Fleet-Map.md`, which the tool treats as read-only truth.
- **Verified by:** `py -3 tools/agent_fleet.py` (24 real cracks surfaced, incl. 2 unmanaged canvases and 5 unowned domains); `py -3 -m pytest tools/test_agent_fleet.py tools/test_session_brief_hook.py tools/test_agent_contract.py tools/test_sync_agent_surfaces.py tools/test_subagent_lifecycle_hook.py tools/test_create_nova_agent.py -q` → 42 passed, 1 pre-existing unrelated failure (`test_stale_detection`, predates this change per `git stash` check); `py -3 tools/agent_contract.py` → PASS (8 agents); `py -3 tools/sync_agent_surfaces.py --write` → canvases synced.
- **Follow-ups:** Phase 3 (scaffold `execution` / `ibkr-ops` / `backtest` specialists for the highest-pain unowned domains) deferred to separate chats per plan. Heartbeat automation (scheduled Cursor Automation running the fleet/maintainer/security checks pre-market) not built — no tool access to create a Cursor Automation in this session; `agent_fleet.py`/`agent_contract.py`/`maintainer_checks.py`/`security_audit.py` are all automation-ready (`--json`) whenever that's wired.
- **Related:** `c:\Users\aalta\.cursor\plans\agent_fleet_router_7a9187aa.plan.md` (Phases 1–2 + docs complete; Phase 3 explicitly deferred).

## 2026-07-18 — hod-momo owns IBKR/HOD architecture UML

- **What:** Registered `knowledge/obsidian/03-Nova-Decisions/IBKR-Scanner-HOD-Architecture.md` as a `hod-momo` canonical input and writable path; documented ownership in the agent spec, memory, specialist-routing table, and the note itself. Synced `agent-hod-momo` canvas snapshot.
- **Why:** The end-to-end feed UML is critical; ownership must be explicit so future sessions update the right durable note instead of leaving diagrams stale in chat/plans.
- **Files touched:** `.cursor/agent-system/registry.json`, `.cursor/agents/hod-momo.md`, `.cursor/agent-memory/hod-momo-memory.md`, `.cursor/rules/specialist-routing.mdc`, `IBKR-Scanner-HOD-Architecture.md`.
- **How it works now:** `hod-momo` reads/updates the Obsidian UML whenever feed topology or HOD truth changes. Plan diagrams under `.cursor/plans/hod_gate_uml_cleanup_*.plan.md` are companions; Obsidian wins on conflict. `docs` still owns unrelated docs/canvas hygiene.
- **Verified by:** `py -3 tools/agent_contract.py` PASS; `sync_agent_surfaces.py --write` refreshed hod-momo canvas `canonical_inputs`.
- **Follow-ups:** Commit this wiring + the refreshed UML note when the user asks.

## 2026-07-17 — End-to-end scanner verification: fix all identified gaps

- **What:** Fixed every gap found in the IBKR → scanner → HOD end-to-end trace: (1) After Hours tab now scans dedicated `TOP_AFTER_HOURS_PERC_GAIN` first, falling back to the intraday gainer-list reshape only when that scan is empty; (2) `scan_symbols()` short-TTL-caches (5s) results per `(scan_code, below_price)` so movers refresh, the gapper→gainer fallback, and the HOD seed loop stop re-querying IBKR for identical scans within a burst; (3) `apply_table_quotes` (cold `reqTickersAsync` snapshot path) now threads `day_high` into `on_trade_update` the same way the live L1 path (`apply_l1_quote`) already did, so HOD truth seeds correctly regardless of which quote path fed a symbol; (4) depth's no-entitlement L1 fallback now reuses `ibkr.ticks`' existing shared `reqMktData` stream for a symbol instead of opening a second raw one, and `unsubscribe()` no longer force-cancels that shared line out from under scanner/HOD/detail owners; (5) removed dead machinery: the `alert_broadcast_queue` (put/drain-only, size never read anywhere) and the unreachable `run_ibkr_afterhours_discovery()` helper; (6) the scanner REST poll now runs at 5s under `discovery=ibkr` (where `/ws/scanner` already streams live price patches) instead of 1s, while staying at 1s for Alpaca discovery where the poll IS the price feed.
- **Why:** A full code-level trace from IB Gateway through every scanner (gappers/gainers/losers/afterhours/HOD) surfaced these as real correctness/efficiency gaps, not just architecture smells — the user asked to fix everything found.
- **Files touched:** `backend/constants_ibkr.py`, `backend/ibkr/discovery.py`, `backend/scanner_runners/afterhours.py`, `backend/afterhours_discovery.py`, `backend/ibkr_bridge.py`, `backend/ibkr/ticks.py`, `backend/ibkr/depth/{state,subscribe,handlers}.py`, `backend/hod_momo_alerts.py`, `backend/hod_momo_trade.py`, `backend/hod_momo_state.py`, `backend/hod_momo.py`, `frontend/src/hooks/useScannerData.ts`, `frontend/src/constantGroups/chart_api.ts`, tests.
- **How it works now:** AH discovery source is logged (`source=ah_scan|gainer_reshape|gainer_reshape_cold`). `ibkr.ticks.get_ticker(symbol)` lets depth attach a read-only listener to an existing L1 stream; `ibkr.depth.state.is_shared_l1()` tracks which symbols borrowed it so `unsubscribe()` skips `cancelMktData` for those (ticks.py still owns cancellation via its own owner refcounting).
- **Verified by:** `pytest` (732 passed, backend), `vitest run` (224 passed, frontend), `npm run build` (clean). New tests: `test_ibkr_discovery.py` (AH scan code, TTL cache hit/miss), `test_ibkr_bridge.py` (day_high threading), `test_depth_stability.py::TestDepthL1FallbackReusesTicksStream`.
- **Follow-ups:** None outstanding from this verification pass; `run_focus_scan` no-op under `discovery=ibkr` was confirmed as intentional (membership churn is scanner-driven, not focus-scan-driven) and needs no fix.
- **Related:** `.cursor/plans/hod_gate_uml_cleanup_69da0848.plan.md` verified-gaps ledger.

## 2026-07-17 — HOD truth seed + mute/burst cleanup

- **What:** Stop inventing session high from the first L1 last; seed from IBKR bar highs + tick-6 day High (`hod_momo_high.py`). Require `high_seeded` for HOD strategies. Remove anti-spam mute (cooldown=0), set consolidation/burst to 10s, drop quiet-tape strategy re-eval, retire master RVOL soft bypass. Document APIs in Obsidian + hod-momo agent memory.
- **Why:** Mid-session admissions and restarts falsely claimed "at HOD"; mute ≥ burst window starved Warrior `(N in Xs)` badges; quiet re-eval amplified fake highs.
- **Files touched:** `hod_momo_high.py`, `hod_momo_trade.py`, `hod_momo_filters.py`, `hod_momo_surge_seed.py`, `ibkr/ticks.py`, `ibkr_bridge.py`, `hod_momo_heartbeat.py`, `constants_hod_momo.py`, `collapseAlertsBySymbol.ts`, Obsidian `IBKR-Scanner-HOD-Architecture.md`, tests.
- **How it works now:** Scanner = membership; L1 + bars = HOD truth. Alerts only on real price/day-high updates. Burst window alone rate-limits. `HOD_RAW_MODE=1` skips strategy filters for raw observability.
- **Verified by:** pytest HOD high/engine/filters/persist/heartbeat/spam suites.
- **Follow-ups:** Central scanner service (Phase 3), raw-scanner UI table, day-keyed high persist across restart.
- **Related:** PROBLEM_LOG 2026-07-17 cold-start false HOD.

## 2026-07-17 — TRT sticky L1: cooled-first rank + cap to 8 slots

- **What:** Session-focus sticky now ranks **cooled** (off mover tables) ahead of still-on-table soft-blocks, and caps the sticky list at `HOD_MOMO_ACTIVE_SESSION_FOCUS_SLOTS` (8) instead of 40.
- **Why:** Soft-block sticky worked once, then hot names (DRTS/ETS/…) prepended until TRT sat at sticky #15 with only 8 reserved L1 slots — empty snap again after restart.
- **Files touched:** `backend/hod_momo_session_focus.py`, `constants_hod_momo.py`, `tests/test_hod_momo_session_focus.py`.
- **How it works now:** `_rank_sticky` uses gainer/gapper/AH/loser caches; cooled stickies fill session_focus first. Do not raise sticky max above slot budget.
- **Verified by:** pytest 14 passed; live TRT price=$10.66 rvol=0.30 session_high=$10.66; Former still `enabled=False`; session_gate PASS(warn).
- **Related:** PROBLEM_LOG 2026-07-17 TRT sticky flood / cooled-first.

## 2026-07-17 — TRT sticky L1: session-focus for master_rvol soft-block

- **What:** New `hod_momo_session_focus` sticky list (day-persisted) pins symbols that hit master_rvol soft-block so they keep reserved L1 after leaving the gainer table. Session-focus slots restored to 8; priority is sticky → today_alerts → Former (last).
- **Why:** TRT dropped to empty `/debug/symbol/TRT` once off movers — Former slots were cut to 2 and only today_alerts got session_focus, so cooled Squeeze names never stayed subscribed.
- **Files touched:** `backend/hod_momo_session_focus.py`, `hod_momo_trade.py`, `hod_momo_session.py`, `hod_momo_former.py`, `ibkr_bridge.py`, `universe.py`, `constants_hod_momo.py`, tests.
- **How it works now:** Soft-block evals call `remember_session_focus`; sticky feeds universe extras + active priority. Not Warrior-fed. Do not sticky on every Squeeze hod/surge miss (floods the list).
- **Verified by:** pytest session_focus/former (8 passed); live TRT `session_focus` price=$10.67 rvol=0.31; session_gate PASS(warn).
- **Related:** PROBLEM_LOG 2026-07-17 TRT empty snap / session-focus sticky.

## 2026-07-17 — HOD strategy pills stack vertically (no horizontal scroll)

- **What:** Strategy column pills stack top-to-bottom; row height grows. Former Momo tags hidden from default filter/collapse/display.
- **Why:** Multi-strategy cells showed a horizontal scrollbar; user asked for vertical stack + expandable rows; Former stays off.
- **Files touched:** `frontend/src/hod_momo/hodMomo.css`, `HodMomoAlertRow.tsx`, `HodMomoTab.tsx`, `HodMomoAlertTable.tsx`, `collapseAlertsBySymbol.ts`, `chart_api.ts`.
- **How it works now:** `.hod-strategy-pills` is a column flex; strategy cells allow wrap; Former (id 1) omitted from default visible set and pills.
- **Verified by:** `vitest run src/hod_momo/collapseAlertsBySymbol.test.ts` (4 passed).

## 2026-07-17 — PN Squeeze L1: under-$20 gainer seed head + upside-only movers

- **What:** Mid-tier IBKR table gainers under $20 (PN-class) now win HOD active `seed_slots` ahead of HOT_BY_VOLUME; discovery explore is gainer-ranked; losers no longer consume HOD mover slots; Former sticky slots 8→2. IBKR `scan_hod_momentum_seeds` puts `TOP_PERC_GAIN(belowPrice=20)` first.
- **Why:** PN was on `/api/movers` gainers (rank ~36, ~$4.40) but empty `/debug/symbol/PN` — volume-seed head + abs-% losers + 8 Former slots starved L1 so Squeeze never evaluated.
- **Files touched:** `backend/hod_momo_universe.py`, `backend/ibkr_bridge.py`, `backend/ibkr/discovery.py`, `backend/constants_hod_momo.py`, tests.
- **How it works now:** `seed_symbols_for_active` / `discovery_for_active` feed `build_active_set`. Reserved seed L1 prefers hottest sub-$20 gainer-table names, then volume scans. No Warrior data in the engine.
- **Verified by:** `pytest backend/tests/test_hod_momo_universe.py backend/tests/test_hod_active_quota.py` (25 passed); live PN `volume_seed` + snap price=$4.44; session_gate PASS(warn); observe --once.
- **Follow-ups:** TRT Squeeze timing once on L1; SDOT mid-move if Warrior re-fires.
- **Related:** PROBLEM_LOG 2026-07-17 PN empty snap / seed head burial.

## 2026-07-17 — Squeeze must require HOD; restore mass-disabled strategies (schema v5)

- **What:** Squeeze 5%/10% defaults + schema v5 migrate force `requires_hod=True`; non-Former strategies that were all-disabled get re-enabled. Live config repaired the same way.
- **Why:** CNF fired Nova Squeeze while never on Warrior Small-Cap HOD — only Squeeze was enabled, with `requires_hod=False` (Running-Up behavior on the HOD widget).
- **Files touched:** `backend/constants_hod_momo.py`, `backend/hod_momo_persist.py`, tests, live config.
- **How it works now:** HOD-widget Squeeze needs a new session high. Running Up (12) stays `requires_hod=False`. Former (1) stays off. Disk schema=5.
- **Verified by:** live config + `test_schema_v5_squeeze_requires_hod_and_reenables` (3 passed with v4 test).
- **Related:** PROBLEM_LOG 2026-07-17 CNF nova_only without Warrior HOD.

## 2026-07-17 — Squeeze ignores master RVOL soft-block; sub-$20 gainer seed pass

- **What:** Master Daily Rate RVOL no longer hard-stops Squeeze 5%/10% (surge-only, `min_rvol=0`). HOD seeds add a second `TOP_PERC_GAIN` scan capped `belowPrice=20` so mega-gainers cannot crowd out microcap squeezes from IB's 50-row cap.
- **Why:** Live Warrior TRT Squeeze with Nova pace RVOL 0.32× (formula correct); BTMD/PN-class empty-snap gaps while SDOT-class names fill uncapped gainers.
- **Files touched:** `hod_momo_filters.py`, `hod_momo_trade.py`, `hod_momo_admin.py`, `ibkr/discovery.py`, `constants_ibkr.py`, tests.
- **How it works now:** Soft `master_rvol` still blocks float RelVol strategies; Squeeze evaluates on surge. Seeds = volume scanners + uncapped gainers + sub-$20 gainers.
- **Verified by:** pytest filters/engine/discovery; live TRT `would_fire` lists Squeeze surge blocks (not empty strategies).
- **Related:** PROBLEM_LOG 2026-07-17 "Squeeze blocked by master RVOL…".

## 2026-07-17 — Former Momo Stock disabled by default (schema v4)

- **What:** Strategy 1 (Former Momo Stock) defaults to `enabled=False` / audio off; config schema bumps to v4 and one-time migrate forces persisted Former Momo off while keeping `former_momo_list` intact.
- **Why:** No public Warrior formula for Former; user asked to disable it and focus parity on Squeeze / Float / Running Up.
- **Files touched:** `backend/constants_hod_momo.py`, `backend/hod_momo_persist.py`, `frontend/src/constantGroups/chart_api.ts`, tests.
- **How it works now:** Fresh installs and schema versions below 4 migrate Former off. List still auto-remembers from other strategy fires for later; re-enable in HOD Strategy UI when ready. Other strategies unchanged.
- **Verified by:** `pytest backend/tests/test_hod_momo_models.py backend/tests/test_hod_momo_persist.py -q` (schema v4 + default tests).
- **Follow-ups:** Own a deliberate Former list fill path before re-enabling; continue Squeeze parity (PN seed / TRT RVOL).

## 2026-07-17 — Fix lifespan spawn typo that skipped scanner_l1 (Squeeze L1 dead)

- **What:** Corrected `app_lifespan` wiring from nonexistent `fills_poll_loop` → `fill_poll_loop`, and made background-task spawn per-task resilient so one bad factory cannot skip `scanner_l1`.
- **Why:** Live Warrior Squeeze parity (SDOT/BTMD/TRT) showed enrichment-only snaps with `surge:None` after restart — HOD/table L1 never subscribed because spawn aborted mid-list.
- **Files touched:** `backend/app_lifespan.py`, `backend/tests/test_app_lifespan_spawn.py`.
- **How it works now:** Bootstrap starts `scanner_l1` + HOD heartbeat/surge-seed first; remaining loops start independently; `bootstrap complete` logs with the count of successfully started tasks.
- **Verified by:** `pytest backend/tests/test_app_lifespan_spawn.py`; live restart → integrity gate + observe (this session).
- **Related:** PROBLEM_LOG 2026-07-17 "HOD L1 never started — lifespan spawn typo".

## 2026-07-17 — Lifespan yields before IBKR connect (API serves while Gateway slow)

- **What:** FastAPI lifespan now yields HTTP immediately after local restore/DB init; Alpaca ping, IBKR connect, recovery, and background loops run in a deferred bootstrap task. `connectAsync` has a hard `asyncio.wait_for` wall; failed connects recreate `IB()`. Default `IBKR_CLIENT_ID` moved 1→17.
- **Why:** TCP listen on :8000 with hung `/docs` — Starlette startup shared the event loop with a wedged IBKR handshake (zombie clientId / Error 326 pattern).
- **Files touched:** `backend/app_lifespan.py`, `backend/ibkr/client.py`, `backend/constants_ibkr.py`, `backend/tests/test_ibkr_client_connect.py`.
- **How it works now:** uvicorn can answer `/docs` and `/api/ibkr/status` even while reconnect_loop retries; status shows disconnected until handshake succeeds. Override client id with `IBKR_CLIENT_ID` in `.env` if needed.
- **Verified by:** `pytest backend/tests/test_ibkr_client_connect.py`; parent must restart uvicorn and curl `/docs`.
- **Related:** PROBLEM_LOG 2026-07-17 "API listens but never serves — lifespan IBKR hang".

## 2026-07-17 — Bound IBKR L1 qualify to stop API CLOSE_WAIT wedge

- **What:** `qualifyContractsAsync` now has a 4s timeout; at most 5 new L1 subscribes per reconcile; blocked L1 fails skipped before re-qualify; `/api/integrity` serves a 2s cache from the background loop.
- **Why:** Unbounded qualify under the ticks subscribe lock (explore churn) wedged the asyncio loop — HTTP clients timed out → dozens of CLOSE_WAIT on :8000, API hung ~2min after restart.
- **Files touched:** `backend/ibkr/ticks.py`, `constants_ibkr.py`, `ibkr/scanner_l1.py`, `integrity_live.py`, `routes/scan.py`, tests.
- **How it works now:** Failed/slow qualifies release the lock quickly; explore adds drain across ticks; integrity polls reuse a fresh cache instead of stacking sync builds.
- **Verified by:** `test_ibkr_ticks` cap test; live gate/observe after parent uvicorn restart.
- **Related:** PROBLEM_LOG 2026-07-17 "API hung CLOSE_WAIT — unbounded L1 qualify".

## 2026-07-17 — HOD L1 fail cooldown + coverage 98% warn floor

- **What:** IBKR L1 subscribe failures (e.g. FRE qualify fail) now cool out of the HOD active set for 300s; demoted actives clear stale quote/eval ages; integrity treats coverage 90–99% as warn (still fails below 90%). Session-gate/observe HTTP timeouts raised to 30s.
- **Why:** Explore admitted unqualifiable symbols → coverage 98% hard-fail + recycled symbols kept hours-old `_last_quote_ts`, flapping integrity FAIL and refusing parity observe while the rest of L1 was healthy.
- **Files touched:** `backend/hod_momo_active.py`, `hod_momo_integrity_hod.py`, `constants_hod_momo.py`, `ibkr/scanner_l1.py`, `tools/hod_momo_session_gate.py`, `tools/hod_momo_parity_observe.py`, tests.
- **How it works now:** Failed L1 symbols cannot occupy discovery slots during cooldown; leaving the active set drops age timestamps; coverage flaps no longer suppress alerts when quote/eval ages are green.
- **Verified by:** `test_hod_momo_active` + `test_hod_momo_integrity` new cases; live `session_gate --profile integrity_only` after reload.
- **Related:** PROBLEM_LOG 2026-07-17 "HOD integrity FAIL from L1-failed explore symbols".

## 2026-07-17 — Archive 1m bars from tape + live-readiness scorecard

- **What:** Wired `archive.bar_builder` so IBKR tape prints build `bars_1m` (live + backfill). Backfilled 2026-07-15/16 (331 bars) and re-compacted cold JSONL. Added `tools/live_readiness_scorecard.py` and `tools/archive_backfill_bars_from_tape.py`. Aligned journal GO gates to Phase I (≥50 trades, ≥90% adherence) and `SLIPPAGE_MAX_ADVERSE_BPS`. Extracted `executor_place.py` (executor back under baseline).
- **Why:** Empty `bars_1m` blocked archive replay/walk; live-readiness checklist needed an honest automatable scorecard; threshold docs/API mismatch.
- **Files touched:** `backend/archive/bar_builder.py`, `ibkr/tape_stream.py`, `strategy/executor_place.py`, `journal/metrics.py`, `constants_ibkr.py`, tools + tests.
- **How it works now:** Each tape print updates a 1m OHLCV bucket → `record_bar`. Scorecard exits NO-GO until paper Gateway + ≥5 shadow days + ≥50 closed non-mock trades. `auto_live` stays rejected.
- **Verified by:** bar_builder tests; backfill 59+272 cold bars; kill/flatten/auto_live API drills; pytest focused suites green.
- **Follow-ups:** Human Phase B shadow days on paper Gateway (API paper-connected 2026-07-17; orders still locked until operator enables paper spends).

## 2026-07-17 — Centralized trading execution path (ADR 007)

- **What:** All broker mutations (place, bracket, cancel, price-only replace, kill, flatten) go through `execution.service.execute` with SQLite idempotency, stage timings, and real IBKR ack/fill callbacks (`PendingSubmit` is not ack). Manual UI and automation share the path; paper/live differ only by Gateway gates.
- **Why:** Prove a single measured execution path against p95 ≤250 ms receive→ack without unlocking `auto_live` or placing live orders.
- **Files touched:** `backend/execution/*`, `backend/ports/execution.py`, `backend/routes/trading.py`, `backend/strategy/executor.py`, `backend/strategy/executor_flatten.py`, `backend/ibkr/orders.py`, `tools/execution_latency_probe.py`, `docs/trading-execution-validation.md`, ADR 007, tests.
- **How it works now:** Callers build an `ExecutionCommand` (stable `idempotency_key`) → validate → reserve ledger row → adapter send → telemetry marks ack/fill on the ledger. Duplicate keys replay the prior receipt. `PATCH /api/ibkr/order/{id}` is price-only replace. Probe: `tools/execution_latency_probe.py --confirm-paper-orders`.
- **Verified by:** pytest execution/executor/trading/staged/auto_paper (77 related); synthetic probe p95 ack ~53 ms; AST no-bypass test.
- **Follow-ups:** Paper Gateway probe when logged in; do not treat Continue as live GO.
- **Related:** `docs/trading-execution-validation.md`, canvas `agent-execution-validation`.

## 2026-07-17 — Stock View full-bleed (kill Tailwind `.container` clamp)

- **What:** Renamed the app shell from `.container` → `.nova-shell` so Stock View stretches edge-to-edge; removed the dead black strip on the right.
- **Why:** Tailwind v4 treats `class="container"` as its responsive max-width utility (`48rem` / `64rem` / …). That utility lives in the `utilities` cascade layer and overrode Nova’s layout CSS.
- **Files touched:** `App.tsx`, `DashboardPage.tsx`, `tokens-shell.css`, `stock-view.css`, `quote-layout.css`, `tailwind-overrides.css`.
- **How it works now:** Shell is `.nova-shell` / `.nova-shell--ticker-detail` with `max-width: none`. Do not reintroduce a layout class named `container`.
- **Verified by:** Browser computed `maxWidth: none`, `gap: 0` at Stock View.
- **Related:** PROBLEM_LOG 2026-07-17 Tailwind `.container` max-width.

## 2026-07-17 — Canvas dashboard refresh + documentation audit

- **What:** Refreshed all 7 preferred canvases (real re-run of `tester`/`security`/`maintainer` deterministic checks via their own subagents, plus hand-fixed stale hardcoded prose outside the generated snapshot blocks in `nova-home`/`agent-tester`/`agent-security`). Ran a markdownlint sweep across the repo's highest-value docs.
- **Why:** User requested a canvas cleanup ("update all canvases and shuffle them around, do not delete") and a documentation audit.
- **Files touched:** All 7 canvases; `gemini.md`, `AGENTS.md` (re-synced, fully lint-clean); `CHANGELOG.md`, `PROBLEM_LOG.md`, `security/SOURCE-PINS.md`, `security/tooling.md`, `findings.md`, `progress.md`; `.cursor/agents/*.md` (4 files); `.cursor/rules/*.mdc` (backend-modularity, frontend-modularity, karpathy-guidelines); `.markdownlint-cli2.jsonc`; `.cursor/agent-memory/{docs,tester,security,maintainer}-memory.md`.
- **How it works now:** `tools/sync_agent_surfaces.py --write` still only refreshes the generated `AGENT_SNAPSHOT_*` block in each canvas from each agent's memory — the surrounding hand-written prose (pills, stat grids, tables) does **not** auto-refresh and needs a manual pass when it drifts (this is what was stale here). `dashboard_freshness: refresh-required` in a snapshot is the signal to dispatch that agent's subagent rather than hand-editing its domain data. markdownlint config now disables `MD037`/`MD050` repo-wide (see PROBLEM_LOG — `--fix` was corrupting bare Python identifiers) and correctly ignores `**/graphify-out/**` (nested, not just root) and `**/test-results/**`/`**/.tmp/**`.
- **Verified by:** `tools/sync_agent_surfaces.py --write` final pass shows 0 writes (fully consistent); `markdownlint-cli2` on all touched files shows 0 errors; repo-wide error count 453→176 (remainder is vendored skill mirrors + Obsidian vault, out of scope).
- **Follow-ups:** `hod_momo_active.py`, `constantGroups/chart_api.ts`, `constantGroups/market_ui.ts`, `ManualOrderTicket.tsx`, `sync_agent_surfaces.py` are newly over their file-size limits (maintainer backlog); `frontend/src/stock_view/` header refactor broke 1 Vitest + 3 Playwright specs (tester backlog, untracked WIP, not fixed here); 176 vendored/vault markdownlint errors remain (docs backlog).
- **Related:** PROBLEM_LOG 2026-07-16 — `markdownlint-cli2 --fix` corrupted bare Python identifiers.

## 2026-07-16 — Design system audit: Nova tokens + Stock View rail

- **What:** Fixed Time & Sales unreadable text (token collision), scoped leaking form/button selectors, moved L2/T&S skin to `ibkr/marketData.css`, recomposed Stock View rail with matched pane headers (no duplicate combined title), PIN unlock → shadcn `InputOTP`, and added maintainer/e2e guardrails.
- **Why:** Stock View looked broken after Tailwind/shadcn wiring: `--color-muted` is a faint *background* in Tailwind but domain CSS used it as *text*, computing ~4% opacity labels on purple fallbacks.
- **Files touched:** `frontend/src/index.css`, `styles/tailwind-theme.css`, `styles/tokens-shell.css`, `styles/scanner-l2.css`, `ibkr/marketData.css`, `ibkr/TimeSalesPanel.tsx`, `TradingPinDialog.tsx`, `stock_view/StockViewDepthTape.tsx`, `architecture/decisions/006-css-itcss-cascade-layers.md`, `tools/maintainer_checks.py`, `e2e/level2-tape-modules.spec.ts`.
- **How it works now:** Canonical `--nova-*` tokens; Tailwind `@theme` is a one-way adapter. Domain CSS never reads `--color-muted` for text. Market-data chrome lives in the `components` layer; Stock View only densifies layout. Narrow tape panes collapse to Time/Price/Size via `@container`.
- **Verified by:** `pytest tools/test_maintainer_checks.py` (17), `npm run test` Stock View + full build (`tsc -b && vite build`).
- **Follow-ups:** Migrate trade ticket segments to shadcn `ToggleGroup`; split `tokens-shell.css` into real base/layout sheets; finish remaining frontend surfaces onto New York recipes.
- **Related:** PROBLEM_LOG 2026-07-16 Time & Sales `--color-muted` collision.

## 2026-07-16 — Tailwind + shadcn foundation (Trade CTA first)

- **What:** Wired Tailwind v4 (Vite plugin, no preflight) and shadcn `Button` + `AlertDialog`. Trade ticket primary CTA and place-order confirm now use those primitives; theme maps to existing Nova CSS tokens.
- **Why:** Incremental design-system direction — reusable chrome for trading UI without rewriting charts/L2/tape.
- **Files touched:** `frontend/vite.config.ts`, `frontend/src/index.css`, `frontend/components.json`, `frontend/src/lib/utils.ts`, `frontend/src/components/ui/{button,alert-dialog}.tsx`, `ManualOrderTicket.tsx`, `PlaceOrderConfirmDialog.tsx`, `tradeTicket.css`.
- **How it works now:** `@import "tailwindcss/theme.css"` + utilities sit in cascade layers; `@theme inline` binds `--color-primary` etc. to Nova vars. New UI goes through `@/components/ui/*`. Charts/L2 stay custom CSS.
- **Verified by:** `npm run test` (224) + `npm run build` in `frontend/` (TS `baseUrl` removed for TS 6; operator-mode capsule type fix).
- **Follow-ups:** Migrate more ticket fields / header chrome; keep domain CSS for market surfaces.
- **Related:** Prior Trade unlock/confirm UX entry same day.

## 2026-07-16 — Unlock Trading (blue) → Place an order + confirm checkbox

- **What:** Primary Trade button is always accent blue. Locked: **Unlock Trading** → PIN → **Place an order**. Place opens a confirm dialog with checkbox “Don’t show this pop-up again to confirm placing a live order.”
- **Why:** After PIN unlock the button wrongly stayed Unlock Trading / used Buy-green; user wanted a clear two-step blue CTA plus skippable confirm.
- **Files touched:** `ManualOrderTicket.tsx`, `PlaceOrderConfirmDialog.tsx`, `placeConfirmPrefs.ts` (+ test), `tradeTicket.css`, `constantGroups/chart_api.ts`.
- **How it works now:** PIN unlock flips label to Place an order. Confirm skip persists in `nova.tickerTrade.skipPlaceConfirm`. IBKR env spend gates still apply at submit.
- **Verified by:** Vitest `placeConfirmPrefs.test.ts` + existing unlock/orderEntry suites.

## 2026-07-16 — Trade ticket default order type: Market

- **What:** Default order type is now **Market** (`MKT`); the Default tag moves to Market.
- **Why:** User correction — Market is the default, not Limit.
- **Files touched:** `frontend/src/constantGroups/chart_api.ts` (`TICKER_TRADE_DEFAULT_ORDER_TYPE`), `ManualOrderFields.tsx`.
- **How it works now:** New tickets and symbol resets select Market; Limit/Stop remain available.
- **Verified by:** Constant + label title update.

## 2026-07-16 — Stock View module title: Open → Trade

- **What:** Renamed the order-ticket module header from **Open** to **Trade**.
- **Why:** User request.
- **Files touched:** `frontend/src/constantGroups/chart_api.ts` (`STOCK_VIEW_MODULE_OPEN_TITLE`), `StockViewRail.tsx`, `TickerTradeActionBar.tsx`.
- **How it works now:** Module card title and rail group label both read `Trade` via the shared constant.
- **Verified by:** Constant + call-site update.

## 2026-07-16 — Unlock Trading PIN gate + Limit default mark

- **What:** Restored **Unlock Trading** CTA. Clicking it prompts for PIN `123456`; only then can Buy/Sell place (session-scoped). Limit shows a **Default** tag and remains `TICKER_TRADE_DEFAULT_ORDER_TYPE`. Primer spacing kept.
- **Why:** User wanted Unlock Trading (not Open Trade), a PIN step before orders, and the default order type marked.
- **Files touched:** `ManualOrderTicket.tsx`, `ManualOrderFields.tsx`, `ticketUnlock.ts` (+ test), `tradeTicket.css`, `constantGroups/chart_api.ts`, Stock View tests.
- **How it works now:** Local PIN unlock is UI-only (`sessionStorage`); IBKR spend/env gates still apply after unlock. Qty remains forced to 1.
- **Verified by:** Vitest `ticketUnlock.test.ts` + Stock View / orderEntry suites.

## 2026-07-16 — Open ticket: Primer spacing + Open Trade CTA

- **What:** Gave the manual order ticket breathing room using GitHub Primer stack/control spacing (16px field gaps, 8px chip gutters, 32px medium controls, padded form).
- **Why:** User asked for spacing/padding like the reference ticket and a design pattern that works for Electron — Primer (`primer/primitives`) is GitHub’s established 8px-grid system.
- **Files touched:** `frontend/src/ibkr/tradeTicket.css`, `ManualOrderTicket.tsx`, `frontend/src/stock_view/stockViewTerminal.css`, `constantGroups/chart_api.ts`, tests.
- **How it works now:** Ticket CSS defines local `--mot-space-*` / `--mot-control-h` aliases mirroring Primer stack tokens (no new npm dep). Rail uses a slightly condensed 12px stack gap. Qty remains forced to 1 via `TICKER_TRADE_FORCE_QTY`.
- **Verified by:** Vitest Open/rail expectations (CTA later restored to Unlock Trading).
- **Follow-ups:** Superseded by Unlock Trading PIN gate entry above.

## 2026-07-16 — Manual order qty forced to 1 (temporary SSOT)

- **What:** Locked every manual Open ticket to **1 share**. UI shows 1 and ignores presets / % / $; `buildManualOrder` / `resolveOrderQuantity` also force qty 1 so the payload cannot diverge.
- **Why:** User asked for a temporary single source of truth to avoid accidental size mistakes.
- **Files touched:** `frontend/src/constantGroups/chart_api.ts` (`TICKER_TRADE_FORCE_QTY = 1`), `orderEntry.ts`, `ManualOrderTicket.tsx`, `ManualOrderFields.tsx`, `orderEntry.test.ts`.
- **How it works now:** Set `TICKER_TRADE_FORCE_QTY` to `null` to unlock editable sizing. Tests pass `{ forceQty: null }` when exercising free %/$ math.
- **Verified by:** Vitest `orderEntry.test.ts`.

## 2026-07-16 — Order ticket: Side / Order Type / Quantity subtitles

- **What:** Restored Material-style field subtitles on the Open ticket — Side, Order Type, Quantity (plus Limit/Stop/Hours). Stock View rail no longer hides them.
- **Why:** User asked for labeled sections; rail CSS had `display: none` on `.manual-order-label`.
- **Files touched:** `frontend/src/ibkr/ManualOrderFields.tsx`, `tradeTicket.css`, `frontend/src/stock_view/stockViewTerminal.css`, `frontend/src/constantGroups/chart_api.ts`.
- **How it works now:** Labels are uppercase overlines above each control group; constants live in `TICKER_TRADE_LABEL_*`.
- **Verified by:** Code review of Open ticket label visibility.

## 2026-07-16 — Order ticket: spaced Qty/%/$ chips (Material gutters)

- **What:** Replaced the fused Qty / % / $ segment control with separate pill chips and 8px gaps; presets use the same gutter.
- **Why:** Adjacent fused buttons were easy to mis-tap; user asked for Material-style separation while staying compact.
- **Files touched:** `frontend/src/ibkr/tradeTicket.css`, `frontend/src/stock_view/stockViewTerminal.css`.
- **How it works now:** Unit toggle and presets are individual outlined chips with `gap: 0.5rem` (dense rail `0.4rem`); active unit gets accent fill + inset ring.
- **Verified by:** CSS review of Open ticket quantity controls.

## 2026-07-16 — Order ticket: balanced quantity row (value ~1/3, units ~2/3)

- **What:** Rebalanced the manual-order quantity row so the number field is ~32% (min ~4.5rem) and Qty / % / $ share the remaining ~2/3 — not full-width, not a tiny stub.
- **Why:** First pass (~10%) made the value field unusably small; user asked for common-sense sizing.
- **Files touched:** `frontend/src/ibkr/tradeTicket.css`, `frontend/src/stock_view/stockViewTerminal.css`.
- **How it works now:** `.manual-order-quantity-row` is `minmax(4.5rem, 32%) | 1fr`; unit toggle is `repeat(3, 1fr)`.
- **Verified by:** Layout review against the Open ticket quantity row.

## 2026-07-16 — Stock View header: mode / Paper-Live capsules

- **What:** Replaced the cluttered Stock View header (LIVE badge, Confirm / Auto Paper / Signal / Stop Automation, Close, Hide charts) with a clean strip: symbol/price, Net Liq + BP, Paper/Live capsule, Manual/Normal/Fully Automated capsule (Normal only), and trading lock.
- **Why:** User requested a minimal trading header matching Webull-style segmented capsules while keeping IBKR safety gates.
- **Files touched:** `frontend/src/stock_view/StockViewHeader.tsx`, `StockViewTradingChrome.tsx`, `StockViewHeader.test.tsx`, `stockViewTerminal.css`, `pages/StockViewPage.tsx`, `constantGroups/chart_api.ts`, `CHANGELOG.md`.
- **How it works now:** Operator mode capsule is display-only with Normal selected; Manual and Fully Automated stay disabled (`auto_live` NO-GO). Paper/Live reflects Gateway `mode` and clicking the other segment only shows the existing reconnect/confirmation guidance — it never arms live orders. Lock mirrors `spend_status` and cannot bypass `IBKR_ORDERS_ENABLED` / live confirmation. Confirm/Auto Paper/Signal/Stop Automation remain on the Trading tab Executor panel.
- **Verified by:** Vitest `StockViewHeader.test.tsx` + `stockViewTerminal.test.tsx` (15 passed).
- **Follow-ups:** Wire Manual later; keep Fully Automated disabled until a separate unlock phase.
- **Related:** widgets Stock View header cleanup (finished in parent after stuck handoff).

## 2026-07-16 — Karpathy guidelines: creativity + thinking ahead

- **What:** Extended the Karpathy skill and always-applied rule so agents explore creative problem frames and anticipate the next step, while still forbidding gold-plating and silent scope expansion.
- **Why:** User asked to encourage creativity in solutions and thinking ahead; the prior "nothing speculative" framing was suppressing useful foresight.
- **Files touched:** `.cursor/skills/karpathy-guidelines/SKILL.md`, `.cursor/rules/karpathy-guidelines.mdc`, `AGENTS.md`, `gemini.md`, `knowledge/obsidian/00-System/Skills-Library.md`.
- **How it works now:** Five pillars — Think Before Coding (explore design space), Elegant Simplicity, Surgical Changes, Creative Solutions & Thinking Ahead (seams + named follow-ups), Goal-Driven Execution (incl. negative checks). Foresight = communicate risks and leave clean seams; do not ship unused futures.
- **Verified by:** Content review of skill/rule/constitution mirrors for consistency.
- **Follow-ups:** None required; agents pick up the new always-applied rule on next turns.

## 2026-07-16 — Stock View rail: L2+T&S together; drag resizes Order Entry

- **What:** Restored Level 2 and Time & Sales as one side-by-side module. The horizontal drag bar now sits between that combined depth block and the Open / Place Order ticket (not between L2 and T&S). Order entry UI (ManualOrderTicket / Unlock Trading) stays mounted.
- **Why:** A prior edit wrongly stacked L2 above T&S with a splitter between them; the user wanted L2+T&S kept together and height control against the order ticket so L2 can show full depth.
- **Files touched:** `frontend/src/stock_view/StockViewDepthTape.tsx`, `StockViewRail.tsx`, `stockViewTerminal.css`, `stockViewTerminal.test.tsx`, `frontend/src/constantGroups/chart_api.ts`, `frontend/src/hooks/useResizableHeight.ts`.
- **How it works now:** Rail = Quote → trade stack `(L2|T&S card · horizontal ResizeHandle · Open card)`. Split ratio persists in `nova.stockView.depthOrderSplitPct` (default 72% depth). L2 stays slightly wider than T&S; no drag between L2 and T&S.
- **Verified by:** Focused Vitest `stockViewTerminal.test.tsx`.
- **Related:** PROBLEM_LOG 2026-07-16 Stock View L2/T&S split regression.

## 2026-07-16 — Stock View header: editable symbol chip (no Look Up)

- **What:** Removed the far-right Symbol / Look Up form from the Stock View command bar. The primary control is now a bordered symbol+price+change chip; double-click (or Enter/F2) opens an inline editor. Enter/blur commits (trim + uppercase, reject empty); Escape cancels.
- **Why:** Match the reference header (ISRG-style boxed quote) and keep a single-row terminal chrome without a stacked lookup field.
- **Files touched:** `frontend/src/stock_view/StockViewHeader.tsx`, `StockViewSymbolChip.tsx` (new), `stockViewTerminal.css`, `stockViewTerminal.test.tsx`, `frontend/src/constantGroups/chart_api.ts`.
- **How it works now:** `StockViewSymbolChip` owns edit state; commit still calls `StockViewPage` `onLookup` → `onSelectSymbol` (+ `replaceStockViewUrl` when detached). Scanner Quote Panel / Trading tab unchanged. Affordances: pointer cursor, hover border/bg lift + symbol underline, chevron hint on hover, tooltip `STOCK_VIEW_SYMBOL_EDIT_TITLE`.
- **Verified by:** Focused Vitest for double-click / commit / Escape; lint + build when practical.
- **Follow-ups:** Visual confirm on a live Stock View window.
- **Related:** Terminal redesign entry below.

## 2026-07-16 — Stock View terminal redesign (reference-first)

- **What:** Redesigned full/detached Stock View into a dark Nova trading terminal: compact command bar, 2×2 charts, and a dense right rail of **module cards** (Stock Quote → Level 2 · Top N → Time & Sales → Open). L2 and T&S are **stacked** (not side-by-side) with a **horizontal drag bar** between them (`useResizableHeight`, persisted via `STOCK_VIEW_L2_TAPE_SPLIT_KEY`). Shared `StockViewModuleCard` chrome (border, radius, italic uppercase title). Rail stays `overflow: hidden` / no column scroll. Scanner Quote Panel side-by-side depth+tape and Trading tab unchanged.
- **Why:** User-directed terminal layout; L2 major + top-10; user-controlled L2/T&S height; reference-style separate module cards; no rail scroll.
- **Files touched:** `frontend/src/pages/StockViewPage.tsx`, `frontend/src/stock_view/*` (Header, QuoteCard, Rail, CSS, tests), `frontend/src/ibkr/TickerTradeActionBar.tsx` (`rail` variant), `frontend/src/constantGroups/chart_api.ts`, `frontend/src/styles/stock-view.css` (trimmed), `frontend/src/index.css`, e2e baseline/quote-panels.
- **How it works now:** `StockViewPage` is a thin data coordinator (`useTickerStream` / IBKR status+account / symbol gate `detail.symbol === selectedSymbol` / resizable rail). Layout chrome lives under `stock_view/`. Order path is still `placeIbkrOrder` + existing confirm/spend/paper-live gates; rail omits duplicate account/automate chrome already shown in the header. Styles scoped under `.stock-view-page` in `stockViewTerminal.css`. Rail vertical priority: L2+T&S (grow) → ticket (fixed) → quote (compact).
- **Verified by:** `npm run lint`, `npm run test`, `npm run build` (frontend); Vitest Stock View terminal suite; e2e contract updated for terminal composition.
- **Follow-ups:** Browser visual confirm that ≥10 L2 rows show on a typical 1440×900 Stock View.
- **Related:** User plan `stock_view_terminal_redesign_854387d2.plan.md`; roadmap History note (Phase B remains NEXT).

## 2026-07-16 — Webull widget parity agent and manual-first trade ticket

- **What:** Added `widgets`, a source-backed 25-capability Webull-to-Nova stock/day-trading map, and the dedicated `agent-widgets` Canvas. Reworked both Nova manual order surfaces into one Webull-inspired ticket with preserved Buy/Sell/Market/Limit controls plus Stop orders, share/%/$ sizing, quick presets, limit/stop prices, and regular/extended-hours selection.
- **Why:** The user wants an explicit competitive map that can drive future widget requests and a manual-control foundation for eventual automation without removing current trading or automation buttons.
- **Files touched:** `.cursor/agents/widgets.md`, `.cursor/agent-memory/widgets-memory.md`, `.cursor/rules/widgets-continuity.mdc`, `.cursor/agent-system/registry.json`, `docs/webull-widget-parity.md`, `backend/ibkr/orders.py`, `backend/routes/trading.py`, `frontend/src/ibkr/ManualOrderTicket.tsx`, `ManualOrderFields.tsx`, `orderEntry.ts`, `placeOrder.ts`, `tradeTicket.css`, and focused tests.
- **How it works now:** The parity ledger uses stable `WID-NNN` IDs, per-row S1–S16 evidence, paired Nova paths, honest status, and implementation-ready prompts; its Canvas is a synchronized snapshot. Manual orders still use the one IBKR endpoint and existing confirmation/safety gates. The backend now validates/constructs `MKT`, `LMT`, and `STP`; `outside_rth` is accepted only for Limit. Stock View keeps account metrics, Flatten/Close, Confirm, Auto Paper, Signal, and Stop Automation beside the richer manual ticket. Locked spend status displays a disabled `Unlock Trading` button that cannot bypass environment gates.
- **Verified by:** Focused IBKR suites 41 PASS; backend full suite 677 PASS with a documented local TorchVision/Python 3.13 fatal-loader warning; frontend Vitest 202 PASS; build/lint PASS; agent contract PASS for 7 agents and 24 lifecycle tests PASS; widgets smoke PASS after evidence hardening; tester browser verification PASS with all controls exercised and no order request submitted.
- **Follow-ups:** WID-014 remains partial because trailing stop, stop-limit, and group orders are not implemented. Repair the unrelated local Torch/TorchVision DLL mismatch before treating the broad backend suite as warning-free.
- **Related:** PROBLEM_LOG 2026-07-16 “Full pytest emits TorchVision DLL fatal exception but exits green” and “Canvas TodoList prop failed type-check”.

## 2026-07-16 — Stock View: bump due to news under quote column

- **What:** Moved the "Bump due to news" (`NewsImpactPanel`) from the full-width Stock View footer into the right quote column, directly under quote/fundamentals. The right column now stretches full height beside the charts; news headlines stay under the chart grid only.
- **Why:** User-annotated layout — bump belongs with the stock quote sidebar, not as a wide footer spanning under the charts.
- **Files touched:** `frontend/src/pages/StockViewPage.tsx`, `frontend/src/components/TickerDetailContent.tsx`, `frontend/src/modules/NewsPanel.tsx`, `frontend/src/components/NewsHeadlineSection.tsx`, `frontend/src/styles/stock-view.css`.
- **How it works now:** Stock View left column = charts + headline strip. Right column = L2 / order ticket / quote / fundamentals / bump (via `afterQuote`). `NewsPanel` accepts `includeImpact={false}` so the footer no longer duplicates the bump. Narrow-column CSS stacks impact factors for the sidebar width.
- **Verified by:** Vitest `quotePanels` / `tickerDetailComposition` / `stockViewNav` (19 passed); browser Stock View AAPL — impact under quote (`after_quote`), no duplicate bump in headline footer.
- **Follow-ups:** None.

## 2026-07-16 — HOD Momo table matches Gappers/Gainers density

- **What:** Restored the HOD Momo alert table to the same dense scanner look as Gappers/Gainers/Losers: full-width parent pane, auto column sizing, nowrap numeric cells, single-line strategy pills, and a fixed **30-row** viewport that no longer shrinks when only one alert exists. Also healed empty `timestamp` values (were rendering as "Invalid Date") from `created_ts` on both API serialize and the Time cell. Column names unchanged.
- **Why:** After a prior "expand Strategy / wrap badges" pass, the table looked broken — one tiny clipped row in a sea of empty space, with values hard to read ("can't even see the thirty").
- **Files touched:** `frontend/src/hod_momo/hodMomo.css`, `frontend/src/hod_momo/HodMomoAlertTable.tsx`, `frontend/src/hod_momo/HodMomoAlertRow.tsx`, `frontend/src/constantGroups/chart_api.ts`, `backend/hod_momo_models.py`.
- **How it works now:** Viewport height is always `HOD_MOMO_VISIBLE_ROWS (30) × HOD_MOMO_ROW_HEIGHT_PX (32)` (+ header), matching Large scanner density. Table uses `table-layout: auto` like other scanners (no forced last-column stretch / wrap). Time falls back to `created_ts` when ISO `timestamp` is blank.
- **Verified by:** Browser on HOD Momo — table height 990px with 1 alert; Change % `+30.00%` legible; Gappers comparison; `npm run build`.
- **Follow-ups:** Trace why some live alerts were persisted with `timestamp=""` (likely test pollution / empty constructor path).
- **Related:** PROBLEM_LOG 2026-07-16 "HOD Momo table shrunk to one ugly row".

## 2026-07-16 — Fix HOD Momo RVOL blowup and alert spam (root cause, not the parity-loop band-aids)

- **What:** Fixed three independently-diagnosed root causes behind live-reported HOD Momo garbage: absurd RVOL multiples (700x-11,000x+) and alert-feed spam (~12-24 new rows/30s on a quiet tape). Restored `master.cooldown_sec` to its 60s default (was persisted as `0.0`); added a periodic fundamentals re-fetch so `avg_volume` no longer freezes at whatever yfinance returned the first time a symbol was ever seen; removed a silent Alpaca-IEX-feed fallback that was overriding yfinance's `avg_volume` for `discovery=ibkr`.
- **Why:** User reported the live table/alert feed still showing the exact symptoms a prior session had claimed to fix via pytest/session_gate. Re-verification against the *running* API (not test mocks) found the prior "fixes" never addressed the actual denominator/rate-limit bugs.
- **Files touched:** `backend/hod_momo_persist.py` (cooldown floor guard on load), `backend/hod_momo_heartbeat.py` (`_maybe_refresh_fundamentals`), `backend/hod_momo_enrichment.py` (new `ibkr_avg_volume()`, removed `avg_volume_cache` read from the ibkr branch), `backend/hod_momo_debug.py` (`avg_volume` now visible in `/debug/symbol` and `/debug/snaps`), `backend/constants_hod_momo.py` (`HOD_MOMO_FUNDAMENTALS_REFRESH_SEC`), `backend/tests/test_hod_momo_persist.py`, `test_hod_momo_heartbeat.py`, `test_hod_momo_enrichment.py` (new), `test_integrity_live_builders.py` (unrelated pre-existing gap fixed — mock `_State` was missing `afterhours_cache`).
- **How it works now:** `on_trade_update`'s `(symbol, strategy_id)` cooldown is the only thing standing between one qualifying trade tick and unbounded re-fires — a persisted `cooldown_sec` of 0 (or any value below 1s) is now self-healed back to `HOD_MOMO_COOLDOWN_SEC` on every config load, with a loud warning. For `discovery=ibkr`, `avg_volume` is yfinance-only end-to-end (`ibkr_avg_volume()` in the 30s universe-enrichment loop, matching the fundamentals-queue loop) — Alpaca's IEX-feed daily bars are never consulted, since IEX captures only a sliver of consolidated volume for the thin/low-float names this scanner targets. The active heartbeat now re-queues `mark_needs_fundamentals` for every active symbol every 300s so a multi-day Former Momo runner's `avg_volume` keeps pace with yfinance instead of freezing at whatever was fetched the very first time it was ever flagged (which could be days stale).
- **Verified by:** Live before/after on a cleanly-restarted backend (no stray IBKR-clientId-conflicted process still serving requests): CJMB rvol 7016.02→46.49, LBGJ 1526.36→10.38, ATPC avg_volume 13,620.44→3,375,816.00 (all now matching a fresh yfinance query). Alert growth 0 new rows/60s once cooldown held. `py -3 -m pytest backend/tests/ -k "hod_momo or integrity or spam or heartbeat or active or former or consolidation or enrichment"` → 97 passed; full suite 665 passed. Parity observe loop (`tools/hod_momo_parity_observe.py --interval 30`) ticked 4x with stable, non-runaway `nova=` counts.
- **Follow-ups:** yfinance's own `averageVolume` field itself drifts within minutes for extreme-volume days (live-observed on ATPC), so `HOD_MOMO_FUNDAMENTALS_REFRESH_SEC` is a mitigation, not a perfect fix — some transient staleness between refresh cycles is expected and acceptable. The Warrior↔Nova parity gap (JSPR/BIYA Squeeze timing misses) is unrelated pre-existing work tracked separately in `.tmp/hod-momo-parity/classify_latest.md`.
- **Related:** PROBLEM_LOG 2026-07-16 "RVOL 700x-11000x blowup + alert spam despite 'fixed' prior session".

## 2026-07-16 — Chart session highlighting (pre / RTH / AH)

- **What:** Intraday charts (panel, page, Stock View 2×2) shade bar backgrounds for premarket, regular hours, and after-hours, with a small legend. Daily+ timeframes stay unshaded.
- **Why:** User asked for consistent session highlighting across all charts from a single source of truth.
- **Files touched:** `backend/constants_scanner.py`, `backend/market.py`, `backend/hod_momo_market.py`, `frontend/src/constantGroups/market_ui.ts`, `frontend/src/chart/sessionHighlight.ts`, `SessionHighlightingPrimitive.ts`, `useChartSessionHighlight.ts`, `TickerChart.tsx`, `TickerChartControls.tsx`, `tickerChart.css`.
- **How it works now:** Session bounds live in `SESSION_*_MIN_ET` (backend scanner constants; frontend mirror). `market.py` and HOD helpers use those; every `TickerChart` attaches one LWC bottom-layer primitive that colors each bar from the same ET clock (`isoToEtTime` convention).
- **Verified by:** Vitest `sessionHighlight.test.ts`; typecheck on touched chart files.
- **Follow-ups:** Holiday / early-close aware bands if needed later.
- **Related:** None.

## 2026-07-16 — Stock View: stable L2 badge + trade bar under depth

- **What:** Level 2 always shows a heuristic row (`Seller stacked` / `Bid heavy` / `Wide spread`, or idle `No stack`) so the book no longer jumps. On Stock View, Open/Close/Automate moves under Level 2; “Bump due to news” + News Headline move to the page footer; quote/fundamentals sit under the trade controls.
- **Why:** Empty heuristic row collapsed L2 layout; user wanted trade actions next to the book and news in the footer.
- **Files touched:** `frontend/src/ibkr/DepthLadder.tsx`, `TickerTradeActionBar.tsx`, `tradingTab.css`, `constantGroups/market_ui.ts`, `components/TickerDetailContent.tsx`, `pages/StockViewPage.tsx`, `styles/stock-view.css`, `workspace/layoutStore.ts`.
- **How it works now:** Heuristics row is always mounted. Stock View passes `afterDepth={<TickerTradeActionBar variant="sidebar" />}` and `omitNews`; `NewsPanel` renders in `.stock-view-news-footer`. Scanner side panel layout unchanged.
- **Verified by:** Typecheck/lint on edited files; reload Stock View for CJMB.
- **Follow-ups:** None.

## 2026-07-16 — HOD Strategy column wraps instead of scrolling

- **What:** STRATEGY pills wrap to additional lines and grow the row; the HOD table no longer shows a horizontal scrollbar. Table is locked to parent width (`table-layout: fixed`) with compact metric columns so Strategy takes the remaining space. Symbol consolidation badges (e.g. `(77 in 4sec)`) no longer ellipsize to `(77...`.
- **Why:** Long strategy tags forced the table wider than the main column; fixed Symbol width also clipped consolidation burst text.
- **Files touched:** `frontend/src/hod_momo/hodMomo.css`, `frontend/src/hod_momo/HodMomoAlertRow.tsx`, `frontend/src/constantGroups/chart_api.ts`.
- **How it works now:** `.hod-table-wrapper` is `overflow-x: hidden` + `width: 100%`. Symbol column is wider (`9.5rem`) and allows wrap; `.hod-symbol-burst` shows full text. Strategy gets leftover parent width; pills wrap; rows use `minHeight` so multi-tag alerts expand downward.
- **Verified by:** CSS layout change; reload HOD Momo — check CJMB-style consolidated symbols show full `(N in Nsec)`.
- **Follow-ups:** None.

## 2026-07-16 — Slim dark-theme scrollbars

- **What:** Replaced chunky system-default scrollbars with thin, low-contrast thumbs that match the dark Nova shell (tables, side panel, main page).
- **Why:** Default Windows/Chromium scrollbars were light gray and visually loud against the dark UI.
- **Files touched:** `frontend/src/styles/tokens-shell.css`, `frontend/src/hod_momo/hodMomo.css`.
- **How it works now:** Global `*` + `body` use Firefox `scrollbar-width`/`scrollbar-color` and WebKit `::-webkit-scrollbar*` with `--scrollbar-*` tokens (8px, transparent track, muted thumb that brightens on hover). Explicitly hidden scrollbars (e.g. `.tab-bar-scroll`) still win via higher specificity.
- **Verified by:** CSS tokens wired; reload UI to confirm on HOD Momo table + page scroll.
- **Follow-ups:** None.

## 2026-07-16 — New specialist subagent: `hod-momo` (HOD Momo ↔ Warrior parity)

- **What:** Added a dedicated `hod-momo` specialist to own the ongoing, multi-session HOD Momo scanner data-quality + Warrior parity workstream: run/monitor `tools/hod_momo_parity_observe.py`, classify `warrior_only`/`nova_only` misses into named buckets, propose/apply surgical fixes in `backend/hod_momo*.py`, and track parity metrics + a root-cause ledger (fixed vs still-open) session over session so future runs don't re-diagnose solved bugs.
- **Why:** The parity effort ("this is not going to be a quick one") needed a persistent owner with living memory instead of being re-litigated from scratch by whichever general-purpose session picks it up next; prior CHANGELOG "fixed" claims for HOD Momo integrity/spam were repeatedly found still-broken live.
- **Files touched:** `.cursor/agents/hod-momo.md`, `.cursor/agent-memory/hod-momo-memory.md` (seeded with the last 5 fixed root causes + 4 still-open buckets from CHANGELOG/PROBLEM_LOG + `.tmp/hod-momo-parity/diff_latest.json`), `.cursor/agent-system/registry.json`, `.cursor/rules/specialist-routing.mdc`, `docs/agent-operations.md`, `AGENTS.md` (specialist table), `tools/test_agent_contract.py` (discovery set), new dashboard `agent-hod-momo.canvas.tsx`.
- **How it works now:** Invoke "Use the hod-momo subagent to continue HOD Momo parity" (or the backlog-improvement phrase). The agent reads memory first, gates on `hod_momo_session_gate.py` before trusting any parity count, classifies misses into `universe_gap` / `gate_mismatch` / `l1_capacity` / `rvol_formula` / `timing_definition` / `spam_cooldown` / `capacity_expected`, and hands off to `warrior` for fresh snapshots or `tester` for full verification. Never feeds Warrior rows into Nova's alert engine (single-market-data-feed boundary). Dashboard visualizes recall/precision, a nova_only strategy breakdown, and the fixed/open root-cause ledger from real `.tmp/hod-momo-parity/diff_latest.json` data (captured 2026-07-16T23:31:51Z).
- **Verified by:** `py -3 tools/agent_contract.py` → PASS (6 agents); `py -3 tools/agent_contract.py --ci` → PASS; `py -3 tools/sync_agent_surfaces.py --write` → wrote snapshot blocks to all 6 dashboards + Nova Home; `py -3 -m pytest tools -q` → 122 passed (after updating the hard-coded discovery set in `test_agent_contract.py`); canvas TypeScript check: no errors.
- **Follow-ups:** First real hod-momo run should re-verify the integrity/spam claims live (memory flags this explicitly) before trusting any parity recall/precision number reported here.
- **Related:** PROBLEM_LOG 2026-07-16 HOD Momo integrity/spam/Former-Momo entries; `hod_momo_parity_e02ce8f4.plan.md` (read-only, not edited).

## 2026-07-16 — Active-set session_focus + per-strategy consolidation

- **What:** Reserved `session_focus` L1 slots (Former-list order); quiet-tape heartbeat re-evals those names every 5s; consolidation emits **one alert per strategy_id** (no longer drops Former when Low Float also fires).
- **Why:** LBGJ Former passed in decisions but never appeared in the feed — same-symbol consolidation kept only the last strategy.
- **Files touched:** `hod_momo_active.py`, `hod_momo_heartbeat.py`, `hod_momo_alerts.py`, `ibkr_bridge.py`, `hod_momo_former.py`, `constants_hod_momo.py`, tests.
- **How it works now:** Former-list names keep L1; flat tapes re-check gates; flush consolidates bursts within a strategy, not across strategies.
- **Verified by:** pytest consolidation/active/former/heartbeat; live LBGJ `session_focus` + Former `passed` in decisions.
- **Follow-ups:** JSPR universe; RTH squeeze timing; watch IBKR gainers/seed empty during AH glitches.
- **Related:** PROBLEM_LOG 2026-07-16 consolidation drops Former.

## 2026-07-16 — Former Momo remember + heartbeat SLO + parity observe

- **What:** Auto-remember tickers on non-Former HOD fires into strategy-1 `former_momo_list`; bootstrap from today's alerts; `would_fire_now` matches real Former/HOD gates; heartbeat 0.5s/0.75s stale; HOD seeds include `TOP_PERC_GAIN`; alerts `?limit=` for parity observer; observe prints flush + capped fetch.
- **Why:** Warrior↔Nova parity stuck on empty Former Momo list / universe gaps; integrity false-failed at ~2.1s p95; observe hung on 9k alert dumps.
- **Files touched:** `hod_momo_former.py`, `hod_momo_trade.py`, `hod_momo_admin.py`, `hod_momo_persist.py`, `universe.py`, `constants_hod_momo.py`, `constants_ibkr.py`, `routes/hod_momo.py`, `tools/hod_momo_parity_observe.py`, tests.
- **How it works now:** Any other strategy fire (or session bootstrap from today alerts) seeds Former Momo. Session alert/former symbols stay in focus universe. Seeds include percent gainers. Parity observe refuses on integrity fail; uses limited alerts.
- **Verified by:** pytest former/engine/integrity; live session_gate integrity_only exit 0 (quote p95~0.55s); observe `--once` prints parity counts.
- **Follow-ups:** RTH remeasure; JSPR remains universe miss until IBKR %/volume seeds surface it.
- **Related:** PROBLEM_LOG 2026-07-16 heartbeat SLO / Former Momo empty.

## 2026-07-16 — HOD Momo integrity heartbeat + Warrior parity harness

- **What:** Active-set L1 heartbeat restores quote/eval SLOs on quiet tapes; mode-aware gappers integrity; Warrior-style burst badge (no all-day 1179-in-2157s); session_gate + parity observer tools; spam/mode/heartbeat tests; alerts route date fix.
- **Why:** Live HOD Integrity fail (p95 ages ~hours, CJMB spam badge, stale gappers) blocked Warrior↔Nova parity.
- **Files touched:** `hod_momo_heartbeat.py`, `hod_momo_active.py`, `hod_momo_integrity_*.py`, `integrity_live.py`, `ibkr/ticks.py`, `hod_momo_trade.py`, `app_lifespan.py`, `routes/hod_momo.py`, `collapseAlertsBySymbol.ts`, `tools/hod_momo_session_gate.py`, `tools/hod_momo_parity_observe.py`, tests, `tester.md`.
- **How it works now:** Quiet subscribed/active symbols get 1Hz `note_quote`/`note_evaluation` without re-firing strategies. Gappers stale after open → pass in RTH/AH. UI burst badge only merges within 15s. `session_gate` exit 3=BLOCKED, 2=FAIL; parity observe refuses on fail. Research snapshots under `.tmp/hod-momo-parity/`.
- **Verified by:** pytest integrity/spam/heartbeat/mode/builders; Vitest collapse; live `/api/integrity` coverage=100 p95~1.5s; latency probe coverage 100; session_gate exit 0; alerts GET fixed.
- **Follow-ups:** Persistent observe during RTH; Former Momo list import; tighten nova_only spam vs Warrior.
- **Related:** PROBLEM_LOG 2026-07-16 HOD active ages / burst badge.

## 2026-07-16 — Active-tab IBKR Level-1 streaming (replace impossible snapshot table loop)

- **What:** Scanner table + HOD hot prices now use bounded persistent IBKR `reqMktData` streams for the active tab (≤50) and a reserved HOD pool (40, with volume-seed quota). Batched `/ws/scanner` patches carry `quote_ts`; UI tints per-row staleness. Cold `reqTickersAsync` kept only for discovery/enrichment with honest ≥12s budgets.
- **Why:** Header showed `stale · updated Ns ago` while Connected — IBKR snapshots complete on `tickSnapshotEnd` ~11s, so the prior 1Hz/4s-timeout `reqTickersAsync` loop could never meet a `<3s` SLA.
- **Files touched:** `.cursor/rules/single-market-data-feed.mdc`, `backend/ibkr/ticks.py`, `backend/ibkr/scanner_l1.py`, `backend/scanner_push.py`, `backend/scanner_tab_registry.py`, `backend/ibkr_bridge.py`, `backend/hod_momo_active.py`, `backend/hod_momo_universe.py`, `backend/hod_momo_enrichment.py`, `backend/app_lifespan.py`, `frontend/src/hooks/useScannerPriceStream.ts`, `DashboardPage.tsx`, `ScannerTable.tsx`, constants.
- **How it works now:** Client sends `set_active_tab` on `/ws/scanner`. Reconcile loop opens shared L1 subscriptions (owners: scanner/hod/detail). Ticks coalesce every ~350ms into `price_patch`. HOD discovery still uses HOT_BY_VOLUME / TOP_VOLUME_RATE / MOST_ACTIVE seeds with reserved slots so off-table runners stay live. Open ticker still adds quote/depth/tape.
- **Verified by:** `pytest` L1/HOD/reprice/ticks/integrity suites; Vitest `useScannerPriceStream` + `scanAge`; `tsc --noEmit`.
- **Follow-ups:** Restart API + live Gateway session to confirm subscription counts and liquid-row `<3s` tick-to-UI; watch market-data line budget on the account.
- **Related:** PROBLEM_LOG 2026-07-16 scanner stale / tickSnapshotEnd.

## 2026-07-16 — Close remediation Phase 7: honest close

- **What:** Restored HOD facade test aliases + depth `reset_all` in smart-depth test setup; refreshed `program-close-metrics.md` and `Nova-Roadmap-Status.md` with fresh gate evidence; stamped close tip SHA.
- **Why:** Close-remediation Phase 7 — prior Phase 13 metrics/overclaims were inaccurate; full suite must be green before declaring closed.
- **Files touched:** `hod_momo.py`, `tests/test_ibkr_safety.py`, `architecture/program-close-metrics.md`, `Nova-Roadmap-Status.md`.
- **How it works now:** Backend pytest 636 passed; Vitest 187; maintainer/ruff/eslint/build green; residual torch CVEs documented. Maintenance + close remediation tracks are CLOSED; Phase B ops remain NEXT.
- **Verified by:** full `pytest backend/tests` · tools pytest · vitest · eslint · ruff · maintainer `--fail-on-findings` · `npm run build`.
- **Follow-ups:** Playwright + live IBKR session when Gateway available; Phase B shadow days.

## 2026-07-16 — Close remediation Phase 6: lifecycle tests + lint green

- **What:** Chart stale-request helper + error-boundary + HOD debug-poll lifecycle tests; ESLint/Ruff exit zero via targeted fixes plus justified config (compiler-hook noise off; BLE001 deferred to maintainer swallow detector; TRY400 → `logger.exception`).
- **Why:** Close-remediation Phase 6 — coverage gaps and static-quality gates left open after the architecture program close.
- **Files touched:** `frontend/src/chart/requestVersion*`, `TickerChartErrorBoundary.test.tsx`, `useHodMomoDebugPoll.test.tsx`, chart/hooks cleanup, `eslint.config.js`, `backend/ruff.toml`, IBKR/enrichment/archive lint fixes.
- **How it works now:** `npm run lint` and `ruff check .` are green. Chart crashes stay isolated; debug poll stops after unmount; stale bar responses are rejected by version check.
- **Verified by:** `ruff check .` · `eslint . --max-warnings 0` · Vitest lifecycle suite 4 passed.
- **Follow-ups:** Phase 7 honest ledgers + full gate rerun.

## 2026-07-16 — Close remediation Phase 5: feature barrels + CSS layers

- **What:** Public barrels for `workspace`/`modules`/`ibkr`/`chart`/`hod_momo`; migrated baselined deep cross-feature imports; moved `TickerChart` into `chart/` with a root facade; applied `@import … layer()` in `index.css`; split `hodMomo.css` + settings sheet; deleted unused `App.css`; cleared cross-feature baselines.
- **Why:** Close-remediation Phase 5 — finish ADR 005/006 (barrels + real cascade layers) left incomplete after the architecture program close.
- **Files touched:** `frontend/src/{workspace,modules,ibkr,chart,hod_momo}/index.ts`, import rewrites, `chart/TickerChart.tsx`, `index.css`, `hodMomoSettings.css`, `tools/maintainer_lib/baselines.json`, `architecture/dependency-rules.md`.
- **How it works now:** Cross-feature imports go through public barrels (maintainer 0 non-baseline). All stylesheets are layered; HOD stylesheets are under 700 lines.
- **Verified by:** `maintainer_checks --fail-on-findings` (0 non-baseline) · Vitest workspace/modules/chart 57 passed · `npm run build` ok.
- **Follow-ups:** Phase 6 lifecycle tests + Ruff/ESLint green.

## 2026-07-16 — Close remediation Phase 4: scanner/ticker ports

- **What:** Added `backend/ports/` + `backend/adapters/` + composition wiring for discovery/movers/ticker snapshots; orchestration uses ports instead of constructing IBKR/Alpaca providers; strangler facades document owner phase + removal criterion; shared adapter contract tests.
- **Why:** Close-remediation Phase 4 — finish ADR 002 boundaries left incomplete after the architecture program close.
- **Files touched:** `backend/ports/*`, `backend/adapters/*`, `backend/composition/market_data_providers.py`, `scanner_runners/{discovery,movers}.py`, `ticker_detail.py`, `scan_runners.py`, facade docstrings, `tests/test_provider_contracts.py`.
- **How it works now:** `get_discovery_port` / `get_movers_port` / `get_ticker_snapshot_port` select IBKR or Alpaca adapters from discovery settings. Application modules do not import concrete discovery SDKs for price rows.
- **Verified by:** `pytest tests/test_scan_runners.py tests/test_provider_contracts.py` (8 passed).
- **Follow-ups:** Phase 5 frontend barrels + real CSS `@layer` migration.

## 2026-07-16 — Close remediation Phase 3: feed + symbol correctness

- **What:** IBKR discovery/movers no longer require Alpaca credentials to populate price caches; chart mock-bar fallback is forbidden under `discovery=ibkr`; quote chart binds to `selectedSymbol` and live-trade merges ignore mismatched symbols.
- **Why:** Close-remediation Phase 3 — stop discarding valid IBKR rows when listing metadata is absent, and stop showing synthetic/stale chart data under an IBKR quote.
- **Files touched:** `backend/scanner_runners/{discovery,movers}.py`, `backend/tests/test_scan_runners.py`, `frontend/src/chart/{useChartBars,useChartLiveTrade,chartBarsPolicy,liveTradeGate}.ts`, `TickerChart.tsx`, `TickerDetailContent.tsx`.
- **How it works now:** Missing Alpaca headers skip news/avg-volume enrichment only. Empty IBKR bars surface an error (no mock candles). Chart + T&S-style live merges gate on the open symbol.
- **Verified by:** `pytest tests/test_scan_runners.py` (3 passed) · Vitest chart policy/gate + composition tests (7 passed).
- **Follow-ups:** Phase 4 ports/adapters boundaries.
- **Related:** PROBLEM_LOG — IBKR discarded without Alpaca keys.

## 2026-07-16 — Close remediation Phase 2: deps + silent handlers

- **What:** Upgraded `python-dotenv`/`transformers`/`torch`; replaced silent WebSocket and coercion `except: pass` handlers with narrow disconnect/cancel handling or explicit defaults; removed IBKR depth `reset_all()` from import time (tests call public `reset_all`).
- **Why:** Close-remediation Phase 2 — CVE surface + Phase 11 honesty + reload-safe depth state.
- **Files touched:** `backend/requirements.txt`, `backend/routes/{hod_momo,ticker}.py`, enrichment/scanner/ticker_detail/ticks/news helpers, `ibkr/depth/__init__.py`, `security/dependency-compensating-controls.md`.
- **How it works now:** Maintainer reports 0 non-baseline findings. Residual torch CVEs without fix are documented with compensating controls. Depth state resets only via explicit API.
- **Verified by:** maintainer 0 non-baseline · focused depth/news/lifecycle tests 43 passed · `pip_audit` residual torch-only.
- **Related:** PROBLEM_LOG for prior overstated swallow-zero claim.

## 2026-07-16 — Close remediation Phase 1: truthful maintainer audit

- **What:** Maintainer scanner now detects tuple `except (...): pass` swallows, fingerprints legacy cross-feature imports (new violations fail `--fail-on-findings`), and treats ignored local artifacts as informational. Fixed stale agent-contract discovery for five specialists including `warrior`.
- **Why:** Post-close review found Phase 11/13 claims overstated (missed WebSocket swallows; architecture baselines were unconditional).
- **Files touched:** `tools/maintainer_checks.py`, `tools/maintainer_lib/{baselines,artifacts,deps}.py`, `tools/test_maintainer_checks.py`, `tools/test_agent_contract.py`.
- **How it works now:** Fingerprints live in `tools/maintainer_lib/baselines.json`. Production `import main` / cross-feature / swallow findings are non-baseline unless listed. Artifacts only fail when git-tracked.
- **Verified by:** `pytest tools` 122 passed; `pytest tools/test_maintainer_checks.py tools/test_agent_contract.py` 25 passed.
- **Follow-ups:** Phase 2 remediates the newly visible swallowed handlers and dependency CVEs.

## 2026-07-16 — Maintenance Phase 13: architecture program close

- **What:** Closed Pattern-Driven Architecture Phases 0–13. Recorded final metrics, refreshed maintainer memory, trimmed `sync_agent_surfaces.py` under 400 lines.
- **Why:** Program definition of done — verify gates, publish ledger, stop.
- **Files touched:** `architecture/program-close-metrics.md`, maintainer memory, roadmap status, CHANGELOG, `tools/sync_agent_surfaces.py`.
- **How it works now:** `index.css` import-only; `main.py`/`App.tsx` within hard limits; HOD/scanner/ticker/depth modularized; constants are barrels; swallowed exceptions cleared; executor deferral documented. Compatibility facades remain with owners.
- **Verified by:** maintainer (0 swallows) · pytest **669** · Vitest **178** · `npm run build` · Playwright **14**.
- **Related:** `architecture/program-close-metrics.md` before/after table + phase SHAs.

## 2026-07-16 — Maintenance Phase 12: defer executor split

- **What:** Documented deferral of `executor.py` structural split; kept the accepted 494-line safety baseline. No code movement of the placement gate chain.
- **Why:** Forced split without a Phase-10-style shared state owner risks stale aliases and fragments the auditable `place_from_ticket` gate chain.
- **Files touched:** `architecture/phase-12-executor-deferral.md`, roadmap status, CHANGELOG.
- **How it works now:** Future fill/state extracts require an explicit executor state owner + security review; `auto_live` stays rejected.
- **Verified by:** Document review against Phase 12 Done (deferral with evidence); executor line count unchanged at 494.

## 2026-07-16 — Maintenance Phase 11: error visibility sweep

- **What:** Replaced remaining production/tool `except: pass` swallows (cache, scanner_push, tape_stream, ticks, nova_os events, create_nova_agent, depth/HOD queue paths) with narrow exception types and logging.
- **Why:** Phase 11 — fail loud / observe failures instead of silent suppression.
- **Files touched:** `backend/cache.py`, `scanner_push.py`, `ibkr/tape_stream.py`, `ibkr/ticks.py`, `ibkr/depth/state.py`, `nova_os/events.py`, `hod_momo_trade.py`, `hod_momo_alerts.py`, `tools/create_nova_agent.py`, focused tests, PROBLEM_LOG.
- **How it works now:** Expected disconnects/queue races log at debug; unexpected I/O failures warn; cancellation/system exceptions are not swallowed.
- **Verified by:** maintainer swallowed_exception 11→0 · focused error-visibility tests 17 passed.

## 2026-07-16 — Maintenance Phase 10: modular HOD Momo engine

- **What:** Replaced `hod_momo.py`'s mutable-global monolith with one replaceable `HodMomoState` owner and focused persistence, session, market, trade, alert, and admin modules. The original import path is now a 137-line compatibility facade.
- **Why:** Maintenance Phase 10 (ADR 003/004) required stale-alias-safe state ownership before extracting imperative-shell boundaries.
- **Files touched:** `backend/hod_momo*.py`, `backend/app_lifespan.py`, `backend/constants_hod_momo.py`, HOD characterization tests.
- **How it works now:** Every stateful HOD boundary resolves `hod_momo_state.get_state()` at call time. Persistence/session, surge buffers, IBKR-fed trade evaluation, consolidation/WS, configs/blocklist, and debug queries use the current owner.
- **Verified by:** HOD tests 61 · focused 8–10 suite 35 · facade 137 lines.
- **Related:** PROBLEM_LOG 2026-07-16 stale HOD state aliases.

## 2026-07-16 — Maintenance Phase 9: IBKR depth package split

- **What:** Converted `backend/ibkr/depth.py` into a package (`state`, `handlers`, `subscribe`, `stream`) with a thin facade. Cleanup paths log narrowly instead of silent `except: pass`.
- **Why:** Phase 9 — preserve depth lifecycle while meeting file-size limits.
- **Files touched:** `backend/ibkr/depth/` package (replaces monolith file).
- **How it works now:** Public API unchanged; refcount/eviction/SMART L1 fallback/symbol gates preserved; no Alpaca depth.
- **Verified by:** depth stability + related L2/tape importer tests (agent report 32+36).

## 2026-07-16 — Maintenance Phase 8: scan_runners + ticker facades

- **What:** Split `scan_runners.py` into `scanner_runners/{discovery,afterhours,movers}` and `ticker.py` into cache/Alpaca/IBKR/detail modules with thin facades. Uses `runtime_state`; IBKR discovery never falls back to Alpaca prices.
- **Why:** Phase 8 after scanner state ownership (ADR 002 ports).
- **Files touched:** `backend/scan_runners.py`, `backend/scanner_runners/*`, `backend/ticker*.py`.
- **How it works now:** Callers keep importing facades; orchestration lives in submodules with `TickerSnapshotPort` for IBKR quotes.
- **Verified by:** test_scan_runners + test_ibkr_cache_priority · focused 35 with depth/HOD.

## 2026-07-16 — Maintenance Phase 7: explicit scanner runtime state

- **What:** Moved scanner caches, mode/health status, HOD watch universe, and env-derived scanner config from `main.py` into typed `backend/runtime_state/`. Production modules no longer lazy-import `main` for state.
- **Why:** Phase 7 — remove FastAPI composition root as a shared-state hub (ADR 001/002).
- **Files touched:** `backend/runtime_state/*`, `backend/main.py` (18-line composition root), scanner/ticker/route/WS consumers, related tests.
- **How it works now:** Consumers use `ScannerRuntimeState` / config providers with reset/rebinding APIs. Tests import `main.app` only; cache patches target runtime_state.
- **Verified by:** `test_runtime_state` + cache-priority · full backend suite 622 passed (agent report) · no production `import main` state access.

## 2026-07-16 — Maintenance Phase 6: low-coupling backend/tool splits

- **What:** Strangler-facade splits for `hod_momo_integrity`, `news/impact`, `archive/r2`, and `tools/security_lib/checks` into focused modules under 400 lines; original import paths remain barrels.
- **Why:** Phase 6 of the pattern-driven architecture roadmap (ADR 004).
- **Files touched:** `backend/hod_momo_integrity*.py`, `backend/news/impact*.py`, `backend/archive/r2*.py`, `tools/security_lib/checks*.py`.
- **How it works now:** Callers keep importing facade paths; implementation lives in family modules (evaluators / helpers / client / day upload / check families).
- **Verified by:** pytest integrity 7 · news 32 · archive r2 10 · security_audit 27 (69 combined spot check).

## 2026-07-16 — Maintenance Phase 5: TickerChart lifecycle hooks

- **What:** Extracted chart instance, bars fetch/versioning, live-trade merge, and drawing-manager lifecycle into `frontend/src/chart/*`. `TickerChart.tsx` is a 187-line composition shell with error boundary + symbol remount preserved.
- **Why:** Phase 5 of the pattern-driven architecture roadmap (ADR 005).
- **Files touched:** `frontend/src/TickerChart.tsx`, `frontend/src/chart/useChart*.ts`, related helpers/types.
- **How it works now:** Hooks own create/dispose/resize, REST versioning/stale rejection, monotonic live candles, and drawings; public `ChartTradeUpdate` export unchanged for ChartGrid.
- **Verified by:** Vitest 178 · `tsc -b` · tickerChartData tests.

## 2026-07-16 — Maintenance Phase 4: split HotkeyManager and HOD settings/debug

- **What:** Decomposed `HotkeyManager`, `HodMomoSettings`, and `HodMomoDebugPanel` into focused child components/hooks under file-size limits. Parents are composition shells; DAS import still authoring-only.
- **Why:** Phase 4 of the pattern-driven architecture roadmap (ADR 005 feature slices).
- **Files touched:** `frontend/src/hotkeys/*`, `frontend/src/hod_momo/*` (settings/debug children + poll hook).
- **How it works now:** Hotkeys UI composes toolbar/table/preview children; HOD settings uses Strategy/Master/Blocklist panels; debug polling lives in `useHodMomoDebugPoll` (stops on unmount).
- **Verified by:** Vitest 178 (hotkeys 19) · Playwright baseline 3 · parent line counts 170/94/66.

## 2026-07-16 — Maintenance Phase 3: domain constants + compatibility barrels

- **What:** Split backend constants into domain modules (`constants_scanner/hod_momo/ibkr/archive_news/nova_os`) and frontend into `constantGroups/*`. `constants.py` / `constants.ts` are re-export barrels. Amended centralized-constants governance.
- **Why:** Phase 3 of the pattern-driven architecture roadmap (ADR 004 strangler barrels).
- **Files touched:** `backend/constants*.py`, `frontend/src/constants.ts`, `frontend/src/constantGroups/*`, `.cursor/rules/centralized-constants.mdc`, `gemini.md` / `AGENTS.md`, `test_constants_domains.py`.
- **How it works now:** Existing `from constants import X` / `from '../constants'` keep working. New tunables belong in domain modules, not the barrels.
- **Verified by:** `pytest backend/tests/test_constants_domains.py` · Vitest 178 · `tsc -b`.

## 2026-07-16 — Maintenance Phase 2: split index.css into domain stylesheets

- **What:** Mechanically split `frontend/src/index.css` (6168 lines) into ordered domain stylesheets under `styles/`, `hod_momo/`, `chart/`, `ibkr/`, and `reports/`. `index.css` is now an 18-line import-only entry with reserved `@layer` order (rules stay unlayered for cascade parity).
- **Why:** Phase 2 of the pattern-driven architecture roadmap (ADR 006).
- **Files touched:** `frontend/src/index.css`, new CSS under `styles/` + feature folders; maintainer `INDEX_CSS_LIMIT=50`.
- **How it works now:** `main.tsx` still imports `./index.css`; Vite resolves `@import`s in monolith order. Stock View `100dvh` / overflow-lock CSS lives in `styles/stock-view.css`.
- **Verified by:** Vitest 178 · `npm run build` · Playwright 14 (incl. Stock View no page scroll) · maintainer CSS table · content reconstruct equal (collapsed blanks).

## 2026-07-16 — Maintenance Phase 1: maintainer CSS and dependency gates

- **What:** Extended `tools/maintainer_checks.py` with CSS hard limit (`index.css` ≤1000), domain CSS reporting, accepted-baseline growth detection, and warning-first `import_main` / cross-feature import checks (`tools/maintainer_lib/deps.py`).
- **Why:** Phase 1 of the pattern-driven architecture roadmap — enforce boundaries before mechanical splits.
- **Files touched:** `tools/maintainer_checks.py`, `tools/maintainer_lib/*`, `tools/test_maintainer_checks.py`, `.cursor/rules/file-size-limits.mdc`, maintainer memory.
- **How it works now:** Scan prints CSS line table; `index.css` at 6168 hard-fails until Phase 2; legacy `import main` findings are baseline warnings; growth past `BASELINE_ACCEPTED_LINES` is non-baseline.
- **Verified by:** `pytest tools/test_maintainer_checks.py` (12 passed) · `py -3 tools/maintainer_checks.py` reports 6168-line stylesheet.

## 2026-07-16 — Maintenance Phase 0A: architecture contract ADRs

- **What:** Added `architecture/` ADRs and dependency rules approving modular monolith, selective hexagonal ports, functional core/imperative shell, Strangler Facades, frontend feature slices, and ITCSS/cascade-layer CSS — before any product code moves.
- **Why:** Phase 0A of the pattern-driven architecture roadmap; “file too large” alone is insufficient justification for new modules.
- **Files touched:** `architecture/README.md`, `architecture/dependency-rules.md`, `architecture/phase-destination-map.md`, `architecture/decisions/001–006`, `gemini.md` pointer, roadmap status, CHANGELOG.
- **How it works now:** Agents classify imports via `dependency-rules.md`; each Phase 1–13 destination is mapped; rejected alternatives (microservices, full FSD rename, big-bang Tailwind) are explicit.
- **Verified by:** Docs-only review against plan Done criteria; no runtime code changed.
- **Related:** Phase 0 SHA `00f0d21`.

## 2026-07-16 — Maintenance Phase 0: architecture baseline

- **What:** Opened the Pattern-Driven Architecture maintenance track; recorded line counts, maintainer findings, test collect counts, and branch ownership. No product code moved.
- **Why:** Phase 0 of `maintenance-audit-roadmap_519236d4.plan.md` — stabilize before ADRs and structural splits.
- **Files touched:** `architecture/baseline-phase0.md`, `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md`, `CHANGELOG.md`.
- **How it works now:** Working tree was already clean (G2 hotkeys committed). Baselines live under `architecture/`; roadmap status has a maintenance ledger that does not change Phase B/C/I.
- **Verified by:** `py -3 tools/maintainer_checks.py` (38/36) · pytest collect 617 · `npx vitest run` 178 passed.
- **Follow-ups:** Phase 0A architecture ADRs before any product moves.

## 2026-07-16 — List all specialists on Nova Home canvas

- **What:** Nova Home “Specialized agents” section now renders the full registry roster (Tester, Maintainer, Security, Docs, Warrior Navigator) from `NOVA_HOME_AGENT_SNAPSHOT`, with invoke phrases and dashboard links.
- **Why:** User asked to list agents on Nova Home; the old hand-coded cards omitted Warrior and ignored the sync snapshot.
- **Files touched:** `tools/sync_agent_surfaces.py` (`home_agents_block` fields), `nova-home.canvas.tsx`.
- **How it works now:** `py -3 tools/sync_agent_surfaces.py --write` refreshes the roster from `.cursor/agent-system/registry.json`; the table always shows every registered agent.
- **Verified by:** sync write · `pytest tools/test_sync_agent_surfaces.py` · canvas TypeScript check.

## 2026-07-16 — Install warrior specialist agent + agent-warrior canvas

- **What:** Registered a dedicated `warrior` subagent for authenticated Warrior Trading navigation; migrated the unmanaged site-map canvas to `agent-warrior.canvas.tsx` so Nova Home hygiene stays clean.
- **Why:** Docs owns Nova Home / unmanaged canvases; Warrior browsing needed a named owner with invoke phrases and a durable dashboard.
- **Files touched:** `.cursor/agents/warrior.md`, `.cursor/agent-memory/warrior-memory.md`, `.cursor/agent-system/registry.json`, `.cursor/rules/specialist-routing.mdc`, `AGENTS.md`, `docs/agent-operations.md`, `docs/warrior-authenticated-access.md`, Obsidian map/router links, `docs.md` handoff.
- **How it works now:** Say “Use the warrior subagent to navigate Warrior Trading” (or “…map Day Trade Dash”). Profile + runbook unchanged; dashboard is `agent-warrior` only. `nova_docs_inventory` reports zero unmanaged canvases.
- **Verified by:** `py -3 tools/agent_contract.py` PASS (5 agents); `py -3 tools/sync_agent_surfaces.py --write`; inventory `preferred_agent` for `agent-warrior`.
- **Related:** map commit `5c8b878`.

## 2026-07-16 — Phase G2: DAS-compatible hotkey manager (authoring only)

- **What:** Settings gains a Hotkeys section with a DAS-style Name / Key / Command(s) manager: `.htk` import/export, row editor, compatibility report, and Help capability catalog. Imported/edited commands are never registered with `useHotkeys` and never place orders.
- **Why:** User asked for DAS Trader–like hotkey authoring (load public `.htk` scripts, edit Name/Key/Command) before any execution phase. Extends completed Phase G automation bindings without rewriting them.
- **Files touched:** `frontend/src/hotkeys/*`, `frontend/src/components/SettingsWorkspace.tsx`, `frontend/src/pages/DashboardPage.tsx`, `frontend/src/constants.ts`, `frontend/src/index.css`, `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md`, nova-home canvas.
- **How it works now:** Profiles persist in `localStorage` (`nova.hotkeys.profile.v1`). Parse splits only the first two `:` delimiters; long scripts use DAS `~ byteLength:` + 51-byte chunks. Compatibility statuses (Nova active / translatable later / backend required / DAS-IBKR-specific / invalid) are separate from evidence (DAS verified / documented / community). Six Phase G automation shortcuts remain the only executable bindings; a persistent banner states imported commands are inactive.
- **Verified by:** Vitest 178 pass (hotkey + SettingsWorkspace + useHotkeys); `npm run build`; browser Settings → Hotkeys import/Help/F8 safety (no order network) via tester subagent.
- **Follow-ups:** Future execution phase may map “translatable later” rows to guarded Nova actions; do not enable without explicit roadmap unlock. `auto_live` remains NO-GO.
- **Related:** commit `645761b`; Phase G finish `722d614`; plan `hotkey_capability_catalog_ad947399.plan.md` (do not edit).

## 2026-07-16 — Warrior authenticated site map + access runbook

- **What:** Added a repeatable headed browser launcher and durable maps of the full Warrior member site (dashboard, LMS, Day Trade Dash widgets, support/CRM entry points) for future agent questions. No Nova UI product changes.
- **Why:** User needs agents to navigate Warrior freely (not just chatroom) when asking for Warrior-parity features later.
- **Files touched:** `scripts/open_warrior_site.ps1`, `docs/warrior-authenticated-access.md`, `knowledge/obsidian/01-Courses/Warrior-Trading/Authenticated-Site-Map.md`, `Memory-Router.md`, `Local-Library-Inventory.md`, `.gitignore` (canvas later migrated to `agent-warrior`).
- **How it works now:** Run `.\scripts\open_warrior_site.ps1` — profile lives under `%LOCALAPPDATA%\Nova\browser-profiles\warrior-site` (never in git). Site hierarchy + Day Trade Dash column/widget inventory lives in Obsidian; visual summary owned by the `warrior` agent canvas. Secrets/cookies/SSO JWTs stay out of the repo.
- **Verified by:** Live login to Members Dashboard, LMS Learner Home + BA101 chapter index, Day Trade Dash after disclaimer ACCEPT; screenshots under `.tmp/warrior-site-map/` (gitignored).
- **Follow-ups:** When building a Nova multi-widget dash, use workspace Phase 8 + this map; do not scrape Warrior feeds.

## 2026-07-16 — Ship pending docs, Vale, and security registry leftovers

- **What:** Committed remaining untracked/modified work: Nova docs inventory tool + tests, Vale/markdownlint pins, Security-Status + findings-registry compensating controls, security check updates, Skills-Library / roadmap-status sync, continuity rules pointing at `nova-home` canvas, `cvss` in requirements-dev. Ignored dated `graphify-out/20*/` snapshots (canonical graph stays at `graphify-out/` root).
- **Why:** Working tree still had leftover files after prior agent/docs/security sessions; user asked for a clean committed+pushed repo.
- **Files touched:** `tools/nova_docs_inventory.py`, `tools/test_nova_docs_inventory.py`, `.vale*`, `.markdownlint-cli2.jsonc`, `docs/SOURCE-PINS.md`, `security/*`, `knowledge/obsidian/**`, `.cursor/rules/nova-*-continuity.mdc`, `.gitignore`, `backend/requirements-dev.txt`.
- **How it works now:** `git status` clean on master after this push; graphify dated folders stay local-only.
- **Verified by:** `git status` clean after commit+push.

## 2026-07-16 — Backend outage flags (API_DOWN / API_WEDGED)

- **What:** When the API drops, the header shows a stable flag chip (`API_DOWN`, `API_WEDGED`, `API_HTTP`) plus a short message/hint; console logs `[Nova][API_FLAG] …` for fast grep. Scanner fetches abort after 8s so a hung port surfaces in seconds, not minutes.
- **Why:** Last outage was a wedged listener on `:8000`; plain "Backend unreachable" did not say whether the process was missing vs hung.
- **Files touched:** `frontend/src/utils/diagnoseBackend.ts`, `hooks/useScannerData.ts`, `components/AppHeader.tsx`, `EmptyState.tsx`, `BackendStartButton.tsx`, `types/health.ts`, `constants.ts`, `index.css`.
- **How it works now:** Network/timeout on scanner poll → probe `/api/health` (2.5s) → classify → show flag + Start API. Hover the flag for the remediation line. F12: search `API_FLAG` or `API_WEDGED`.
- **Verified by:** Vitest `diagnoseBackend` + `startLocalApi`; `npm run build`.
- **Related:** PROBLEM_LOG 2026-07-16 — Wedged API on port 8000.

## 2026-07-16 — Start API button for Backend unreachable

- **What:** When the header shows Disconnected / "Backend unreachable", a **Start API** button appears. One click kills a wedged process on port 8000 and restarts the local FastAPI (Vite-dev via `POST /__nova/start-api`, Electron via `nova:restartApi` IPC).
- **Why:** A hung orphan python on `:8000` made the UI look permanently offline ("Backend unreachable"); users needed a one-click recovery without hunting for `Run Nova.bat`.
- **Files touched:** `frontend/src/components/BackendStartButton.tsx`, `AppHeader.tsx`, `DashboardPage.tsx`, `utils/startLocalApi.ts`, `scripts/vite-nova-start-api.ts`, `vite.config.ts`, `electron/{main,preload,sidecar}`, `constants.ts`, `index.css`.
- **How it works now:** Disconnected → click **Start API** → Stop-NovaPorts(8000) + Start-NovaApi.ps1 (browser/Vite) or restart sidecar (desktop) → wait for `/api/health` → scanner refetch. If the button is missing, double-click `Run Nova.bat`.
- **Verified by:** Killed wedged PID on 8000, restarted API (`/api/health` OK); Vitest `startLocalApi` (2); `npm run build`; Vite restarted with start-api middleware.
- **Related:** PROBLEM_LOG 2026-07-16 — Wedged API on port 8000.

## 2026-07-16 — Unified Nova agent lifecycle OS

- **What:** Versioned agent contract + registry under `.cursor/agent-system/`; memories moved to `.cursor/agent-memory/` (no longer discovered as callable agents); four agents normalized to shared lifecycle headings + Lifecycle footer; specialist routing rule; fail-open `subagentStop` hook; `sync_agent_surfaces` / `create_nova_agent` / `agent_contract` tools + tests; CI `agent-contract` job; ops guide `docs/agent-operations.md`.
- **Why:** Memory Markdown in `.cursor/agents/` was exposed as fake agents; wiring was duplicated across prompts, canvases, and docs with no blocking validation for future agents.
- **Files touched:** `.cursor/agent-system/*`, `.cursor/agent-memory/*`, `.cursor/agents/*.md`, `.cursor/hooks.json`, `.cursor/rules/specialist-routing.mdc`, `tools/agent_contract.py`, `tools/sync_agent_surfaces.py`, `tools/create_nova_agent.py`, `tools/subagent_lifecycle_hook.py`, matching tests, `.github/workflows/deploy.yml`, `docs/agent-operations.md`, AGENTS/gemini, canvases (generated snapshot blocks).
- **How it works now:** Only real prompts live in `.cursor/agents/`. Registry owns wiring. Canvases get generated snapshot blocks via `sync_agent_surfaces.py --write`. Every agent report ends with a **Lifecycle** line; the hook may remind once. Future agents use `create_nova_agent.py` then must pass `agent_contract.py`.
- **Verified by:** `py -3 tools/agent_contract.py` PASS (4 agents); 27 tool tests PASS; sync dry-run/write idempotent (second write=0).
- **Follow-ups:** Smoke-invoke each specialist in a live chat to confirm memory paths + Lifecycle footer; optionally bind canvas Stat widgets to generated snapshot consts.
- **Related:** PROBLEM_LOG 2026-07-16 memory-as-agent discovery.

## 2026-07-16 — Docs (docs + canvas steward)

- **What:** Added `docs` subagent + living memory + `docs-continuity.mdc`. Adopted upstream standards (Diátaxis, markdownlint-cli2 0.23.0, Vale 3.15.1 + Google/write-good, Lychee 0.24.2) with pins in `docs/SOURCE-PINS.md`. Added deterministic `tools/nova_docs_inventory.py` (+ tests). Dashboard is Nova Home (no separate agent-nova canvas). Merged unmanaged `nova-security-audit` into `agent-security` and deleted the orphan.
- **Why:** User asked for a dedicated documentation agent that uses real GitHub standards (not invented house rules) and stewards canvases so random boards do not accumulate.
- **Files touched:** `.cursor/agents/docs.md`, `docs-memory.md`, `.cursor/rules/docs-continuity.mdc`, `.markdownlint-cli2.jsonc`, `.vale.ini`, `.vale/styles/Vocab/Nova/accept.txt`, `docs/SOURCE-PINS.md`, `tools/nova_docs_inventory.py`, `tools/test_nova_docs_inventory.py`, `.gitignore`, canvases (`nova-home`, `agent-security`), `AGENTS.md`, `gemini.md`, `Security-Status.md`.
- **How it works now:** Invoke “Use the Docs to review documentation” or “canvas hygiene.” Preferred canvases: `nova-home`, `agent-*`, Cursor `context-usage-*`. Unmanaged canvases require evidence before delete (or ask). Missing Vale/Lychee = BLOCKED gate, not silent skip.
- **Verified by:** `pytest tools/test_nova_docs_inventory.py`; `nova_docs_inventory.py --json`; canvas TypeScript clean.
- **Follow-ups:** Install Vale + Lychee locally; warning-first CI for docs linters (Docs backlog).

## 2026-07-16 — Security sentinel + baseline audit registry

- **What:** Enriched `security/findings-registry.json` with `compensating_controls` for all 6 open findings (SEC-001–SEC-006). Updated `Security-Status.md` with real SEC-* rows, verification ledger entry, and current-position reflecting baseline captured. Updated `security-memory.md` run log. Added maintenance-log rows to `gemini.md` and `AGENTS.md`.
- **Why:** Post-install documentation pass after the initial security subagent baseline scan produced 6 findings — the registry existed but `compensating_controls` fields were empty and the status ledger still said "not yet run."
- **Files touched:** `security/findings-registry.json`, `knowledge/obsidian/03-Nova-Decisions/Security-Status.md`, `.cursor/agents/security-memory.md`, `gemini.md`, `AGENTS.md`, `CHANGELOG.md`.
- **How it works now:** Registry has compensating context for each finding so future agents understand the accepted risk surface without re-triaging from scratch. `security-review` (Cursor) owns diff triage; `security` (Nova) owns scheduled full-repo posture — these roles are distinct and documented in `Security-Status.md`. All 6 findings remain **open/unfixed** — the compensating controls are acknowledgement of mitigating architecture, not remediation.
- **Verified by:** Manual review of registry JSON and status ledger; no product code changed.
- **Follow-ups:** Add USER directive to Dockerfile (SEC-006); restrict GET /api/config (SEC-001); add API auth middleware (SEC-004); add gitleaks/osv-scanner/semgrep to CI (SEC-005).
- **Related:** Prior entry 2026-07-16 "Security audit runner and findings registry" (initial scan + tooling); `security/findings-registry.json` (canonical finding IDs).

## 2026-07-16 — Specialized agent canvases (tester / maintainer / security)

- **What:** Added three Cursor dashboards — `agent-tester`, `agent-maintainer`, `agent-security` — and linked them from `nova-home`. Each mirrors that subagent’s gates, backlog, and latest scan/memory. Agent `.md` specs now point at their canvas.
- **Why:** User asked for dedicated canvases under the three specialized agents.
- **Files touched:** `canvases/agent-*.canvas.tsx`, `nova-home.canvas.tsx`; `.cursor/agents/{tester,maintainer,security}.md`.
- **How it works now:** Open the agent canvas beside chat when running or reviewing that agent. Refresh after audits / full gate runs. Security canvas is for `security` (full-repo), not Cursor `security-review` (diff).
- **Verified by:** Canvas TypeScript clean; live `maintainer_checks` (34 findings) + `security_audit` (5 open: 2 crit / 2 high / 1 med).
- **Follow-ups:** Tester memory count refresh; triage SEC-001–005; install blocked security tools.

## 2026-07-16 — Security audit runner and findings registry

- **What:** Added a modular, side-effect-free security audit tool stack under `tools/security_audit.py` + `tools/security_lib/` (normalize, registry, redact, checks). First scan produced 5 open findings (SEC-001–SEC-005) written to `security/findings-registry.json`. 27 pytest tests pass.
- **Why:** Phase to establish deterministic security scanning baseline for Nova, with persistent SEC-NNN ID tracking and merge semantics that preserve human triage decisions (accepted/false_positive status survives re-scans).
- **Files touched:** `security/schema.md`, `security/findings-registry.json`, `security/SOURCE-PINS.md`, `security/safe_api_profile.json`, `tools/security_audit.py`, `tools/security_lib/__init__.py`, `tools/security_lib/normalize.py`, `tools/security_lib/registry.py`, `tools/security_lib/redact.py`, `tools/security_lib/checks.py`, `tools/test_security_audit.py`.
- **How it works now:** Run `py -3 tools/security_audit.py --json --write-registry` from repo root. Built-in checks (no binary required) always fire: credential exposure in GET /api/config (critical), unauthenticated executor POST routes (critical), CORS wildcard default (high), no API auth middleware (high), CI missing security jobs (medium). External tools (semgrep, gitleaks, osv-scanner, trivy, pip-audit, npm) are detected at runtime; if missing they are reported as BLOCKED (not clean). Fingerprint = SHA-256(source+kind+path+title); re-scans preserve IDs and human-set statuses. `--fail-on-findings` exits 1 on new critical open findings.
- **Verified by:** `py -3 -m pytest tools/test_security_audit.py -q` → 27 passed; `py -3 tools/security_audit.py --json --write-registry` → 5 findings SEC-001–SEC-005 written.
- **Follow-ups:** Add gitleaks/osv-scanner/semgrep to CI deploy.yml; add auth middleware to backend; restrict GET /api/config to authenticated callers only.

## 2026-07-16 — Single Nova homepage canvas (retire stale boards)

- **What:** Consolidated five overlapping Cursor canvases into one project homepage (`nova-home.canvas.tsx`) with live health, roadmap queue, control ladder, shipped inventory, and doc links. Deleted stale boards: master-roadmap, OS mission, product-health, gap-and-opportunity, module-architecture-audit.
- **Why:** Boards had drifted (gap analysis still called alerts/workspace “missing”; product-health stuck on 396 tests). User asked for one clean homepage dashboard.
- **Files touched:** `canvases/nova-home.canvas.tsx` (Cursor projects); deleted five `.canvas.tsx`; retargeted `Nova-Roadmap-Status.md`, `Nova-OS-Status.md`, `Automation-Roadmap.md`, continuity `.mdc` rules, `AGENTS.md`, `gemini.md`.
- **How it works now:** Open `nova-home.canvas.tsx` beside chat for status. Agents refresh that file when phase or live health changes. System `context-usage-*.canvas.tsx` left alone (Cursor-owned).
- **Verified by:** Canvas TypeScript check clean; live probes `/api/health`, `/api/ibkr/status`, `/api/integrity`, `/api/archive/health` embedded as of tip `29d836f`.
- **Follow-ups:** Re-probe integrity during RTH; refresh stats after next verify suite.
- **Related:** Canvas inventory cleanup 2026-07-16

## 2026-07-16 — security subagent installed

- **What:** Added three new files: `.cursor/agents/security.md` (agent definition, 156 lines), `.cursor/agents/security-memory.md` (living memory with accepted risks table, backlog, run log), `.cursor/rules/security-continuity.mdc` (glob-scoped pre-edit protocol for security-sensitive modules). Also scaffolded `security/findings-registry.json` as the canonical `SEC-NNN` findings store.
- **Why:** User-requested security posture sentinel distinct from Cursor's built-in `security-review` subagent (which handles PR/diff reviews). `security` does full-repo audits, CVSS/OWASP rating, dep CVE scanning, secrets sniffing, and maintains a durable accepted-risks registry.
- **Files touched:** `.cursor/agents/security.md`, `.cursor/agents/security-memory.md`, `.cursor/rules/security-continuity.mdc`, `security/findings-registry.json`.
- **How it works now:** Invoke with "Use the security subagent to audit the repo." It reads memory + registry first (honors accepted risks), runs `py -3 tools/security_audit.py --json` + pip_audit + npm audit + ruff + secrets grep, assigns SEC-NNN IDs, and outputs a structured report. `security-continuity.mdc` fires on edits to `backend/ibkr/**`, `backend/strategy/**`, `backend/alerts/**`, execution routes, and `security/**` — prompting agents to check the registry and accepted risks before changing those files.
- **Verified by:** Files created and line counts confirmed (sentinel 156 lines ≤ 180 target; memory 82 lines; rule 48 lines).
- **Follow-ups:** `tools/security_audit.py` still needs to be implemented; CI gate (GitHub Actions) is next in the sentinel's backlog.

## 2026-07-16 — HOD Momo live accuracy: integrity, surge seed, active-set reprice

- **What:** Shipped the previously ghost-documented HOD integrity + Squeeze surge-seed + capacity-bounded active evaluation set. Fail-loud API/CLI/UI banner; IBKR 1Min historical seed on first active entry; fair 1Hz `reqTickersAsync` scheduler (hot + age-rotating tail) without dumping the whole discovery universe into one batch.
- **Why:** Master tip claimed integrity/surge-seed in CHANGELOG but runtime modules were missing; live HOD evaluated ~9 symbols/sec across ~200 watch symbols (~20s cycle) and Squeeze cold-started at `surge=None`.
- **Files touched:** `backend/hod_momo_integrity.py`, `integrity_live.py`, `hod_momo_surge_seed.py`, `hod_momo_active.py`, `hod_momo_flow.py`, `hod_momo.py`, `ibkr/reprice.py`, `ibkr_bridge.py`, `app_lifespan.py`, routes, `tools/hod_momo_integrity_check.py`, `tools/hod_momo_latency_probe.py`, `HodMomoIntegrityBanner.tsx`, constants, tests.
- **How it works now:** Discovery watch set stays broad; only `HOD_MOMO_ACTIVE_SET_CAPACITY` (40) symbols are kept within quote/eval SLOs. Uncovered symbols are explicit in integrity metrics/banner. Surge seed queues once per symbol/session via IBKR bars (no Alpaca fallback under `discovery=ibkr`). `GET /api/integrity` + CLI exit 0/1/2; HOD tab banner uses existing `.hod-integrity-*` CSS.
- **Verified by:** `pytest` full backend 617 passed; targeted integrity/surge/active/reprice; Vitest banner + collapse; `npm run build`. Live: `/api/integrity` + CLI exit codes work; overnight session showed IBKR `reqTickersAsync` snapshot timeouts so quote-age SLO not claimed until market hours.
- **Follow-ups:** 15-minute RTH live probe for p95≤2s / max≤3s gates; Warrior CDP parity harness deferred until cookies/CDP available. Avoid multiple uvicorn processes (orphan workers steal port 8000 / IBKR clientId 1).
- **Related:** Corrects ghost 2026-07-15 integrity/surge-seed CHANGELOG claims; PROBLEM_LOG 2026-07-16 HOD live parity.

## 2026-07-16 — Harden Phases D–G (alert test format + route tests)

- **What:** Fixed empty Discord/Telegram payloads on alert channel Test fire; redacted webhook/bot secrets from sender exception return paths; hardened HOD formatter against null price/change; added formatter/hooks + journal Reports v2 HTTP tests; BacktestPanel no longer double-fetches days on selection; journal `trades` CREATE includes `tags`.
- **Why:** Post-ship harden of Master Roadmap D–G — Test fire was a silent UX bug; route coverage for tags/R/drawdown/import was unit-only.
- **Files touched:** `backend/alerts/{formatters,telegram,discord,generic_webhook,dispatch}.py`, `backend/routes/alerts.py`, `backend/constants.py`, `backend/journal/db.py`, `backend/tests/test_alerts_formatters.py`, `backend/tests/test_journal_reports_v2.py`, `frontend/src/strategy/BacktestPanel.tsx`, `CHANGELOG.md`, `PROBLEM_LOG.md`.
- **How it works now:** `format_event_payload` copies `text` for test/unknown events so Discord embeds and Telegram messages show the test sentence. Sender failures return generic messages; logs keep redacted URLs/tokens. Journal analytics routes covered via TestClient. Routers were already registered in `app_routers.py` (no missing includes).
- **Verified by:** `pytest` alerts + journal reports + backtest (40 passed); Vitest hotkeys/maskSecret/format (18); `npm run build`.
- **Follow-ups:** Live Discord from a real HOD alert still needs a configured channel + market session; Phase B shadow days / Phase C cold `walk_day` remain human ops.
- **Related:** PROBLEM_LOG 2026-07-16 empty Discord embeds; finish pass `722d614`.

## 2026-07-16 — Fix overlapping tab bar labels

- **What:** Tab buttons no longer shrink below their label width, so adjacent titles (e.g. HOD Momo / Trading) stop painting over each other.
- **Why:** User screenshot showed mashed tab text with the cursor on HOD Momo / Trading.
- **Files touched:** `frontend/src/index.css`, `CHANGELOG.md`, `PROBLEM_LOG.md`.
- **How it works now:** `.tab` is `flex: 1 0 auto` — shares spare width when the bar is wide, keeps content width when crowded; `.tab-bar-scroll` still scrolls horizontally on narrow viewports.
- **Verified by:** Frontend build + app launch; CSS review of flex shrink/min-width.
- **Related:** PROBLEM_LOG 2026-07-16 tab mashup entry.

## 2026-07-16 — Roadmap continuity sync after feature dump

- **What:** Aligned `Nova-Roadmap-Status.md` with post-finish-pass reality (A/D–G/J DONE with SHAs; B/C honest ops blockers; I framework/NO-GO; tip `89712d5`; verify counts last-known 592/149/14 @ 2026-07-15). Plan body + canvas outside-repo companions updated to match.
- **Why:** Feature dump left plan body still showing A/D–G/J as PENDING while YAML todos and status were DONE — agents would reopen shipped work.
- **Files touched:** `Nova-Roadmap-Status.md`, `CHANGELOG.md`; plan/canvas under `.cursor/` (may be outside git).
- **How it works now:** NEXT = human Phase B shadow days; BLOCKED = Phase C console/cold day; do not re-implement A/D–G/J; `auto_live` NO-GO.
- **Verified by:** Git history (`9f4ca3f`, `722d614`, `89712d5`); docs cross-check; suites not re-run (counts dated 2026-07-15).
- **Follow-ups:** Graphify: AST `update` + `export wiki` refreshed root `graphify-out/` (249 nodes; wiki rewritten). Full LLM semantic re-extract of Markdown still needs assistant `/graphify --update` if concepts look thin. Re-run full verify when convenient.
- **Related:** Finish pass `722d614`.

## 2026-07-15 — Master Roadmap finish: B/C docs honesty + I framework + J decision

- **What:** Phase B day-log template; Phase C Bucket Lock / token rotation / walk_day runbook in `docs/r2-archive-setup.md`; Phase I evidence thresholds in Live-Readiness review; Phase J `Productization-Decision.md` (local-first); Roadmap-Status + plan/canvas synced. B/C/I remain ops-honest (`[~]`), not fake `[x]`.
- **Why:** Close all implementable Master Roadmap todos; document blockers that require human market days / Cloudflare console.
- **Files touched:** `docs/shadow-day-log-template.md`, `docs/r2-archive-setup.md`, `docs/paper-shadow-protocol.md`, `Nova-Roadmap-Status.md`, `Nova-OS-Live-Readiness-Review.md`, `Productization-Decision.md`, plan/canvas.
- **How it works now:** Agents treat B as protocol-ready awaiting ≥5 shadow days; C as docs-ready awaiting cold day + console; I as framework-ready / NO-GO verdict; J as decided local-first. `auto_live` still rejected.
- **Verified by:** Docs review; full suite on finish commit.
- **Related:** Phases D–G code entries below; Phase A `9f4ca3f`.

## 2026-07-15 — Phase E: Nova-native backtest UX on archived 1m bars

- **What:** Added `backend/backtest/` (scorer, engine, jobs), `/api/backtest` routes (`/days`, `/run`, `/health`), and a **Backtest** sub-tab on Watchlist with day/setup picker, metrics table, and honesty banner. No vectorbt at runtime.
- **Why:** Nova Master Roadmap Phase E — product backtest UX on cold-archive replay helpers without live orders or hindsight.
- **Files touched:** `backend/backtest/{__init__,scorer,engine,jobs}.py`, `backend/routes/backtest.py`, `backend/app_routers.py`, `backend/constants.py`, `frontend/src/strategy/{BacktestPanel,WatchlistTab}.tsx`, `backend/tests/test_backtest_{scorer,engine}.py`, `CHANGELOG.md`.
- **How it works now:** POST `/api/backtest/run` loads `bars_by_symbol_for_day`, walks 1m bars with `slice_bars_as_of`, evaluates gap_and_go/bull_flag/abcd, enters long at next bar open, exits at stop/target/EOD. `scorer.score_trades` returns win rate, profit factor, drawdown, equity curve. Response includes `honesty: {bar_resolution: 1m, spread_modeled: false, hindsight: false}`.
- **Verified by:** `py -3 -m pytest backend/tests/test_backtest_scorer.py backend/tests/test_backtest_engine.py -q`.
- **Follow-ups:** Async job polling via `jobs.py` if day walks get slow; richer candidate metadata from archived scanner rows when available.
- **Related:** Phase A skills library; archive replay no-hindsight contract.

## 2026-07-15 — Phase D: outbound alert channels (Discord / Telegram / webhook)

- **What:** Added `backend/alerts/` module with channel persistence, Discord/Telegram/generic webhook senders, dispatch fan-out + status ring buffer, and `/api/alerts` CRUD/test/status routes. HOD Momo flush loop and Nova OS `record_receipt` call thin `hooks.py` helpers. Settings panel gains an "Alert channels" section in the dashboard.
- **Why:** Nova Master Roadmap Phase D — deliver outbound notifications for HOD alerts and interesting Nova OS receipts without touching execution or live-order paths.
- **Files touched:** `backend/alerts/*`, `backend/routes/alerts.py`, `backend/app_routers.py`, `backend/hod_momo.py`, `backend/nova_os/events.py`, `backend/constants.py`, `frontend/src/components/AlertChannelsSettings.tsx`, `frontend/src/hooks/useAlertChannels.ts`, `frontend/src/pages/DashboardPage.tsx`, tests `test_alerts_dispatch.py` / `test_routes_alerts.py`.
- **How it works now:** Channels persist under cache `alerts_channels.json`; secrets are stored but API GET returns masked tails only. `dispatch_alert` fans out to enabled channels and records failures in an in-memory ring surfaced at `GET /api/alerts/status`. HOD alerts fire after WS broadcast via `notify_hod_alert_async`; Nova OS notifies on `KIND_ACTION` / would_execute / executed receipts per constant filter. No auto_live; dispatch errors log warnings and never swallow silently.
- **Verified by:** `py -3 -m pytest backend/tests/test_alerts_dispatch.py backend/tests/test_routes_alerts.py -q`; frontend `maskSecret` Vitest; `npm run build`.
- **Follow-ups:** Optional Discord embed color per strategy; retry/backoff policy for transient HTTP failures.
- **Related:** Master Roadmap Phase D.

## 2026-07-15 — Phase G: executor hotkeys + one-action bracket

- **What:** Added default Automation hotkeys (approve/reject first staged, raise/drop mode, open Flatten dialog, kill switch) via `useHotkeys` + `HotkeySettings`. New **Place bracket…** button approves the first staged ticket through the existing `approveStaged` confirm flow. Order hotkeys no-op in **signal** mode with an inline notice.
- **Why:** Nova Master Roadmap Phase G — keyboard speed for confirm-mode paper brackets without bypassing executor safety or typed FLATTEN confirm.
- **Files touched:** `frontend/src/constants.ts` (HOTKEY_DEFAULTS), `frontend/src/hooks/{hotkeyUtils,useHotkeys,useHotkeys.test}.ts`, `frontend/src/strategy/{HotkeySettings,ExecutorPanel}.tsx`, `CHANGELOG.md`.
- **How it works now:** Hotkeys register only while the Automation panel is active. Approve/reject/arm call the same handlers as the UI buttons (`approveStaged` / `rejectStaged` / arm with window.confirm). Flatten hotkey opens the typed-confirm prompt — it never skips `NOVA_OS_FLATTEN_CONFIRM_TOKEN`. Signal mode blocks approve/reject/arm keys; disarm, flatten-focus, and kill remain available.
- **Verified by:** `cd frontend && npx vitest run src/hooks/useHotkeys.test.ts`.
- **Follow-ups:** User-configurable rebinding (localStorage) if desired later.
- **Related:** Master Roadmap Phase G; no new backend routes (existing staged approve API only).

## 2026-07-15 — Phase F: Reports v2 (tags, R-multiples, drawdown)

- **What:** Extended journal analytics with optional trade `tags`, per-tag performance, R-multiple expectancy (skips trades without stops), equity-curve max drawdown, and new Reports tab panels below the calendar. Added POST `/api/journal/trades/{id}/tags` and POST `/api/journal/import/ibkr` (Gateway fill probe or JSON trade upload).
- **Why:** Nova Master Roadmap Phase F — richer post-trade analytics without CSV import fiction or live fill invention.
- **Files touched:** `backend/journal/{db,store,tags,r_multiples,drawdown,ibkr_import}.py`, `backend/routes/journal.py`, `backend/constants.py`, `backend/tests/test_journal_reports_v2.py`, `frontend/src/reports/{TagPerformance,RMultiplesPanel,DrawdownPanel,useReportsV2,format,types,ReportsTab}.tsx`.
- **How it works now:** Tags live as JSON on `trades.tags`; analytics read closed trades via existing store helpers. R = pnl / (|entry-stop|×qty) only when stop exists. Drawdown sorts by `closed_ts` and tracks cumulative P&L peak-to-trough. IBKR import never fabricates fills — returns 503 with loud message unless caller uploads explicit JSON trades.
- **Verified by:** `py -3 -m pytest backend/tests/test_journal_reports_v2.py -q`; frontend `format.test.ts`; Reports tab sections wired under calendar.
- **Follow-ups:** Automated round-trip reconstruction from IBKR `fills()` when Gateway history is available.
- **Related:** Master Roadmap Phase F.

## 2026-07-15 — Phase A: vendored agent skills + discoverability indexes

- **What:** Vendored high-fit Cursor skills into `.cursor/skills/` (real files, no symlinks): VectorBT `backtest` / `optimize` / `strategy-compare` / `vectorbt-expert`, `backtesting-frameworks`, `llm-trading-agent-security`. Added Obsidian `Skills-Library.md` + `Reference-Repos.md`, AGENTS.md pointer section, and SOURCE-PINS with commit SHAs.
- **Why:** Nova Master Roadmap Phase A — embed research/backtest/security skills and make them discoverable before Phase E backtest product work.
- **Files touched:** `.cursor/skills/{backtest,optimize,strategy-compare,vectorbt-expert,backtesting-frameworks,llm-trading-agent-security,SOURCE-PINS.txt}`, `knowledge/obsidian/00-System/Skills-Library.md`, `knowledge/obsidian/00-System/Reference-Repos.md`, `AGENTS.md`, `CHANGELOG.md`, plan/canvas Phase A status.
- **How it works now:** Agents read `Skills-Library.md` for purpose/triggers/safety; pins live in `SOURCE-PINS.txt`. Skills advise offline research/backtest only — they must not bypass IBKR-only execution, single-market-data-feed, or `auto_live` NO-GO. Reference repos (nautilus, vectorbt, TradeNote, deltalytix, awesome-cursor-skills, vercel-labs/skills) are study catalog only.
- **Verified by:** Each `SKILL.md` frontmatter present; referenced `rules/` / `references/details.md` files exist; zero reparse/symlink points under new skill dirs; licenses reviewed (MIT vendored; deltalytix CC BY-NC and vectorbt Commons Clause cataloged as study-only).
- **Follow-ups:** Phase E product backtest adapter; do not run upstream `setup` / crypto skill dumps.
- **Related:** Master roadmap Phase A; pins `05d9e8b` / `b6af371` / `ed38744`.

## 2026-07-15 — Master Roadmap governance + Phase B enablement docs

- **What:** Opened the product roadmap ledger and continuity contract: `Nova-Roadmap-Status.md` (phase checkboxes B/C/A/D–J + K–Z deferred, COMPLETE history, verification baseline 562/131/14, `auto_live` NO-GO, Phase B NEXT), `.cursor/rules/nova-roadmap-continuity.mdc`, and `docs/paper-shadow-protocol.md`. Brief pointers in `AGENTS.md` / `gemini.md`; Nova-OS-Status Next points at Roadmap-Status. Plan governance todo + master canvas Gov/Phase B callout synced.
- **Why:** Master Roadmap A–Z needs the same continuity pattern as Nova OS before human paper-shadow ops and later feature phases.
- **Files touched:** `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md`, `Nova-OS-Status.md`, `.cursor/rules/nova-roadmap-continuity.mdc`, `docs/paper-shadow-protocol.md`, `AGENTS.md`, `gemini.md`, `CHANGELOG.md`, `.gitignore` (ignore nested vault `graphify-out/`); plan/canvas under Cursor plans/canvases (outside repo).
- **How it works now:** Agents read `Nova-Roadmap-Status.md` first for product phase; humans run Phase B via `docs/paper-shadow-protocol.md` (`signal` → `confirm` → `auto_paper`, evening review routes, hard ban on `auto_live`). Feature phases D–G stay blocked until B exits.
- **Verified by:** File existence + continuity frontmatter sanity; docs-only (no code path change). Accidental CLI write to `knowledge/obsidian/graphify-out/` discarded — root `graphify-out/` left intact.
- **Follow-ups:** Human paper shadow days (≥5) per protocol; Phase C remainder after first compacted day; Cursor `/graphify knowledge/obsidian --update --wiki` semantic pass to index `Nova-Roadmap-Status.md` into root `graphify-out/`.
- **Related:** Plan `nova_master_roadmap_a_z`; baseline tip `fb330cf`.

## 2026-07-15 — Continuity refresh: Nova-OS-Status + tester ledger

- **What:** Reconciled `Nova-OS-Status.md` and tester agent facts to current master after Modular Panel Workspace Phases 0–6 and post-pause product work. Updated verification ledger to 562 pytest / 131 Vitest (28 files) / 14 Playwright / build PASS. Removed stale “uncommitted HOD/modular WIP” language; recorded modular workspace as done (separate from Nova OS plan map). `auto_live` remains NO-GO.
- **Why:** Status note still pointed at `9773c04` with 561/73 ledger while HEAD was `61ea86c` and gates had grown — cold handoffs were starting from wrong facts.
- **Files touched:** `knowledge/obsidian/03-Nova-Decisions/Nova-OS-Status.md`, `.cursor/agents/tester.md`, `.cursor/agents/tester-memory.md`, `CHANGELOG.md`, `graphify-out/` (if rebuild succeeded).
- **How it works now:** Next ops chat starts from paper shadow + evening review, then first real `walk_day`; do not reopen modular workspace 0–6 or implement `auto_live` without a new approved phase.
- **Verified by:** Full pytest 562; Vitest 131; Playwright 14 (one flake + retry); `npm run build` PASS; app health probe on running local servers.
- **Follow-ups:** Paper shadow ops (Step 2 of continuation handoff).
- **Related:** Continuation handoff plan `nova_continuation_handoff_14891adb`.

## 2026-07-15 — Restore Stock View viewport-lock CSS + commit dangling detach/chart work

- **What:** Re-applied the lost Stock View `100dvh` viewport-lock CSS in `index.css` (body/`#root` flex chain, portal/grid fill, compact trade bar). Committed the surviving uncommitted TS work: `measureChartFillHeight`, detached-window `popup=yes` nav + constants.
- **Why:** Phase agents discarded uncommitted `index.css` changes; baseline e2e failed (`documentElement must not page-scroll on Stock View`). Dangling chart/nav fixes risked the same loss.
- **Files touched:** `frontend/src/index.css`, `TickerChart.tsx`, `constants.ts`, `utils/stockViewNav.ts` + test, `CHANGELOG.md`, `PROBLEM_LOG.md`.
- **How it works now:** Stock View is a locked `100dvh` flex shell (`overflow: hidden`); quote scrolls internally; chart portal/host + `.chart-body` use `flex: 1 1 0`; charts measure fill height from the card. Double-click opens a popup window via `STOCK_VIEW_WINDOW_FEATURES`.
- **Verified by:** Playwright 14/14 (incl. no-page-scroll); Vitest 131; `npm run build`; live `?view=stock&symbol=AAPL` → `scrollHeight === clientHeight`.
- **Related:** PROBLEM_LOG “uncommitted Stock View CSS lost during phase automation”.

## 2026-07-15 — Stock View double-click opens a detached window, not a tab

- **What:** Double-click / Stock View now calls `window.open` with `popup=yes` + width/height features and a per-symbol window name, so the browser opens a real OS window instead of a new tab.
- **Why:** User reported double-click only opened a tab; they want Stock View detached.
- **Files touched:** `frontend/src/utils/stockViewNav.ts`, `frontend/src/constants.ts`, `stockViewNav.test.ts`.
- **How it works now:** Bare `_blank` → tab. Features string (`STOCK_VIEW_WINDOW_FEATURES`) → popup window. Same symbol reuses/focuses `nova-stock-SYMBOL`. Electron still prefers IPC `novaDesktop.openStockView`.
- **Verified by:** Vitest `stockViewNav.test.ts`; frontend build.
- **Follow-ups:** If the browser blocks popups, allow Nova for the origin (user gesture is already a double-click).

## 2026-07-15 — Stock View: remove chart-row gaps; lock to one viewport

- **What:** Stock View no longer document-scrolls. The 2×2 chart grid fills leftover height so canvases stretch cell-to-cell (no black void between 1-min and full-day rows). Quote panel scrolls internally; trade bar stays compact at the bottom.
- **Why:** User reported ugly empty space between chart rows and a page scrollbar that hid parts of the view.
- **Files touched:** `frontend/src/index.css`, `frontend/src/TickerChart.tsx`, `CHANGELOG.md`, `PROBLEM_LOG.md`.
- **How it works now:** `body:has(.container--ticker-detail)` + `#root` are a `100dvh` flex column (`overflow: hidden`). Portal slot/host and `.chart-card--grid .chart-body` use `flex: 1 1 0` so height propagates. `measureChartFillHeight` sizes lightweight-charts from the card leftover space (not stuck at `CHART_HEIGHT_GRID`).
- **Verified by:** Playwright baseline no-page-scroll; live AAPL Stock View `scrollHeight === clientHeight`.

## 2026-07-15 — Archive health fails loud on L2 R2 upload failures

- **What:** `archive_health()` now adds L2-bridge R2 failed days to top-level `problems` / `ok=false` when R2 is enabled and configured (was report-only via `l2_bridge_failed_days`). Status note updated: R2 keys live locally, maintenance enabled, connectivity verified.
- **Why:** Carry-forward after R2 setup — a failed L2 cold upload must not leave archive health green.
- **Files touched:** `backend/archive/health.py`, `backend/tests/test_archive_r2.py`, `knowledge/obsidian/03-Nova-Decisions/Nova-OS-Status.md`, `CHANGELOG.md`.
- **How it works now:** Same loud pattern as primary R2 day failures. Local `.env` (not committed) has `ARCHIVE_R2_ENABLED` + `ARCHIVE_MAINTENANCE_ENABLED` so compact+upload can run after market days.
- **Verified by:** `pytest tests/test_archive_r2.py::TestR2Status` (3 passed); live R2 probe earlier same day (`head_bucket` + upload/delete).
- **Follow-ups:** Bucket Lock + token rotation later; `walk_day` on first real compacted day; paper shadow ops.

## 2026-07-15 — Drag-and-drop panel rearrange via dnd-kit (Phase 6)

- **What:** Added `@dnd-kit/core` + `@dnd-kit/sortable` drag handles on Modules menu panel-order rows; drop reorders within a slot and persists through the Phase 5 `layoutStore`. ↑↓ buttons remain as keyboard/a11y fallback.
- **Why:** Modular Panel Workspace Phase 6 (FINAL) — drag-drop rearrange completing the workspace phase plan.
- **Files touched:** `frontend/package.json`, `package-lock.json`, `components/LayoutOrderList.tsx`, `ModulesMenu.tsx`, `TabNav.tsx`, `workspace/layoutStore.ts`, `useLayoutStore.tsx`, `layoutStore.test.ts`, `index.css`, e2e `layout-store.spec.ts`, `CHANGELOG.md`.
- **How it works now:** `LayoutOrderList` wraps the order `<ul>` in `DndContext`/`SortableContext`; drag end calls `reorderModulesInSlot` → `saveLayout`. Quote hosts still read order via `useLayoutStore().getOrder` — no new persist schema.
- **Verified by:** `npx vitest run`, `npx playwright test`, `npm run build`.
- **Follow-ups:** Modular workspace phases 0–6 complete. Optional later: drag between slots / resize handles.
- **Related:** Phase 5 `3403b3a`.

## 2026-07-15 — Maintainer sentinel subagent

- **What:** Added a read-only `maintainer` Cursor subagent (sibling to `tester`) that audits maintainability decay and dangers, plus a deterministic scanner script and living memory/baselines.
- **Why:** Keep Nova maintainable with a dedicated danger-sniffer: file limits, secrets, swallowed exceptions, ruff/npm/pip audits — report only, never auto-fix.
- **Files touched:** `.cursor/agents/maintainer.md`, `.cursor/agents/maintainer-memory.md`, `tools/maintainer_checks.py`, `tools/test_maintainer_checks.py`, `backend/requirements-dev.txt` (`pip-audit`), `AGENTS.md`, `CHANGELOG.md`.
- **How it works now:** Invoke with “Use the maintainer subagent to audit the repo.” It runs `py -3 tools/maintainer_checks.py --json` first, then optional ruff / lint / pip_audit / npm audit, and returns a severity-ranked report. Known over-limit files (`hod_momo.py`, `executor.py`) are accepted baselines, not new CRITICALs. Fixes stay with a separate writer session.
- **Verified by:** `py -3 -m pytest tools/test_maintainer_checks.py -q`; `py -3 tools/maintainer_checks.py --json` smoke.
- **Follow-ups:** Optional weekly automation / CI gate (listed in maintainer-memory backlog).

## 2026-07-15 — Layout store with persisted panel order (Phase 5)

- **What:** Added versioned `workspace/layoutStore.ts` (slot → module id list + optional sizes) persisted in localStorage, Modules menu ↑↓ reorder + reset, and quote hosts that render panels in saved order.
- **Why:** Modular Panel Workspace Phase 5 — prove the layout model before Phase 6 drag-drop.
- **Files touched:** `frontend/src/workspace/layoutStore.ts`, `useLayoutStore.tsx`, `layoutStore.test.ts`, `components/TickerDetailContent.tsx`, `ModulesMenu.tsx`, `TabNav.tsx`, `SidePanel.tsx`, `StockViewPage.tsx`, `App.tsx`, `constants.ts`, `index.css`, e2e `layout-store.spec.ts`, `CHANGELOG.md`.
- **How it works now:** `LayoutStoreProvider` loads `nova_workspace_layout_v1` (`version`, `slots.side_panel` / `slots.stock_view`). Side panel and Stock View pass `layoutSlot`; `TickerDetailContent` coalesces level2+tape into one depth block and orders blocks via `data-layout-block`. Modules menu edits order per slot and can reset to defaults. Visibility (Phase 4) still gates show/hide independently.
- **Verified by:** `npx vitest run` (130), `npx playwright test` (12), `npm run build`.
- **Follow-ups:** Phase 6 — `@dnd-kit` drag handles writing through this layout store.
- **Related:** Phase 4 `06cacb5`; plan `modular_panel_workspace_phases_53ac9db5`.

## 2026-07-15 — Module registry + data-driven tabs (Phase 4)

- **What:** Added `workspace/registry.ts` (`NovaModule` catalog), registry-driven `TabNav`, Gainers/Losers as separate top-level tabs, a Modules show/hide menu persisted in `localStorage`, and `TabModuleHost` for Dashboard tab bodies.
- **Why:** Modular Panel Workspace Phase 4 — data-driven tabs before Phase 5 layout store / Phase 6 drag-drop.
- **Files touched:** `frontend/src/workspace/registry.ts`, `moduleVisibility.ts`, `useModuleVisibility.tsx`, `components/TabNav.tsx`, `ModulesMenu.tsx`, `TabModuleHost.tsx`, `ScannerTabPanels.tsx`, `pages/DashboardPage.tsx`, `modules/DepthTapePanel.tsx`, `ChartsModule.tsx`, Vitest + e2e `module-registry.spec.ts`, `CHANGELOG.md`.
- **How it works now:** TabNav maps `listTabModules()` filtered by visibility. Dashboard renders via `getModule` + `TabModuleHost` (no hardcoded movers sub-tabs). Panel modules (level2/tape/news/quote/charts) honor the same visibility map in quote composition. Storage key: `nova_module_visibility_v1`.
- **Verified by:** `npx vitest run` (122), `npx playwright test` (10), `npm run build`.
- **Follow-ups:** Phase 5 — `layoutStore.ts` (slot → module id list, sizes, versioned schema, reset-to-default).
- **Related:** Phase 3 `a045207`; plan `modular_panel_workspace_phases_53ac9db5`.

## 2026-07-15 — Decompose TickerDetailContent into quote panels (Phase 3)

- **What:** Split `TickerDetailContent` into mountable panels: `QuoteHeaderPanel`, `NewsPanel`, `FundamentalsPanel`, `DataSourcesPanel`, `WatchlistStripPanel`, plus `DepthTapePanel` (wraps Phase-1 L2/T&S). Composition root stays API-compatible for SidePanel + Stock View.
- **Why:** Modular Panel Workspace Phase 3 — optional panels before Phase 4 registry.
- **Files touched:** `frontend/src/modules/*Panel*.tsx`, `quoteMetrics.ts`, `TickerDetailContent.tsx`, Vitest panel/composition tests, e2e `quote-panels.spec.ts`.
- **How it works now:** `TickerDetailContent` only orders panels (`stack` / `columns`). Each panel owns its markup; DataSources / QuoteHeader / DepthTape / Fundamentals read `useWorkspace()` for discovery/IBKR. CSS class names unchanged (`cq-*`).
- **Verified by:** `npx vitest run`, `npx playwright test`, `npm run build`.
- **Follow-ups:** Phase 4 — module registry + data-driven TabNav; Gainers/Losers as separate modules.
- **Related:** Phase 2 `67a3ee7`, Phase 1 `96bdafc`.

## 2026-07-15 — Tester subagent self-improvement loop + memory

- **What:** Tester now reads/writes `.cursor/agents/tester-memory.md` (backlog, pending facts, run log) and follows a mandatory self-improvement protocol: promote durable command/trap/routing learnings into `tester.md`, log failures/BLOCKED/infra surprises, and work backlog items when asked to "improve the tester".
- **Why:** User wanted a way to keep improving the subagent over time — a living to-do plus per-run updates instead of a static prompt.
- **Files touched:** `.cursor/agents/tester.md`, `.cursor/agents/tester-memory.md`, `CHANGELOG.md`.
- **How it works now:** Start of run → read memory. End of run → update memory and/or promote into `tester.md` when something was learned; report includes **Memory update:**. Humans continue via the backlog in `tester-memory.md` or by asking the tester to work the next backlog item.
- **Verified by:** Files written; protocol sections present; backlog seeded with concrete next items.
- **Follow-ups:** Work backlog items (test-count refresh, routing expansion, CI parity, golden browser path) on subsequent tester runs.

## 2026-07-15 — Nova-specialized `tester` subagent

- **What:** Added a project-level testing subagent at `.cursor/agents/tester.md` (a generic personal fallback also exists at `~/.cursor/agents/tester.md`; the project one wins in Nova).
- **Why:** User asked for a specialized testing sub-agent so test runs, regression gates, and failure diagnosis can be delegated with Nova-specific knowledge baked in.
- **Files touched:** `.cursor/agents/tester.md`, `CHANGELOG.md`.
- **How it works now:** Delegating a test/verify task to `subagent_type: tester` gets an agent that knows the verified commands (pytest from **repo root** via `py -3 -m pytest backend/tests -q`; scoped Vitest via `npm run test -- <file>` in `frontend/`), a changed-files→test-file routing table, known traps from PROBLEM_LOG (pytest exit 5, UTF-16 BOM null bytes, Vitest/Playwright exclusions, IB Gateway login vs "no gaps"), a one-retry flakiness policy, server-reuse rules for browser checks, and a hard ban on arming the executor or placing orders during verification. It returns a fixed Test report (Scope / Commands / PASS-FAIL-BLOCKED / evidence / root cause).
- **Verified by:** Ran both prescribed commands directly (561 backend tests collected; scoped Vitest file 3/3 pass), then launched the tester subagent on `stockViewNav.test.ts` — it followed the format and reported 4/4 PASS.

- **What:** Added `WorkspaceProvider` / `useWorkspace()` for `selectedSymbol`, `discoveryProvider`, `alpacaFeed`, `ibkrConnected`, and `openStockView`. Mounted in `App.tsx`. `StockViewPage` no longer fetches `/api/config`; SidePanel / TickerDetailContent / Dashboard read workspace instead of drilled props.
- **Why:** Modular Panel Workspace Phase 2 — shared selection/discovery before Phase 3 panel decomposition.
- **Files touched:** `frontend/src/workspace/*`, `App.tsx`, `DashboardPage.tsx`, `SidePanel.tsx`, `TickerDetailContent.tsx`, `StockViewPage.tsx`, e2e `workspace-context.spec.ts`, Vitest workspace tests; `jsdom` for provider tests.
- **How it works now:** One provider owns symbol selection + Stock View open path + discovery/feed (config fetch + Settings sync). Quote surfaces call `useWorkspace()`; scanner tabs still receive symbol callbacks from Dashboard (Phase 4 registry later).
- **Verified by:** `npx vitest run` (96), `npx playwright test` (7), `npm run build`.
- **Follow-ups:** Phase 3 — decompose `TickerDetailContent` into optional panels.
- **Related:** Plan `modular_panel_workspace_phases_53ac9db5`; Phase 1 commit `96bdafc`.

## 2026-07-15 — Phase 1: Level 2 + Time & Sales as independent modules

- **What:** Moved `useIbkrTape` ownership into `TimeSalesPanel` (mirrors `DepthLadder` → `useIbkrDepth`). Added mountable `Level2Module` / `TimeSalesModule` wrappers; `DepthAndTape` is composition-only. Pure tape helpers live in `tapeFeed.ts` for symbol-gating tests.
- **Why:** Modular Panel Workspace Phase 1 — each panel owns its feed so later workspace layout can show L2 and T&S alone or together.
- **Files touched:** `frontend/src/ibkr/TimeSalesPanel.tsx`, `DepthAndTape.tsx`, `useIbkrTape.ts`, `tapeFeed.ts`, `frontend/src/modules/Level2Module.tsx`, `TimeSalesModule.tsx`, `frontend/e2e/level2-tape-modules.spec.ts`, unit tests under `ibkr/` and `modules/`.
- **How it works now:** Callers still use `<DepthAndTape symbol={…} />`. Internally it renders `Level2Module` + `TimeSalesModule`, each keyed/bound to `symbol` only. Stale WS prints are rejected via `tapeMessageAllowed`; symbol change resets via `emptyTapeState()`.
- **Verified by:** `npx vitest run`, `npx playwright test`, `npm run build`.
- **Follow-ups:** Phase 2 — `WorkspaceContext` for symbol/discovery/ibkr; remove prop drilling.
- **Related:** Plan `modular_panel_workspace_phases_53ac9db5`; Phase 0 commit `fab60f3`.

## 2026-07-15 — Phase 0: Karpathy skill + Playwright baseline e2e

- **What:** Installed portable Karpathy skill under `.cursor/skills/`; added Playwright (`@playwright/test`) with `frontend/playwright.config.ts`, baseline suite `frontend/e2e/baseline.spec.ts`, and npm scripts `test:e2e` / `test:e2e:ui`. Vitest now excludes `e2e/`.
- **Why:** Modular Panel Workspace plan Phase 0 — gate every later phase on unit + e2e + build.
- **Files touched:** `.cursor/skills/karpathy-guidelines/SKILL.md`, `frontend/playwright.config.ts`, `frontend/e2e/baseline.spec.ts`, `frontend/package.json`, `frontend/vite.config.ts`, `.gitignore`.
- **How it works now:** `npm run test` = Vitest only; `npm run test:e2e` starts/reuses Vite on `:5173` and runs Chromium specs (app load, tab switch, Stock View via `?view=stock&symbol=…`, no page scroll, no uncaught console errors). Existing `.cursor/rules/karpathy-guidelines.mdc` unchanged — skill is the portable copy.
- **Verified by:** `npx vitest run` (78 passed), `npx playwright test` (3 passed), `npm run build`.
- **Follow-ups:** Phase 1 — split DepthAndTape into Level2Module + TimeSalesModule.
- **Related:** plan `modular_panel_workspace_phases_53ac9db5`; PROBLEM_LOG 2026-07-15 Vitest/Playwright exclude.

## 2026-07-15 — Double-click → Stock View on all symbol tables

- **What:** Row double-click (click-vs-double via `SelectableTableRow` / Decision cards) opens Stock View on every multi-symbol table: scanners, catalysts, HOD feed + debug, watchlist, journal, automation staged/open, trading positions/orders, and Nova OS decision cards.
- **Why:** User asked for the same double-click Stock View behavior everywhere — not only HOD / scanners.
- **Files touched:** `JournalPanel.tsx`, `ExecutorPanel.tsx`, `ExecutorTables.tsx`, `PositionsPanel.tsx`, `TradingTab.tsx`, `DecisionPanel.tsx`, `WatchlistTab.tsx`, `DashboardPage.tsx`, `HodMomoDebugPanel.tsx`, `HodMomoDebugTables.tsx`, `HodMomoTab.tsx`.
- **How it works now:** Any symbol row uses `createClickVsDoubleClick` — single click selects Quote Panel; second click within `SYMBOL_DOUBLE_CLICK_MS` calls `onOpenTrading` → `openStockViewWindow`. Action buttons (`Approve`/`Reject`/`Cancel`) call `stopPropagation` so they do not open Stock View.
- **Verified by:** `npm run build`; live browser double-click opened `?view=stock&symbol=…` for Gappers, Gainers, After Hours, Catalysts, HOD feed, HOD debug Decisions/Snaps, Watchlist, Journal (demo), Trading positions, and Decision cards. Executor had no staged rows at verify time (wiring present).
- **Follow-ups:** None for this request.

## 2026-07-15 — HOD Momo feed: one row per symbol with multiple strategy tags

- **What:** The HOD Momo table now collapses to one row per ticker. Distinct strategies that fired for that symbol render as multiple strategy pills on the same row.
- **Why:** User wanted “one row per symbol” instead of a separate row for every strategy fire.
- **Files touched:** `frontend/src/hod_momo/collapseAlertsBySymbol.ts`, `collapseAlertsBySymbol.test.ts`, `HodMomoTab.tsx`, `HodMomoAlertRow.tsx`, `HodMomoAlertTable.tsx`, `types.ts`, `frontend/src/index.css`.
- **How it works now:** After strategy filtering, `collapseAlertsBySymbol` keeps newest-first ticker order, uses the newest alert for price/metrics, and collects unique strategy tags (newest-first). Alert-count badges still reflect total fires for that symbol.
- **Verified by:** Vitest unit tests for multi-strategy collapse; live browser on populated HOD feed confirms unique tickers in the first batch and multi-pill strategy cells; `npm run build`.

## 2026-07-15 — HOD Momo row double-click opens Stock View

- **What:** HOD Momo alert rows now use the same `SelectableTableRow` click/double-click path as scanners and watchlist: click selects the Quote Panel, double-click opens Stock View in a new window.
- **Why:** Double-clicking a HOD row (outside the symbol button) previously did nothing; only the symbol button opened Stock View.
- **Files touched:** `frontend/src/hod_momo/HodMomoAlertRow.tsx`, `frontend/src/components/SelectableTableRow.tsx`.
- **How it works now:** Each HOD alert row is a `SelectableTableRow` wired to `onSelect` / `onOpenTrading`. The symbol button still stops propagation and keeps its own click vs double-click handlers.
- **Verified by:** Live browser on populated HOD Momo — two rapid clicks on a non-symbol cell opened `?view=stock&symbol=…` via `window.open`; single click selected the Quote Panel. `npm run build`; Vitest green.

## 2026-07-15 — Enforce 40-row HOD Momo rendering against populated data

- **What:** Replaced the ineffective HOD Momo virtualizer with deterministic incremental mounting: 40 rows initially and 40 more only when the table's own fixed-height scroller reaches bottom.
- **Why:** Production-scale browser evidence proved the virtualizer mounted all 6,603 available rows at once because its flex viewport expanded to the table's intrinsic height. Prior empty-data testing missed the actual failure.
- **Files touched:** `frontend/src/hod_momo/HodMomoAlertTable.tsx`, `frontend/src/hod_momo/HodMomoAlertTable.test.ts`, `frontend/src/constants.ts`, `frontend/src/index.css`, `.cursor/rules/browser-testing.mdc`.
- **How it works now:** The table slices the alert array to a 40-row render limit. A latched bottom handler increases the limit by one 40-row batch per distinct bottom reach. The 532px wrapper owns scrolling and cannot expand with the full dataset.
- **Verified by:** Same live browser session, 6,630 alerts: before = 6,603 mounted rows / 137,325 DOM nodes / 212,564px wrapper; after = 40 rows / 964 DOM nodes / 532px wrapper. One bottom reach = exactly 80 rows while document height stays unchanged. Clean console, 52.2ms tab-open measurement, `npm run build`, and 75/75 Vitest tests.
- **Related:** `PROBLEM_LOG.md` 2026-07-15 “HOD Momo ‘virtualized’ table mounted all 6,603 rows.”

## 2026-07-15 — HOD Momo alert stream no longer double-delivers on WS reconnect/remount

- **What:** `frontend/src/hod_momo/useHodMomoStream.ts` now ignores events from a stale/superseded WebSocket instance (checks `wsRef.current === ws` on every handler, in addition to the existing `mountedRef` flag) and de-duplicates incoming alerts by `id` via an O(1) `Set` lookup instead of trusting every 'alert' message to be new.
- **Why:** User reported the HOD Momo tab was laggy enough to feel like a browser crash, despite prior fixes (virtualization, batching, save throttling). Root cause: every alert was being delivered into React state **twice**, which not only doubled the effective list size but produced a continuous flood of React "duplicate key" reconciliation errors — see `PROBLEM_LOG.md` (2026-07-15, same title pattern) for the full diagnosis.
- **Files touched:** `frontend/src/hod_momo/useHodMomoStream.ts`.
- **How it works now:** A `seenIdsRef: Set<string>` is rebuilt once from the `initial` WS payload and then grown incrementally as live alerts arrive — never rescanned from the full day list. `connect()`'s `onopen`/`onmessage`/`onerror`/`onclose` handlers all bail out early if `wsRef.current !== ws`, so a socket that's mid-close (e.g. from React StrictMode's dev-mode mount→cleanup→remount cycle, or any future reconnect race) can never push a message into state after a newer socket has taken over. Cleanup also nulls all four handlers before calling `close()`.
- **Verified by:** `agent-browser` against the live dev server — before the fix, opening the tab produced hundreds of "Encountered two children with the same key" console errors within seconds of the live alert count (already at ~4000+ that day); after the fix, watched for 75+ seconds with alerts growing from ~4097 to 4458 with zero console errors. `npm run build` and `npm run test` (73/73) pass.
- **Related:** `PROBLEM_LOG.md` 2026-07-15 "HOD Momo tab still crash-level laggy after three prior fixes."

## 2026-07-15 — Nova OS hardening section 6: phase-status correction (re-verified, not re-claimed)

- **What:** Closes section 6 (the final section) of the Nova OS hardening plan. Re-verified each of the five gaps a post-P10 audit had found in P2–P7 (unsafe flatten, non-atomic staged approval, mode-receipt split-brain, ambiguous startup recovery, consecutive- vs daily-loss policy) against the *current* code — not against docstrings or prior changelog claims — and replaced `Nova-OS-Status.md`'s blanket "P0 continuity → ... → P6/P7 local archive — all verified on master" line with a per-phase exit-criteria table naming concrete file:line evidence and the test that covers each claim. Found and fixed one residual stale UI string: `WatchlistTab.tsx`'s Automation-tab tooltip still said "Arm/disarm... Disarmed by default" from before the mode ladder existed.
- **Why:** The hardening plan's whole premise was that a prior "all phases verified" status was itself part of the problem — P2–P7 had been marked verified on master while still containing the five gaps above. Closing sections 1–5 (code fixes) without re-checking the status document would repeat that exact mistake: claiming "hardening complete" without independently confirming each fix actually landed as claimed, rather than trusting the commit messages that introduced them.
- **Files touched:** `knowledge/obsidian/03-Nova-Decisions/Nova-OS-Status.md`, `frontend/src/strategy/WatchlistTab.tsx` (tooltip copy only).
- **How it works now:** `Nova-OS-Status.md` now has a "Phase exit criteria (re-verified 2026-07-15, evidence-based)" table: one row per phase/claim, each with a PASS/PARTIAL status and a file:line + test-name citation, instead of a single "all verified" sentence. The "Current position" section no longer states a bare "verified" without qualification — it points at the table. "In progress / uncommitted" now says hardening sections 1–6 are all closed (previously section 6 was listed as still in progress). The Automation tab tooltip in `WatchlistTab.tsx` now describes the real `signal/confirm/auto_paper/auto_live` ladder instead of legacy "Arm/disarm" language that predates it.
- **Verified by:** Read the actual guard/transition code (not comments) for all five originally-audited gaps: `executor_flatten.py` (`confirm_token != NOVA_OS_FLATTEN_CONFIRM_TOKEN` raises), `staged_tickets.py` (`approve()` claims via `dict.pop` before gates/placement), `setups_stream.py`/`routes/nova_os.py` (both call `_control_mode.get_mode()`, not a hardcoded default), `recovery.py` (`run_startup_recovery` forces `signal` on ambiguity, only restores positions when IBKR confirms), `codes.py`/`risk.py` (`loss_policy_mode(losses_today, ...)` is distinct from `consecutive_losses`) — all confirmed still correct, each backed by an existing test. Ran the full suite fresh as the closing checkpoint: `py -3 -m pytest` — 561/561 backend tests passed; `npm run build` — clean; `npx vitest run` — 73/73 frontend tests passed (16 files).
- **Follow-ups:** None from this section. Carried-forward infra/scope items (not code bugs, unchanged from section 4/5 entries): R2 Bucket Lock still not configured (console change, not code); `l2_bridge` verified status not yet folded into `archive_health()`'s top-level ok/problems gate; no real compacted archive day exists locally to exercise `walk_day` end-to-end outside of fixture-seeded tests.
- **Related:** Closes the Nova OS hardening plan (all 6 sections). See `CHANGELOG.md` 2026-07-15 entries for sections 1–5 ("Nova OS hardening", "hardening section 3", "hardening section 4", "hardening section 5").

## 2026-07-15 — Graphify knowledge graph for Obsidian vault

- **What:** Installed [graphify](https://github.com/Graphify-Labs/graphify) (`graphifyy` CLI) for this Windows/Cursor setup and built a knowledge graph over `knowledge/obsidian/` (52 nodes · 92 edges · 6 communities). Wired always-on Cursor rule, project skills, agent wiki, and Obsidian recall docs.
- **Why:** User asked to read Graphify docs and implement it properly against the project knowledge / Obsidian vault (not a silent codebase-only install).
- **Files touched:** `.cursor/rules/graphify.mdc`, `.cursor/skills/graphify/`, `.agents/skills/graphify/`, `.claude/skills/graphify/`, `CLAUDE.md` (graphify section), `graphify-out/{graph.json,GRAPH_REPORT.md,graph.html,wiki/}`, `knowledge/obsidian/00-System/{Graphify-Knowledge-Graph,How-Recall-Works,Memory-Router}.md`, `.gitignore`.
- **How it works now:** Agents treat `graphify-out/` as a navigation layer over the vault. For “what connects X to Y?” decision questions, run `graphify query` / `path` / `explain` (or open `graphify-out/wiki/index.md`) before grepping notes. Exact decision wording still lives in Obsidian; course content still goes through Pinecone. Rebuild after vault edits with `/graphify knowledge/obsidian --update --wiki` in Cursor. Open `graphify-out/graph.html` for the interactive view. CLI install: `uv tool install graphifyy` then ensure `%USERPROFILE%\.local\bin` is on PATH.
- **Verified by:** `graphify query` returns Gap-and-Go ↔ IBKR safety subgraph; `graphify path "Gap and Go Setup" "IBKR Safety Gates"` = 2 hops via Nova OS decide() gate pipeline; `graphify explain "Nova OS"`; wiki + HTML written; app launched via `Run Nova.bat`.
- **Follow-ups:** Optional `/graphify . --wiki` to add backend/frontend code into a merged graph; optional MCP (`python -m graphify.serve graphify-out/graph.json`) if live tool calls are preferred over CLI.
- **Related:** `knowledge/obsidian/00-System/Graphify-Knowledge-Graph.md`.

## 2026-07-15 — Nova OS hardening section 5: no-hindsight replay/rewind/review (walk_day, replay_at)

- **What:** Closes section 5 (event-time replay) of the Nova OS hardening plan. `backend/archive/replay.py::replay_day()` fed `decide()` the *entire* archived day's bars for a single decision per symbol — a decision "made" at any point could see the day's close before it happened. Added `slice_bars_as_of()`, `replay_at()`, and `walk_day()` so decide() only ever sees bars up to an explicit `as_of_ts`; `walk_day()` steps through a day in `ARCHIVE_REPLAY_WALK_STEP_MIN`-minute increments and returns a scrubbable decision timeline — the "rewind" primitive. `evening_review()` was rewritten on top of `walk_day()` to pick each symbol's real (no-hindsight) decision moment and score its outcome *forward* from that exact `as_of_ts`, fixing a second bug where it scored backward from the day's last bar regardless of when a decision happened. New/updated REST routes expose all of it: `GET /api/archive/replay/{day}?as_of=`, new `GET /api/archive/walk/{day}`, new `GET /api/archive/review/{day}`, new `GET /api/archive/ask` (ask/review previously had zero HTTP exposure, CLI-only). `ArchiveRewind.tsx` now drives a real rewind slider off `/walk` instead of a single whole-day "Replay" button. `tools/nova_os_replay.py` gained `at`/`walk` subcommands.
- **Why:** The post-P10 hardening audit named this "no-hindsight replay, rewind, ask, and review loop" as an unimplemented gap. Inspecting `replay_day()` confirmed it: `by_symbol[sym]` held every bar in the day, sorted, handed straight to `decide()` with no time boundary, so `gate_setup`/`gate_pillars`/the candidate's `price`/`change_pct` (built from `bars[-1]`, the day's close) all reflected the full day's outcome before "deciding." `evening_review._outcome_for_decision()` compounded this by computing `ref = bars[-(horizon+1)]` vs `fwd = bars[-1]` — always the last bars of the whole day, with no connection to when a decision actually fired. Neither bug would be visible from a decision-quality metric looking merely "reasonable"; the whole point of a replay/backtest tool is to prove decisions weren't cheating, so a silently hindsight-biased replay is worse than no replay tool at all.
- **Files touched:** `backend/archive/replay.py`, `backend/archive/evening_review.py`, `backend/archive/ask.py` (added `limit`), `backend/routes/archive.py`, `backend/constants.py`, `backend/archive/__init__.py` (docstring), `tools/nova_os_replay.py`, `frontend/src/strategy/ArchiveRewind.tsx`, new `backend/tests/test_routes_archive.py`, extended `backend/tests/test_archive_replay.py`.
- **How it works now:** `replay.bars_by_symbol_for_day()` loads full-day bars (unchanged shape); `replay.slice_bars_as_of(bars, as_of_ts)` returns only `ts <= as_of_ts`. `_decide_snapshot()` is the shared no-hindsight decision primitive both `replay_day(as_of_ts=...)` and `walk_day()` call — each decision's `replay` sub-dict now carries `as_of_ts`/`bar_count`/`hindsight` so a caller can verify no lookahead occurred. `replay_day()` without `as_of_ts` keeps its original whole-day behavior *only* for backward compatibility with the existing CLI/route default, but its response is now explicitly `"hindsight": True` with a note explaining why — `replay_at()`/`walk_day()` are the recommended no-hindsight entry points. `walk_day()` computes as-of steps from the min/max bar `ts` actually present (not a hardcoded session window) every `step_min` minutes, capped at `ARCHIVE_REPLAY_WALK_MAX_STEPS`, and returns `{steps: [{as_of_ts, as_of_iso, decisions, errors}, ...]}` — a UI/CLI can index into this to "rewind." `evening_review()` calls `walk_day()`, picks each symbol's first BUY across the walk (or the final step's decision if none ever fired — still no lookahead, since that step's own bars are bounded by its own `as_of_ts`), then `_outcome_for_decision()` looks at bars strictly *after* that `as_of_ts` to find a forward price near `as_of_ts + horizon_min*60` — using future bars to *grade* an already-made decision is correct and is not hindsight bias; feeding decide() those same bars *before* it decided would be, which is exactly what no longer happens. `ArchiveRewind.tsx` fetches `/api/archive/walk/{day}` once and renders a range-slider scrubber over `steps[]`, defaulting to the final (most-informed) step and letting the operator step backward.
- **Verified by:** `py -3 -m pytest` — 561/561 backend tests passed (10 new in `TestNoHindsight`/extended `TestEveningReview` in `test_archive_replay.py` proving `walk_day` never leaks a later step's bars into an earlier one and `evening_review` scores forward not backward; 11 new in `test_routes_archive.py` covering `/replay?as_of=`, `/walk`, `/review`, `/ask`). `npm run build` and `npx vitest run` (73/73) both green. Live-clicked the Watchlist → Archive tab in a fresh browser session against the running dev server — renders the new no-hindsight copy and empty state with no console errors (no local cold days exist in this environment yet, so the slider itself needs a real compacted day to exercise end-to-end; the underlying `walk_day`/`evening_review` mechanics are covered by the fixture-seeded unit/route tests instead).
- **Follow-ups:** Plan section 6 (phase-status correction) remains. `walk_day`'s per-step decide() calls are O(steps × symbols) — fine for local/CLI batch use, capped by `ARCHIVE_REPLAY_WALK_MAX_STEPS`, but not tuned for a "walk every archived day in bulk" job; a future pass could parallelize or vectorize if that use case appears.
- **Related:** `PROBLEM_LOG.md` 2026-07-15 "Nova OS event-time replay: decide() saw the whole day (hindsight); evening review scored outcome backward from close, not forward from decision".

## 2026-07-15 — Nova OS hardening section 4: crash-safe archive writes, hard-fail on missing/tampered cold data, L2 bridged into R2

- **What:** Closes section 4 (archive durability) of the Nova OS hardening plan. Fixed two integrity bugs in the existing bars/tape_ibkr cold-archive pipeline and added a new bridge so IBKR Level 2 depth history — already durably recorded by the pre-existing `l2/continuous.py` → `l2/db.py` subsystem — gets the same checksummed cold export and Cloudflare R2 backup as bars/tape_ibkr.
- **Why:** An audit found `archive/r2.py::upload_day()` and `archive/restore.py::restore_day_to_temp()` silently `continue`d past a missing table manifest instead of failing — a day where `compact_day()` crashed mid-loop (writing only 4 of 5 table manifests) could still be marked `verified_remote: True` in R2, or `ok: True` in a restore drill, with the missing table's data simply gone and no signal anywhere. Separately, `compact.py`'s JSONL writer opened the final path directly, so a crash mid-write left a truncated file paired with a *stale* manifest from a previous run claiming the old (now wrong) row_count/sha256 — exactly the "partial rewrite + stale manifest lets the upload proceed as if everything is valid" failure mode the audit named. And `archive/capture.py::record_l2_snapshot()` — the only L2-persistence-looking code inside the Nova OS archive package — turned out to be an unwired, in-memory-only stub with zero production callers; L2 depth was in fact already durably captured by an older, separate subsystem the archive package never connected to cold/R2.
- **Files touched:** `backend/archive/{manifest,compact,r2,restore,health,capture}.py`, new `backend/archive/l2_bridge.py`, `backend/archive/scheduler.py`, `backend/constants.py`, new `backend/tests/test_archive_l2_bridge.py`, `backend/tests/test_archive_scheduler.py`, plus new failure-path tests added to `test_archive_r2.py` / `test_archive_compact_restore.py`.
- **How it works now:** `manifest.write_manifest()` and `compact.write_jsonl_atomic()` (renamed from the old private `_write_jsonl`) both write to a sibling temp file, fsync, then `os.replace()` into the final path — the final path is always either the old complete file or the new complete file, never a half-written one. `r2.py::upload_day()` now appends an explicit `{"ok": False, ...}` failure entry (instead of skipping) when a table's manifest is missing, and calls `manifest.verify_payload()` against the local file's actual sha256 immediately before uploading — a mismatch is refused, logged, and never reaches R2. `restore.py::restore_day_to_temp()` gets the same missing-manifest-is-a-failure fix. New `archive/l2_bridge.py` queries `l2/db.py`'s `l2_snapshots`/`tape_trades` by `ts` range for one America/New_York calendar day (that db has no `session_date` column, so it stays out of `ARCHIVE_TABLES_COLD`/`compact_day` to avoid a second sqlite connection inside the existing bars/tape_ibkr contract), writing the same checksummed-JSONL-manifest format under the same `archive_cold/{date}/{schema_version}/` tree. It has its own R2 upload (`upload_l2_day`) and verified index (`_r2_verified_l2.json`) — deliberately separate from the primary index so an L2 backup failure never falsely flips the bars/tape_ibkr day's verified status (or vice versa) — plus its own restore drill (`restore_l2_day_to_temp`). `archive/scheduler.py::run_maintenance_once()` now calls `compact_l2_day()`/`upload_l2_day()` for every finished day, wrapped in its own try/except so an L2 export failure never blocks that day's primary compaction. `archive/health.py` surfaces `l2_bridge_tables`/`l2_bridge_verified_days`/`l2_bridge_failed_days` (additive fields; does not affect the existing `ok`/`problems` computation). `capture.py`'s dead L2 stub is left in place (still zero callers) but its docstring and the module docstring now explicitly point future readers at `l2_bridge` as the real capture path, instead of implying the stub itself does anything durable.
- **Verified by:** `py -3 -m pytest` — 543/543 backend tests passed (10 new in `test_archive_l2_bridge.py`, 2 new in `test_archive_scheduler.py`, plus 4 new failure-path tests added to the existing r2/compact-restore suites covering: missing-manifest hard failure in both `upload_day` and `restore_day_to_temp`, local-payload-tamper detection before upload, atomic-write leaves no stray temp file, L2 round-trip compact→upload→restore, and L2/primary verified-index independence).
- **Follow-ups:** Plan sections 5–6 (no-hindsight replay, phase-status correction) remain. `l2_bridge`'s verified status is not yet folded into `archive_health()`'s top-level `ok`/`problems` gate (reported separately so it can't regress the existing R2 health contract) — a future pass could add an opt-in strictness flag once the L2 backup path has run in production for a while. R2 Bucket Lock (object immutability) was flagged in the original audit as a missing hardening step and is still not configured — that is an infrastructure/console change outside this repo, not a code fix.
- **Related:** `PROBLEM_LOG.md` 2026-07-15 "Nova OS archive durability: silent missing-manifest skip + non-atomic cold writes + L2 never bridged".

## 2026-07-15 — Nova OS hardening section 3: global attention strip, unified mode controls, event-driven notifications

- **What:** Closes section 3 (operator UX) of the Nova OS hardening plan. Three gaps found by browser E2E against the live app: (1) `TickerTradeAutomateControls.tsx` (the ticker action-bar controls) still spoke the legacy binary "Arm/Disarm/Kill" vocabulary while the backend had moved to the `signal|confirm|auto_paper|auto_live` mode ladder — an operator staring at the trading panel had no way to tell which of 4 modes was actually active; (2) the `NovaOsAttentionKind` union and copy table had `staged`/`expired`/`fill`/`stop`/`kill`/`archive_fail` entries that nothing ever pushed — only `decide()` BUY/WAIT/NO_BUY verdicts reached the strip; (3) `NovaOsAttentionStrip` was mounted only inside `DecisionPanel.tsx` (Watchlist → Decision sub-tab), so a kill switch or risk halt fired while the operator was on the Trading tab — the one page with live order controls — was invisible until they happened to switch tabs.
- **Why:** An attention system that only reaches one sub-tab out of eight is worse than no attention system — it creates false confidence that "no alert = nothing happened."
- **Files touched:** `frontend/src/ibkr/TickerTradeAutomateControls.tsx`, `frontend/src/strategy/{novaOsAttention,NovaOsAttentionStrip,DecisionPanel}.tsx`, new `frontend/src/strategy/novaOsEventAttention.ts` (+ test), `frontend/src/App.tsx`, `frontend/src/constants.ts`, `frontend/src/index.css`.
- **How it works now:** `TickerTradeAutomateControls` now renders the real `mode` (color-coded SIGNAL/CONFIRM/AUTO PAPER) with `Confirm`/`Auto Paper`/`Signal`/`Stop Automation` buttons and the same confirm-dialog language as `ExecutorPanel.tsx`, calling `setMode()` directly instead of a legacy `arm()`/`disarm()` pair. `novaOsEventAttention.ts` polls `GET /api/nova-os/events` every 5s (`NOVA_OS_EVENT_ATTENTION_POLL_INTERVAL_MS`), tracks a high-water-mark event id (first poll only initializes the mark — it never backfills history from before mount), and `mapNovaOsEventToAttention()` (pure, unit-tested) translates receipt `kind`/`action`/`payload.event` into the existing `staged|expired|fill|stop|kill|archive_fail|risk_halt|mode_reset` attention kinds. `NovaOsAttentionStrip` takes a `global` prop: with it, the idle "No alerts" line is suppressed (so it doesn't clutter every tab) and the strip renders `position: fixed` at the very top of the viewport only while there is an active event — mounted once in `App.tsx` above both the Dashboard and detached-Stock-View render trees (the only component both trees share), so a kill switch reaches the operator regardless of which tab or window is focused. Removed the old per-page mount from `DecisionPanel.tsx` to avoid a duplicate strip when both are visible.
- **Verified by:** `npx vitest run` — 73/73 passed (7 new for the event→attention mapping). `npm run build` clean. Live browser E2E against the running dev app (`agent-browser`): opened AAPL in Stock View, confirmed the Trading actions panel renders `SIGNAL` / `Confirm` / `Auto Paper` / `Signal` / `Stop Automation` with correct disabled states and the "Orders go through Interactive Brokers only" copy; confirmed the Watchlist → Decision sub-tab still renders without the removed inline strip and without a console error; confirmed a fresh browser session shows zero console errors and the global strip stays invisible with no Nova OS events yet fired. Did **not** click any mode-raising button during E2E — the connected IBKR Gateway in this dev environment is a **live** account (small NET LIQ balance), so mode transitions were verified by static render only, not exercised end-to-end against the broker.
- **Follow-ups:** Plan sections 4–6 (archive durability, no-hindsight replay, phase-status correction) remain. A pre-existing, unrelated tab-bar label-overlap rendering artifact was observed in narrow viewports during E2E (present before this session's changes) — not fixed here, out of scope.
- **Related:** `PROBLEM_LOG.md` 2026-07-15 "Nova OS mode-receipt split-brain + unsafe flatten/recovery".

## 2026-07-15 — Nova OS hardening: safe execution + truthful decision receipts

- **What:** An audit of Nova OS P2–P7 found the flatten control could sell after a cancelled/never-filled parent left protective legs orphaned, staged-ticket approval and auto_paper placement did not re-check safety gates at the moment of action, startup recovery ran before IBKR connected (always "ambiguous"), the loss policy used consecutive losses instead of a daily count, `setups_stream`/`routes/nova_os.py` hardcoded `mode=signal` into every decide() receipt regardless of the real control mode (so `would_execute` was always wrong once a mode was raised), and the `/api/nova-os/decide` polling endpoints wrote a real append-only receipt on every UI poll tick. This entry closes sections 1–2 of the resulting "Nova OS hardening" plan (contain-execution + truthful-decisions).
- **Why:** These are safety- and audit-critical defects — a misleading receipt or an unreconciled flatten is worse than no automation at all.
- **Files touched:** `backend/strategy/executor.py` (+ new `executor_flatten.py`), `backend/nova_os/{control_mode,staged_tickets,recovery,decide,gates,codes}.py`, `backend/strategy/{risk,setups_stream}.py`, `backend/app_lifespan.py`, `backend/routes/{executor,nova_os}.py`, `frontend/src/strategy/{useNovaOsDecide.ts,DecisionPanel.tsx}`, new tests `test_routes_executor.py`, `test_routes_nova_os.py`, `test_setups_stream.py`, `test_ws_strategy.py`.
- **How it works now:** Flatten reconciles against actual IBKR positions before selling and always cancels protective legs on close (`executor_flatten.py`). `place_from_ticket()` and `staged_tickets.approve()` re-check kill switch / control mode / concurrency / auto_paper gates / risk at the moment of action, with an explicit `placement_declined` receipt on every rejection path; ticket approval is atomic (`dict.pop`) so two concurrent Approve calls can't double-place. `set_mode()`/`force_signal()` reject any staged ticket the instant mode drops to `signal` — a stale Approve afterward gets a 409, never an order. Startup recovery now runs after `ibkr.client.startup()` and never restores a ghost position it can't verify against IBKR; `risk.reconstruct_from_journal()` rebuilds today's loss count from the trade journal so a restart can't reset a halted day to "clean." `RiskState.losses_today` (not `consecutive_losses`) drives `codes.loss_policy_mode()` — an intervening win no longer erases the count toward the 3-loss halt. `setups_stream._scan_once()` and both `/api/nova-os/decide*` routes now pass the real current control mode instead of a hardcoded default, so `would_execute`/`mode` on every receipt and WS broadcast match what the executor can actually do; the two `/decide*` routes call `decide(record=False)` since they're polled every few seconds and must not spam the audit log. A per-symbol bars-fetch failure in the batch `/decide` route now returns a separate `errors: [...]` list instead of silently becoming an indistinguishable NO_BUY.
- **Verified by:** `py -3 -m pytest` — 527 passed (was 509 before this session's route/WS contract additions). `npm run build` passes with the new `dataErrors` plumbing.
- **Follow-ups:** Plan sections 3–6 (operator UX unification, archive durability, no-hindsight replay, phase-status correction) remain — tracked as separate todos in this session.
- **Related:** `PROBLEM_LOG.md` 2026-07-15 "Nova OS mode-receipt split-brain + unsafe flatten/recovery".

## 2026-07-15 — Nova OS P8–P10 R2, replay, live NO-GO

- **What:** P8 Cloudflare R2 upload module + archive health API (code-complete without keys); P9 replay/ask/evening-review + CLI + ArchiveRewind Watchlist subtab; P10 live-readiness doc with explicit **NO-GO** for `auto_live`.
- **Why:** Close the Nova OS plan map through durability, learning loop, and an honest live gate.
- **Files touched:** `backend/archive/r2.py`, `health.py`, `replay.py`, `ask.py`, `evening_review.py`, `routes/archive.py`, `tools/nova_os_replay.py`, `docs/r2-archive-setup.md`, Obsidian restore + live-readiness notes, `ArchiveRewind.tsx`, status/roadmap/canvas, tests.
- **How it works now:** Cold days optionally upload as content-addressed R2 objects when `ARCHIVE_R2_ENABLED` + `R2_*` are set in `.env` (never pretend success). `GET /api/archive/health|days|replay/{date}` expose status and `decide(record=False)` replay. `ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM` stays True. `auto_live` remains rejected in `control_mode`. Next action: **stop** — separate approved phase required for live.
- **Verified by:** pytest `test_archive_r2.py` + `test_archive_replay.py` (+ prior archive tests); `npm run build` for ArchiveRewind.
- **Follow-ups:** Operator creates R2 bucket/token; parent commit+push; no live unlock.
- **Related:** [[Nova-OS-Live-Readiness-Review]], [[Nova-OS-Archive-Restore-Runbook]], `docs/r2-archive-setup.md`.

## 2026-07-15 — Nova OS P6/P7 local archive capture + cold compact

- **What:** New `backend/archive/` package: hot SQLite capture (`bars_1m`, `bars_1d`, `tape_ibkr`, gaps, incomplete windows, integrity counters) and stdlib JSONL+sha256 cold compact/restore. IBKR tape prints also call `record_tape_print`. L2 timer purge no-ops while `ARCHIVE_REQUIRE_VERIFIED_BEFORE_TRIM` (default True). Optional `archive_maintenance_loop` behind `ARCHIVE_MAINTENANCE_ENABLED` (default false).
- **Why:** Nova OS phases P6 (loss-aware local capture) and P7 (local cold archive) — stop discarding IBKR AllLast and never purge unverified hot data on a timer.
- **Files touched:** `backend/archive/*`, `backend/constants.py` (`ARCHIVE_*`, `ARCHIVE_SCHEMA_VERSION`), `ibkr/tape_stream.py`, `l2/db.py`, `app_lifespan.py`, `tests/test_archive_*.py`.
- **How it works now:** Live UI still uses `/api/l2/*`. Durable writes go to `archive.db` under `cache_dir`. Finished days export to `archive_cold/<date>/<schema>/…jsonl` + manifests; `restore_day_to_temp` rebuilds a temp DB and compares row counts/checksums. L2 changed-book hook is a stub (`record_l2_snapshot`) until depth wiring is benchmarked. Does **not** bump `NOVA_OS_POLICY_VERSION`.
- **Verified by:** `pytest tests/test_archive_capture.py tests/test_archive_compact_restore.py`.
- **Follow-ups:** P8 R2 upload + verified trim; wire L2 changed-book + focus 1m bar feeder; parent verify + status phase bump + commit.
- **Related:** [[Nova-OS-Status]] P6/P7 recreate; Local-Market-Data-Recorders.md.

## 2026-07-15 — Nova OS P5 auto_paper + restart recovery

- **What:** `set_mode("auto_paper")` gated (paper IBKR + orders enabled + risk + not holiday); `on_signal` auto-places via `place_from_ticket`; `executed_paper` receipts include order ids; `recovery.py` reconstructs tracked positions on startup; `auto_live` still blocked. ExecutorPanel can raise Auto Paper on paper Gateway with disclosure; Auto Live disabled.
- **Why:** Phase P5 — automatic paper execution with restart reconciliation; no live money.
- **Files touched:** `constants.py` (policy `nova-os-p5-2026-07-15`, `NOVA_OS_NYSE_HOLIDAYS`), `nova_os/control_mode.py`, `gates.py`, `recovery.py`, `strategy/executor.py`, `app_lifespan.py`, `ExecutorPanel.tsx`, `tests/test_nova_os_auto_paper.py`.
- **How it works now:** Restart → always `signal` (never restores auto_paper). Raise Auto Paper only when paper Gateway + spend + risk + not holiday (else 409). BUY in auto_paper places immediately; confirm still stages. Recovery reads recent events + optional IBKR open orders; ambiguous → force_signal + loud system receipt.
- **Verified by:** pytest `test_nova_os_auto_paper.py` + related control_mode/executor; `npm run build` (parent verifies before marking verified).
- **Follow-ups:** Parent verify + commit; then next phase per status note.
- **Related:** [[Nova-OS-Status]] P5 in_progress.

## 2026-07-15 — Nova OS P4 confirm mode + emergency controls

- **What:** In-memory control modes (`signal`/`confirm`; auto_* rejected until P5), staged-ticket queue with TTL Approve/Reject, safer kill (preserve filled protective stops), cancel-working-entry, typed FLATTEN flatten, Automation panel mode ladder + staged queue UI.
- **Why:** Phase P4 — per-trade manual approval end-to-end with no automatic order path enabled.
- **Files touched:** `backend/nova_os/control_mode.py`, `staged_tickets.py`, `strategy/executor.py`, `routes/executor.py`, `constants.py` (policy `nova-os-p4-2026-07-15`), `ExecutorPanel.tsx`, `useExecutor.ts`, tests.
- **How it works now:** Restart → `signal`. Raise to Confirm stages BUY tickets (45s TTL). Approve places paper bracket. Kill → signal + reject staged + cancel unfilled parents only. Flatten requires typing `FLATTEN`.
- **Verified by:** pytest control_mode/staged/executor; `npm run build` PASS.
- **Follow-ups:** P5 auto_paper + restart reconciliation.
- **Related:** [[Nova-OS-Status]] P4.

- **Related:** Nova-OS-Status P4.

## 2026-07-15 — Fail-loud HOD/scanner integrity checks

- **What:** Continuous integrity evaluators + API + CLI + HOD tab banner so silent data-flow bugs (no ticks, surge cold-start, empty volume seeds, IBKR down, stale scanner caches) cannot look like “quiet market.”
- **Why:** HKIT Squeeze miss was an invisible `surge:None` / empty-history bug; user asked how we make sure this class of error does not happen again across scanners.
- **Files touched:** `hod_momo_integrity.py`, `integrity_live.py`, `hod_momo.py`, `ibkr/reprice.py`, `routes/hod_momo.py`, `routes/scan.py`, `app_lifespan.py`, `tools/hod_momo_integrity_check.py`, `HodMomoIntegrityBanner.tsx`, `HodMomoTab.tsx`, constants, tests.
- **How it works now:** Poll `GET /api/integrity` (or `/api/hod-momo/debug/integrity`, `/api/scan/integrity`). Background loop logs `INTEGRITY FAIL/WARN`. Banner on HOD tab surfaces fail/warn. CLI: `py -3 tools/hod_momo_integrity_check.py` (exit 0/1/2).
- **Verified by:** `pytest tests/test_hod_momo_integrity.py` + surge-seed tests; frontend build.
- **Follow-ups:** Warrior live parity poller once real auth cookies available; fix `watch_seed_size=0` when integrity warns.
- **Related:** PROBLEM_LOG HKIT surge:None; surge bar-seed CHANGELOG entry.
- **Correction (2026-07-16):** This entry was aspirational — runtime modules were missing at master `d3a8985`. Real ship is **2026-07-16 — HOD Momo live accuracy**.

## 2026-07-15 — HOD Momo Squeeze cold-start: seed surge buffer from 1-min bars

- **What:** When a symbol first gets a HOD tick, Nova now seeds the Squeeze price buffer from recent 1-min bars (IBKR when discovery=ibkr), then re-evaluates strategies. Fixes `surge:None` / flat-surge misses like HKIT vs Warrior.
- **Why:** Warrior already has tape history; Nova only started measuring after the name entered the focus watch set — too late for Up 5% in 5min.
- **Files touched:** `backend/hod_momo_surge_seed.py`, `backend/hod_momo.py`, `backend/app_lifespan.py`, `backend/constants.py`, `backend/tests/test_hod_momo_surge_seed.py`.
- **How it works now:** `on_trade_update` queues `request_surge_seed(sym)` once/session → background `surge_seed_loop` fetches 1Min bars → merges low+close points into `_price_buffer` → `reevaluate_after_surge_seed`. Session rollover clears seed state.
- **Verified by:** `pytest tests/test_hod_momo_surge_seed.py` (+ existing HOD engine tests).
- **Follow-ups:** Warrior ↔ Nova alert parity poller once real auth cookies are available (analytics cookies alone are not enough); investigate `watch_seed_size=0`.
- **Related:** PROBLEM_LOG 2026-07-15 HKIT surge:None.
- **Correction (2026-07-16):** Runtime was missing at master tip; re-implemented under **2026-07-16 — HOD Momo live accuracy**.

## 2026-07-15 — Nova OS Phase P3: Decision UX + attention

- **What:** Watchlist **Decision** sub-tab with gate-by-gate audit UI; Signals column for Nova OS verdict; muteable attention strip/sounds; read-only `tools/nova_os_cli.py`.
- **Why:** P3 — operators must see every BUY/WAIT/NO_BUY and the first failing gate without reading logs.
- **Files touched:** `DecisionPanel.tsx`, `NovaOsAttentionStrip.tsx`, `novaOsAttention.ts`, `useNovaOsDecide.ts`, `WatchlistTab.tsx`, `SignalsPanel.tsx`, `useSignalsStream.ts`, `types.ts`, `constants.ts`, `index.css`, `tools/nova_os_cli.py`.
- **How it works now:** DecisionPanel polls `/api/nova-os/decide`; highlights first failed gate; BUY/WAIT push attention events (mute silences sound only). CLI is HTTP-only.
- **Verified by:** vitest attention 2 passed; `npm run build` PASS.
- **Follow-ups:** P4 confirm queue + mode ladder UI.
- **Related:** [[Nova-OS-Status]] P3.

## 2026-07-15 — Nova OS Phase P2: decide() brain (signal only)

- **What:** Implemented `nova_os.decide()` — ordered gates that emit `BUY | WAIT | NO_BUY` with reason codes, ticket, confidence, citations, and an append-only receipt. Wired `GET /api/nova-os/decide` (+ `/{symbol}`) and routed `setups_stream` eligible setups through decide (only BUY reaches the executor). Execution remains impossible: `would_execute=False`.
- **Why:** P2 of the Nova OS plan — compose Five Pillars, setups, risk, first-minute volume, watchlist rank, and news-impact into one auditable brain before any confirm/auto modes.
- **Files touched:** `backend/nova_os/{decide,gates}.py`, `backend/constants.py` (decide tunables + reason codes; policy `nova-os-p2-2026-07-15`), `backend/routes/nova_os.py`, `backend/strategy/setups_stream.py`, `tests/test_nova_os_decide.py`.
- **How it works now:** Gate 0 session/risk/`loss_policy_mode` → Gate 1 pillars → Gate 2 setup + ≥100k first-minute volume + top-4 watchlist rank → Gate 3 ticket/`validate_trade_plan`/sizing → Gate 4 soft news-impact (`WAIT` if weak) → Gate 5 `MICROSTRUCTURE_NOT_EVALUATED`. Receipts always recorded; no broker actions.
- **Verified by:** pytest baseline + decide suite = 140 passed; 4 nova-os routes registered; `npm run build` PASS.
- **Follow-ups:** P3 DecisionPanel + notifications; daily-loss-count (vs consecutive) for loss policy; Gate 5 tuning after archive days.
- **Related:** plan `nova_os_decision_engine_c4367abc`; [[Nova-OS-Status]] P2.

## 2026-07-15 — Nova OS Phase P1: audit + event foundation

- **What:** Added Nova OS's append-only decision/event log, a stable code vocabulary (decision verdicts, control modes, action codes, reason codes), policy-version metadata, a temporary graduated loss policy, and a read-only API (`GET /api/nova-os/policy`, `GET /api/nova-os/events`). No decision logic runs yet.
- **Why:** P1 of the Nova OS plan — lay the audit foundation so future `decide()` (P2) and the UI speak one vocabulary and every action leaves an immutable receipt ("no silent action").
- **Files touched:** `backend/constants.py` (Nova OS section), `backend/nova_os/{__init__,codes,events_db,events}.py`, `backend/routes/nova_os.py`, `backend/main.py` (router), `backend/app_lifespan.py` (init db), tests `test_nova_os_codes.py` / `test_nova_os_events.py`.
- **How it works now:** `nova_os.events.record_receipt()` is the one write path; it validates every code against `nova_os.codes` (fail-closed on unknown codes) and appends an immutable row to `nova_os_events.db` (under `paths.cache_dir()`), returning the receipt. `get_events()` reads newest-first with symbol/kind filters. `codes.loss_policy_mode()` only ever lowers autonomy toward `confirm` (first loss → downgrade, third → halt), never raises it. All code strings live in `constants.py`.
- **Verified by:** `pytest` P0 baseline + new suites = 126 passed; `main` imports with 2 nova-os routes; `npm run build` PASS.
- **Follow-ups:** P2 — `decide()` engine emitting these receipts; DecisionPanel UI; event retention pruning.
- **Related:** plan `nova_os_decision_engine_c4367abc`; [[Nova-OS-Status]] P1.

## 2026-07-15 — Nova OS Phase P0: continuity baseline

- **What:** Canonical `Nova-OS-Status.md`, always-on continuity rule (read status → phase-close commit+push), mission canvas, duplicate L2 recorder constants removed, stale journal/risk/roadmap docs fixed to match A–F backbone + Nova OS P0–P10 plan.
- **Why:** Cross-chat handoff so agents can answer “what is Nova OS / where are we / what next?” from repo artifacts alone before P1 events.
- **Files touched:** `Nova-OS-Status.md`, `.cursor/rules/nova-os-continuity.mdc`, `backend/constants.py` (L2 dedupe only), `risk.py`, `JournalPanel.tsx`, Automation/Decision-Brain/Local-Market-Data-Recorders notes, `CHANGELOG.md`.
- **How it works now:** Status note is source of truth; canvas mirrors it; every phase must commit+push with SHA recorded before the next chat starts. Executor/journal docs no longer claim Phase D is missing.
- **Verified by:** strategy/L2 pytest 109 passed; `npm run build` PASS.
- **Follow-ups:** P1 audit/event foundation; unrelated scanner/HOD/earnings WIP left uncommitted.
- **Related:** plan `nova_os_decision_engine_c4367abc`; mission canvas outside repo under Cursor `canvases/`.

## 2026-07-15 — Settings labels name the Alpaca API

- **What:** Credential fields are labeled **Alpaca API Key ID / Secret / Base URL / Data Feed** (Dashboard + Settings), with a short hint that these are for news, listing metadata, and optional Alpaca scanner mode.
- **Why:** User wants provider-prefixed labels so future keys/APIs stay unambiguous.
- **Files touched:** `constants.ts`, `SettingsPanel.tsx`, `DashboardTab.tsx`.
- **How it works now:** Labels/placeholders live in constants; same copy in both settings surfaces.
- **Verified by:** frontend build.

## 2026-07-15 — Scanner table density default Large (reset stale prefs)

- **What:** Confirmed default Table text size = Large; bumped storage key to `nova_scanner_table_density_v2` so older Compact/Medium prefs from early testing are ignored.
- **Why:** User asked to default to large; some browsers still held a smaller saved value under v1.
- **Files touched:** `constants.ts`.
- **How it works now:** Fresh loads without a v2 key start at Large (1rem). Users can still pick Extra large in Dashboard → Display.
- **Verified by:** constants default already `large`.

## 2026-07-15 — Scanner table text size setting

- **What:** Added **Table text size** (Compact / Medium / Large / Extra large) under Dashboard → Display and header Settings. Default is Large (`1rem`). Preference persists in localStorage.
- **Why:** After densifying scanners, text was still too small; user asked for a Font size setting.
- **Files touched:** `useScannerTableDensity.ts`, `ScannerTableDensitySelect.tsx`, `SettingsPanel.tsx`, `DashboardTab.tsx`, `DashboardPage.tsx`, `constants.ts`, `index.css`.
- **How it works now:** Hook sets `--scanner-table-fs` on `:root`; Gappers/Gainers/AH/Catalysts scale from that CSS variable. Immediate on change; no backend save needed.
- **Verified by:** frontend build.

## 2026-07-15 — Scanner table density slightly enlarged

- **What:** Gappers/Gainers/After Hours/Catalysts type and row padding bumped (~0.68→0.75rem, padding ~0.28rem) after the first compact pass felt too small.
- **Why:** User found the HOD-tight density hard to read on scanner tables.
- **Files touched:** `frontend/src/index.css`.
- **How it works now:** Still denser than the old 1rem rows; readable middle ground.
- **Verified by:** frontend build.

## 2026-07-15 — News column before Symbol on scanner tables

- **What:** News (flame) column is now the first column on Gappers, Gainers, After Hours, and Catalysts — before Symbol.
- **Why:** User wants news visible before the ticker for faster scanning.
- **Files touched:** `constants.ts` (`SCANNER_COLUMNS`), `CatalystsTable.tsx`.
- **How it works now:** Column order is News → Symbol → … HOD Momo has no news column (unchanged).
- **Verified by:** frontend build.

## 2026-07-15 — HOD Momo rows fully clickable

- **What:** Click (or Enter/Space) anywhere on a HOD Momo alert row opens the quote/chart for that ticker; double-click opens Stock View — same behavior as Gappers/Gainers.
- **Why:** Only the blue symbol was clickable before; user wants full-row selection for speed.
- **Files touched:** `HodMomoAlertRow.tsx`.
- **How it works now:** Row uses the same click-vs-double-click helper as `SelectableTableRow`. Symbol button still works (stops propagation).
- **Verified by:** frontend build.

## 2026-07-15 — Dense scanner tables (Gappers/Gainers match HOD look)

- **What:** Gappers, Gainers, After Hours, Catalysts (and other `.table-wrapper` tables) use HOD-Momo-like density: ~0.68rem type, tight row padding, uppercase headers, single-line symbol + compact exchange.
- **Why:** Scanner tables felt oversized vs the compact HOD Momo feed; user wanted the same look to save space.
- **Files touched:** `index.css`, `ScannerTable.tsx`, `CatalystsTable.tsx`.
- **How it works now:** Density is scoped under `.table-wrapper` so IBKR/order tables keep their own styles. Sub-tabs (Gainers/Losers) are also tighter.
- **Verified by:** frontend build.

## 2026-07-15 — Level 2 heuristic row no longer jumps

- **What:** The Level 2 badge row (Seller stacked / Bid heavy / Wide spread) always reserves height via an invisible placeholder when no heuristic is active.
- **Why:** Showing/hiding the badges shifted the book up and down.
- **Files touched:** `DepthLadder.tsx`, `constants.ts`, `index.css`.
- **How it works now:** `.ibkr-depth-heuristics` always mounts; empty state uses a hidden "Seller stacked"-sized placeholder.
- **Verified by:** frontend build.

## 2026-07-15 — HOD Strategies dropdown: denser + taller

- **What:** Filter Strategies menu uses smaller type (~0.65rem) and taller max height (520px) so most strategies fit with little or no scrolling.
- **Why:** User disliked scrolling the strategy checklist.
- **Files touched:** `index.css`, `HodMomoStrategyFilterDropdown.tsx`, `constants.ts`.
- **How it works now:** Scoped under `.hod-strategy-filter-dropdown` (exchange filter unchanged).
- **Verified by:** frontend build.

## 2026-07-15 — Earnings-today party badge on symbols

- **What:** Any `SymbolSelectButton` (HOD Momo, Gappers/Gainers, Catalysts, Watchlist, Signals) shows 🥳 next to the ticker when Yahoo earnings date is **today** (US/Eastern).
- **Why:** Spot possible earnings catalysts quickly in scanner tables.
- **Files touched:** `backend/fundamentals.py`, `routes/fundamentals.py`, `backend/constants.py`, `main.py`, `useEarningsToday.ts`, `SymbolSelectButton.tsx`, `useTickerStream.ts`, `isEarningsDateToday.ts`, `constants.ts`.
- **How it works now:** Buttons register symbols; a debounced batch hits `GET /api/earnings-today`. Ticker-detail fundamentals also seed the map. **Test without a live earnings name:** `localStorage.setItem('nova_force_earnings_today','VVAI')` or open `?earningsParty=VVAI` then refresh.
- **Verified by:** vitest date helper; pytest cache flags; browser force override.
- **Related:** PROBLEM_LOG not required (feature).

## 2026-07-15 — Fix HOD Momo stacked/overlapping row paint

- **What:** Virtualized alert rows no longer paint on top of each other. Cells are clipped to a fixed 28px row; consolidation shows as compact `×N`; strategy pills truncate instead of overflowing.
- **Why:** Absolute-position virtualization + overflowing cell content (strategy `overflow:visible`, multi-line symbol stack) caused illegible stacked text.
- **Files touched:** `HodMomoAlertTable.tsx`, `HodMomoAlertRow.tsx`, `SymbolSelectButton.tsx`, `index.css`, `PROBLEM_LOG.md`.
- **How it works now:** Every `.hod-virtual-row` is fixed height + `overflow:hidden`. Content that does not fit is ellipsized; hover title still has full consolidation detail.
- **Verified by:** frontend build; stress scroll on HOD tab.
- **Related:** PROBLEM_LOG 2026-07-15 HOD Momo rows stacked.

## 2026-07-15 — HOD Momo strategy filters → dropdown

- **What:** Replaced the multi-row strategy chip strip with a single-row toolbar and a **Strategies ▾** multi-select dropdown (select all, Running Up only, per-strategy checkboxes + counts).
- **Why:** Chips ate too much vertical space above the alert table.
- **Files touched:** `HodMomoStrategyFilterDropdown.tsx`, `HodMomoTab.tsx`, `HodMomoAlertTable.tsx`, `index.css`.
- **How it works now:** Visibility still filters the feed client-side. Open **Strategies** for checkboxes; summary shows All / N of M / Running Up only. Column-header filter removed (toolbar is the one place).
- **Verified by:** frontend build; browser open HOD Momo + dropdown.

## 2026-07-15 — HOD Momo strategy chips compacted

- **What:** Strategy filter chips (and header Clear/Configure) are much smaller: ~0.62rem type, tight padding, single-line labels so more chips fit per row and less vertical space is eaten above the table.
- **Why:** After densifying the alert table, the chip strip still dominated the left panel.
- **Files touched:** `frontend/src/index.css`, `CHANGELOG.md`.
- **How it works now:** Same chip behavior; denser chrome only.
- **Verified by:** frontend build; visual check on HOD Momo tab.

## 2026-07-15 — HOD Momo scroll: dense absolute virtualization

- **What:** Replaced spacer-`<tr>` virtualization with TanStack absolute/`translateY` CSS-grid rows; denser 28px rows and smaller type; overscan cut from 40→6. Dev-only **Stress scroll** cycles live feed → 1000 → 2000 mock rows.
- **Why:** Scrolling ~480+ alerts felt janky (especially scrolling back up); fonts felt oversized.
- **Files touched:** `HodMomoAlertTable.tsx`, `HodMomoAlertRow.tsx`, `HodMomoTab.tsx`, `buildHodMomoStressAlerts.ts`, `constants.ts`, `index.css`.
- **How it works now:** Only ~viewport+overscan rows mount. Fixed row height + single-line consolidation badges keep scroll math stable. Stress button (dev builds) injects mock data without hitting the WS.
- **Verified by:** vitest stress builder; frontend build; manual scroll with stress 1k/2k.
- **Related:** PROBLEM_LOG 2026-07-15 HOD Momo scroll jank.

## 2026-07-15 — Draggable scanner / quote panel splitter

- **What:** The vertical divider between the main scanner column and the quote side panel is now draggable. Width persists in `localStorage`.
- **Why:** User wants more room on the left (scanner) or right (quote/chart) depending on the moment.
- **Files touched:** `frontend/src/hooks/useSidePanelWidth.ts`, `frontend/src/components/PanelResizeHandle.tsx`, `DashboardPage.tsx`, `SidePanel.tsx`, `constants.ts`, `index.css`.
- **How it works now:** Drag the thin handle left to widen the quote panel, right to give the scanner more space. Clamped so the scanner keeps at least ~400px; hidden when the layout stacks below 1100px.
- **Verified by:** frontend build.

## 2026-07-15 — Fix chart Loading starvation (IBKR historical priority)

- **What:** Open ticker chart bars now take priority over background setup scans. Setups under discovery=ibkr fetch fewer symbols less often; 1Min lookback shortened to 1 day; UI aborts stuck fetches at 25s with a clear error.
- **Why:** Chart sat on "Loading…" for half a minute because `setups_stream` was flooding Gateway historical requests.
- **Files touched:** `backend/ibkr/historical_gate.py`, `backend/ibkr/bars.py`, `backend/chart_bars.py`, `backend/strategy/setups_stream.py`, `backend/constants.py`, `backend/routes/ticker.py`, `frontend/src/TickerChart.tsx`, `frontend/src/constants.ts`.
- **How it works now:** One historical request at a time. Chart path uses `interactive=True`. Background setups skip while a chart fetch is active. IBKR setup scan: top 3 symbols, 60s interval, 2s gap between symbols.
- **Verified by:** pytest historical_gate; timed `/api/ticker/NVVE/bars` after reload.

## 2026-07-15 — Fix transparent Filter Exchanges dropdown

- **What:** Defined missing `--card-bg` / `--hover-bg` design tokens and gave the exchange/HOD filter dropdown a solid `--panel-bg` background.
- **Why:** Dropdown had no background — text overlapped the Settings form underneath.
- **Files touched:** `frontend/src/index.css`, `PROBLEM_LOG.md`.
- **How it works now:** `:root` owns `--card-bg` (alias of `--panel-bg`) and `--hover-bg`. Filter panels reuse those tokens instead of undefined variables.
- **Verified by:** visual check of Exchange Filter dropdown on Dashboard.

## 2026-07-15 — Dashboard tab + exchange filter

- **What:** Added a Dashboard tab before Gappers with a multi-select exchange dropdown (NASDAQ checked by default). The exchange filter applies across Dashboard, Gappers, Gainers, After Hours — rows from unchecked venues disappear everywhere. Selection persists via `localStorage`.
- **Why:** User wants to focus on NASDAQ (or chosen exchanges) without seeing AMEX/BATS/etc. noise across all scanner tabs.
- **Files touched:** `frontend/src/constants.ts`, `frontend/src/components/TabNav.tsx`, `frontend/src/hooks/useExchangeFilter.ts`, `frontend/src/components/ExchangeFilterDropdown.tsx`, `frontend/src/pages/DashboardTab.tsx`, `frontend/src/pages/DashboardPage.tsx`, `frontend/src/index.css`, `frontend/src/hooks/useExchangeFilter.test.ts`.
- **How it works now:** `useExchangeFilter` (singleton in DashboardPage) holds the selected exchanges and exposes `filterRows()`. Dashboard tab renders a toolbar with sub-tabs (Gappers/Gainers/Losers) + the `ExchangeFilterDropdown`. `DashboardPage` filters all scanner arrays and passes them to both `DashboardTab` and `ScannerTabPanels`. App opens on Dashboard by default; tab counts reflect the filtered lists.
- **Verified by:** `npm run build` clean + `vitest run` 5/5 pass; live app smoke check.

## 2026-07-15 — Chart maximize: fix header collision + blank candles

- **What:** Maximizing the price chart now covers the true viewport (above the app header) without remounting the lightweight-charts instance. Escape restores; body scroll locks while open.
- **Why:** Maximize used `position: fixed` inside `.side-panel` (`container-type: inline-size`), so the overlay was trapped in the panel and collided with the Nova header. Chart effect also depended on `maximized`, destroying/recreating the chart and making bars appear much later.
- **Files touched:** `frontend/src/TickerChart.tsx`, `frontend/src/hooks/useMaximizedChartPortal.ts`, `frontend/src/index.css`.
- **How it works now:** A stable portal host moves between an in-flow slot and `document.body` on maximize. Chart create effect no longer depends on `maximized` — only ResizeObserver / a post-toggle resize pass.
- **Verified by:** frontend build + local app; maximize click path.
- **Related:** PROBLEM_LOG 2026-07-15 chart maximize header.

## 2026-07-15 — HOD Momo: stop wiping today's alerts on API restart

- **What:** Fixed a false "session rollover" on every cold start after 4 AM ET that cleared alerts just loaded from disk, then overwrote today's snapshot with the tiny post-restart list. Real day changes now archive the previous day's alerts before clearing. Added explicit **Clear today** (`DELETE /api/hod-momo/alerts`) so only the user wipes the feed.
- **Why:** User saw ~1000 HOD alerts drop to ~89 after server restarts — not caused by virtual-scroll UI work.
- **Files touched:** `backend/hod_momo.py`, `backend/cache.py`, `backend/routes/hod_momo.py`, `frontend/.../HodMomoTab.tsx`, `DashboardPage.tsx`, tests.
- **How it works now:** Empty `_session_date` only initializes (never clears). On true ET day change, alerts are written to `hod-momo-YYYY-MM-DD.json` for the prior day first. Restart keeps today's file. Clear is opt-in via UI confirm.
- **Verified by:** `pytest` 401 passed (incl. new persist tests); vitest; `tsc -b` clean.
- **Related:** PROBLEM_LOG 2026-07-15 HOD restart wipe.

## 2026-07-15 — Chart EMAs + VWAP overlays (library-backed)

- **What:** Price chart toolbar now has EMAs / VWAP toggles (default on). Enabling them draws Warrior-colored 9/20/50/200 EMA lines plus an orange dashed VWAP on the main candle pane.
- **Why:** User asked for Ross-style EMA + VWAP overlays using the already-installed `lightweight-charts-indicators` stack (same as RSI/MACD) — no hand-rolled TA.
- **Files touched:** `frontend/src/constants.ts`, `chartIndicators.ts` (+ test), `components/TickerChartOverlays.tsx` (new), `TickerChart.tsx`, `TickerChartOscillatorPanes.tsx`.
- **How it works now:** `EMA.calculate` (×4 lengths) and `VwapMvwapEmaCrossover` plot0 feed `LineSeries` on the existing price chart. Oscillator panes stay RSI/MACD-only. Colors: grey 9 / light-blue 20 / red 50 / purple 200 / orange dashed VWAP.
- **Verified by:** vitest chartIndicators; frontend build; app run.
- **Follow-ups:** Session-boundary VWAP reset across multi-day lookbacks if the community cumulative VWAP looks wrong on long histories.

## 2026-07-15 — HOD Momo: @tanstack/react-virtual for continuous scroll

- **What:** Replaced the custom pager + hand-rolled `useWindowedRows` with `@tanstack/react-virtual`. Scroll the full day list continuously; the library mounts only the viewport + overscan (~50–100 DOM rows). Removed `HodMomoPager` / `HOD_MOMO_PAGE_SIZE`.
- **Why:** User asked not to reinvent windowing — use a standard library so scrolling loads the next batch of rows the usual way.
- **Files touched:** `frontend/package.json`, `HodMomoAlertTable.tsx`, `HodMomoTab.tsx`, `constants.ts`, deleted `HodMomoPager.tsx` / `useWindowedRows*`.
- **How it works now:** `useVirtualizer` owns scroll indexes/measurements; spacer rows keep scrollbar accurate for 1000+ alerts without mounting them all.
- **Verified by:** `npx vitest run`; `npm run build`.

## 2026-07-15 — Quote panel: Watchlist + L2/T&S under the chart

- **What:** In the stacked quote-panel layout (`layout="columns"`), Watchlist strip and Level 2 / Time & Sales now render directly under the price chart, above the news/catalyst row.
- **Why:** User asked to move those two surfaces up under the graph so trading context sits next to the candles.
- **Files touched:** `frontend/src/components/TickerDetailContent.tsx`
- **How it works now:** Column order is chart → watchlist → L2/T&S → news → quote | fundamentals. Stack layout (non-columns) unchanged.
- **Verified by:** Layout reorder only; Vite HMR on running UI.

## 2026-07-15 — Configurable CORS + frontend vendor chunk-splitting

- **What:** CORS origins are now configurable via `NOVA_CORS_ALLOWED_ORIGINS` (comma-separated), defaulting to `CORS_ALLOWED_ORIGINS_DEFAULT = ["*"]` for local dev; `allow_credentials` dropped to `False` since the frontend never sends cookies/auth (also fixes the spec-invalid `*` + `credentials=True` combo). Vite build now splits `react`/`react-dom` and the `lightweight-charts*` libs into dedicated vendor chunks via `manualChunks` in `vite.config.ts`.
- **Why:** Last two "optional low-priority" items from the 2026-07-14/15 codebase audit (`allow_origins=["*"]` before non-local deploy, and the ~673 kB app bundle warning).
- **Files touched:** `backend/constants.py`, `backend/app_lifespan.py`, `frontend/vite.config.ts`, `frontend/.env.example`.
- **How it works now:** `configure_cors()` reads `NOVA_CORS_ALLOWED_ORIGINS` at startup; unset (local dev) keeps the permissive `*` default, set it on the Railway/Vercel backend once the frontend has a real deployed origin to lock CORS down. The app JS chunk dropped from ~673 kB to ~168 kB after code-splitting; `vendor-react` (~190 kB) and `vendor-charts` (~505 kB) are now separate, independently cacheable chunks — the charting-library chunk still exceeds Vite's 500 kB warning threshold, which is expected and fine since it rarely changes between deploys.
- **Verified by:** `pytest` 399 passed; `npm run build` clean (verified new chunk sizes); `npx vitest run` 60 passed.
- **Follow-ups:** None — this closes out the last two audit pickups from 2026-07-15.

## 2026-07-15 — Fix reset_config(12) off-by-one and stale-symbol fundamentals queueing in HOD Momo debug path

- **What:** Fixed the two latent bugs flagged (but deliberately not fixed) in the `hod_momo.py` module-split entry below: (1) `reset_config()` now accepts strategy ID 12 ("Running Up Alert") by checking against `HOD_MOMO_STRATEGY_ID_MAX + 1` instead of a hardcoded `range(1, 12)`; (2) `_would_fire_now()` (the HOD Momo debug-symbol evaluator) now calls `mark_needs_fundamentals(symbol)` with its own `symbol` argument instead of routing through the `_active_symbol_name` global that only the live `on_trade_update` path sets, so it no longer queues a stale/wrong ticker for fundamentals.
- **Why:** Genuine incorrect-behavior bugs identified during the prior refactor pass (commit `69824de`) and now fixed per user follow-up request.
- **Files touched:** `backend/hod_momo.py`, `backend/tests/test_hod_momo_engine.py` (3 new regression tests), `PROBLEM_LOG.md`.
- **How it works now:** `reset_config(strategy_id)` validates `strategy_id not in range(1, HOD_MOMO_STRATEGY_ID_MAX + 1)`, matching the same inclusive-bound pattern `_load_configs_from_disk()` already used — strategies 1 through 12 can all now be reset individually. `_would_fire_now(symbol)` no longer depends on `_active_symbol_name`/`_active_symbol()` at all; it closes over the `symbol` parameter it was already given, so the fundamentals-queue side effect always targets the ticker actually being debugged. The live `on_trade_update()` alert-firing path is untouched — it still sets/clears `_active_symbol_name` exactly as before, and its own `lambda: mark_needs_fundamentals(_active_symbol())` callback is unchanged.
- **Verified by:** Added `test_reset_config_resets_strategy_12_running_up`, `test_reset_config_still_rejects_out_of_range_ids`, and `test_would_fire_now_queues_symbol_being_debugged_not_stale_active_symbol` to `backend/tests/test_hod_momo_engine.py`; confirmed all three fail against the pre-fix code (via `git stash` of just `hod_momo.py`) and pass after the fix. Full `pytest` from `backend/`: 399 passed (396 baseline + 3 new tests, 0 regressions).
- **Related:** `PROBLEM_LOG.md` 2026-07-15 ("reset_config(12) rejected; HOD Momo debug path queued stale fundamentals symbol"); follow-up to the 2026-07-15 `hod_momo.py` module-split entry below (commit `69824de`).

## 2026-07-15 — hod_momo.py module split (1226 → 716 lines) + datetime deprecation fix

- **What:** Split the 1226-line `backend/hod_momo.py` HOD Momo alert engine into a facade + three new sibling modules, following the flat-sibling convention already used by `hod_momo_metrics.py` / `hod_momo_enrichment.py`. `hod_momo_models.py` (188 lines) holds the dataclasses (`StrategyConfig`, `MasterGateConfig`, `AlertObject`, `DecisionRecord`, `TickerSnap`) plus pure serialization/default-builder helpers and the two new UTC timestamp formatters. `hod_momo_filters.py` (140 lines) holds the pure per-strategy gate evaluators (`evaluate_strategy`, `passes_master_gate`, `fails_hod_gate`, `price_surge`, `passes_range`) — no module-level state, everything passed in as arguments. `hod_momo_debug.py` (95 lines) holds pure debug-payload builders for the `/api/hod-momo/debug/*` endpoints. `hod_momo.py` itself (716 lines) keeps every mutable global (price buffers, session highs, cooldowns, configs, alerts) and the trade-ingestion path that reads/writes it (`on_trade_update`, `load_state`, config/blocklist CRUD), since the existing test suite monkeypatches those globals directly. Also fixed the two `DeprecationWarning`s from `datetime.utcnow()` / `datetime.utcfromtimestamp()` by moving both call sites into `hod_momo_models.format_alert_timestamp()` / `format_trade_log_timestamp()`, rewritten with `datetime.fromtimestamp(ts, tz=timezone.utc)` / `datetime.now(timezone.utc)` — byte-identical string output (verified: neither format string includes `%z`/`%Z`, so aware-vs-naive doesn't change the rendered string).
- **Why:** Product-health audit flagged `hod_momo.py` at 1226 lines (file-size-limits.mdc target: 400) and its two per-run deprecation warnings as a deferred cleanup item (see 2026-07-15 audit-hygiene entry above).
- **Files touched:** `backend/hod_momo.py` (rewritten), `backend/hod_momo_models.py` (new), `backend/hod_momo_filters.py` (new), `backend/hod_momo_debug.py` (new), `backend/tests/test_hod_momo_models.py` (new), `backend/tests/test_hod_momo_filters.py` (new), `AGENTS.md` (§2.1 module layout table), `.cursor/rules/file-size-limits.mdc` (Known Violations entry + justification).
- **How it works now:** `hod_momo.py`'s public API (every function callers already used via `import hod_momo as _hod_momo`) is 100% unchanged — `main.py`, `routes/hod_momo.py`, `websocket.py`, `scan_runners.py`, `hod_momo_enrichment.py`, `universe.py`, `ibkr_bridge.py`, `app_lifespan.py`, `ticker.py`, and `scanner.py` needed zero import changes. Internally, `on_trade_update()` now calls the pure functions in `hod_momo_filters.py` (passing `_master`, `_price_buffer.get(symbol)`, `_session_highs.get(symbol, 0.0)`, etc. as explicit arguments each call) instead of those functions reading module globals directly, and builds `AlertObject.timestamp` / the per-trade debug log line via the new `hod_momo_models` timestamp helpers. `get_debug_counters/recent/snaps()` are now 2–3 line wrappers that gather the current globals and delegate to `hod_momo_debug.build_*()`.
- **Verified by:** `pytest` from `backend/` — 396 passed (379 baseline + 17 new tests covering the extracted pure modules, 0 regressions). Confirmed zero `DeprecationWarning`s in the full run (previously reported as part of a 35-warning run). Manually diffed `format_alert_timestamp()` / `format_trade_log_timestamp()` output against the old `utcfromtimestamp()`/`utcnow()` calls for byte-identical results. `main.py` imports cleanly end-to-end (smoke-tested via `python -c "import main"`).
- **Follow-ups:** `hod_momo.py` is still 716 lines (over the 400 target) — see the `file-size-limits.mdc` entry for why further splitting the stateful engine core is deliberately out of scope for this pass (would require breaking the existing monkeypatch-based test contract or introducing cross-module qualified-attribute state sharing, both higher-risk than warranted for live alert logic). Two pre-existing latent quirks noted but intentionally **not** fixed (flagged for separate triage): (1) `reset_config()` uses a hardcoded `range(1, 12)` instead of `HOD_MOMO_STRATEGY_ID_MAX` (=12), so strategy 12 ("Running Up") can never be reset individually via the config API; (2) `_would_fire_now()` (backing `/api/hod-momo/debug/symbol/{sym}`) never sets the internal "active symbol" that `mark_needs_fundamentals()` relies on, so a debug-only evaluation that hits the float/52wk "unknown" branch queues whatever symbol `on_trade_update` last touched (or `""`) instead of the symbol being debugged — a debug-endpoint side-effect quirk with no effect on live alert firing.

## 2026-07-15 — Audit hygiene pass: main.py size, stale docs, silent excepts, test coverage, pinned deps

- **What:** Addressed the "should-fix-soon" items from a read-only codebase audit (excluding the deferred `hod_momo.py` split). `backend/main.py` trimmed from 201 to 194 lines by extracting CORS middleware setup into `app_lifespan.configure_cors()`. `.cursor/rules/run-app.mdc` updated from stale "Stock Alert" / `stock_alert/` branding to current `Run Nova.bat` / `Nova` naming; `.cursor/rules/file-size-limits.mdc` and `AGENTS.md` §2.3 corrected to the true current line counts instead of stale "~199"/"~68" claims. Added `logger.debug`/`logger.warning` calls to 7 previously-silent `except Exception: pass` sites in `backend/cache.py` (disk-persistence and legacy-migration paths), plus one each in `backend/logging_setup.py` and `backend/run_api.py` (UTF-8 console reconfigure fallback), and to the silent `l2_features = None` catches in `backend/routes/news.py` and `backend/news/enrich.py`. Added new pytest coverage for three previously-untested, money-adjacent modules: `backend/routes/trading.py`, `backend/ibkr/account.py`, `backend/scan_runners.py`. Pinned previously-unpinned `backend/requirements.txt` entries (`fastapi`, `uvicorn`, `python-dotenv`, `alpaca-py`, `requests`, `tzdata`, `yfinance`, `websockets`, `watchfiles`, `ib_async`) to their exact currently-installed versions. Deleted `backend/_repro_test.py`, a one-off manual repro script (no `test_*` functions) for the already-fixed Windows console UTF-8 issue.
- **Why:** Audit-driven hygiene pass requested to close out "should-fix-soon" gaps without touching the three concurrently-running subagents' files (`backend/ibkr/{reprice,client,tape_stream,ticks,depth}.py`, `backend/observability.py`, `backend/ibkr/errors.py`, related frontend depth/tape/chart hooks) or the deferred `backend/hod_momo.py`.
- **Files touched:** `backend/main.py`, `backend/app_lifespan.py`, `backend/cache.py`, `backend/logging_setup.py`, `backend/run_api.py`, `backend/routes/news.py`, `backend/news/enrich.py`, `backend/requirements.txt`, `backend/tests/test_routes_trading.py` (new), `backend/tests/test_ibkr_account.py` (new), `backend/tests/test_scan_runners.py` (new), `.cursor/rules/run-app.mdc`, `.cursor/rules/file-size-limits.mdc`, `AGENTS.md`. Removed `backend/_repro_test.py`.
- **How it works now:** CORS middleware registration lives in `app_lifespan.configure_cors(app)` (called once from `main.py`'s app factory) instead of inline in `main.py`, matching how `lifespan` itself was already extracted there. All previously-silent cache/logging fallback paths now emit a `logger.debug`/`logger.warning` call before swallowing — behavior is unchanged (still non-fatal), but failures are now visible in `blast.log` instead of disappearing. Requirements pins reflect what's already installed in this environment, so no dependency version actually changed.
- **Verified by:** `pytest` from `backend/` — 379 passed (361 baseline + 18 new tests, 0 regressions). `(Get-Content backend/main.py).Count` → 194 (≤200 limit). `pip install -r requirements.txt` dry-run — all pins already satisfied, no resolution errors.
- **Follow-ups:** `backend/hod_momo.py` split + its `datetime.utcnow()`/`utcfromtimestamp()` deprecation warnings are explicitly deferred per user instruction (not part of this pass).

## 2026-07-15 — Filter ib_async's own noisy ERROR logs out of Sentry

- **What:** Added `backend/ibkr/log_filters.py` (`BenignIbkrErrorFilter` + `install_ibkr_log_filters()`), wired into `logging_setup.configure_logging()`. It attaches a `logging.Filter` to ib_async's own internal loggers (`ib_async.wrapper`, `ib_async.ib`, `ib_async.client`) that downgrades known-benign ERROR records to WARNING **in place** before they reach Sentry's `LoggingIntegration`. Matches IBKR Error 162/365 (`Error \d+, reqId ...`) and `cancelMktData`/`cancelMktDepth: No reqId found for contract ...`.
- **Why:** Those loggers (not our own app code) log expected/benign Gateway conditions at ERROR, and Sentry's default `event_level=ERROR` turned every one into an issue. Confirmed live in Sentry (`altay-studio`/`python-fastapi`): PYTHON-FASTAPI-1, -2, -3, -7, -8, -9 (`Error 162`/`365`, logger `ib_async.wrapper`) and PYTHON-FASTAPI-A/-9 (`cancelMktData: No reqId found...`, logger `ib_async.ib`).
- **Files touched:** `backend/ibkr/log_filters.py` (new), `backend/logging_setup.py`, `backend/constants.py` (`IBKR_BENIGN_LOG_ERROR_CODES`, `IBKR_BENIGN_LOG_MESSAGE_SUBSTRINGS`), `backend/tests/test_ibkr_log_filters.py` (new).
- **How it works now:** `logging.Filter.filter()` runs on the *logger* before `callHandlers` dispatches to handlers — mutating `record.levelno`/`levelname` there means local handlers (console + `blast.log`, still at INFO) log the downgraded WARNING as before, but Sentry's patched `callHandlers` (which re-checks `record.levelno >= event_level` in its `finally` block) now sees WARNING and skips issue creation. Records are never dropped — only downgraded, and only for the specific matched patterns; anything else stays ERROR and still reaches Sentry. Intentionally a separate, narrower pattern list from `ibkr/errors.py::is_transient_historical_failure` (that one classifies *our own* raised exceptions for one call site and is deliberately lax); this filter matches a third party's exact log text and must stay precise so it never hides a genuinely new IBKR error.
- **Verified by:** `pytest tests/test_ibkr_log_filters.py` (10 new tests: pattern matching, filter downgrade, no-drop, idempotent install, real `logging.getLogger("ib_async.wrapper").error(...)` call); full suite `pytest` from `backend/` — 361 passed. Cross-checked pattern text against live Sentry issues via the `user-sentry` MCP server before implementing.
- **Related:** Follow-up to 2026-07-15 "IBKR chart bars: clear errors, less Sentry spam" (that entry's own follow-up note called this out).

## 2026-07-15 — Live-verified rapid symbol-switch quote panel (L2/T&S/chart) against connected IBKR Gateway

- **What:** Ran the previously manual-only "rapid symbol switch" item from `scripts/ibkr_smoke_checklist.md` against a live, logged-in IB Gateway (`connected: true`, `mode: live`) and a running dev server. Rapidly switched the scanner's selected symbol across five Gainers-tab rows (AEHG → KUST → VTAK → AEHR → JLHL, forward and back to AEHR/JLHL) with the Level 2 depth ladder, Time & Sales tape, and price chart all visible. No code changes were needed — everything passed cleanly.
- **Why:** This was the one item in the IBKR smoke checklist that had stayed human-only, and it is exactly the regression class `single-market-data-feed.mdc`'s "quote panel symbol gate" rules exist to prevent (see the 2026-07-14 MVO/NXTC entry below). Automating a pass of it closes the last manual gap in the checklist.
- **Files touched:** None (verification-only). Added proof screenshots `frontend/rapid-switch-1-aehr-clean.png`, `frontend/rapid-switch-jlhl.png`. Annotated `scripts/ibkr_smoke_checklist.md` with the pass date.
- **How it works now:** Read via `agent-browser eval` after each rapid click, `.cq-symbol` (quote header) and `.depth-and-tape` textContent always matched the just-clicked row's price for both a first visit and a revisit (e.g. AEHR's book stayed 94.39×95.30 both times, JLHL's stayed 9.7x×9.80, VTAK's stayed 0.74x — no leftover rows or prices from the previously selected symbol). This confirms the existing guards hold under live data: `DepthAndTape`/`DepthLadder` remount via `key={depthSymbol}`, `TickerChart` remounts via `key={props.symbol}` on its error boundary, and `useIbkrTape`/`useTickerStream` gate on `msg.symbol !== symKey` plus a `ws !== wsRef.current` staleness check. `npx agent-browser@latest console` showed no new uncaught errors or React crash warnings across the switching sequence (only pre-existing, unrelated `Scanner API network error` health-probe logs).
- **Verified by:** Live browser session via `agent-browser` CLI against `http://localhost:5173` (backend already running on `:8000`, IBKR Gateway connected). `npx vitest run` in `frontend/`: 14 files / 60 tests passed (no regressions, no changes needed).
- **Follow-ups:** None — this item can now be considered automatable-on-demand via `agent-browser`; the manual checklist step remains as a fallback for a human pass without tooling.
- **Related:** `scripts/ibkr_smoke_checklist.md` "Quote panel (rapid symbol switch)" section; PROBLEM_LOG 2026-07-14 MVO/NXTC entry; `.cursor/rules/single-market-data-feed.mdc`.

## 2026-07-15 — Open ticker: skip redundant snapshot backstop while reqMktData is streaming

- **What:** `ibkr/reprice.py`'s `detail_reprice_loop` (the open ticker-detail "backstop") now skips its 3s `reqTickersAsync` snapshot entirely for symbols whose `ibkr/ticks.py` `reqMktData` streaming subscription is already ticking. Investigation confirmed the open ticker was **already** streaming last price via `reqMktData` (2026-07-14, "Chart data/live path"); the remaining bottleneck was the legacy snapshot backstop still firing every 3s for every open detail symbol regardless of whether streaming was already delivering, competing on the shared Gateway request queue with `table_reprice_loop`'s 1Hz chunked snapshots.
- **Why:** Follow-up called out in the "IBKR chart bars" entry below ("IBKR open-ticker streaming for queue contention"). The open ticker had already moved to `reqMktData` — the real fix is removing the now-redundant duplicate `reqTickersAsync` call so the backstop only fires when genuinely needed (before the first tick arrives, or once a stream goes stale/dead), cutting real Gateway-queue contention without weakening the backstop's safety purpose.
- **Files touched:** `backend/ibkr/ticks.py` (tracks `last_update_ts` per subscription + new `is_fresh(symbol, max_age_sec)`), `backend/ibkr/reprice.py` (`reprice_detail_symbols` / `detail_reprice_loop` accept optional `is_stream_fresh`), `backend/app_lifespan.py` (wires `ticks.is_fresh` in), `backend/constants.py` (`IBKR_DETAIL_STREAM_FRESH_SEC = 8.0`), `backend/tests/test_ibkr_ticks.py` (new), `backend/tests/test_ibkr_reprice.py`.
- **How it works now:** `ticks._on_ticker_update` stamps `last_update_ts = time.time()` on every `updateEvent` (not just on a price change), so `ticks.is_fresh(symbol, max_age_sec)` reports whether that symbol's stream is alive within the window, independent of whether the price itself moved. `detail_reprice_loop` passes `lambda sym: ticks.is_fresh(sym, IBKR_DETAIL_STREAM_FRESH_SEC)` into `reprice_detail_symbols`, which partitions `detail_symbols` into "fresh" (skip — `ticks.py` already owns that symbol's broadcasts) and "backstop" (unchanged snapshot + broadcast path). Omitting the freshness function (existing call sites/tests) preserves the exact prior "snapshot every open symbol every tick" behavior.
- **Verified by:** New unit tests (`test_ibkr_ticks.py`: `is_fresh` false pre-subscribe/pre-first-tick, true within window, false after window, case-insensitive, freshness tracked even when price is unchanged; `test_ibkr_reprice.py`: fresh symbols get zero snapshot/broadcast calls, mixed fresh+stale batches only snapshot the stale one, omitting the freshness fn keeps old behavior). Full backend suite: `py -3 -m pytest` from `backend/` → 351 passed, 0 failed. Confirmed the local `--reload` dev server on :8000 stayed healthy and IBKR-connected (`/api/health`, `/api/ibkr/status`) throughout.
- **Follow-ups:** Live verification of the actual open-ticker responsiveness improvement under real Gateway contention (many open panels + an active movers scan) still needs eyeballing against a connected Gateway during market hours — the unit tests lock in the request-skipping logic, not the end-to-end latency win.
- **Related:** CHANGELOG 2026-07-14 "Chart data/live path: IBKR historical bars + streaming last-price ticks" (added the `reqMktData` stream this entry now de-contends with).

## 2026-07-15 — IBKR chart bars: clear errors, less Sentry spam

- **What:** `ibkr/errors.py` formats exceptions that have empty `str(exc)` (TimeoutError/cancels). Transient historical failures log at warning with an explicit 503 detail; unexpected failures still ERROR with traceback. No Alpaca fallback under discovery=ibkr.
- **Why:** Sentry PYTHON-FASTAPI-6 showed `IBKR bars failed for AAPL:` with nothing after the colon.
- **Files touched:** `backend/ibkr/errors.py`, `backend/chart_bars.py`, `backend/ibkr/bars.py`, `backend/tests/test_ibkr_bars.py`.
- **How it works now:** Cancel/timeout → warning + “timed out or was cancelled” 503. Other failures → `logger.error(..., exc_info=True)` with `TypeName: message`.
- **Verified by:** `pytest tests/test_ibkr_bars.py`.
- **Follow-ups:** Optional Sentry ignore for `ib_async.wrapper`; IBKR open-ticker streaming for queue contention.
- **Related:** PROBLEM_LOG 2026-07-15 empty IBKR bars message.

## 2026-07-15 — Ticker speed, TOD RVOL, Sentry opt-in, IBC docs, _main thin

- **What:** REST ticker composes fast+slow builders, cache-only avg volume, shorter HTTP + IBKR snapshot budgets. 5-min RVOL uses a coarse ET TOD curve. Optional Sentry via `SENTRY_DSN`. IBC setup docs + example launcher. `scan_runners` / `scan_loop` / `routes/health` call leaf modules directly for functions.
- **Why:** User asked for the full next queue (ticker latency, cleanup, deferred deepeners).
- **Files touched:** `backend/ticker.py`, `hod_momo_metrics.py`, `observability.py`, `scan_runners.py`, `scan_loop.py`, `routes/health.py`, `docs/ibc-gateway-setup.md`, `scripts/start_gateway_ibc.ps1.example`.
- **How it works now:** `/api/ticker/{sym}` wall time ≈ max(IBKR snap ≤6s bridge, news/fund); avg volume never blocks. `typical_5min_volume` weights open/close when `HOD_MOMO_RVOL_5MIN_USE_TOD`. Sentry no-ops without DSN. IBC credentials stay under `%USERPROFILE%\.nova\ibc\`.
- **Verified by:** 341 pytest; smoke 10/10; ticker timing after IBKR budget change.
- **Follow-ups:** Tune TOD knots from live Warrior curves; frontend Sentry if desired.

## 2026-07-15 — Smoke: longer timeout for IBKR ticker detail

- **What:** `smoke_check.ps1` uses 25s for `/api/ticker/{sym}` and 20s for bars (other checks stay at 8s).
- **Why:** Overnight IBKR detail consistently took ~11–12s; 8s false-failed a healthy Gateway session.
- **How it works now:** Light endpoints stay snappy; ticker/bars get IBKR-realistic budgets.
- **Verified by:** Re-ran smoke after bump → 10/10 with Gateway connected.
- **Related:** Alpaca WS idle under ibkr (`ac6fc47`).

## 2026-07-15 — Alpaca WS idle under discovery=ibkr (no socket)

- **What:** `stream_loop` no longer opens Alpaca's market-data WebSocket when discovery is ibkr — it idles and polls every `ALPACA_WS_IDLE_POLL_SEC`. Closes mid-session if Settings flips to ibkr.
- **Why:** After gating HOD from Alpaca trades, the socket was still connecting (wasting Alpaca's one-WS slot and risking 406). Follow-up from dual-feed reliability track.
- **Files touched:** `backend/websocket.py`, `backend/constants.py`, `test_websocket_hod_feed.py`, `single-market-data-feed.mdc`.
- **How it works now:** ibkr → idle poll; alpaca → connect/subscribe as before. HOD/live prices under ibkr stay on IBKR table/detail ticks only.
- **Verified by:** pytest (idle loop test) + smoke_check with Gateway up.
- **Follow-ups:** TOD 5-min RVOL profile; optional Sentry.

## 2026-07-15 — Reliability: Alpaca WS no longer drives HOD under ibkr

- **What:** When `discovery=ibkr`, Alpaca trade messages are skipped before HOD `on_trade_update` / `l2.tape` ingest. L2/T&S hooks normalize symbol case; Trading / DepthAndTape remount depth with `key={symbol}`. HOD enrichment uses direct leaf imports (`universe`, `ibkr_bridge`, `scanner`, `fundamentals`) instead of `_main` function re-exports.
- **Why:** Remaining dual-feed hole after Phases 1–7 + A/C/D — Alpaca IEX prints still fed HOD while IBKR owned scanner prices.
- **Files touched:** `backend/websocket.py`, `backend/hod_momo_enrichment.py`, `frontend/src/ibkr/useIbkrDepth.ts`, `useIbkrTape.ts`, `TradingTab.tsx`, `DepthAndTape.tsx`.
- **How it works now:** IBKR table/detail ticks are the only HOD price path under ibkr (`alpaca_trades_drive_hod()`). Depth/tape compare `msg.symbol` to an uppercased hook key so case mismatch cannot drop or bleed updates.
- **Verified by:** pytest (incl. `test_websocket_hod_feed`) + vitest + production build; live API health.
- **Follow-ups:** Manual A→B→A rapid-switch checklist still human/agent-browser; optional stop Alpaca WS subscribe entirely under ibkr; TOD 5-min RVOL profile.

## 2026-07-14 — Tracks A/C/D: Warrior quote RVOL, cleanup, client-error intake

- **What:** Quote panel now shows live **5-min RVOL** + **volume in 5 min** from the shared HOD cum-vol buffer; HOD tab gets a **Running Up only** chip (strategy #12). Deduped `HealthStatus` to `types/health.ts`. Added `POST /api/client-errors` + `AppErrorBoundary` / window error reporting into `blast.log`. Fixed ticker WS route to import `ibkr.ticks` directly (was broken `_ibkr_ticks` on main).
- **Why:** User asked for remaining product-health tracks A (Warrior parity), C (cleanup), D (observability) after Phases 1–7 + smoke.
- **Files touched:** `backend/ticker.py`, `backend/hod_momo.py`, `backend/routes/ticker.py`, `backend/routes/client_errors.py`, `frontend/src/components/TickerDetailContent.tsx`, `HodMomoTab.tsx`, `AppErrorBoundary.tsx`, `App.tsx`, `main.tsx`, `types/health.ts`.
- **How it works now:** Opening a ticker seeds cum-vol and returns `rvol_5min` / `volume_in_5min` on REST + WS `initial`/`detail_update`. Running Up is still strategy #12 (`requires_hod=false`); the chip just filters the feed. Browser crashes POST to `/api/client-errors` (capped payload) when `CLIENT_ERRORS_ENABLED` / `CLIENT_ERROR_REPORT_ENABLED` are true.
- **Verified by:** 335 pytest + 60 vitest; `npm run build` clean; client-errors endpoint tests.
- **Follow-ups:** Optional Sentry; TOD 5-min RVOL profile; further `_main` re-export thinning; manual rapid-switch L2/T&S checklist.
- **Related:** Track B smoke SOP entry same day.

## 2026-07-14 — Live smoke SOP: fix smoke_check.ps1 + expand checklist

- **What:** Rewrote `scripts/smoke_check.ps1` to hit real routes (`/api/movers`, `/api/afterhours`, `/api/newss`, `/api/hod-momo/alerts`, `/api/config`) instead of dead `/api/gainers`/`/api/losers`. Loud WARN when discovery=ibkr but Gateway disconnected. Expanded `scripts/ibkr_smoke_checklist.md` so the automated script is the first step.
- **Why:** Track B of the post-Phase-7 plan — live reliability SOP. Old script would false-fail on missing endpoints and miss movers/HOD/AH.
- **How it works now:** From repo root with API on `:8000`, run `.\scripts\smoke_check.ps1`. Exit 1 only on hard FAILs; empty scanners outside session hours are WARN when IBKR is up.
- **Verified by:** Live run → **10 passed, 0 failed, 0 warnings** (IBKR connected live, discovery=ibkr, gappers 11, movers 50/50, AH 47, HOD 108, AAPL bars 10).
- **Follow-ups:** Manual UI rapid-switch L2/T&S still human-only (checklist section). Optional: agent prompt that runs this script after Gateway login.

## 2026-07-14 — Phase 7: App.tsx hits 150-line target (DashboardPage + scanner hooks)

- **What:** Extracted the dashboard monolith out of `App.tsx` into `pages/DashboardPage.tsx`, `components/ScannerTabPanels.tsx`, `hooks/useScannerData.ts`, `hooks/useSettingsForm.ts`, `utils/sortRows.ts`, and `types/health.ts`. Added `API_URL` to `constants.ts`. `App.tsx` is now **68 lines** (Stock View gate + Dashboard shell only).
- **Why:** Completes the frontend half of the product-health modularity plan after backend Phases 1–6. Constitution / file-size target for `App.tsx` was &lt;150 lines.
- **Files touched:** `frontend/src/App.tsx`, `pages/DashboardPage.tsx` (new), `components/ScannerTabPanels.tsx` (new), `hooks/useScannerData.ts` (new), `hooks/useSettingsForm.ts` (new), `utils/sortRows.ts` (new), `types/health.ts` (new), `constants.ts`.
- **How it works now:** `App` only routes Stock View vs dashboard. `DashboardPage` owns tabs/header/side panel and composes hooks. Scanner table bodies live in `ScannerTabPanels`. Live poll + history + IBKR price stream live in `useScannerData`.
- **Verified by:** `npm run build` (tsc + vite) clean.
- **Follow-ups:** Optionally dedupe local `HealthStatus` interfaces in EmptyState/CatalystsTable to use `types/health.ts`.

## 2026-07-14 — Phase 6: main.py hits 200-line target (ibkr_bridge / universe / health / lifespan)

- **What:** Extracted the last business-logic blocks from `main.py` into `ibkr_bridge.py` (IBKR run/enrich/table-reprice), `universe.py` (assets cache, avg volume, gapper enrich, HOD watch refresh), `health_status.py` (Alpaca health ping), and `app_lifespan.py` (startup/shutdown task wiring). `main.py` is now **199 lines**: cache state, tunables, re-exports, and FastAPI router wiring only.
- **Why:** Completes the product-health monolith-reduction plan (Phases 1–6). Constitution / file-size target for `main.py` was &lt;200 lines.
- **Files touched:** `backend/main.py`, `backend/ibkr_bridge.py` (new), `backend/universe.py` (new), `backend/health_status.py` (new), `backend/app_lifespan.py` (new).
- **How it works now:** Mutable scanner caches still live on `main` so attribute rebinding is globally visible. Domain modules mutate them via `import main as _m` / `_m()`. Lifespan and routers import helpers from the new modules (or legacy `_` aliases re-exported by `main` for `hod_momo_enrichment` / `ticker`).
- **Verified by:** 333 backend pytest tests pass; frontend production build clean.
- **Follow-ups:** Frontend `App.tsx` still exceeds its 150-line target (separate track). Optional: point callers at `universe` / `ibkr_bridge` directly and drop some `_main` re-exports.

## 2026-07-14 — Phase 5: extract scan runners, WS stream, and scan_loop from main.py

- **What:** Pulled the remaining scan/WS monolith out of `main.py` into three modules: `websocket.py` (Alpaca trade stream + cache overlays + `mark_resub`), `scan_runners.py` (discovery / focus / after-hours / movers), and `scan_loop.py` (news scan + mode-aware `scan_loop`). `main.py` shrinks from 1624 → ~648 lines and now keeps caches, IBKR table-reprice helpers, HOD universe refresh, lifespan, and router wiring.
- **Why:** Continuing the product-health monolith-reduction plan. Scan/WS logic was the largest remaining block and blocked further modular work.
- **Files touched:** `backend/main.py`, `backend/websocket.py` (new), `backend/scan_runners.py` (new), `backend/scan_loop.py` (new).
- **How it works now:** Lifespan still starts `_scan_loop` / `_ws_stream_loop` via re-exports from the new modules. Runners mutate scanner caches through a lazy `import main` accessor (same pattern as routes). WS subscription state lives in `websocket.py`; callers still use `main._ws_mark_resub`.
- **Verified by:** 333 backend pytest tests pass; frontend production build clean.
- **Follow-ups:** Further shrink possible by moving IBKR reprice helpers / health ping / assets cache out of `main.py` (Phase 6).

## 2026-07-14 — Phase 4: routes/hod_momo.py + routes/scan.py + routes/health.py extraction

- **What:** Extracted all REST + WebSocket route handlers that were inline in `main.py` into three new route modules: `routes/hod_momo.py` (HOD Momo + strategy WS), `routes/scan.py` (gappers / movers / afterhours / catalysts / history), and `routes/health.py` (health, config, mode). Added `reset_scan_caches()` helper to `main.py` so `update_config` can invalidate primitive caches from a separate module without the Python rebinding problem. `main.py` shrinks from 1934 → 1624 lines (17% reduction this phase).
- **Why:** Continuing the product-health monolith-reduction plan (Phases 1–4). Route handlers had zero business logic; extracting them is purely housekeeping.
- **Files touched:** `backend/main.py`, `backend/routes/hod_momo.py` (new), `backend/routes/scan.py` (new), `backend/routes/health.py` (new).
- **How it works now:** `main.py` includes four new routers (`_health_router`, `_scan_router`, `_hod_momo_router`, `_hod_momo_ws_router`) immediately after the existing router block. Route handlers access `main.py` globals via a `_m()` lazy-import accessor, same pattern as `routes/ticker.py`. `_strip_blocked` helper lives in `routes/scan.py` (single caller).
- **Verified by:** 333 backend pytest tests pass; frontend production build clean.

## 2026-07-14 — Phase 3: scanner.py extraction + _ensure_avg_volume refactor

- **What:** Extracted stateless scanner helpers from `main.py` into `backend/scanner.py` (`_fetch_snapshots`, `_check_news`, `_pick_prev_close`, `_is_common_stock`, `_gapper_meets_min_gap`, `_prune_gappers_below_min`, `_compute_gappers`, `fetch_avg_volume_batch`). `main.py` re-imports them so all existing `_main.*` callers work unchanged. `_ensure_avg_volume` now delegates the network fetch to `scanner.fetch_avg_volume_batch`. `main.py` shrinks from 2148 → 1934 lines.
- **Why:** Phase 3 of the product-health phased plan: reduce `main.py` monolith by extracting the scanner compute layer into a testable leaf module.
- **Files touched:** `backend/scanner.py` (new), `backend/main.py`.
- **How it works now:** `scanner.py` imports from `alpaca.py`, `constants.py`, `market.py` only — no circular deps at load time. Functions that need runtime values (`_MIN_GAP_PCT`, `_TOP_N`, `_SCAN_REQUIRE_TRADABLE`) use lazy `import main as _main`. Cache state (primitives like `_assets_cache_ts`) stays in `main.py` to avoid Python rebinding issues; `fetch_avg_volume_batch` accepts the caller-supplied cache dict.
- **Verified by:** `pytest backend/tests/ -x -q` → 333 passed; `npm run build` → clean.
- **Follow-ups:** Phase 4 — extract HOD Momo routes, WS/trade handler, scan-loop into separate modules.
- **Related:** CHANGELOG 2026-07-14 Phase 2.

## 2026-07-14 — Warrior library merge saved to Obsidian + Pinecone

- **What:** Documented the Warrior Trading downloads de-dupe/merge in Obsidian; upserted **588** new PDF chunks (ebook, ss-07, ss-16…20, Trader Rehab, Jess/Danny/Max grads, TOS layout PDFs) into Pinecone `nova-warrior-courses` / `warrior-slides`.
- **Why:** Persist what we learned from the member-dashboard sync so recall/ask use one library story (no parallel `docs/warrior-trading/` tree).
- **Files touched:** `knowledge/obsidian/01-Courses/Course-Index.md`, `knowledge/obsidian/01-Courses/Warrior-Trading/Local-Library-Inventory.md` (new), `knowledge/obsidian/03-Nova-Decisions/Warrior-Trading-Library-Merge.md` (new), `knowledge/obsidian/00-System/{How-Recall-Works,Memory-Router}.md`, `docs/README.md`, `.gitignore` (`docs/warrior-trading/`).
- **How it works now:** On-disk canon is `downloads/warrior-trading-{slides,resources,caption-notes,videos}/`. Obsidian holds inventory + merge decision. Pinecone searchable text includes the newly merged PDFs (prefer 1pp slides). Agents check the inventory before re-downloading.
- **Verified by:** `py recall.py --source obsidian` hits Library Merge + Inventory notes; `py recall.py --source pinecone` returns Trader Rehab PDF, free ebook float section, and new SS Chapter 13 (`ss-16`) chunks.
- **Related:** Prior merge of unique files into `downloads/` (same day).

## 2026-07-14 — Phase 2: alpaca.py extraction + blind-except triage

- **What:** Extracted Alpaca client helpers + discovery-provider state from `main.py` into a new leaf module `backend/alpaca.py`; removed duplicate copies in `bars.py`; updated 6 callsites (`ticker.py`, `bars.py`, `routes/strategy.py`, `strategy/setups_stream.py`, `hod_momo_enrichment.py`, `routes/news.py`) to import directly from `alpaca.py`. Fixed 5 blind `except Exception` blocks in `main.py` that swallowed errors without logging. `main.py` shrinks from 2229 → 2148 lines.
- **Why:** Phase 2 of the product-health phased plan: centralize Alpaca helpers to eliminate duplicate definitions, break the lazy-main-import pattern for pure helpers, and stop silently swallowing scan errors.
- **Files touched:** `backend/alpaca.py` (new), `backend/main.py`, `backend/ticker.py`, `backend/bars.py`, `backend/routes/strategy.py`, `backend/strategy/setups_stream.py`, `backend/hod_momo_enrichment.py`, `backend/routes/news.py`.
- **How it works now:** `_env`, `_alpaca_headers`, `_get_feed/_set_feed`, `_try_fallback_to_iex`, `_get_discovery_provider/_set_discovery_provider` all live in `alpaca.py` and own their own state (`_active_feed`, `_active_discovery_provider`). `main.py` re-exports them via `from alpaca import ...` so existing callers that do `import main as _main; _main._get_feed()` still work. Modules that can import directly (routes, setups_stream, ticker, bars, hod_momo_enrichment) now do so without the lazy-import boilerplate. Blind excepts in `_get_tradable_symbols`, `_fetch_snapshots`, `_check_news`, `_run_gainers_update`, and the catalyst scan now emit `logger.warning/exception` so failures surface in logs.
- **Verified by:** `pytest backend/tests/ -x -q` → 333 passed; `npm run build` → clean.
- **Follow-ups:** Phase 3 — extract scanner/news catalyst functions from `main.py`. Phase 4 — Warrior parity. Phase 5 — IBC/telemetry.
- **Related:** CHANGELOG 2026-07-14 Phase 1.

## 2026-07-14 — Phase 1 reliability: feed coherence + ticker module extraction

- **What:** Eliminated all remaining silent Alpaca-fallback paths under `discovery=ibkr`; extracted ticker domain (~440 lines) from `main.py` into `backend/ticker.py` + `backend/routes/ticker.py`; added live smoke checklist.
- **Why:** Product-health audit identified 3 open dual-feed surfaces (REST ticker, strategy bars, catalyst prices) and `main.py` at 2300+ lines well over the 200-line target.
- **Files touched:** `backend/main.py`, `backend/ticker.py` (new), `backend/routes/ticker.py` (new), `backend/routes/strategy.py`, `backend/strategy/setups_stream.py`, `backend/tests/test_ibkr_cache_priority.py`, `scripts/ibkr_smoke_checklist.md` (new), `scripts/smoke_check.ps1` (new).
- **How it works now:** (1) `GET /api/ticker/{symbol}` with IBKR discovery returns empty snapshot when IBKR is empty — no silent Alpaca price fallback. (2) Strategy endpoints and background setups scanner use `chart_bars.fetch_chart_bars` (discovery-aware) — IBKR failure surfaces as 503 not silent Alpaca. (3) Catalyst price/gap% comes from IBKR scanner cache when discovery=ibkr; Alpaca is still used for news headlines. (4) Ticker builders, caches, WS client registry, and routes live in `ticker.py` + `routes/ticker.py`; `main.py` imports `_ticker_ws_clients` + `_find_ibkr_cache_row` from ticker so all reprice/WS/HOD paths stay unchanged. `main.py` shrinks from ~2300 to ~1820 lines.
- **Verified by:** `pytest backend/tests/ -x -q` → 333 passed; `npm run build` → clean; `python -c "import main; import ticker"` → OK.
- **Follow-ups:** Phase 2 — extract `alpaca.py` client + continue blind-except triage. Phase 3 — scanner/news catalyst extraction. Phase 4 — Warrior parity (5-min RVOL, Running-Up). Phase 5 — IBC / telemetry.
- **Related:** PROBLEM_LOG 2026-07-14 (catalyst feed, strategy bars).

## 2026-07-14 — Faster scanner table prices (chunked IBKR snapshots)

- **What:** Gainers/Gappers/Losers table prices refresh in batches of 20 via rotating `reqTickersAsync` chunks, with a push after each chunk so the header age stays ~1s instead of 7–10s.
- **Why:** One 100-symbol snapshot blocked the UI until the whole batch finished; HOD seed symbols on the same path made it worse.
- **Files touched:** `backend/ibkr/reprice.py`, `backend/ibkr/discovery.py`, `backend/main.py` (`_table_reprice_symbols`), `backend/constants.py`, `frontend/src/constants.ts`, `backend/tests/test_ibkr_reprice.py`.
- **How it works now:** `table_reprice_loop` takes one chunk per 1Hz tick (size `IBKR_TABLE_REPRICE_CHUNK_SIZE`, timeout `IBKR_TABLE_REPRICE_CHUNK_TIMEOUT_SEC`), rotates across the scanner universe, and pushes `/ws/scanner` `price_patch` immediately. Scanner rows only — no HOD seeds on this hot path.
- **Verified by:** `pytest backend/tests/test_ibkr_reprice.py`; frontend build; API restart.
- **Related:** PROBLEM_LOG 2026-07-14 table reprice 7–10s stale.

## 2026-07-14 — HOD consolidates same-ticker bursts like Warrior "(N in Xs)"

- **What:** Same-ticker alerts in a short window merge into one feed row with `(3 in 5sec)` under the symbol (not a stack of duplicate tickers).
- **Why:** Each alert previously got its own consolidation deadline, so bursts never merged; UI also hid the badge under Time instead of Symbol.
- **Files touched:** `backend/hod_momo.py`; `collapseConsecutiveTickerAlerts.ts`; `HodMomoAlertRow.tsx`; `HodMomoTab.tsx`.
- **How it works now:** First fire in a burst opens a consolidation window; later same-ticker fires join it. Emit uses newest price + real span seconds. UI also collapses leftover consecutive rows within ~3× consolidation window.
- **Verified by:** pytest consolidation window test; vitest collapse helper; frontend build.

## 2026-07-14 — HOD Momo performance: full list + virtualize + debounce disk saves

- **What:** Live HOD feed keeps the **full** day's alerts in memory; the table virtualizes (~14 visible rows). Disk saves are rate-limited to ≤1 / 5s. Live WS alerts are batched; scroll updates are rAF-throttled. (An earlier UI/WS truncate-to-500 was reverted — users must still scroll to older alerts.)
- **Why:** 3k+ entries caused freezes from full-list disk writes + mounting every row. Truncating the list hid history; virtualization alone is the right DOM fix.
- **Files touched:** `backend/hod_momo.py`, `constants.py`, `main.py` WS init; `useHodMomoStream.ts`, `useWindowedRows.ts`, `HodMomoAlertTable.tsx`.
- **How it works now:** All alerts stay in the array / on disk. Only the scroll window mounts `<tr>` nodes. Persistence dirty-flags until the save interval elapses.
- **Verified by:** pytest persist + full WS payload tests; frontend build.
- **Related:** PROBLEM_LOG 2026-07-14 HOD freeze.

## 2026-07-14 — Hide IEX chrome on IBKR; HOD strategy chips wrap

- **What:** Header no longer shows the Alpaca IEX/SIP badge when discovery is IBKR. Removed the HOD "IEX Free Tier" banner. Strategy filter chips wrap (no horizontal scrollbar), show full names, are larger, and click toggles that strategy on/off.
- **Why:** With IBKR discovery, IEX badges were misleading; truncated chip strip forced horizontal scroll and made filters hard to disable.
- **Files touched:** `AppHeader.tsx`, `HodMomoTab.tsx`, `App.tsx`, `index.css`.
- **How it works now:** Feed badge is Alpaca-only. Strategy chips = visibility toggles on the main feed; Main feed / Debug switch panels.
- **Verified by:** frontend build.

## 2026-07-14 — HOD Momo table virtualized (~14-row window)

- **What:** HOD alert table no longer mounts every alert in the DOM. It shows a fixed ~14-row scroll viewport and only renders the visible slice (+ overscan).
- **Why:** 2k+ alerts were crashing/janking the UI; overflow alone still creates thousands of `<tr>` nodes. Windowing is the standard list pattern.
- **Files touched:** `frontend/src/hod_momo/HodMomoAlertTable.tsx`, `useWindowedRows.ts`, `HodMomoTab.tsx`, `constants.ts`, `index.css`.
- **How it works now:** `computeWindowSlice` + spacer rows keep scroll height correct while mounting ~20 rows. Sticky header; consolidation detail is a tooltip (no expanding second row that breaks fixed row height).
- **Verified by:** vitest window math; frontend build; UI scroll on HOD tab.
- **Follow-ups:** Apply same pattern to other multi-thousand scanners if needed.

## 2026-07-14 — After-hours HOD Momo uses IBKR gainers + IBKR volume RVOL

- **What:** After-hours discovery/focus now pulls IBKR top % gainers (not thin Alpaca IEX AH scans). HOD enrichment and table ticks recompute pace RVOL from IBKR cum volume. AH scan loop also refreshes Top Gainers; master RVOL gate uses `afterhours_min_rvol`.
- **Why:** Warrior AH HOD showed ATHE/TRT/XCUR while Nova showed DYAI spam / missed XCUR — AH tab had ~2 Alpaca rows and RVOL stuck at yfinance ~1.3x.
- **Files touched:** `backend/afterhours_discovery.py` (new), `main.py`, `hod_momo.py`, `hod_momo_enrichment.py`, tests.
- **How it works now:** During after-hours with `discovery=ibkr`, each scan cycle refreshes Top Gainers then reshapes them into the After Hours cache (same names Warrior watches). No Alpaca fallback. 1Hz IBKR ticks / enrichment set `ibkr_pace` RVOL. Master RVOL uses `afterhours_min_rvol`.
- **Verified by:** pytest afterhours + HOD engine tests; build + run app.
- **Related:** PROBLEM_LOG 2026-07-14 AH HOD mismatch.

## 2026-07-14 — HOD 5-min RVOL + Running Up Alert

- **What:** HOD table shows Warrior-style **RVOL (Daily)** and **RVOL (5m)**. New strategy **#12 Running Up Alert** fires on surge/RVOL without requiring a new HOD (`requires_hod=false`).
- **Why:** Follow-up after Warrior parity — Day Trade Dash shows both Rel Vol columns and a separate Running Up scanner.
- **Files touched:** `backend/hod_momo_metrics.py` (new), `hod_momo.py`, `hod_momo_enrichment.py`, `constants.py`, frontend HOD types/columns/settings, tests.
- **How it works now:** Cumulative day-volume samples → 5m delta ÷ (avg_daily / 144 bars). Master gate no longer owns HOD; each strategy’s `requires_hod` does. Schema v3 adds strategy 12.
- **Verified by:** `pytest` HOD suite 18 passed; frontend build.
- **Related:** commit after Warrior parity `94b8f6e`.

## 2026-07-14 — HOD Momo Warrior parity (pace RVOL, volume seeds, gates)

- **What:** Nova HOD Momo now closer to Warrior Day Trade Dash: pace RVOL (Daily Rate), IBKR volume-scanner seeds, Former Momo no longer fires on an empty list, master surge default off so float/RVOL strategies are not double-gated.
- **Why:** Side-by-side with Warrior showed different symbols (TSSI/YG/FRE vs CNEY spam); strategy names matched but gates/universe/RVOL did not.
- **Files touched:** `backend/market.py`, `hod_momo.py`, `hod_momo_universe.py`, `hod_momo_seed.py` (new), `hod_momo_enrichment.py`, `ibkr/discovery.py`, `constants.py`, `main.py`, `frontend/src/constants.ts`, tests.
- **How it works now:** Focus watch set = gappers/gainers/losers/AH + IBKR `HOT_BY_VOLUME` / `TOP_VOLUME_RATE` / `MOST_ACTIVE` seeds + open details. RVOL = today_vol / (avg × 04:00–16:00 ET elapsed frac). Master gate is HOD + min RVOL; squeeze strategies keep their own surge. Former Momo requires a non-empty list. Persisted configs with master surge 3.0 migrate to 0 once (schema v2). Table reprice includes HOD seeds (cap 100).
- **Verified by:** `pytest tests/test_hod_momo_engine.py tests/test_hod_momo_universe.py tests/test_pace_rvol.py` (14 passed).
- **Follow-ups:** True 5-min RVOL column; Running Up scanner (no HOD required); optional former-runner list import from Warrior history.
- **Related:** PROBLEM_LOG 2026-07-14 HOD Momo ≠ Warrior; closes CHANGELOG follow-up on Daily Rate RVOL.

## 2026-07-14 — L2 | T&S side-by-side + bid/ask tape colors

- **What:** Level 2 and Time & Sales sit side-by-side in one full-width row again. Each T&S print is classified against the open symbol’s live BBO and highlighted: green ASK (at/above ask), red BID (at/below bid), black MID (inside spread).
- **Why:** User asked for side-by-side panels (not stacked rows) and aggressor-side coloring; prior uptick/downtick coloring did not answer bid vs ask.
- **Files touched:** `backend/ibkr/tape_side.py`, `backend/ibkr/tape_stream.py`, `backend/tests/test_ibkr_tape_side.py`, `backend/tests/test_ibkr_tape_stream.py`, `frontend/src/ibkr/DepthAndTape.tsx`, `frontend/src/ibkr/TimeSalesPanel.tsx`, `frontend/src/ibkr/useIbkrTape.ts`, `frontend/src/constants.ts`, `frontend/src/index.css`.
- **How it works now:** On each AllLast print, `tape_stream` reads `depth.current_book(symbol)` top-of-book and sets `side`/`bid`/`ask` on the WS payload. UI uses row block highlights + `ASK`/`BID`/`MID` labels (not color-only). Grid stacks to one column below 560px.
- **Verified by:** `pytest tests/test_ibkr_tape_side.py tests/test_ibkr_tape_stream.py`; frontend build; browser check of layout + colors.
- **Follow-ups:** (none for RVOL — see Warrior parity entry above).

## 2026-07-14 — HOD Momo empty: Ross focus universe + IBKR ticks

- **What:** HOD Momo now watches the Top Gainer/Gapper/Loser shortlist (Ross-style) instead of subscribing Alpaca IEX to ~6k symbols. IBKR 1Hz table reprice also feeds `on_trade_update` when discovery=ibkr. Alpaca WS subscribe/unsubscribe is chunked. Unit tests cover universe building and alert firing.
- **Why:** Tab stayed empty (`total_trades_seen=0`) despite enriched snaps — free IEX cannot deliver a usable tape for a full-universe subscribe. Project decision note already required shrinking under IBKR.
- **Files touched:** `backend/hod_momo_universe.py` (new), `backend/main.py`, `backend/constants.py`, `backend/hod_momo.py`, `backend/tests/test_hod_momo_universe.py`, `backend/tests/test_hod_momo_engine.py`, `frontend/src/constants.ts`, `frontend/src/hod_momo/HodMomoTab.tsx`.
- **How it works now:** `HOD_MOMO_UNIVERSE_MODE=focus` (default) rebuilds watch set from scanner caches every 5s. Enrichment follows that set. IBKR table snapshots call `hod_momo.on_trade_update`. Debug counters expose `watch_universe_size` / `watch_universe_mode`.
- **Verified by:** `pytest tests/test_hod_momo_universe.py tests/test_hod_momo_engine.py`; live Alpaca IEX probe confirmed trades on a 5-symbol shortlist; post-reload debug counters.
- **Related:** PROBLEM_LOG 2026-07-14 HOD Momo empty / IEX 6k subscribe.

## 2026-07-14 — Level 2 / Time & Sales full-width stack + tape WS live

- **What:** Level 2 and Time & Sales now each occupy a full-width row (stacked like Watchlist) instead of a cramped side-by-side pair inside the quote column. Empty T&S was fixed: the running API had not loaded `/ws/ibkr/tape/{symbol}` (WS 403), so the panel never received prints; after restart prints flow, and IB tick-by-tick errors surface in the panel.
- **Why:** User reported cramped L2 beside an empty T&S under CNEY.
- **Files touched:** `frontend/src/ibkr/DepthAndTape.tsx`, `frontend/src/components/TickerDetailContent.tsx`, `frontend/src/ibkr/TickerTradeSideColumn.tsx`, `frontend/src/index.css`, `backend/ibkr/tape_stream.py`, `backend/routes/trading.py`, `backend/constants.py`, `backend/tests/test_ibkr_tape_stream.py`.
- **How it works now:** `DepthAndTape` is always a vertical stack. In the side panel, the depth stack sits full-width under Watchlist (not inside the half-width quote column). Tape uses `reqTickByTickData(AllLast)`; subscription errors (10089/10189/354) are pushed to the WS as `type:error`.
- **Verified by:** `pytest tests/test_ibkr_tape_stream.py`; live WS probe received CNEY prints; `npm run build`.
- **Related:** PROBLEM_LOG 2026-07-14 empty Time & Sales / tape 403.

## 2026-07-14 — Live Time & Sales panel next to Level 2 (IBKR AllLast)

- **What:** Added a Webull-style Time & Sales tape beside Level 2 for the open symbol, fed by IBKR `reqTickByTickData(AllLast)` — not Alpaca. Rows coloured green/red vs prior print, newest-first, capped at 200 rows. Appears wherever `DepthLadder` was: side panel quote view and trading side column.
- **Why:** User request — match the Webull T&S experience beside L2; IBKR is the single data source.
- **Files touched:** `backend/ibkr/tape_stream.py` (new), `backend/routes/trading.py` (new `/ws/ibkr/tape/{symbol}` endpoint), `backend/constants.py` (`TAPE_SOURCE_IBKR`, `IBKR_TAPE_TICK_TYPE`, `TAPE_UI_MAX_ROWS`), `frontend/src/constants.ts`, `frontend/src/ibkr/useIbkrTape.ts` (new), `frontend/src/ibkr/TimeSalesPanel.tsx` (new), `frontend/src/ibkr/DepthAndTape.tsx` (new), `frontend/src/components/TickerDetailContent.tsx`, `frontend/src/ibkr/TickerTradeSideColumn.tsx`, `frontend/src/utils/dataSourceMap.ts`, `frontend/src/index.css`, `.cursor/rules/single-market-data-feed.mdc`.
- **How it works now:** `tape_stream.py` manages refcounted `reqTickByTickData` subscriptions (15s resubscribe guard). WS route `ws_tape` follows identical viewer pattern as `ws_depth`. `useIbkrTape` clears prints on symbol change and gates all messages on `msg.symbol === symbol`. `DepthAndTape` wraps both panels side-by-side (CSS flex, stacks below 600px). `dataSourceMap` now includes a "Time & Sales" row with IBKR attribution.
- **Verified by:** TypeScript build check; visual inspection of component structure.

## 2026-07-14 — Scanner table 1Hz IBKR snapshots (fix 10–12s freeze)

- **What:** Independent `table_reprice_loop` refreshes Gainers/Losers/Gappers prices every 1s via `reqTickersAsync` (not streaming MD). `/ws/scanner` pushes patches; UI flashes price changes and shows yellow “stale · updated Xs ago” when a tick is late. Open quote panel still uses ticks + L2.
- **Why:** Header showed “updated 10–12s ago” because table reprice was nested after the full movers scan (20–90s), so prices froze during scans.
- **Files touched:** `backend/ibkr/reprice.py`, `discovery.py` (contract cache), `scanner_push.py`, `main.py`, `constants.py`, `useScannerPriceStream.ts`, `ScannerTable`/`AppHeader`/`App.tsx`, CSS, rule.
- **How it works now:** Full scan still rebuilds membership on its own cadence; price freshness is a separate 1Hz loop + WS. Skip-if-busy emits stale heartbeats instead of hiding lag.
- **Verified by:** pytest `test_ibkr_reprice`; frontend build; browser header age + NXTC table ticks.
- **Related:** PROBLEM_LOG 2026-07-14 table reprice starvation.

## 2026-07-14 — Quote panel symbol gate + IBKR-only chart bars (no silent Alpaca)

- **What:** Fixed Level 2 showing a previous ticker’s book under a new quote (e.g. MVO @ $0.80 with NXTC ~$7 depth). Cleared detail on symbol change, gated SidePanel/Stock View on `detail.symbol === selectedSymbol`, bound DepthLadder to `selectedSymbol` with WS identity/`msg.symbol` checks. When discovery=ibkr, `chart_bars` no longer falls back to Alpaca — fails with HTTP 503. Added `.cursor/rules/single-market-data-feed.mdc`. Listing section retitled as Alpaca metadata (not a price feed).
- **Why:** User cannot tolerate cross-symbol L2/quote desync or unaware Alpaca price fallback while IBKR is the discovery feed.
- **Files touched:** `useTickerStream.ts`, `useIbkrDepth.ts`, `depthBookGuards.ts`, `SidePanel.tsx`, `TickerDetailContent.tsx`, `StockViewPage.tsx`, `chart_bars.py`, `main.py` (`trade_update.symbol`), `dataSourceMap.ts`, `constants.ts`, rule + tests + logs.
- **How it works now:** Quote panel surfaces only paint when selection and detail agree. L2 ignores stale sockets and wrong symbols. IBKR mode chart bars are IBKR-only; Alpaca bars only when discovery=alpaca. Attribution copy says “no Alpaca fallback.”
- **Verified by:** pytest `test_ibkr_bars`; vitest dataSourceMap + depthBookGuards; frontend build + browser switch NXTC→MVO.
- **Related:** PROBLEM_LOG 2026-07-14 Level 2 / quote desync; single-market-data-feed rule.

## 2026-07-14 — Chart data/live path: IBKR historical bars + streaming last-price ticks

- **What:** When `discovery_provider=ibkr`, `/api/ticker/{symbol}/bars` now pulls OHLCV from IBKR `reqHistoricalData` (same JSON shape as Alpaca). Opening a ticker-detail WebSocket also starts an IBKR `reqMktData` last-price stream so `trade_update` (quote panel + forming chart candle) can move on real ticks, not only the 3s snapshot reprice. Reprice still runs as a volume/prev_close backstop, but broadcasts no longer go through the IB `run_coro` bridge.
- **Why:** User needed the deferred "data/live path" fix — chart looked wrong/sparse on Alpaca IEX while live price was IBKR, and updates were not tick-fast.
- **Files touched:** `backend/ibkr/bars.py`, `backend/ibkr/ticks.py`, `backend/chart_bars.py`, `backend/ibkr/reprice.py`, `backend/main.py`, `backend/constants.py`, `backend/tests/test_ibkr_bars.py`, `backend/tests/test_ibkr_reprice.py`, `frontend/src/constants.ts` (`CHART_REFETCH_SEC`), `frontend/src/utils/dataSourceMap.ts`.
- **How it works now:** Bars facade prefers IBKR when Gateway is connected (Alpaca fallback otherwise). Detail WS subscribe/unsubscribe refcounts tick streams. Active names see sub-second `trade_update`s; flat names still get ~3s reprice heartbeats. Chart poll intervals were relaxed (1Min 10s→30s) because ticks own the live candle.
- **Verified by:** pytest `test_ibkr_bars` + `test_ibkr_reprice`; `/api/ticker/MVO/bars` returns `source=ibkr` with 500 bars; NXTC WS saw 36 `trade_update`s / 20s with ~0.2s gaps; frontend build + dataSourceMap tests.
- **Follow-ups:** Strategy setup routes still call Alpaca `bars.fetch_bars` directly — can switch to `chart_bars` later.

## 2026-07-14 — Integrate lightweight-charts-indicators (RSI + MACD panes)

- **What:** Chart toolbar now has RSI / MACD toggles. Enabling either opens a synced oscillator pane under the price chart. Indicator math comes from `lightweight-charts-indicators` (+ `oakscriptjs` peer), not hand-rolled formulas.
- **Why:** User asked to adopt existing Lightweight Charts ecosystem tech for indicators (RSI/MACD now; more later) instead of reinventing them.
- **Files touched:** `frontend/package.json` / lockfile (`lightweight-charts-indicators`, `oakscriptjs`), `frontend/src/constants.ts`, `frontend/src/chartIndicators.ts` (+ test), `frontend/src/components/TickerChartOscillatorPanes.tsx`, `frontend/src/components/TickerChartControls.tsx`, `frontend/src/TickerChart.tsx`, `frontend/src/index.css`.
- **How it works now:** On each bars fetch, Nova stores OHLC as indicator bars. Toggling RSI/MACD mounts a separate lightweight-charts pane that calls `RSI.calculate` / `MACD.calculate` and syncs the visible time range with the main chart. More indicators from the same library can be added by extending `CHART_INDICATORS` + a pane branch — no need to rewrite TA math.
- **Verified by:** `tsc --noEmit`; Vitest for adapters; browser toggle RSI/MACD on quote-panel chart.
- **Follow-ups:** Broader indicator picker (446 available); live tick recalculation of oscillators (currently refreshes with bar polls).

## 2026-07-14 — Restore "Gainers" tab name with a Losers sub-tab (was merged into unlabeled "Movers")

- **What:** The tab formerly labeled "Movers" is now labeled "Gainers" and has "Gainers"/"Losers" sub-tabs (mirroring the Gappers tab's "All Gaps"/"Small Cap" sub-tabs), instead of silently concatenating gainers+losers into one unlabeled combined table.
- **Why:** User remembered a "Gainers" view, couldn't find it, and didn't recognize "Movers" — a prior change (commit `94e7388`) had merged the separate Gainers/Losers tabs into one "Movers" tab without the user's buy-in on the rename. Confirmed via `AskQuestion` that the user wanted the Gainers name back with Losers as a distinct sub-tab (not dropped, not silently merged).
- **Files touched:** `frontend/src/components/TabNav.tsx` (label only — internal tab id/route stays `movers`, no backend or history-endpoint changes), `frontend/src/App.tsx` (split single `movers` state into `gainers`/`losers`, added `moverSubTab` state + sub-tab bar), `frontend/src/components/EmptyState.tsx` (new optional `emptyLabel` prop so the empty message says "No losers…" on that sub-tab instead of always "No gainers…").
- **How it works now:** `/api/movers` is unchanged (still returns `{gainers, losers}` from `_gainer_cache`/`_loser_cache`, refreshing continuously through market hours, never freezing — this is exactly the "gappers freeze at the open, gainers don't" behavior the user described, and it already worked correctly before this change). The frontend just stopped hiding that structure: `gainers` and `losers` are separate arrays in state again, rendered via a sub-tab toggle under one top-level "Gainers" tab, both using the same `ScannerTable` component Gappers uses (same columns, same look, as requested).
- **Verified by:** `npm run build` (clean, no type errors); `agent-browser` — fresh session, clicked into the Gainers tab (50 rows, all positive % change) and the Losers sub-tab (50 rows, all negative % change), confirmed no console errors on a clean reload.
- **Related:** Gappers tab's existing "freeze after market open" behavior was confirmed unchanged/correct and required no code change (already implemented — see `_scan_loop`'s premarket-only discovery/focus scan calls in `backend/main.py`).

## 2026-07-14 — Decouple ticker-detail repricing from the scan loop; add Ruff + a regression test for the bug class

- **What:** The ticker-detail panel's fast price refresh (IBKR provider) is now its own independent `asyncio` task on a flat `IBKR_REPRICE_INTERVAL_SEC` timer, instead of being nested inside the main scan loop's sleep — so it can no longer be starved by a slow `_run_gainers_update()` scan. The reprice logic moved out of `main.py` into a new `backend/ibkr/reprice.py` module. Also added a Ruff config (`backend/ruff.toml`, `backend/requirements-dev.txt`) and a new test file (`backend/tests/test_ibkr_reprice.py`) targeting the exact bug classes hit this session (silent exception swallowing, reprice starvation).
- **Why:** User reported the quote/fundamentals panel wasn't live while Level 2 was; root cause traced to the detail-symbol reprice being nested behind a slow full IBKR movers scan every iteration. Separately, the user asked for tooling that would have caught this class of mistake earlier.
- **Files touched:** `backend/main.py`, `backend/ibkr/reprice.py` (new), `backend/tests/test_ibkr_reprice.py` (new), `backend/ruff.toml` (new), `backend/requirements-dev.txt` (new).
- **How it works now:** `main.py`'s lifespan starts `detail_reprice_loop(...)` as its own task alongside `_scan_loop`; it sleeps `IBKR_REPRICE_INTERVAL_SEC`, then reprices only the 0-2 symbols with an open ticker-detail WS via `ibkr.reprice.reprice_detail_symbols`, independent of whatever the scan loop is doing. `_scan_loop`'s `_sleep_with_ibkr_reprice` still calls `_reprice_ibkr_caches` (now a thin wrapper around `ibkr.reprice.reprice_table_caches`) for the big gapper/gainer/loser table — that one is still best-effort and can lag behind a slow scan, which is acceptable since nothing depends on it for low latency. Running `ruff check` under `backend/ruff.toml` surfaces 77 pre-existing bare/blind `except Exception:` blocks in `main.py` (mostly silent, un-logged) — these were **not** mass-fixed in this change (out of scope, needs individual review), but the tool is now wired up and configured specifically to catch this bug class going forward.
- **Verified by:** `py -3 -m pytest` — 290/290 backend tests pass, including 5 new tests in `test_ibkr_reprice.py`. Manual WS listen against `/ws/ticker/{symbol}` before/after: `trade_update` cadence went from ~30-90s gaps (blocked behind the movers scan) to a few seconds under real IBKR load (residual jitter is IB API request queueing under concurrent L2/depth + movers traffic, not the scan-loop starvation this fix targets). `py -3 -m ruff check backend` runs clean against the new module.
- **Follow-ups:** Consider a streaming `reqMktData` subscription per open detail symbol instead of polling `snapshot_quotes()` every 3s, to remove the remaining IBKR-request-queueing jitter entirely. The 77 pre-existing blind-except sites in `main.py` should be triaged and fixed incrementally (log during self-annealing whenever a task happens to touch one).
- **Related:** PROBLEM_LOG 2026-07-14 "Detail panel updates every ~30s instead of every tick" and "Agent shell env var (NOVA_API_RELOAD) silently survived across an entire session."

## 2026-07-14 — Unify IBKR quote panel with scanner (same price / gap %)

- **What:** Ticker detail WebSocket Phase 1 and quote UI now use the same IBKR cache row as the gappers/movers table when `discovery_provider=ibkr`. Quote shows one live price + gap % vs IBKR `prev_close` (no Alpaca Webull dual-line split). Live `trade_update` ticks also carry `prev_close` and patch React state so % stays aligned.
- **Why:** NXTC showed scanner $9.02 / +313.60% while the quote panel showed Alpaca session 2.28 / +16.92% and Pre: +295.46% — three feeds, two `prev_close` bases. Not a React render bug; Phase 1 still called `_fetch_ticker_snapshot` (Alpaca).
- **Files touched:** `backend/main.py` (`_build_ticker_fast`, `_fetch_ticker_snapshot_ibkr`, `_broadcast_trade_update`, `_reprice_ibkr_caches`), `frontend/src/hooks/useTickerStream.ts`, `frontend/src/components/TickerDetailContent.tsx`, `frontend/src/pages/StockViewPage.tsx`, `frontend/src/types/ticker.ts`.
- **How it works now:** With IBKR discovery, WS `initial` uses `_fetch_ticker_snapshot_ibkr` (mirror cache row). `session_close` = prior close (not live last). UI: single line live vs `prev_close`. Reprice every `IBKR_REPRICE_INTERVAL_SEC` pushes price + `prev_close`. Level 2 bid/ask can bracket last (normal); last need not equal bid or ask.
- **Verified by:** Frontend build; backend import check; manual NXTC click after restart.
- **Related:** PROBLEM_LOG 2026-07-14 quote/scanner mismatch.

## 2026-07-14 — Premarket IBKR gappers fall back to TOP_PERC_GAIN; loud Gateway-login rule

- **What:** IBKR gapper discovery no longer relies solely on `TOP_OPEN_PERC_GAIN` (empty before RTH open). When that scan returns 0 symbols, it falls back to `TOP_PERC_GAIN` and keeps the ≥10% gap filter. Added `.cursor/rules/ibkr-gateway-login-warning.mdc` so agents must loudly tell the user when Gateway needs manual login/2FA instead of silently waiting.
- **Why:** User logged into Gateway (mobile 2FA) but gappers stayed empty; live probe showed `TOP_OPEN_PERC_GAIN` → 0 rows while `TOP_PERC_GAIN` returned real premarket gaps (NXTC, MVO, etc.). Earlier session also failed to surface "look at Gateway and log in" clearly enough.
- **Files touched:** `backend/ibkr/discovery.py`, `.cursor/rules/ibkr-gateway-login-warning.mdc`, `PROBLEM_LOG.md`.
- **How it works now:** `get_gappers()` tries open-gap scan first, then last-vs-prior-close scan in premarket/pre-open. Scanner row counts are logged. Agents must warn loudly on IBKR disconnect (see the new always-apply rule).
- **Verified by:** Live IB scanner probe on port 4001; backend restarted with fix; waiting on `/api/gappers` population after reconnect.
- **Follow-ups:** Optional IBC auto-login (local secrets only, never in git) for Gateway credentials + 2FA handoff.
- **Related:** `PROBLEM_LOG.md` 2026-07-14 premarket TOP_OPEN empty.

## 2026-07-14 — Empty scanner now names IB Gateway disconnect; Gateway launched for login

- **What:** When `discovery_provider=ibkr` but IB Gateway is offline/not logged in, Gappers/Movers/After Hours no longer show the misleading "No gappers with a gap of at least 10% yet — scan running…" copy. They show `EMPTY_IBKR_DISCONNECTED` instead. Also launched the installed IB Gateway (`C:\Jts\ibgateway\1045\ibgateway.exe`) and brought its login window forward so the user can complete live login + 2FA; Nova keeps retrying `127.0.0.1:4001` every ~10s.
- **Why:** Empty gappers were caused by Gateway not being logged in (no API socket), not by a lack of real gaps. The old empty state hid that.
- **Files touched:** `frontend/src/components/EmptyState.tsx`, `frontend/src/constants.ts`, `frontend/src/App.tsx`, `PROBLEM_LOG.md`.
- **How it works now:** `EmptyState` polls `useIbkrStatus()`. If `discoveryProvider === 'ibkr'` and `!connected`, it renders the IBKR-down message before any "no gaps yet" copy. Once Gateway login opens port 4001, the existing `ibkr.client` reconnect loop connects and the next discovery scan fills gappers.
- **Verified by:** Confirmed Gateway process up with title "IBKR Gateway" but zero sockets until login; `/api/ibkr/status` still `connected:false`; `tsc --noEmit` clean on EmptyState changes. Live gapper population still blocked on user Gateway login (cannot automate IBKR Mobile 2FA).
- **Follow-ups:** After login, confirm `/api/gappers` populates; optional future: surface the same IBKR-down state in the header badge, not only the empty table.
- **Related:** `PROBLEM_LOG.md` 2026-07-14 (empty gappers / Immersed port 40001 red herring).

## 2026-07-14 — Diagnosed empty gappers (IB Gateway disconnected) and documented every Alpaca dependency before any removal

- **What:** Diagnosed why gappers/movers/after-hours showed empty despite real gaps existing: `.env` has `NOVA_DISCOVERY_PROVIDER='ibkr'` (scanner already sourced from IBKR, not Alpaca), but IB Gateway wasn't running on the machine, so `_run_ibkr()`'s try/except in `backend/main.py` silently degraded every scan to an empty list — by design (`_run_ibkr` "so callers degrade like an empty scan"), but with no visible signal that the real cause was connectivity, not a lack of gaps. Also added a full written inventory of everywhere Alpaca is used today, since the user wants to move off Alpaca entirely (too slow on the free IEX feed) but a same-day full removal would break News, Charts, RVOL, After-Hours, HOD Momo's real-time feed, and L2 tape — none of which have an IBKR replacement yet.
- **Why:** User reported real gappers weren't showing up; root-cause investigation showed a disconnected IB Gateway, not a code bug. Follow-up ask was to fully remove Alpaca from the active codebase and preserve how it worked in an MD file for later reconstruction — but before touching any code, every Alpaca dependency needed to be mapped so removal doesn't silently break features that have no IBKR equivalent.
- **Files touched:** `knowledge/obsidian/03-Nova-Decisions/Alpaca-Integration-Reference.md` (new), `PROBLEM_LOG.md`.
- **How it works now:** No code changed. `knowledge/obsidian/03-Nova-Decisions/Alpaca-Integration-Reference.md` is now the single reference for every Alpaca REST/WS call in `backend/main.py` and `backend/bars.py`, every `.env`/`constants.py` Alpaca key, and every frontend file that references Alpaca — each classified as (A) already replaced by IBKR, (B) IBKR-partial, or (C) Alpaca-only with no replacement. Decision made this session: **phased rebuild** — Alpaca stays wired up exactly as-is for News, Charts, RVOL, After-Hours, HOD Momo's feed, and L2 tape; each gets an IBKR-native (or other) replacement built and verified before its Alpaca code path is touched. Charts/bars via IB `reqHistoricalData` is the next concrete target (most tractable, no external blocker). News (no free IBKR news feed) and HOD Momo's ~6,000-symbol real-time streaming (IBKR market-data-line limits) are flagged for a separate conversation, not treated as drop-in rebuilds.
- **Verified by:** Confirmed root cause via `GET /api/ibkr/status` (`connected: false`), no `ibgateway`/`tws`/`javaw` process running, and repeating `ConnectionRefusedError` to `127.0.0.1:4001` in `backend/logs/blast.log`. Two `explore` subagents independently mapped every Alpaca call site and every existing IBKR alternative to build the classification table in the new doc.
- **Follow-ups:** User needs to log into IB Gateway (live session, matches `IBKR_GATEWAY_MODE=live` → port 4001) for scanning to resume; once connected, verify `/api/gappers`/`/api/movers` populate from IBKR. First rebuild target: charts/bars on IBKR historical data.
- **Related:** `PROBLEM_LOG.md` 2026-07-14, `knowledge/obsidian/03-Nova-Decisions/Scanner-Provider-IBKR-Primary.md`, `knowledge/obsidian/03-Nova-Decisions/IBKR-Orders-Locked-On-Live-Gateway.md`.

## 2026-07-14 — News headlines in the quote panel now render as a horizontal, clickable strip

- **What:** The "News Headline" list under the chart in the quote panel (`NewsHeadlineSection`) now lays out headlines as a horizontally-scrolling row of clickable cards instead of a vertical, height-limited list with a "More ▼" toggle. Each card shows the full headline (up to 3 lines, clipped), the freshness dot, source, and time-ago, and the whole card is an `<a target="_blank">` to the article — clicking it opens the source article in a new tab. All headlines render (no more slicing to 3 + expand); horizontal scroll handles overflow instead.
- **Why:** User reported the quote panel had no visible place to see news titles and click through to the article, and recalled the news area used to be laid out horizontally ("It was horizontal, didn't we? Just have it, bro."). The vertical list + pagination design from the earlier rules-first decision-layer work buried headlines and didn't match that expectation.
- **Files touched:** `frontend/src/components/NewsHeadlineSection.tsx`, `frontend/src/index.css`.
- **How it works now:** `NewsHeadlineSection` still renders `NewsImpactPanel` first (the rules-first verdict), then — only when `news.length > 0` — a `.cq-news-list` flex row (`overflow-x: auto`) of `.cq-news-chip` anchor cards. Old vertical-list CSS (`.cq-news-item`, `.cq-news-icon`, `.cq-news-main`, `.cq-news-link`, `.cq-news-more`) was removed since it's now dead; `.cq-news-source` / `.cq-news-time` were kept and repurposed inside the new chip's meta row. If a ticker genuinely has zero news articles right now (e.g. QTTB during the current market-closed window — confirmed via `GET /api/ticker/QTTB` returning `news: []`), only the impact panel's "No news to evaluate" message shows, matching existing rules-first behavior — this is expected, not a regression.
- **Verified by:** `npx tsc --noEmit` and `npm run build` clean. Live-rendered the exact compiled markup/CSS in a standalone preview page via `agent-browser` with 5 mock headlines of varying length/source/age to confirm the horizontal scroll strip, line-clamping, and freshness dots render correctly; then loaded the real app and looked up QTTB to confirm the impact panel still renders with no console errors when there's genuinely no news.
- **Follow-ups:** None — will look right the next time any ticker actually has news articles once the market re-opens / catalyst scan finds one.

## 2026-07-14 — Quote panel Block button could never unblock; block now asks for confirmation

- **What:** The quote panel's "Block" button (HOD Momo blocklist) is fixed and now confirms before blocking. Previously, clicking it once set local `blocked` state to `true` and the button became permanently `disabled` — there was no way to undo it from the UI short of reloading a different symbol. It also always assumed `blocked=false` on symbol change instead of checking the real blocklist, so a symbol that was already blocked showed "Block" (not "Blocked"). Now the button fetches the real blocklist state per symbol, reads "Block" or "Unblock" accordingly, and clicking always toggles the real state via the existing `POST`/`DELETE /api/hod-momo/blocklist` endpoints. Blocking now requires confirming a `window.confirm()` dialog explaining the effect; unblocking is immediate (restorative, not destructive).
- **Why:** User accidentally blocked a ticker (LVLU), tried to click the button again to undo it, and nothing happened — the button was inert once blocked. They asked for a confirmation step before every block so an accidental click doesn't happen again.
- **Files touched:** `frontend/src/components/TickerDetailContent.tsx`, `frontend/src/index.css`.
- **How it works now:** `TickerDetailContent` now `GET /api/hod-momo/blocklist` on mount/symbol-change and sets `blocked = symbols.includes(detail.symbol)` — no more assuming unblocked. The single `onToggleBlock()` handler branches: if already blocked, it `DELETE`s immediately (mirrors the existing Settings → Blocklist panel's unblock-without-confirm pattern); if not blocked, it shows `window.confirm(...)` (same pattern already used in `TickerTradeActionBar.tsx`/`ExecutorPanel.tsx`) and only `POST`s if the user accepts. The button is never `disabled` anymore — `.cq-block-btn--blocked` in `index.css` changed from a dimmed/inert look to a full-opacity red "currently blocked" state that turns green on hover to hint it will unblock.
- **Verified by:** Live-clicked through the running dev app (`http://127.0.0.1:5173`) with `agent-browser`, confirming against the actual backend blocklist (`GET /api/hod-momo/blocklist`) at each step: LVLU (already blocked) showed "Unblock"; clicking it removed LVLU from the backend list immediately and flipped the button to "Block"; clicking "Block" raised the confirm dialog; dismissing it left the backend list unchanged; accepting it re-added LVLU and flipped the button back to "Unblock". `npx tsc --noEmit`, `eslint` on the file, `vitest run`, and `npm run build` all clean — the fix also resolved a pre-existing `react-hooks/set-state-in-effect` lint violation on this file since the state update now happens inside the fetch's `.then()`, not synchronously in the effect body.
- **Follow-ups:** No automated component test added — this repo has no React Testing Library harness yet (all current frontend tests are pure-function unit tests); verified via live browser + backend state checks instead.
- **Related:** `PROBLEM_LOG.md` 2026-07-14 "Block button in quote panel could not be undone".

## 2026-07-14 — Catalysts tab loses "Experimental" badge; news source now shown everywhere

- **What:** Removed the yellow "Experimental" badge from the Catalysts tab button. The Catalysts tab's headline cell now shows the article's literal source name under the headline and its impact badge is a clickable toggle that expands the full `NewsImpactPanel` inline (same component the quote panel uses) instead of only exposing a hover tooltip. `NewsImpactPanel` (used by both the Catalysts tab and the ticker-detail "quote panel") now renders the headline itself as a clickable link and the Source row shows the literal source name (e.g. "Business Wire") alongside its tier, not just the tier bucket. The quote panel's raw news list also shows each article's source under its headline.
- **Why:** User asked to remove the "Experimental" label and wanted the full news picture — including where each headline came from — visible and laid out the same way in both the Catalysts tab and the quote panel, not hidden in a tooltip.
- **Files touched:** `frontend/src/components/TabNav.tsx`, `frontend/src/components/CatalystsTable.tsx`, `frontend/src/components/NewsImpactPanel.tsx`, `frontend/src/components/NewsHeadlineSection.tsx`, `frontend/src/constants.ts`, `frontend/src/index.css`, `frontend/src/types/newsImpact.ts`, `frontend/src/types/catalyst.ts`, `backend/main.py`, `backend/news/enrich.py`, `backend/news/sources.py`, `backend/news/impact.py`, `backend/routes/news.py`, `backend/tests/test_news_impact.py`.
- **How it works now:** While fixing this, found and fixed a real bug (see `PROBLEM_LOG.md` 2026-07-14): the Catalysts scanner (`_run_news_catalyst_scan` in `main.py`) never captured the Alpaca article's `source` field, and `enrich_catalyst_row`/`_gather_context`'s cache-fallback path hardcoded `"source": ""` — so every catalyst row's `source_tier` silently fell back to `unknown`/`none` regardless of the real publisher. Both now carry the real `source` string end to end (`catalyst_source` field on catalyst rows). `news/sources.py` gained `best_source_name()` (mirrors `best_source_tier()` but returns the literal string of whichever article won the tier/recency tie-break), and `NewsImpactVerdict` gained `source_name: str | None` + `headline_url: str | None` (the newest article's URL, previously computed but discarded). `CatalystsTable` keeps a local `Set<string>` of expanded symbols; clicking a row's impact badge toggles a sibling `<tr colSpan=…>` containing `<NewsImpactPanel verdict={c.news_impact} />` — no prop drilling through `App.tsx`, no new global state.
- **Verified by:** `python -m pytest` in `backend/` — 285 passed (2 new cases in `test_news_impact.py` for `source_name`/`headline_url`); `npx tsc --noEmit`, `npm run build`, and `vitest run` in `frontend/` — all clean; manually verified via `agent-browser` against the running dev app (`http://127.0.0.1:5173`, note: use `127.0.0.1` not `localhost` — the system proxy hijacks `localhost:5173` in this environment) that the Catalysts tab button no longer shows "Experimental" and the quote panel's `NewsImpactPanel` renders Age/Source/Price/Attention/Level 2/both sentiment reads/reasons/AI line for a live symbol (TSLA) with no console errors.
- **Follow-ups:** None — Catalysts tab currently shows no rows (after-hours, no active news catalysts) so the expand-to-`NewsImpactPanel` row and the literal source name were verified via the ticker-detail quote panel and backend unit tests instead of a live catalyst row; re-verify visually once market news catalysts are flowing.
- **Related:** `PROBLEM_LOG.md` 2026-07-14 "Catalyst rows always showed 'unknown' source tier".

## 2026-07-13 — News impact layer gains FinBERT + Loughran-McDonald sentiment, plus opt-in Lincoln AI narrative

- **What:** `NewsImpactVerdict` now carries two independent language reads of the headline: `sentiment`/`sentiment_score` from a local FinBERT model, and `lexicon_sentiment`/`lexicon_polarity` from the Loughran-McDonald financial word list (`pysentiment2`) — both always-on, free, no API key. It also carries a filled-in `ai_reasoning` from an opt-in LLM call ("Lincoln AI") that was previously always `null`. All three are informational — `impact_class`/`confidence` are still decided purely by the existing rules in `impact.py`.
- **Why:** User asked whether a library already exists that's fine-tuned to interpret news, then asked to add the lexicon-based option too since it was easy; wired a free neural model, a free lexicon-based model, and the previously-placeholder LLM narrative slot into the existing rules-first news impact layer.
- **Files touched:** `backend/news/sentiment.py` (new), `backend/news/lexicon.py` (new), `backend/news/ai_reasoning.py` (new), `backend/news/impact.py`, `backend/constants.py`, `backend/routes/news.py`, `backend/requirements.txt`, `.env.example`, `frontend/src/types/newsImpact.ts`, `frontend/src/constants.ts`, `frontend/src/components/NewsImpactPanel.tsx`.
- **How it works now:** `news/sentiment.py` lazily loads `ProsusAI/finbert` via `transformers` on the first real headline, caches the pipeline for the process lifetime, and degrades to `{"label": "unavailable", "score": None}` on any load/inference failure — it never raises. `news/lexicon.py` lazily constructs a `pysentiment2.LM()` word-list scorer (no model download, no GPU) and counts Loughran-McDonald positive/negative hits to derive `label`/`polarity`, with the same fail-safe degradation. `news/ai_reasoning.py` calls OpenAI (`LINCOLN_AI_MODEL`, default `gpt-4o-mini`) only when `LINCOLN_AI_ENABLED=true` (env override; default `False` in `constants.py`, same opt-in gate pattern as IBKR) **and** `OPENAI_API_KEY` is set; otherwise it returns `None` with zero network calls, so tests stay deterministic and offline-safe. `impact.py` calls all three after computing the headline/rule factors, appends narration to `reasons[]`, and attaches the results to the verdict — none of the three signals can change `impact_class` or `confidence`, preserving the "rules remain the visible decision layer" contract in the module's own docstring.
- **Verified by:** `python -m pytest` in `backend/` — 283 passed (new `test_news_sentiment.py` + `test_news_lexicon.py`, plus 3 new cases in `test_news_impact.py` covering off-by-default AI reasoning and the non-authoritative sentiment/lexicon fields); `npx tsc --noEmit` + `npm run build` + `vitest run` in `frontend/` — all clean; live-checked FinBERT + Loughran-McDonald both independently classify a real negative headline ("shares plunge") as `negative` while `impact_class` stayed governed purely by the price/rule logic.
- **Follow-ups:** Enable `LINCOLN_AI_ENABLED=true` + `OPENAI_API_KEY` in `.env` to turn on real narrative generation; currently off by default to avoid surprise API costs.

## 2026-07-13 — Stock View quote-panel width is now drag-to-resize

- **What:** The Stock View quote/watchlist/Level 2 column (previously a fixed 380px) now has a draggable divider between it and the chart grid. Users can drag it between 300–640px; the width persists across sessions, and double-clicking the divider resets it to the 380px default.
- **Why:** User request for micro-adjustable UI, plus an explicit ask for a reusable pattern so future "make X adjustable" requests don't need bespoke code each time.
- **Files touched:** `frontend/src/hooks/useResizableWidth.ts` (new), `frontend/src/components/ResizeHandle.tsx` (new), `frontend/src/pages/StockViewPage.tsx`, `frontend/src/constants.ts`, `frontend/src/index.css`.
- **How it works now:** `useResizableWidth({ storageKey, defaultPx, minPx, maxPx, anchor })` is a generic hook — it tracks a pixel width in state, persists it to `localStorage` under `storageKey`, and exposes `onDragStart` (wire to a `ResizeHandle`'s `onPointerDown`) plus `reset`. `ResizeHandle` is a thin, styled `role="separator"` div (`.resize-handle` in `index.css`, supports `vertical`/`horizontal`) with no business logic — any future split layout (sidebar width, panel height, etc.) can reuse both pieces by picking a new storage key and CSS grid slot. `StockViewPage` wires this into `--ticker-trade-side-width` (the existing CSS var) instead of the old constant, with the handle sitting between `.stock-view-charts` and `.stock-view-quote` in the grid.
- **Verified by:** `npm run build` + `npm run lint` (no new errors); CDP-driven synthetic pointer drag confirmed width grows/shrinks and clamps at 300/640px, persists to `localStorage`, and double-click resets to 380px on the live Stock View page (`?view=stock&symbol=AAPL`).
- **Follow-ups:** Apply the same hook/component to other panels if/when requested (e.g. sidebar, chart grid rows).

## 2026-07-13 — Stock View double-click uses timed click pairing

- **What:** Ticker rows/buttons no longer rely on native `dblclick`. Two clicks within `SYMBOL_DOUBLE_CLICK_MS` (280ms) open Stock View; a single click still loads the Quote Panel after the delay. Electron Stock View windows are shown/focused after load.
- **Why:** Real mouse double-clicks failed when the first click selected a symbol and re-rendered/shifted the row before the second click, so native `dblclick` never fired (IPC itself was fine).
- **Files touched:** `utils/clickVsDoubleClick.ts`, `SymbolSelectButton.tsx`, `SelectableTableRow.tsx`, `constants.ts`, `electron/main.mjs`.
- **How it works now:** `createClickVsDoubleClick` owns a short timer per control. Second click cancels the pending Quote Panel select and calls `onOpenTrading` → `openStockViewWindow` (desktop IPC).
- **Verified by:** Vitest `clickVsDoubleClick.test.ts`; CDP real mouse double-click on a scanner symbol opens `?view=stock&symbol=…` in a new BrowserWindow.
- **Related:** PROBLEM_LOG 2026-07-13 "Stock View double-click lost to layout re-render".

## 2026-07-13 — Fix Stock View double-click opening in the same window

- **What:** Double-click / Stock View now opens a real new Electron window (IPC `nova:openStockView`). Browser `window.open` no longer uses `noopener` (that returned null and falsely triggered same-tab fallback).
- **Why:** User reported double-click did not open a new window; desktop was navigating in-place.
- **Files touched:** `utils/stockViewNav.ts`, `App.tsx`, `electron/main.mjs`, `electron/preload.cjs`.
- **How it works now:** Desktop prefers `window.novaDesktop.openStockView(url)` → child BrowserWindow. Web uses `window.open` without noopener, then clears `opener`. Same-tab fallback only if both fail.
- **Verified by:** Vitest `stockViewNav.test.ts`; restart Electron `electron:dev` and double-click a symbol.
- **Related:** PROBLEM_LOG 2026-07-13 "Stock View double-click stayed in the same window".

## 2026-07-13 — Stock View page (detachable) mirrors Quote Panel

- **What:** Double-click / “Stock View” opens a named **Stock View** page in a new browser tab (`?view=stock&symbol=LVLU`). It reuses the same `TickerDetailContent` as the scanner **Quote Panel** (fundamentals, broker listing, data sources, news). The 2×2 chart grid is collapsible (“Hide charts” / “Show charts”). IBKR Open/Close/Automate bar stays at the bottom. Electron opens a real child window for the same URL.
- **Why:** User wanted the full quote panel on the single-stock page (not the old compact side column), clear names for each surface, detachable tabs, and more room for quote data when charts are minimized.
- **Files touched:** `pages/StockViewPage.tsx`, `utils/stockViewNav.ts`, `App.tsx`, `SidePanel.tsx`, `SymbolSelectButton.tsx`, `constants.ts`, `index.css`, `electron/main.mjs`.
- **How it works now:** Click → Quote Panel (sidebar). Double-click → `openStockViewWindow` (new tab). Both poll `useTickerStream` so they stay API-synced. Popup blocked → in-tab fallback. Charts collapsed state persists in `localStorage`.
- **Verified by:** Vitest `stockViewNav.test.ts`; `npm test`; `npm run build`.
- **Naming for agents/users:** **Quote Panel** = scanner right sidebar; **Stock View** = detachable single-stock page.

## 2026-07-13 — Explicit Data sources panel on ticker detail

- **What:** Added a **Data sources** section on the ticker side panel that lists which API powers scanner rows, quote/chart, Level 2, broker listing flags, and fundamentals. Clarified the broker grid “Listing feed” row as Alpaca Assets API (flags only). Level 2 title now shows `· IBKR`.
- **Why:** User saw “Listing feed: Alpaca Trading API” next to IBKR overnight Level 2 and reasonably assumed prices/depth were Alpaca. Feeds are already switchable (Settings discovery + IEX/SIP); attribution needs to stay visible when they change.
- **Files touched:** `frontend/src/utils/dataSourceMap.ts`, `components/TickerDataSources.tsx`, `TickerDetailContent.tsx`, `SidePanel.tsx`, `App.tsx`, `constants.ts`, `index.css`.
- **How it works now:** `buildTickerDataSources({ discoveryProvider, alpacaFeed, ibkrConnected })` drives the grid. Header still shows the short `IEX` + `Data: IBKR` badges; the panel has the full breakdown.
- **Verified by:** Vitest `dataSourceMap.test.ts` (4 tests); `npm test` (39 passed); `npm run build`.
- **Related:** Settings discovery provider / Alpaca feed toggles.

## 2026-07-13 — Quote OHLC "—" for missing data + UTC split dates

- **What:** Session Open/High/Low now render as "—" when missing or zero (instead of `$0.00` / bogus copies of prev close). Recent-split dates from yfinance use UTC calendar days so LVLU shows `1:15 (2025-07-07)` (trading-effective date) instead of a local-tz off-by-one. Fundamentals fetch extracted to `backend/fundamentals.py`.
- **Why:** User audit of LVLU panel showed Open `0`, High/Low equal to a stale prev close, and split date off vs official Jul 7, 2025.
- **Files touched:** `backend/fundamentals.py`, `backend/main.py`, `backend/tests/test_fundamentals_dates.py`, `frontend/src/utils/quoteFormat.ts`, `quoteFormat.test.ts`, `TickerDetailContent.tsx`, `TickerTradeSideColumn.tsx`.
- **How it works now:** `fmtSessionPrice` / `sessionPriceOrNull` gate OHLC display; Alpaca `_bar` coerces non-positive O/H/L to null; IBKR snapshot leaves OHLC null when unknown. `_yf_date_str` formats Yahoo epochs with `timezone.utc`.
- **Verified by:** `pytest tests/test_fundamentals_dates.py` (6 passed); Vitest `quoteFormat.test.ts` (3 passed); `npm run build`; live `fetch_fundamentals('LVLU')` → `1:15 (2025-07-07)`.
- **Related:** PROBLEM_LOG.md 2026-07-13 "LVLU Open 0 / wrong split date".

## 2026-07-13 — Level 2 / scanner stability regression tests

- **What:** Added a dedicated backend suite (`tests/test_depth_stability.py`) and frontend unit tests for depth book guards, DepthLadder status badges, overnight-only books, L2 heuristics, and tab-aware scan age. Extracted pure helpers (`depthBookGuards.ts`, `depthUiStatus.ts`) so these invariants stay testable without a browser. Thin OVERNIGHT-only books now show an explicit hint that sparse after-close quotes are normal.
- **Why:** User asked for durable regression coverage after repeated L2 reconnect / Symbol-cap / stale-age failures, and was still seeing only OVERNIGHT rows (expected when MARKET CLOSED — not a broken ladder).
- **Files touched:** `backend/tests/test_depth_stability.py`, `frontend/src/ibkr/depthBookGuards.ts`, `depthUiStatus.ts`, `DepthLadder.tsx`, `useIbkrDepth.ts`, `constants.ts`, plus matching `*.test.ts` files.
- **How it works now:** CI/local `pytest tests/test_depth_stability.py` locks concurrent-subscribe, cap eviction with leaked viewers, MM forwarding, and stream heartbeats. `npm test` locks empty-book keep, Symbol-cap badge preference, overnight-only detection, and Movers-vs-afterhours scan age. Helpers are the source of truth; React components call them.
- **Verified by:** `pytest tests/test_depth_stability.py tests/test_ibkr_safety.py` (38 passed); `npm test` (32+ passed); `npm run build`.
- **Related:** PROBLEM_LOG entries on Symbol cap / Reconnecting / scan age (2026-07-13).

## 2026-07-13 — Stabilize Level 2 slot thrash + misleading "updated Xs ago"

- **What:** Level 2 no longer sits on a forever "Reconnecting…" badge when the real failure is the 3-symbol IBKR depth cap. Depth subscribe is serialized under a lock, reserves the slot before `qualifyContractsAsync`, and actively evicts idle/leaked slots (also stopping `l2.continuous`) so the viewed ticker can take a line. Header scan age is now tab-aware so Movers is not shown as hours-stale from a frozen after-hours `last_scan`.
- **Why:** Live probe of SHPH while EHGO/GFUZ/LVLU held the cap returned `Symbol cap reached`; the UI kept the last book and only showed "Reconnecting…". Separately, `fetchData` always overwrote `lastScan` with after-hours (often frozen after 8pm), producing "updated 5962s ago" on the Movers tab.
- **Files touched:** `backend/ibkr/depth.py`, `backend/tests/test_ibkr_safety.py`, `frontend/src/ibkr/DepthLadder.tsx`, `frontend/src/App.tsx`, `frontend/src/utils/scanAge.ts`.
- **How it works now:** Concurrent WS opens for the same symbol share one `reqMktDepth`. Cap pressure always frees a slot for the active symbol. DepthLadder surfaces backend error text even when a prior book is still on screen. Header "updated Xs ago" uses the active tab's feed timestamp (`scanAgeForTab`).
- **Verified by:** `pytest tests/test_ibkr_safety.py`; Vitest `scanAge.test.ts`; live WS probe of SHPH after reload; frontend build.
- **Related:** PROBLEM_LOG.md 2026-07-13 "Level 2 Reconnecting forever on Symbol cap + stale scan age".

## 2026-07-13 — Level 2 "Connecting depth…" reconnect flicker

- **What:** Depth ladder no longer blanks to "Connecting depth for SYMBOL…" on every brief WebSocket reconnect. Last book stays visible (with a small "Reconnecting depth…" badge). Backend keeps the IBKR depth line alive for `IBKR_DEPTH_RELEASE_GRACE_SEC` (0.75s) after the last viewer disconnects so React remounts can reattach without tearing down `reqMktDepth`. When the 3-slot IBKR depth cap is full, `subscribe_async` now evicts an idle (or force-evicts a leaked) slot so the actively viewed ticker can load instead of reconnect-looping on "Symbol cap reached".
- **Why:** User saw Level 2 cycle Connecting → book → Connecting on EHGO while sitting on one symbol. Live probe showed the real blocker: slots stuck on AAPL/VMAR/SHPH with EHGO rejected at cap.
- **Files touched:** `frontend/src/ibkr/useIbkrDepth.ts`, `DepthLadder.tsx`, `backend/ibkr/depth.py`, `backend/routes/trading.py`, `backend/constants.py`, `backend/tests/test_ibkr_safety.py`.
- **How it works now:** UI only shows the full Connecting placeholder when there is no book yet (and shows the backend error text when subscribe fails). Transient empty DOM frames are ignored if a prior non-empty book exists. WS cleanup waits the grace window before `unsubscribe` / `continuous.stop`. Cap pressure calls `_evict_for_capacity()` (idle first, then force-evict + clear leaked viewer count).
- **Verified by:** `pytest tests/test_ibkr_safety.py`; frontend build; browser on EHGO after freeing stuck slots — error surface + eviction path.
- **Related:** PROBLEM_LOG.md 2026-07-13 "Level 2 Connecting depth flicker on reconnect".

## 2026-07-13 — DAS-style Level 2 montage (tier colors + MMID)

- **What:** Replaced the plain two-column depth table with a DAS Trader–style side-by-side montage: Bid (MM / Size / Price) | Ask (Price / Size / MM), price-tier background colors, size heat bars. Backend now forwards `marketMaker` as `mm` on each DOM level.
- **Why:** User could not “see the depth” — prior UI looked like a thin L1-ish list without colors or market-maker IDs.
- **Files touched:** `frontend/src/ibkr/DepthLadder.tsx`, `dasDepthTiers.ts`, `types.ts`, `constants.ts`, `index.css`, `backend/ibkr/depth.py`.
- **How it works now:** Smart Depth rows keep exchange/MM labels; each distinct price band gets the next color from `L2_DAS_TIER_BID` / `L2_DAS_TIER_ASK`. Montage shows up to `TICKER_TRADE_DEPTH_LEVELS` (10) rows per side. After-hours books can still be thin — that is venue data, not the UI.
- **Verified by:** Vitest `dasDepthTiers.test.ts`; browser check on a live IBKR depth symbol.
- **Related:** PROBLEM_LOG prior entry on `isSmartDepth=True` (data path); this entry is presentation.

## 2026-07-13 — Level 2 depth now uses SMART depth (`isSmartDepth=True`)

- **What:** `reqMktDepth` / `cancelMktDepth` now pass `isSmartDepth=True` (and `IBKR_DEPTH_NUM_ROWS`) for SMART-routed US stocks. Constants: `IBKR_DEPTH_SMART`, `IBKR_DEPTH_NUM_ROWS`.
- **Why:** User had NASDAQ TotalView but every symbol (including AAPL/F) got IBKR error 10092 and fell back to L1. Root cause was our request shape, not the subscription.
- **Files touched:** `backend/ibkr/depth.py`, `backend/constants.py`, `backend/tests/test_ibkr_safety.py`.
- **How it works now:** Depth on SMART contracts is requested as Smart Depth (TWS API ≥974). Gateway warning 2152 may still list missing non-NASDAQ depth packs (ARCA/NYSE/BATS); NASDAQ TotalView alone is enough for NASDAQ-listed names. Cancel uses the same smart flag so it matches the subscribe.
- **Verified by:** `pytest tests/test_ibkr_safety.py` (25 passed); live WS probe `/ws/ibkr/depth/AAPL` returned `l1_fallback=False` with real bid/ask rows; blast.log shows `smart=True` and no 10092 for that subscribe.
- **Related:** PROBLEM_LOG.md 2026-07-13 "SMART depth requested without isSmartDepth=True".

## 2026-07-13 — Prevent chart errors from blanking Nova

- **What:** `TickerChart` now drops invalid/out-of-order live trades, ignores stale REST responses after symbol/timeframe changes, and runs inside a chart-local React error boundary. Added Vitest with permanent chart-ordering regression coverage.
- **Why:** The user's intermittent black page was a real `TickerChart` crash, not merely dev-server churn. A delayed WebSocket trade could be older than the newest REST candle; passing it to `lightweight-charts` violated the library's monotonic-time requirement and threw an uncaught exception that unmounted the app.
- **Files touched:** `frontend/src/TickerChart.tsx`, `frontend/src/tickerChartData.ts`, `frontend/src/tickerChartData.test.ts`, `frontend/src/components/TickerChartControls.tsx`, `frontend/src/components/TickerChartErrorBoundary.tsx`, `frontend/src/constants.ts`, `frontend/package.json`, `frontend/package-lock.json`, `.cursor/rules/browser-testing.mdc`.
- **How it works now:** Live trades are bucketed and compared with the current candle before `series.update()`; older buckets and invalid timestamps never enter the imperative chart library. Each REST request receives a generation number and only the newest generation may update chart state. If another chart-library exception occurs, the chart card shows a retry message while the scanner remains mounted. Browser verification now requires a clean console after exercising affected interactions.
- **Verified by:** `npm test` (3/3 chart ordering tests), targeted ESLint (clean), `npm run build` (success), and a fresh browser session with five rapid switches across SHPH/LVLU/GMEX/VEEE/SHPH; the scanner and chart remained rendered and the browser console contained no errors.
- **Related:** PROBLEM_LOG.md 2026-07-13 "Out-of-order chart trade crashed React and blanked the entire app."

## 2026-07-13 — Root logger now prints to console too, not just blast.log

- **What:** Extracted the logging bootstrap out of `main.py` into a new `backend/logging_setup.py` (`configure_logging()`). The root logger now has both a console `StreamHandler` and the existing rotating file handler, so every module's `logger.info`/`warning`/`error` call is visible in whatever terminal is running the backend, not just in `logs/blast.log`.
- **Why:** Diagnosing the Level 2 flicker (see entry below / PROBLEM_LOG.md) took longer than it should have because the diagnostic logs that would have shown the bug immediately were invisible in the terminal — only `logs/blast.log` had them. Root-caused: no `StreamHandler` was ever attached, only the `RotatingFileHandler`.
- **Files touched:** `backend/logging_setup.py` (new), `backend/main.py` (now just calls `configure_logging()`).
- **How it works now:** `configure_logging()` builds one shared formatter, attaches a console handler and the rotating file handler to `logging.getLogger()`, and reconfigures `sys.stdout`/`stderr` to UTF-8 (previously only `run_api.py`'s entrypoint did this, which is skipped when running `uvicorn main:app` directly for local dev). Also shrinks `main.py` slightly, which was already over its 200-line target.
- **Verified by:** `pytest` (252 passed). Restarted the backend and confirmed `ibkr.depth`/`ibkr.client`/etc. log lines now print live in the terminal alongside uvicorn's own access logs.
- **Related:** PROBLEM_LOG.md 2026-07-13 "Root logger had no console handler, slowing down live debugging".

## 2026-07-13 — Fixed Level 2 depth ladder flicker caused by a stale listener on a reused IBKR ticker

- **What:** `backend/ibkr/depth.py` now precisely detaches a symbol's previous `ticker.updateEvent` listener before wiring a new one, instead of only ever adding listeners. `routes/trading.py`'s `ws_depth` also sends the current cached book immediately on connect when it's already meaningful (has bids/asks or is on L1 fallback), instead of waiting for the next tick.
- **Why:** The user still reported "I only see 'Waiting for book data,' I don't really see level 2" even after the async-rejection L1 fallback landed. A raw WebSocket probe against `/ws/ibkr/depth/SHPH` showed every real tick emitting *two* `book` messages back to back: an empty one (`l1_fallback=False`) immediately followed by the real one (`l1_fallback=True`). Root cause: `ib_async` caches `Ticker` objects per `hash(contract)`, so `reqMktData()` during the L1 fallback returned the exact same `Ticker` that `reqMktDepth()` had already returned — both the old depth listener and the new L1 listener stayed wired to it, racing an always-empty depth read against the real L1 read on every tick.
- **Files touched:** `backend/ibkr/depth.py` (`_attach_update_handler`, `_detach_update_handler`, `_update_handlers`), `backend/routes/trading.py` (`ws_depth` initial snapshot), `backend/tests/test_ibkr_safety.py` (`TestUpdateHandlerReplacement`).
- **How it works now:** `_update_handlers` tracks the exact listener function currently wired per symbol. `_attach_update_handler()` detaches whatever was wired before adding the new listener; used in `subscribe_async()`'s depth path, its L1-fallback except branch, and `_fallback_to_l1()`. `unsubscribe()` detaches on cleanup too. A symbol can now only ever have one live `updateEvent` listener, regardless of how many times it flips between depth and L1 across reconnects.
- **Verified by:** `pytest` (252 passed, incl. new `TestUpdateHandlerReplacement`). Live: restarted the backend, ran a raw WS probe against SHPH for 45s post-fix — 60+ consecutive `book` messages, all `l1_fallback=True` with real bid/ask, zero empty frames (pre-fix probe on the same symbol showed the empty/real pair racing every tick). Confirmed in the browser via `agent-browser`: SHPH's side panel Level 2 section renders a populated ladder (bid 900@$5.22, ask 400@$5.25, "Bid heavy" heuristic, "Level 1 only" badge) and stays stable.
- **Related:** PROBLEM_LOG.md 2026-07-13 "Level 2 depth ladder flickered between empty and real book after L1 fallback".

## 2026-07-13 — Level 2 depth falls back to L1 on async IBKR rejection; fixed a viewer-refcount leak

- **What:** `backend/ibkr/depth.py` now listens for IBKR's `errorEvent` and automatically switches a symbol to L1 top-of-book when the Gateway asynchronously rejects a depth request (error 10092, "Deep market data is not supported for this combination of security type/exchange"). Also fixed `routes/trading.py`'s `ws_depth` so a client disconnecting immediately after connecting can no longer leak a Level 2 viewer-count slot.
- **Why:** After wiring `DepthLadder` into the scanner side panel, the user reported the Level 2 section never showing data — just "Waiting for book data…" forever — for real symbols like SHPH. Live log inspection (`backend/logs/blast.log`) showed IBKR accepting the `reqMktDepth()` call synchronously (so the existing try/except never fired) and then rejecting it moments later via an async error callback that nothing was listening for.
- **Files touched:** `backend/constants.py` (`IBKR_ERROR_DEPTH_NOT_SUPPORTED`), `backend/ibkr/depth.py` (`_install_error_hook`, `_on_ib_error`, `_fallback_to_l1`), `backend/routes/trading.py` (`ws_depth`), `backend/tests/test_ibkr_safety.py` (`TestDepthAsyncErrorFallback`, 4 new tests).
- **How it works now:** `subscribe_async()` wires a one-time `ib.errorEvent` listener per IBKR connection (tracked by `id(ib)` so reconnects re-wire it). On error code 10092, the handler matches the rejected contract by `conId` against `_contracts`, cancels the depth request, and re-subscribes that symbol via `reqMktData` (L1), setting `l1_fallback=True` exactly like the synchronous-failure path already did. Separately, `ws_depth` now does `ws_viewer_opened()` → send `"subscribed"` → stream loop all inside one try/finally (previously the "subscribed" send was outside it), guarded by a `viewer_opened` flag so cleanup only runs when open actually happened — a disconnect racing the initial send can no longer leave the refcount permanently inflated.
- **Verified by:** `pytest` (247 passed, incl. 4 new). Live: reproduced the original stall on SHPH via `backend/logs/blast.log` (`Error 10092 ... contract: Stock(... symbol='SHPH' ...)`), confirmed the fix wires correctly with mocked `ib.errorEvent` fallback tests. Separately investigated the user's "page goes blank, needs refresh" report with `agent-browser`: reproduced twice only while backend/frontend files were being actively edited (dev-server reload churn); a clean rapid-fire click test (`batch`, 6 clicks / 4 symbols in <5s) with no concurrent edits did not reproduce it — see `PROBLEM_LOG.md` 2026-07-13.
- **Follow-ups:** If the blank-page report recurs during a stable (non-editing) session, it needs a fresh repro with an error-stack capture — not yet root-caused as a code defect.
- **Related:** PROBLEM_LOG 2026-07-13 ("Level 2 DepthLadder stuck on 'Waiting for book data' forever + WS viewer-count leak").

## 2026-07-13 — Ticker detail panel now matches the movers table for IBKR-sourced symbols

- **What:** Fixed `_find_ibkr_cache_row()` in `backend/main.py` so it checks `_gainer_cache`/`_loser_cache` before `_gapper_cache` when looking up a symbol's current row. Removed leftover `[DEBUG]` print statements and the throwaway `backend/_debug_timing.py` diagnostic script from this session's investigation.
- **Why:** User reported the ticker detail panel showing a different (stuck) price than the Gainers/Losers table for the same symbol. Verified live against the running IBKR-backed server: `/api/movers` showed VEEE at 25.05 (prev_close 4.82, live), `/api/ticker/VEEE` showed 12.01 (prev_close 4.34, frozen) — a real backend bug, not a frontend caching issue.
- **Files touched:** `backend/main.py` (`_find_ibkr_cache_row`, `_build_ticker_detail`, `_fetch_ticker_snapshot_ibkr`), `backend/tests/test_ibkr_cache_priority.py` (new), `backend/_debug_timing.py` (deleted).
- **How it works now:** Gappers intentionally freeze once the market opens (the "Market Open Halt" rule), so `_gapper_cache` can hold a stale premarket snapshot for a symbol that later also becomes an active gainer/loser and gets continuously repriced. `_find_ibkr_cache_row()` now searches `(_gainer_cache, _loser_cache, _gapper_cache)` in that order, so the live gainer/loser row always wins for any symbol tracked in both; `_gapper_cache` is only consulted as a fallback for symbols that aren't a current mover. `_fetch_ticker_snapshot_ibkr` (backing the ticker detail endpoint) and `/api/movers` now read the exact same row object for a given symbol.
- **Verified by:** `pytest` (239 passed, incl. 4 new tests covering the priority order), and a live comparison against the running IBKR-backed server for all 8 symbols currently present in both the gapper cache and a gainer/loser cache — every one now matches exactly between `/api/movers` and `/api/ticker/{symbol}`.
- **Related:** `PROBLEM_LOG.md` 2026-07-13 ("Ticker detail panel stuck on frozen premarket gapper price").

## 2026-07-13 — Gappers/gainers/losers can now run on live IBKR data, toggleable back to Alpaca

- **What:** New `backend/ibkr/discovery.py` scans IBKR's own market scanner (`TOP_OPEN_PERC_GAIN` for gappers, `TOP_PERC_GAIN`/`TOP_PERC_LOSE` for movers) and snapshots live quotes via `reqTickersAsync`, producing rows in the exact shape the existing Alpaca pipeline already used. A new `DISCOVERY_PROVIDER` setting (`alpaca` default, `ibkr`) switches the source at runtime — persisted to `.env`, exposed via `/api/config`, and toggleable from a new "Scanner Source" dropdown in Settings. Header badge now shows "Data: Alpaca" or "Data: IBKR" accordingly.
- **Why:** User connected a live IBKR account and wants real, non-delayed market data for the full scanner (gappers/gainers/losers) instead of Alpaca's free delayed IEX feed, without losing the ability to switch back or paying for Alpaca's SIP add-on. Built as a clean, self-contained module per the user's explicit ask ("study how Alpaca works, do a fresh clean start with IBKR") rather than threading IBKR calls into the existing Alpaca-shaped functions.
- **Files touched:** `backend/ibkr/discovery.py` (new), `backend/ibkr/client.py` (`run_coro` thread→event-loop bridge), `backend/market.py` (new — extracted `now_et`/`in_premarket`/`in_market_hours`/`in_after_hours` out of `main.py`), `backend/main.py` (provider branch in `_run_discovery_scan`/`_run_gainers_update`, `/api/config` fields, `_handle_trade` provider gate), `backend/constants.py` (`DISCOVERY_PROVIDER_*`, `IBKR_SCAN_*`), `backend/tests/test_ibkr_discovery.py` (new), `frontend/src/components/SettingsPanel.tsx` (new, extracted from `App.tsx`), `frontend/src/components/AppHeader.tsx`, `frontend/src/App.tsx`, `frontend/src/constants.ts`.
- **How it works now:** `_run_discovery_scan()`/`_run_gainers_update()` branch on `_get_discovery_provider()`. On `ibkr`, they call `ibkr.discovery.get_gappers()/get_gainers()/get_losers()` via `_run_ibkr()`, which bridges the worker-thread scan loop into the asyncio loop IBKR's `IB` instance is bound to (`ibkr.client.run_coro`), then feed the resulting rows through the *same* Alpaca-independent enrichment (`_ensure_avg_volume`, `_check_news`, `_fetch_fundamentals_batch`, `_exchanges.attach_exchange`) as before — those still use Alpaca/yfinance regardless of provider. News/fundamentals were never in scope for the swap. `_handle_trade` (Alpaca's WS price overlay) now skips gapper/mover caches entirely when the IBKR provider is active, since mixing a second live feed into IBKR-sourced rows without a shared recompute basis caused inconsistent price/change fields (see `PROBLEM_LOG.md`).
- **Verified by:** `pytest` (232 passed, incl. 8 new discovery tests with a faked `ib_async` client), `npm run build`/`npm run lint` (frontend, no new errors), and a live check against the running server + IBKR Gateway during market hours: switched provider to `ibkr`, confirmed `/api/movers` returned live, internally-consistent IBKR data with correct exchange tags, and confirmed via agent-browser screenshots that the header badge and Settings dropdown reflect the switch.
- **Follow-ups:** Gapper path (`TOP_OPEN_PERC_GAIN`) validated via a standalone scan but not exercised through `/api/gappers` end-to-end this session (premarket window had passed). Ticker detail page and HOD Momo universe still use Alpaca regardless of this toggle — a separate, larger migration if ever needed. `main.py`/`App.tsx` are still over their line-count targets (pre-existing, tracked violation); this task extracted `market.py` and `SettingsPanel.tsx` but did not attempt the full modularization.
- **Related:** `knowledge/obsidian/03-Nova-Decisions/Scanner-Provider-IBKR-Primary.md`, `PROBLEM_LOG.md` 2026-07-13 (IBKR mover row inconsistency).

## 2026-07-13 — Live IB Gateway OK; orders locked by default (safety SSOT)

- **What:** Split Gateway connection mode from spending. New `ibkr/safety.py` is the single gate for place_order / brackets. Defaults: `IBKR_ORDERS_ENABLED=false`. Live Gateway can supply L1/L2 while buys/sells stay blocked unless orders are enabled **and** (for live) `IBKR_LIVE_TRADING_CONFIRMED=true`. Status API + Trading tab show `spend_status` / “ORDERS LOCKED”.
- **Why:** User connected live Gateway (~$600) after paper login failed; needed hard guardrails against accidental spends.
- **Files touched:** `backend/ibkr/safety.py`, `client.py`, `orders.py`, `routes/trading.py`, `constants.py`, `tests/test_ibkr_safety.py`, frontend IBKR status/types/TradingTab, `.env.example`, decision note.
- **How it works now:** `IBKR_GATEWAY_MODE=live` → port 4001 for data. Spending requires `IBKR_ORDERS_ENABLED=true` (+ live confirm on live). Cancel still works when connected.
- **Verified by:** `pytest backend/tests/test_ibkr_safety.py` (9 passed); frontend build.
- **Related:** PROBLEM_LOG 2026-07-13 live Gateway spend risk; `knowledge/obsidian/03-Nova-Decisions/IBKR-Orders-Locked-On-Live-Gateway.md`

## 2026-07-13 — Listing exchange under each scanner ticker

- **What:** Scanner Symbol cells (Gappers / Movers / After Hours / Catalysts) now show the stock’s listing venue in small secondary text under the ticker — same stack style as dollar change under %. Values come from Alpaca asset metadata (e.g. NASDAQ, NYSE, AMEX, ARCA).
- **Why:** User needs to see which exchange each name is listed on because data feeds can differ by venue.
- **Files touched:** `backend/exchanges.py` (new), `backend/main.py`, `backend/tests/test_exchanges.py`, `SymbolSelectButton.tsx`, `ScannerTable.tsx`, `CatalystsTable.tsx`, `types/scanner.ts`, `types/catalyst.ts`.
- **How it works now:** Universe refresh builds a symbol→exchange map from Alpaca `/v2/assets`. Enrichment and `_strip_blocked` attach `exchange` on rows before the API returns them. `SymbolSelectButton` renders `exchange` via `cell-stack-secondary` under the symbol button.
- **Verified by:** pytest `test_exchanges.py`; frontend build; app run + browser check on Gappers.
- **Follow-ups:** Optionally plumb exchange into HOD Momo / Watchlist rows the same way.

## 2026-07-13 — Click anywhere on a scanner row to load the chart

- **What:** Clicking any cell in a Gappers / Movers / After Hours / Catalysts / Watchlist / Signals row selects that symbol and updates the side-panel price chart (not only the Symbol button). Double-click anywhere on the row still opens full trading view.
- **Why:** User wanted row-wide selection so they don’t have to hit the ticker text specifically.
- **Files touched:** `SelectableTableRow.tsx` (new), `ScannerTable.tsx`, `CatalystsTable.tsx`, `WatchlistTab.tsx`, `SignalsPanel.tsx`, `SymbolSelectButton.tsx`, `index.css`.
- **How it works now:** `SelectableTableRow` owns click / double-click / Enter-Space. Symbol buttons stopPropagation so they don’t double-fire. Catalyst headline links also stopPropagation so they open without changing selection unless you click elsewhere in the row.
- **Verified by:** Frontend build + agent-browser row click outside the symbol cell.

## 2026-07-13 — Side panel: news row + watchlist pillars strip

- **What:** Under the Price Chart, News Headline is now a full-width row. Directly below it, a Watchlist strip shows Pillars / Detail chips / % Chg / RVOL / Float / News / Score for the selected symbol (same data as the Watchlist tab). Quote + Fundamentals sit in a two-column row underneath.
- **Why:** User asked to see headlines alone, then watchlist pillars/details/scoring in their own row under the chart.
- **Files touched:** `TickerDetailContent.tsx`, `TickerWatchlistStrip.tsx` (new), `PillarChips.tsx` (extracted), `SidePanel.tsx`, `App.tsx` (`EmptyState` extracted), `constants.ts`, `index.css`.
- **How it works now:** `App` passes `watchlist.entries` into `SidePanel`, which joins the selected symbol to a `WatchlistEntry` and feeds `TickerWatchlistStrip`. Symbols not currently ranked show “Not ranked on the current watchlist.”
- **Verified by:** `npm run build`; agent-browser on AGEN confirmed `.cq-news-row`, strip with `3/5` pillars + chips + score `26`.

## 2026-07-13 — Price chart defaults to 1-minute timeframe

- **What:** Opening a ticker’s Price Chart now starts on **1m** instead of **5m**. Users can still switch timeframes with the chart tabs.
- **Why:** User requested 1-minute as the default chart interval.
- **Files touched:** `frontend/src/constants.ts`, `backend/constants.py`.
- **How it works now:** `TickerChart` initializes from `CHART_DEFAULT_TIMEFRAME` (`1Min`). The bars API default query param mirrors the same constant. There is no Settings UI for this — change the constant to retune.
- **Verified by:** Frontend build; app run with chart opening on 1m.
- **Follow-ups:** Optional Settings toggle if users want a per-session preference without editing constants.

## 2026-07-12 — Watchlist Five Pillars score infused into scanner tables

- **What:** Gappers / Movers / After Hours tables gained a new dense `Watch` column (between `News` and `Float`) showing each symbol's Five Pillars checkmark (e.g. `3/5`, green `✅` when `all_pass`) stacked over its composite score (e.g. `25 pts`), hover tooltip lists which pillars are failing. The Watchlist tab itself is unchanged — same sub-tabs, same ranked table, same Signals/Journal/Automation panels.
- **Why:** User asked to "infuse all of the details that the watch list has given us into each of the scanners" as a new column, without duplicating scoring logic on the client or touching the Watchlist tab's own UX.
- **Files touched:** `frontend/src/strategy/useWatchlistOverlay.ts` (new hook), `frontend/src/types/scanner.ts` (`ScannerRow.watchlist` / `watchlist_score`), `frontend/src/components/ScannerTable.tsx` (new `WatchCell`), `frontend/src/constants.ts` (`SCANNER_COLUMNS`), `frontend/src/App.tsx` (wiring only). Extracted `frontend/src/components/CatalystsTable.tsx` + `frontend/src/types/catalyst.ts` out of `App.tsx` first (per file-size-limits: never make an existing monolith worse before adding to it) — net result is `App.tsx` shrank from ~732 to ~613 lines despite the new feature.
- **How it works now:** `App.tsx` already polls `GET /api/strategy/watchlist` continuously via the existing `useWatchlist(true)` call (used for the tab badge count). `useWatchlistOverlay(rows, watchlistEntries)` builds a `symbol -> WatchlistEntry` map from that same poll and joins it onto each Gappers/Movers/After Hours row *before* sorting (so the new column sorts correctly on the primitive `watchlist_score` field, same "sort key stays on the primary field" convention as `change_pct`/`volume`). No new backend endpoint, no re-scoring on the client, no per-row fetches — it is a pure client-side join of an already-fetched feed. Rows with no current watchlist rank (outside `WATCHLIST_MAX_ROWS`) show a muted `—`.
- **Verified by:** `npm run build` (tsc + vite) succeeds; `npm run lint` shows the same 16 pre-existing errors as on a clean `git stash` of `master` (no new lint errors introduced); `pytest` in `backend/` still 218/218 passing (no backend files touched); loaded the running dev server and visually confirmed the `Watch` column renders on Gappers and Movers with live pillar/score data, and that the Watchlist tab (ranked table, pillar chips, sub-scores, Signals/Journal/Automation sub-tabs) is pixel-for-pixel unchanged.
- **Follow-ups:** Eligible-setup badges (Gap and Go / Bull Flag / ABCD) were intentionally left out of the column — the background `setups_stream.py` scan only emits a triggered-signal history via `/ws/strategy`, not a steady-state "currently eligible" snapshot per symbol, so surfacing that cheaply would need a small backend change; the tooltip already exposes the full pillar breakdown in the meantime.
- **Related:** builds on the `News column restored` entry directly below (same session, same `SCANNER_COLUMNS` file).

## 2026-07-12 — News column restored to the main scanner tables

- **What:** Gappers / Movers / After Hours tables show `Symbol | Price | Change | Gap % | Volume | News | Float | Short Int. | Mkt Cap` again — the `News` column (red/orange/yellow hotness dot for how fresh the newest headline is) is back between `Volume` and `Float`.
- **Why:** The prior densify pass (see the entry below) dropped `newest_headline_at`/`News` from `SCANNER_COLUMNS` entirely, so users lost the at-a-glance news-freshness signal on the main scanner grid (it only remained on the separate Catalysts tab).
- **Files touched:** `frontend/src/constants.ts` (`SCANNER_COLUMNS`).
- **How it works now:** `ScannerTable.tsx`'s `renderCell` already had a `case 'newest_headline_at'` wired to the existing `NewsCell` component (red `flame-hot` ≤ `NEWS_FLAME_HOT_HOURS`, orange `flame-warm` ≤ `NEWS_FLAME_WARM_HOURS`, yellow `flame-cool` ≤ `NEWS_FLAME_MAX_HOURS`, dash beyond that or when null) — it was never removed, just orphaned when the column entry was dropped from `SCANNER_COLUMNS`. Re-adding `['newest_headline_at', 'News']` to the column list was the only change needed; no new render/CSS logic required.
- **Verified by:** `npm run build` (tsc + vite) succeeds; loaded the running dev server in a browser and confirmed the `News` header/column renders in Gappers and Movers, with a live yellow `flame-cool` dot showing for a symbol (SILO) that had a headline in the last ~24h.
- **Related:** follows directly from the densify entry below.

## 2026-07-12 — Scanner tables consolidate into dense dual-value columns

- **What:** Gappers / Movers / After Hours tables now show `Symbol | Price | Change | Gap % | Volume | Float | Short Int. | Mkt Cap` — 8 columns instead of 12. `Change` stacks Change % (primary, colored) over Change $ (secondary); `Volume` stacks raw volume over rel. volume (`x rel`); `Short Int.` stacks short interest over short ratio (`x ratio`). The standalone Change $, Daily Rel. Volume, Short Ratio, and News columns are gone from the main scanner grid (News stays on the Catalysts tab).
- **Why:** User asked to match a denser mockup layout with combined metric cells instead of separate columns per value.
- **Files touched:** `frontend/src/constants.ts` (`SCANNER_COLUMNS`), `frontend/src/components/ScannerTable.tsx` (new), `frontend/src/types/scanner.ts` (new), `frontend/src/App.tsx`, `frontend/src/index.css`.
- **How it works now:** `ScannerTable`, `renderCell`, and `NewsCell` were extracted out of `App.tsx` into `components/ScannerTable.tsx` per the frontend-modularity rule; `ScannerRow`/`Gapper`/`Mover`/`Afterhours`/`SortConfig`/`SortDir` moved to `types/scanner.ts` so both `App.tsx` and the new component share one definition. `renderCell` renders dual-value cells with a shared `.cell-stack` / `.cell-stack-primary` / `.cell-stack-secondary` CSS pattern (primary bold line, secondary dim smaller line) added to `index.css`. Column keys stay on the primary field (`change_pct`, `volume`, `short_interest`) so existing generic `sortedArray`/`toggleSort` logic in `App.tsx` keeps sorting correctly with no changes needed. `App.tsx` now imports `ScannerTable`/`NewsCell` instead of defining them inline; the Catalysts tab keeps using `NewsCell` directly since it isn't part of `SCANNER_COLUMNS`.
- **Verified by:** `npm run build` (tsc + vite) succeeds; `npm run lint` shows the same pre-existing error count as before this change (no new lint errors introduced).
- **Follow-ups:** `App.tsx` is still well over the 150-line target; further extraction (e.g. the Catalysts table) is out of scope for this task.

## 2026-07-12 — Full-view charts expand to ~80% of the viewport

- **What:** Double-click trading page now gives the 2×2 chart cube almost all available height/width: full-bleed container, tiny chrome gaps, narrower side column (220px), charts fill parent cells via ResizeObserver instead of a fixed 260px height. Symbol/price sits inline in the toolbar.
- **Why:** User asked for graphs to dominate (~80% of screen) with bare-minimum margins; bottom Open/Close/Automate bar stays compact.
- **Files touched:** `frontend/src/index.css`, `frontend/src/TickerChart.tsx`, `frontend/src/pages/TickerDetailPage.tsx`, `frontend/src/constants.ts`.
- **How it works now:** Trading full-view drops the compact AppHeader (Back + symbol live in the page toolbar). `.ticker-trade-body` targets ~80vh; `.chart-grid` uses equal `1fr` rows/cols at `height: 100%`; each grid chart card flexes so `.chart-body` owns leftover cell height. Side column is 220px.
- **Verified by:** `npm run build` (tsc + vite).
- **Follow-ups:** Live 10s panel still deferred; action bar can be refined later without stealing chart space.

## 2026-07-11 — Full ticker page is an active trading screen

- **What:** Double-click / Full view is no longer a sidebar info dump. Layout is **2×2 charts (primary) + compact side column (quote/stats/news/depth/position) + sticky bottom action bar** with Open (BUY/SELL ticket), Close (flatten), and Automate (arm/disarm/kill via `useExecutor`).
- **Why:** User asked for a page built for acting on a trade, reusing IBKR paper order paths and existing executor controls.
- **Files touched:** `pages/TickerDetailPage.tsx`, `ibkr/{TickerTradeSideColumn,TickerTradeActionBar,TickerTradeAutomateControls,useIbkrAccount}.tsx`, `constants.ts`, `index.css`, CHANGELOG.
- **How it works now:** `TickerDetailPage` wires `useTickerStream` + `useIbkrStatus`/`useIbkrAccount`. Side column is compact (not `TickerDetailContent`). Action bar POSTs `/api/ibkr/order` for open/close; automate reuses executor status/actions with the same disclosure dialogs. Disabled states explain IBKR disconnected / no position. Sidebar single-click path unchanged (`TickerDetailContent layout="columns"`).
- **Verified by:** `npm run build`; browser open Full view — charts + side column + Open/Close/Automate bar with clear disabled why when IBKR offline.
- **Follow-ups:** Optional: cancel open orders for this symbol from the side column; richer depth truncation to `TICKER_TRADE_DEPTH_LEVELS`.

## 2026-07-11 — Single-row tabs + header meta cleanup

- **What:** Main tabs stay on one horizontal line (no wrap). Scan age ("updated Xs ago") and "Data: Alpaca" moved from the tab bar into the header beside Connected / latency / IEX. Header layout reorganized: brand | market mode | connection+feed+scan meta | history+symbol lookup+settings.
- **Why:** User screenshot — tabs wrapping onto a second row, meta cluttering the tab bar, header spacing felt incoherent.
- **Files touched:** `frontend/src/components/{AppHeader,TabNav}.tsx`, `frontend/src/App.tsx`, `frontend/src/constants.ts`, `frontend/src/index.css`, `CHANGELOG.md`.
- **How it works now:** `TabNav` is tabs-only. `AppHeader` owns brand, mode badge, status cluster (scan age + Alpaca source inline with Connected), and actions. Tab CSS uses `flex-wrap: nowrap`, denser padding/font, equal-flex tabs across full width; overflow-x auto with hidden scrollbar only as a tiny-viewport fallback.
- **Verified by:** `npm run build`; browser eval: `tabBarH≈31`, single `tabTops`, meta not in `.tab-bar`.
- **Follow-ups:** None.

## 2026-07-11 — Fix sidebar chart/quote side-by-side regression + lock 2×2 grid

- **What:** Restored sidebar to **chart full-width on top**, quote/news/fundamentals in `.cq-info-row` **underneath** (not beside). Renamed root class to `cq-root--stacked`. Full trading page keeps a true **2×2 cube** (`.chart-grid`: 1Min|5Min / 1Day|15Min).
- **Why:** Regression — `.cq-root--columns` still used a 3-column CSS grid, so chart and info-row became peer columns. Chart-grid CSS was also missing from `index.css`.
- **Files touched:** `frontend/src/index.css`, `frontend/src/components/TickerDetailContent.tsx`, CHANGELOG.
- **How it works now:** Stacked root is `display:flex; flex-direction:column`. Multi-col applies only to `.cq-info-row`. `.chart-grid` is `grid-template-columns: 1fr 1fr`.
- **Verified by:** Browser hard-check: chartAboveInfo + 4 grid cells in 2×2.
- **Related:** prior 2×2 / sidebar layout entries same day.

## 2026-07-11 — Full trading page 2×2 multi-timeframe chart grid

- **What:** Double-click / Full view now shows a **2×2 chart grid** (1Min, 5Min, Full Day / 1Day, 15Min) instead of a single chart. Each cell has its own drawing toolbar. Sidebar still uses one full-width chart on top with info columns underneath.
- **Why:** User still only saw one chart on the trading page and asked for multi-chart panels.
- **Files touched:** `frontend/src/components/ChartGrid.tsx` (new), `frontend/src/pages/TickerDetailPage.tsx`, `frontend/src/TickerChart.tsx` (`fixedTimeframe` / `variant="grid"`), `frontend/src/constants.ts` (`CHART_GRID_PANELS`, `CHART_HEIGHT_GRID`), `frontend/src/index.css` (`.chart-grid`, sidebar `.cq-info-row`).
- **How it works now:** `ChartGrid` maps `CHART_GRID_PANELS`. Fourth panel is **15Min** labeled as a temporary stand-in — Alpaca has no historical sub-minute; a live **10s** tape panel will replace/add later. Sidebar `layout="columns"` = chart row then `.cq-info-row`.
- **Verified by:** `npm run build`; browser double-click → four `.chart-grid-cell` panels with bars.
- **Follow-ups:** Replace/add 10-second live tape as fourth (or fifth) panel when feed exists.

## 2026-07-11 — Side panel: full-width chart above info columns

- **What:** Sidebar ticker layout is now chart (full width + drawing toolbar) on top, then a multi-column info row underneath (quote/stats | news/impact | fundamentals/broker). Wider panel and click/double-click rules unchanged.
- **Why:** User feedback — chart must not sit in a side column next to the quote; it should dominate the top of the panel.
- **Files touched:** `frontend/src/components/TickerDetailContent.tsx`, `frontend/src/index.css` (`.cq-root--columns`, `.cq-info-row`), CHANGELOG.
- **How it works now:** `layout="columns"` renders `.cq-col--chart` first (100% width), then `.cq-info-row` as a 3-col grid that stacks via container queries at ≤640px / ≤420px.
- **Verified by:** `npm run build`; browser: single-click → chart on top, info row below; double-click still opens full page.
- **Related:** prior 3-column side-by-side entry same day (superseded for chart placement).

## 2026-07-11 — Side panel 3-column layout (wider)

- **What:** Scanner side panel widened (~820px / 48vw) and ticker detail content laid out in three columns when width allows: quote + key stats + news | chart | fundamentals + broker. Narrow viewports stack. Click/double-click rules unchanged.
- **Why:** User reported the tall vertical sidebar wasted horizontal space and forced needless scrolling.
- **Files touched:** `frontend/src/components/{SidePanel,TickerDetailContent}.tsx`, `frontend/src/constants.ts` (`SIDE_PANEL_WIDTH_PX`, `CHART_HEIGHT_PANEL`), `frontend/src/index.css`.
- **How it works now:** `TickerDetailContent layout="columns"` uses CSS grid (`cq-root--columns`). At ≤1400px fund column spans full width under quote+chart; at ≤1100px panel stacks under scanner. Full trading page still via double-click / Full view.
- **Verified by:** `npm run build`; browser screenshot of 3-col sidebar on wide viewport.
- **Related:** single-click/double-click entry same day.

## 2026-07-11 — Single-click keeps sidebar; double-click opens full trading page

- **What:** Restored the scanner **side panel** for single-click symbol select. Double-click (or side-panel **Full view**) opens the dedicated `TickerDetailPage` with large charts + drawing tools. Back clears only the full-page state and returns to the prior scanner tab with the sidebar still selected.
- **Why:** User clarified UX: keep the sidebar on click; only open a full trading/detail screen when ready to act (double-click).
- **Files touched:** `frontend/src/App.tsx`, `components/{SidePanel,SymbolSelectButton,TickerDetailContent}.tsx`, `pages/TickerDetailPage.tsx`, `strategy/{WatchlistTab,SignalsPanel}.tsx`, `hod_momo/HodMomoTab.tsx`, `index.css`, CHANGELOG/PROBLEM_LOG.
- **How it works now:** `selectedSymbol` drives `SidePanel` only (scanner tabs stay). `tradingSymbol` drives full-page `TickerDetailPage`. `SymbolSelectButton` wires click → select, double-click → `openTradingView`. Panel chart uses `variant="panel"`; page chart uses `variant="page"` (mock bars if Alpaca empty).
- **Verified by:** `npm run build`; browser: single-click → sidebar + tabs remain; double-click → full page + Back.
- **Related:** supersedes prior “click opens full page” CHANGELOG entry same day; PROBLEM_LOG same date.

## 2026-07-11 — Reports tab: TraderVue-style P&L calendar

- **What:** New top-level **Reports** tab with a year calendar of daily net P&L from journal closed trades, month Open detail (daily $ + trade count + week totals), and a growth summary (year P&L, win/loss days, best/worst day). Backend `GET /api/journal/calendar?year=&month=`. Import is intentionally skipped (journal already has trades).
- **Why:** User asked to mirror TraderVue reporting skills — calendar first — without broker import.
- **Files touched:** `backend/journal/calendar.py` (new), `backend/routes/journal.py`, `backend/constants.py`, `backend/journal/mock_data.py` (multi-day seed), `backend/tests/test_journal_calendar.py` (new), `frontend/src/reports/*` (new), `frontend/src/components/TabNav.tsx`, `frontend/src/App.tsx`, `frontend/src/constants.ts`, `frontend/src/index.css`, `knowledge/obsidian/03-Nova-Decisions/TraderVue-Reporting-Parity.md`.
- **How it works now:** Closed trades are bucketed by `closed_ts` into America/New_York calendar days. Year response returns 12 months + analytics; `&month=` returns every day in the month plus Sunday-start week totals. UI demo toggle uses `include_mock` like Journal.
- **Verified by:** `pytest backend/tests/test_journal_calendar.py`; `npm run build`; browser check of Reports tab.
- **Follow-ups:** Recent 30/60/90 charts, drawdown, tag breakdown.
- **Related:** TraderVue-Reporting-Parity.md

## 2026-07-11 — Click ticker opens full detail page with working charts

- **What:** Clicking a symbol no longer only fills a narrow side panel beside the scanner. It navigates to a dedicated full-width **Ticker Detail** page with Back, symbol lookup, large price chart (drawing tools: trend / horizontal / vertical), and fundamentals/news. Header Look Up also opens that page. Empty Alpaca bar responses fall back to demo candles so the chart and drawings stay usable.
- **Why:** User reported that clicking a ticker did not open an active trading/detail screen with visible graphs — the old SidePanel UX felt blank / not navigational.
- **Files touched:** `frontend/src/pages/TickerDetailPage.tsx` (new), `frontend/src/components/{TickerDetailContent,SymbolSearchBox}.tsx` (new), `frontend/src/hooks/useTickerStream.ts`, `frontend/src/types/ticker.ts`, `frontend/src/utils/quoteFormat.ts`, `frontend/src/TickerChart.tsx` (`variant`, mock bars), `frontend/src/App.tsx` (navigation; SidePanel removed), `frontend/src/constants.ts` (`CHART_HEIGHT_*`, `CHART_MOCK_*`), `frontend/src/index.css`.
- **How it works now:** `selectedSymbol` set → App renders `TickerDetailPage` instead of the scanner layout. Back clears `selectedSymbol` and restores the prior tab. Chart uses `variant="page"` (440px). If `/api/ticker/{symbol}/bars` returns zero bars, `TickerChart` synthesizes `CHART_MOCK_BAR_COUNT` candles and shows a demo badge.
- **Verified by:** `npm run build`; agent-browser: click QTTB → detail page (no side panel, chartH=440, 6 tools); draw horizontal + vertical + trend; Back → Gappers; screenshots `ticker-detail-page.png` / `ticker-detail-drawings.png`.
- **Follow-ups:** Optional 2x2 multi-timeframe grid from the earlier chart redesign plan; keep drawings across symbol switches.
- **Related:** PROBLEM_LOG 2026-07-11 ticker click navigation.

## 2026-07-11 — Efficient local L2 + tape recorders (WAL SQLite, batching, recall API)

- **What:** Extended Phase F `backend/l2/` into a high-write local recorder stack: WAL SQLite, batched inserts, continuous L2 while depth is open, Alpaca time & sales for watched symbols, session metadata, retention purge, and minimal point-in-time recall (`GET /api/l2/at`, `/range`, `/sessions`, `/status`). Decision note: `knowledge/obsidian/03-Nova-Decisions/Local-Market-Data-Recorders.md`.
- **Why:** User wants efficient local recorders to later ask “what did L2 / tape look like at second T?” and recover data for relearning/backtesting — without a replay UI yet.
- **Files touched:** `backend/l2/{db,batch,store,sessions,tape,continuous,recall,recorder}.py`, `backend/routes/{l2,trading}.py`, `backend/main.py` (thin tape + flush/retention wiring), `backend/constants.py` (`L2_BATCH_*`, `TAPE_*`, retention/recall), `backend/tests/test_l2_recorder.py`, `backend/tests/test_l2.py` (session_id on `_record_window`), decision note + CHANGELOG.
- **How it works now:** Signal windows still use `recorder.on_signal`. Opening DepthLadder / depth WS also starts `continuous` snapshots (~1 Hz) and watches the symbol for Alpaca prints (`tape.on_alpaca_trade` from the existing WS loop). Writes enqueue in `l2.batch` and flush by size or interval into `l2.db`. Recall via `l2.recall.recall_at(symbol, ts)` or `GET /api/l2/at?symbol=&ts=`. Parquet cold archive deferred.
- **Verified by:** `pytest backend/tests/test_l2.py backend/tests/test_l2_recorder.py`; app boot with new routes.
- **Follow-ups:** Replay UI, full backtester, optional Parquet archive, optional full-universe tape recording.
- **Related:** `Local-Market-Data-Recorders.md`; Phase F L2 entry below.

## 2026-07-11 — Explicit news-impact decision layer (rules-first)

- **What:** Nova now classifies whether news actually affects a ticker / Level 2 with a visible `NewsImpactVerdict` (`moved_price` / `attention_only` / `no_effect` / `insufficient_data`), including age, source credibility, official confirmation, price reaction, attention (RVOL), L2 reaction, `reasons[]`, exposed `factors` thresholds, and `ai_reasoning: null` (Lincoln AI placeholder). Surfaced on ticker detail, Catalysts row badges, and `GET /api/news/impact/{symbol}`.
- **Why:** User asked for news comprehension that feeds an explicit decision layer — not a black box — covering bump-due-to-news vs attention-only vs no effect, with tunable age/credibility/official-source factors.
- **Files touched:** `backend/news/{__init__,sources,impact,enrich}.py` (new), `backend/routes/news.py` (new), `backend/constants.py` (`NEWS_IMPACT_*`), `backend/main.py` (router + catalyst enrich + ticker/WS payload), `backend/tests/test_news_impact.py` (new), `frontend/src/{types/newsImpact.ts,hooks/useNewsImpact.ts,components/NewsImpactPanel.tsx,components/NewsHeadlineSection.tsx,constants.ts,App.tsx,index.css}`, `knowledge/obsidian/03-Nova-Decisions/News-Impact-Decision-Layer.md`.
- **How it works now:** Existing Alpaca news + catalyst scan stay the data source. `news.impact.evaluate_news_impact()` is pure rules over articles + gap% + RVOL + optional L2 features; every threshold is in `NEWS_IMPACT_*` and copied into `verdict.factors`. Catalyst scan attaches `news_impact` per row; ticker WS `detail_update` and REST ticker detail include it; UI shows summary + expandable reasons. AI narrative is intentionally null until Lincoln AI is wired.
- **Verified by:** `pytest backend/tests/test_news_impact.py`; frontend build; API import/boot with `/api/news/impact/{symbol}` registered.
- **Follow-ups:** Wire Lincoln AI into `ai_reasoning`; refine source keyword lists from live Alpaca `source` values; optionally feed impact_class into Five Pillars / watchlist scoring later.
- **Related:** Builds on existing flame thresholds, catalyst scan, and L2 features — does not invent a parallel news pipeline.

## 2026-07-11 — Arithmetic correctness + automation transparency test suite

- **What:** Added `backend/tests/test_arithmetic_correctness.py` with hard-number expectations for risk stop/R:R math, position-sizing boundaries, setup entry/stop/target 2:1 brackets (Gap and Go / Bull Flag / ABCD), Five Pillars thresholds, L2 imbalance/stacked/spread/drying-up ratios, journal win-rate/avg/ratio/go-no-go arithmetic, and executor disclosure / disarmed-by-default contracts. Fixed two real bugs in `validate_trade_plan` found by those tests.
- **Why:** User cannot afford arithmetic mistakes or unclear execution messaging; existing tests often asserted shape/`not None` rather than exact dollars and ratios.
- **Files touched:** `backend/strategy/risk.py`, `backend/tests/test_arithmetic_correctness.py`, `backend/tests/test_risk.py`, `backend/tests/test_bull_flag.py`, `CHANGELOG.md`, `PROBLEM_LOG.md`.
- **How it works now:** Long trade plans must have stop strictly below entry and target strictly above; stop/reward distances are rounded to cents before the `$0.20` max-stop check (avoids float false rejects). New tests lock exact expected numbers (e.g. bull-flag target `4.86`, gap/ABCD `$0.20` stop + 2:1 target) and assert executor status disclosure still says paper / disarmed-by-default / restart.
- **Verified by:** `py -3 -m pytest` in `backend/` — 176 passed.
- **Follow-ups:** No Vitest yet — frontend Automation copy remains covered indirectly via backend disclosure contract; add a minimal frontend test when Vitest is wired.
- **Related:** PROBLEM_LOG 2026-07-11 — inverted long plans + float max-stop reject.

## 2026-07-11 — Tab bar wraps instead of horizontally scrolling

- **What:** The top tab bar (Gappers/Movers/After Hours/Catalysts/HOD Momo/Trading/Watchlist) no longer shows a horizontal scrollbar when it doesn't fit the available width. Tabs now wrap onto additional rows instead.
- **Why:** User feedback — the horizontal scroll/scrollbar under the tab row looked broken and was disliked; the bar should always show every tab at full width.
- **Files touched:** `frontend/src/index.css` (`.tab-bar`, `.tab-bar-scroll`).
- **How it works now:** `.tab-bar-scroll` switched from `flex-wrap: nowrap` + `overflow-x: auto` (with a thin scrollbar) to `flex-wrap: wrap`; `.tab-bar` itself also got `flex-wrap: wrap` so the row height grows cleanly to fit however many lines the tabs need. No JS changes — `TabNav.tsx` is unchanged.
- **Verified by:** `npm run build` clean; visually confirmed via `agent-browser` screenshots at 1024px, 1440px, and 1920px viewport widths — no scrollbar at any width, tabs wrap onto a second row when the (fixed-width) main panel is narrower than the full tab set.
- **Follow-ups:** None — the fixed max-width of the main content column (separate from this change) is why tabs still wrap even at very wide windows; that's pre-existing layout, not a regression.

## 2026-07-11 — Phase F: L2 recorder + tape feature extraction + outcome labeling + heuristic badges (final phase of the Trading Automation Machine plan)

- **What:** Nova now automatically records the Level 2 order book around every setup signal, computes tape/order-book features on it, labels each recording with its eventual trade outcome from the journal, and surfaces single-snapshot heuristic badges ("Seller stacked on ask", "Bid heavy", "Wide spread") on the live `DepthLadder`. New `backend/l2/` package: `db.py`/`store.py` (own `l2.db` SQLite file, `l2_snapshots` table), `recorder.py` (subscribes IBKR depth on signal, snapshots the book every `L2_SNAPSHOT_INTERVAL_SEC` for `L2_RECORD_WINDOW_SEC`), `features.py` (pure math: bid/ask imbalance, ask-stacked, bid-heavy, buying-pressure-drying-up), `labeling.py` (joins recordings to `journal` trades by symbol + closest timestamp within `L2_LABEL_MATCH_TOLERANCE_SEC`). New `GET /api/l2/recordings` route. Frontend: `ibkr/l2Heuristics.ts` mirrors the backend's single-snapshot math for live badges on `DepthLadder.tsx`.
- **Why:** Final phase of the approved "Trading Automation Machine" plan — Phase F, "record first, automate later." Builds the labeled dataset needed before any tape-based rule or model could ever be trusted enough to influence the executor.
- **Files touched:** `backend/l2/{__init__,db,store,features,recorder,labeling}.py` (new), `backend/routes/l2.py` (new), `backend/strategy/setups_stream.py` (hooks `l2_recorder.on_signal()` after journaling each signal), `backend/main.py` (router + `l2.db` init in lifespan), `backend/constants.py` (`L2_*`), `backend/tests/test_l2.py` (new, 23 tests), `frontend/src/ibkr/{l2Heuristics.ts,DepthLadder.tsx}`, `frontend/src/constants.ts` (`L2_ASK_STACKED_RATIO`/`L2_BID_HEAVY_RATIO`/`L2_SPREAD_WIDE_DOLLARS`), `frontend/src/index.css`.
- **How it works now:** `setups_stream._scan_once()` calls `l2_recorder.on_signal(symbol, setup, ts)` right after `executor.on_signal()`, in its own try/except so a recorder failure can never break the signal pipeline. `recorder.on_signal` subscribes IBKR depth via `ibkr/depth.py`'s existing refcounted subscription manager (never exceeds IBKR's symbol cap, never steps on an already-open `DepthLadder` view) and spawns a background task that snapshots `current_book()` on an interval, writing each snapshot to `l2.db` via `store.record_snapshot()`, then releases its own subscription reference when the window ends (only unsubscribing from IBKR if no other consumer still holds it). `features.py` has zero I/O — `compute_feature_dict()` is single-snapshot (imbalance, ask-stacked, bid-heavy), `compute_feature_series()` adds a trailing-window `drying_up` flag across snapshots. `labeling.label_recordings()` reads every recording's snapshots, calls `journal.store.get_trades()`, and for each recording tags the closest trade for that symbol within the tolerance window as win/loss (mock journal trades excluded by default) or `unlabeled` if nothing matches — this labeled set is the future training data and isn't consumed by anything yet. On the frontend, `l2Heuristics.ts` recomputes the same single-snapshot ratios client-side from the already-streaming `/ws/ibkr/depth/{symbol}` book so the live badge a trader sees matches exactly what gets recorded server-side; thresholds are intentionally duplicated in `frontend/src/constants.ts` (commented as mirroring backend/constants.py) since there's no shared-constants build step across the Python/TS boundary. **Deliberately not wired into the executor or risk engine** — per section 3 of `Automation-Strategy-Backbone.md`, tape-based automation waits until there are enough labeled recordings to trust a rule or model; today this is a recording pipeline plus a display aid, nothing more.
- **Verified by:** 23 new backend tests (feature math, snapshot store round-trip, recorder subscribe/unsubscribe refcounting including the "still subscribed elsewhere" case, labeling match/no-match/tolerance/mock-exclusion) — 144/144 full backend suite green. `main.py` imports and boots with `l2.db` initialized and the new router registered (58 routes total). Frontend: `tsc -b && vite build` clean, `npx eslint` clean on all new/changed files. Not yet exercised against a live IB Gateway paper session with real depth data (none was running this session) — that remains a manual verification step for whenever Gateway is up.
- **Follow-ups:** All six plan phases (A–F) are now implemented. Natural next steps beyond the plan: a small analysis script/notebook over `GET /api/l2/recordings` once enough real (non-mock) recordings exist, and eventually a learned model to replace the current rule-based badges — explicitly deferred per the backbone doc.
- **Related:** `Automation-Strategy-Backbone.md` 2026-07-11 Phase F entry.

## 2026-07-11 — Phase D: paper bracket-order execution + Arm Automation toggle + kill switch

- **What:** Nova can now place real IBKR **paper** bracket orders (entry + stop + 2:1 target) automatically when an already risk-approved setup signal fires — but only when a human has explicitly armed it. Added `ibkr.orders.place_bracket_order()` (native `ib_async` bracket, same safety gate as every other order call), a new `backend/strategy/executor.py` engine (disarmed by default and on every restart; requires armed + `risk.can_trade()` + `risk.validate_trade_plan()` + no existing position for that symbol before placing an order; a background loop detects fills and journals the closed trade), and `backend/routes/executor.py` (`GET status`, `POST arm|disarm|kill-switch|reset-kill-switch`). New **Automation** sub-tab in the Strategy tab (`ExecutorPanel.tsx`) shows armed/disarmed/kill-switch state, IBKR connection, and open automated positions; arming requires confirming a plain-language disclosure dialog first.
- **Why:** Next step in the approved "Trading Automation Machine" plan — Phase D (paper execution), the last mechanical piece before Phase F (Level 2 learning).
- **Files touched:** `backend/ibkr/orders.py` (`place_bracket_order`), `backend/strategy/executor.py` (new), `backend/strategy/setups_stream.py` (hooks `executor.on_signal()` after journaling each signal), `backend/routes/executor.py` (new), `backend/main.py` (router + `fill_poll_loop()` lifespan wiring), `backend/constants.py` (`EXECUTOR_*`), `backend/tests/test_executor.py` (new, 17 tests), `frontend/src/strategy/{types,useExecutor,ExecutorPanel,WatchlistTab}.ts(x)`, `frontend/src/constants.ts` (`EXECUTOR_POLL_INTERVAL_MS`), `frontend/src/index.css`.
- **How it works now:** `setups_stream._scan_once()` journals a signal, broadcasts it over `/ws/strategy`, then calls `executor.on_signal(symbol, setup, signal_dict)` in a try/except so an executor failure can never break the signal pipeline. `on_signal` is a pure gate chain — armed, risk-approved, no existing open position for the symbol — before calling `ibkr.orders.place_bracket_order()`, which itself still enforces `IBKR_ENABLED` / connected / paper-vs-`IBKR_LIVE_TRADING_CONFIRMED` independently (defense in depth). Open positions live in executor memory only (`_open_positions: dict[symbol, OpenPosition]`) — a background `fill_poll_loop()` polls `ibkr.orders.open_orders()` every `EXECUTOR_FILL_POLL_INTERVAL_SEC`; once none of a position's three bracket order IDs remain open, it resolves the exit price from `ib.fills()`, writes **one** `journal.store.record_trade()` row (matches the original "record only at close" design note already in `journal/store.py` — no schema change needed) with `adherent=True` (automation never deviates from the risk-approved plan), and calls `risk.record_trade_result()`. **Deliberate limitations, documented in the module docstring:** a backend restart mid-bracket loses the in-app position record (IB itself is unaffected, but that trade never gets journaled); kill switch cancels the module's own open orders but does not flatten an already-filled position. All 3 current setups are long-only, so entry side is the fixed constant `EXECUTOR_ENTRY_SIDE_IBKR = "BUY"`.
- **Verified by:** 17 new backend tests (arm/disarm/kill-switch state, every `on_signal` gate individually, fill resolution for both winning and losing exits, no-fill-found cleanup, disconnected/no-open-position no-ops) — 121/121 full backend suite green, no live IB Gateway required (IBKR + risk calls mocked). `main.py` imports and boots with the new router and background task registered (57 routes total). Frontend: `tsc -b && vite build` clean, no new ESLint errors introduced (pre-existing unrelated lint debt in `App.tsx`/`HodMomoDebugPanel.tsx`/etc. left untouched). Not yet exercised against a live IB Gateway paper session — that real-world proof is still pending a manual test with Gateway running.
- **Follow-ups:** Phase F (Level 2 learning) is next per the plan. A future durability pass could persist open positions to SQLite instead of memory-only if restart-safety becomes important before this ever nears live money.
- **Related:** `knowledge/obsidian/03-Nova-Decisions/Automation-Strategy-Backbone.md` 2026-07-11 Phase D entry.

## 2026-07-11 — Journal demo-data mode, real risk state, and UI tooltips (E2E hardening)

- **What:** Since Phase D (paper execution) doesn't exist yet, the `trades` table has no real feeder. Added an opt-in, clearly-labeled way to test the whole Journal pipeline end-to-end without ever risking confusion with real results: a new `is_mock` column on `trades` (migrated in automatically for existing DBs), a fixed 12-row synthetic dataset (`backend/journal/mock_data.py`, run via `py -3 -m journal.mock_data seed|clear`), and an `include_mock` query param on `/api/journal/{trades,metrics}` that defaults to `False` everywhere. The Journal panel gained a "Show demo data" checkbox (off by default) that shows a persistent blue "DEMO DATA ACTIVE" banner and tags every synthetic row with a `DEMO` chip whenever it's checked. Also wired in the real `/api/strategy/risk` status as a "Today's risk state" card in the Journal panel (promised but not delivered in the Phase C log), and did a pass adding `title=` hover tooltips to every interactive element and metric across the Watchlist/Signals/Journal UI so hovering anything explains exactly what it does and where its number comes from.
- **Why:** Direct user request: "loaded with mock data if we don't have real data feeder yet, and test all the logic... The UI is functional... it's well documented... when the user hovers over something it says exactly what it does... full comprehension behind the UX... we don't want automations the user is not aware of."
- **Files touched:** `backend/journal/{db,store,metrics,mock_data}.py`, `backend/routes/journal.py`, `backend/constants.py` (`JOURNAL_MOCK_TRADE_COUNT`), `backend/tests/test_journal.py` (+5 tests), `frontend/src/strategy/{types,useJournal,JournalPanel,WatchlistTab,SignalsPanel}.ts(x)`, `frontend/src/constants.ts` (`WATCHLIST_SUBSCORE_TOOLTIPS`), `frontend/src/index.css`.
- **How it works now:** `journal/db.py::init_db()` runs a small `PRAGMA table_info` migration that `ALTER TABLE`s `is_mock INTEGER NOT NULL DEFAULT 0` into any pre-existing `trades` table, so an already-running `journal.db` upgrades in place with zero data loss. Every store/metrics function takes `include_mock: bool = False`; real go/no-go math can never be inflated by demo rows unless a caller explicitly opts in. `useJournal(active, includeMock)` fetches `/api/journal/metrics`, `/api/journal/trades`, `/api/journal/signals`, and `/api/strategy/risk` together on one poll loop; the risk card is always real (it reads today's actual `RiskState`, currently all-zero because nothing feeds it real trades yet) while the demo toggle only affects the trades/metrics fetch. There is deliberately no "seed" API endpoint — loading mock data is a terminal-only dev action (`py -3 -m journal.mock_data seed`), never a button a real user could click by accident.
- **Verified by:** 104/104 backend tests passing (6 new: mock isolation on `get_trades`/`get_closed_trades`, `clear_mock_trades`, idempotent reseed, a simulated pre-`is_mock` table proving the migration preserves existing rows, and mock trades never leaking into default `compute_metrics()`). Live end-to-end: seeded the 12-row dataset against the running dev server, confirmed `/api/journal/metrics` excludes it by default and includes it with `?include_mock=true` (58.3% win rate, 2.22:1 P/L ratio, 91.7% adherence — deliberately mixed pass/fail/pending across all three go/no-go criteria), checked the "Show demo data" box in a headless browser and screenshotted the NO-GO bar, metrics grid, real risk card, and DEMO-tagged trades table all rendering correctly, then unchecked it and confirmed it reverted to the honest empty/pending state, then cleared the mock rows from the dev DB so it's clean again.
- **Follow-ups:** Phase D will start populating real `is_mock=0` trades; the demo toggle stays available afterward for regression-testing the metrics math without touching real data.
- **Related:** `PROBLEM_LOG.md` 2026-07-11 (orphaned `uvicorn --reload` worker serving stale code, found while investigating why `includes_mock_data` wasn't appearing in responses).

## 2026-07-11 — Journal SQLite + metrics + go/no-go bar (Phase E)

- **What:** New `backend/journal/` package (`db.py`, `store.py`, `metrics.py`) persists every detected setup signal to a SQLite database (`signals` table) and provides a `trades` table + `record_trade()`/`get_closed_trades()` for Phase D to populate once paper execution exists. `metrics.py` computes win rate, avg win/loss, profit/loss ratio, and the plan's three-criteria live-money go/no-go bar (>=100 closed trades, >=2:1 P/L ratio, 100% rule adherence) — reporting `met: null` (pending, not failing) when there isn't enough data yet, rather than faking a result from zero trades. Exposed via `GET /api/journal/{signals,trades,metrics}`. New **Journal** sub-tab inside the Watchlist tab renders the go/no-go bar, a metrics grid, and a table of recently detected signals.
- **Why:** Phase E of the trading automation plan — the journal must exist and log signals *before* any order is ever placed, so Phase D's paper fills have somewhere to land from day one.
- **Files touched:** `backend/journal/{__init__,db,store,metrics}.py` (new), `backend/routes/journal.py` (new), `backend/strategy/setups_stream.py` (`_record_signal` now persists to the journal), `backend/main.py` (`init_db()` at startup, router registration), `backend/constants.py` (`JOURNAL_*`), `backend/tests/test_journal.py` (new), `frontend/src/strategy/{types,useJournal,JournalPanel,WatchlistTab}.ts(x)`, `frontend/src/constants.ts`, `frontend/src/index.css`.
- **How it works now:** `journal/db.py` resolves the DB file to `paths.cache_dir()/journal.db` (same convention as `cache.py`, not git-tracked) and opens a fresh connection per call rather than holding one open across the asyncio loop and FastAPI handlers. `setups_stream._record_signal()` calls `journal.store.record_signal()` right after broadcasting over `/ws/strategy`, wrapped in try/except so a journal write failure never breaks the live signal stream. `metrics.compute_metrics()` reads only `trades` with a non-null `pnl`; with zero trades every rate is `null` and the go/no-go bar shows NO-GO with the sample-size criterion failing and the other two pending. The "adherence" criterion folds in the plan's "max daily loss never breached" gate — a trade the executor marks `adherent=False` covers any risk-rule violation, including trading through a halt.
- **Verified by:** 8 new unit tests (isolated per-test SQLite file via a `tmp_path` fixture) + 98/98 full backend suite passing; live `GET /api/journal/{metrics,signals}` verified against the running server; headless-browser screenshot confirms the Journal sub-tab renders the NO-GO bar and empty-state metrics correctly.
- **Follow-ups:** Phase D (paper execution) will call `journal.store.record_trade()` after each bracket order closes, which is what turns the go/no-go bar from all-pending into real pass/fail.

## 2026-07-11 — Risk / discipline engine (Phase C)

- **What:** New `backend/strategy/risk.py` — a pure state machine tracking today's realized P&L, win/loss streaks, and position sizing, enforcing three walk-away guardrails (daily max loss, 3 losses in a row, giving back 50% of the day's peak profit). `validate_trade_plan()` checks a proposed trade's stop distance and profit/loss ratio. Exposed via `GET /api/strategy/risk` and `POST /api/strategy/risk/validate-trade`.
- **Why:** Phase C of the trading automation plan — the discipline layer that will gate Phase D (paper execution).
- **Files touched:** `backend/strategy/risk.py` (new), `backend/routes/strategy.py`, `backend/main.py` (session-reset background task), `backend/constants.py` (`RISK_*`), `backend/tests/test_risk.py` (new).
- **How it works now:** `RiskState` is a plain dataclass; a module-level singleton is mutated by `record_trade_result()` (not yet called by anything — Phase D/E will call it after each paper fill closes). Sizing looks at *current* daily P&L (not the historical peak), so a big win followed by a big loss correctly drops back to a cut quarter size. Halting is sticky for the rest of the day once tripped; only `reset_day()` (called automatically at 4 AM ET) clears it. This module places no orders and is not yet wired to any execution path.
- **Verified by:** 15 new unit tests + 90/90 full backend suite passing; live `GET /api/strategy/risk` verified against the running server.
- **Follow-ups:** Phase E (Journal + go/no-go bar) will read this endpoint in the UI; Phase D (paper execution) will call `record_trade_result()` after each fill.

## 2026-07-11 — Setup trigger engine: Bull Flag + ABCD + live signal stream (Phase B)

- **What:** Two new signal-only setup detectors — Bull Flag and ABCD — join Gap and Go behind a shared `evaluate_setups()` aggregator. Exposed on-demand (`GET /api/strategy/setups/{symbol}`) and live over a new `/ws/strategy` WebSocket fed by a background scan loop over the top-ranked watchlist symbols. New **Signals** sub-tab inside the Watchlist tab shows live triggers with entry/stop/target math.
- **Why:** Phase B of the full trading automation plan — mechanical setup detection layered on top of the Phase A watchlist.
- **Files touched:** `backend/strategy/{indicators,bull_flag,abcd,setups,setups_stream}.py` (new), `backend/routes/strategy.py`, `backend/main.py` (`/ws/strategy` route + lifespan task), `backend/constants.py` (`BULL_FLAG_*`, `ABCD_*`, `SETUPS_*`), `backend/tests/{test_indicators,test_bull_flag,test_abcd,test_setups}.py` (new), `frontend/src/strategy/{types,useSignalsStream,SignalsPanel,WatchlistTab}.ts(x)`, `frontend/src/constants.ts`.
- **How it works now:** `bull_flag.py`/`abcd.py` are pure functions over a candidate dict + a list of 1-min OHLCV bars — no fetching, no state, `would_execute` hard-coded `False`, matching `gap_and_go.py`'s existing contract exactly. `setups_stream.py` runs a 15s loop (`SETUPS_SCAN_INTERVAL_SEC`) that re-scores the top 15 watchlist symbols, fetches fresh bars via `bars.fetch_bars` in a thread executor, and broadcasts newly-eligible signals to `/ws/strategy` clients with a 2-minute per-symbol+setup cooldown so the same trigger doesn't spam every cycle.
- **Verified by:** 34 new unit tests + 75/75 full backend suite passing; live endpoint and WebSocket both tested against the running scanner with real bars; headless-browser screenshot confirms the Signals sub-tab connects and renders.
- **Follow-ups:** Phase C (risk engine) is next per the backbone doc.

## 2026-07-11 — Watchlist dashboard (Phase A of full trading automation plan)

- **What:** New composite-ranked watchlist on top of the existing Five Pillars scorer. `GET /api/strategy/watchlist` merges gapper + gainer caches, scores every symbol, and ranks all-pillars-pass candidates first with a weighted 0-100 composite score (change %, RVOL, float tightness, catalyst freshness) breaking ties. New **Watchlist** tab in the frontend shows a ranked table with per-pillar pass/fail chips.
- **Why:** First phase of the full "5 Pillars -> setups -> risk -> journal -> paper execution -> Level 2 learning" automation plan (see `Automation-Strategy-Backbone.md`).
- **Files touched:** `backend/strategy/watchlist.py` (new), `backend/routes/strategy.py`, `backend/constants.py` (`WATCHLIST_*`), `backend/tests/test_watchlist.py` (new), `frontend/src/strategy/{types,useWatchlist,WatchlistTab}.ts(x)` (new), `frontend/src/components/TabNav.tsx`, `frontend/src/App.tsx`, `frontend/src/constants.ts`, `frontend/src/index.css`.
- **How it works now:** `watchlist.py` is pure, signal-only scoring (no fetches, no orders) reused from `five_pillars.py`. The route dedupes gapper/gainer rows by symbol and caps output at `WATCHLIST_MAX_ROWS`. The frontend polls the endpoint every 3s (`WATCHLIST_POLL_INTERVAL_MS`) regardless of active tab so the tab badge count stays live; the tab itself is a plain table reusing existing `table-wrapper`/`symbol-btn`/`positive`/`na-muted` CSS classes plus 4 new pillar-chip classes.
- **Verified by:** 12 new unit tests + 41/41 full backend suite passing; live endpoint returned 30 ranked real candidates against the running scanner; headless-browser screenshot confirms the tab renders and updates the live count badge.
- **Follow-ups:** Phase B (Bull Flag / ABCD setup triggers + signal stream) is next per the backbone doc.

## 2026-07-11 — Grounded Q&A CLI (`ask.py`) over the course knowledge base

- **What:** New `tools/course_memory/ask.py`: retrieves from Pinecone (slides + official captions) and Obsidian, then has the model answer using ONLY the retrieved blocks, with numbered citations. Out-of-scope questions return `NOT_IN_KNOWLEDGE_BASE` instead of a guess.
- **Why:** User wants a single command that asks the database and answers solely from indexed course material.
- **Files touched:** `tools/course_memory/ask.py`, `tools/course_memory/constants.py` (ASK_* tunables), `knowledge/obsidian/00-System/How-Recall-Works.md`.
- **How it works now:** `py ask.py "question"` → router (reused from `recall.py`) → top-12 Pinecone chunks + top-4 Obsidian hits capped at 24k chars → chat completion at temperature 0 with a context-only system prompt → answer + citation list. `--show-sources` prints the retrieved text. `recall.py` remains the raw-retrieval tool.
- **Verified by:** Level 2 question answered with 16 citations from SS/BA slides + transcripts; crude-oil-futures control question correctly returned `NOT_IN_KNOWLEDGE_BASE`.
- **Related:** Same-day fidelity-test entry (guarantees the underlying data is caption-exact).

## 2026-07-11 — Fidelity tests: transcripts proven identical to raw captions

- **What:** Added `tools/course_memory/test_transcript_fidelity.py` (word-for-word comparison of every exported transcript against the raw Wistia caption JSON, plus timestamp validation and provenance checks) and `verify_pinecone_sources.py` (audits Pinecone vectors by `source` metadata). Deleted the last leftover sparse-notes file (`BA101_TIMESTAMPED_NOTES.md`), which the new provenance test caught.
- **Why:** User required proof the indexed transcripts contain no hallucinations or AI rewriting.
- **Files touched:** `tools/course_memory/test_transcript_fidelity.py`, `tools/course_memory/test_obsidian_recall.py`, `tools/course_memory/verify_pinecone_sources.py`, removed `downloads/warrior-trading-caption-notes/BA101_TIMESTAMPED_NOTES.md`.
- **How it works now:** Fidelity tests parametrize over every `warrior-trading-official-captions` MD file; the full transcript text must equal the concatenated raw caption cues and every timestamp must map to a real cue start. The Pinecone audit confirms only `warrior-trading-slides` and `warrior-trading-official-captions` sources exist and the stale `warrior-trading-caption-notes` source is fully purged.
- **Verified by:** 45/45 pytest passing (incl. `test_obsidian_recall.py`: vault holds no transcript/paraphrase bodies, recall admits only official-caption files); Pinecone audit reports 1,506 vectors, stale source purged, PASS.
- **Related:** Same-day entries below on official transcripts and purge.

## 2026-07-11 — Purge inaccurate caption notes; index official LMS transcripts only

- **What:** Added `py ingest.py --official-transcripts` which deletes stale `warrior-trading-caption-notes` vectors, then upserts only `warrior-trading-official-captions` Markdown from `downloads/warrior-trading-caption-notes/`. Obsidian recall now also keyword-searches those official transcript files on disk (Whisper files excluded). Documented the accuracy model in How-Recall-Works.
- **Why:** Sparse/paraphrase notes were inaccurate; user required the knowledge stores not learn non-video-aligned text.
- **Files touched:** `tools/course_memory/{ingest,constants,extract_markdown,pinecone_store,obsidian_store}.py`, `knowledge/obsidian/00-System/How-Recall-Works.md`.
- **How it works now:** Default transcript ingest is official LMS subtitle tracks only. Whisper gap transcripts stay local until `--include-whisper`. Slide PDFs unchanged.
- **Verified by:** Dry-run (18 files / 426 chunks / official source only); live purge+upsert 426 vectors; recall queries return `warrior-trading-official-captions`.
- **Follow-ups:** Optional opt-in Whisper indexing after manual spot-checks; do not claim absolute 100% ASR accuracy.
- **Related:** Real transcript export from same day.

## 2026-07-11 — Real video-aligned transcripts (official captions + Whisper)

- **What:** Replaced sparse title-only caption notes with real timestamped transcripts. For 18 LMS units with English captions, exported the official Wistia subtitle track. For 7 local BA101 MP4s that had no caption track, extracted audio with ffmpeg and transcribed via OpenAI Whisper.
- **Why:** Prior notes were paraphrased topic titles, not video-aligned speech. User asked for transcripts that match the videos without downloading more remote video.
- **Files touched:** `downloads/warrior-trading-caption-notes/` (local transcripts + `_export_official_transcripts.py`, `_whisper_local_videos.py`), Obsidian course index pointers under `knowledge/obsidian/01-Courses/`.
- **How it works now:** Official-caption units use the same text/timing as the LMS player. Gap units use local audio only (`_audio_cache/`). Full transcripts stay under gitignored `downloads/`; Obsidian holds path indexes only.
- **Verified by:** DE101 mentor-session MD now shows real spoken lines at matching timestamps; Whisper wrote 7 BA101 gap transcripts; frontend build + app already running.
- **Follow-ups:** Optional Pinecone re-ingest of transcript Markdown; Whisper remaining courses only if local videos exist.
- **Related:** Replaces the sparse-note approach from 2026-07-10.

## 2026-07-10 — Timestamped LMS notes in Obsidian and Pinecone

- **What:** Added source-aware Markdown ingestion and per-unit note export to the course-memory tooling, plus curated timestamped notes for captioned BA101, SS101, Live Trading Archive, and Platform Demo units. Inventoried all 12 enrolled LMS courses without downloading videos or storing full transcripts.
- **Why:** The user wanted caption-derived strategy material to complement the existing slide PDFs in both Obsidian and Pinecone.
- **Files touched:** `tools/course_memory/{constants,extract,extract_markdown,export_unit_notes,chunk,ingest,pinecone_store,recall}.py`, `tools/course_memory/test_extract_markdown.py`, `knowledge/obsidian/00-System/How-Recall-Works.md`, `knowledge/obsidian/01-Courses/`, `PROBLEM_LOG.md`.
- **How it works now:** `py ingest.py --content markdown` splits curated course notes by Markdown section, preserves course/source/unit/timestamp metadata, and upserts them into the existing course namespace. Recall output labels slide versus caption-note provenance and prints arbitrary Unicode safely on Windows.
- **Verified by:** Six pytest tests; 18 per-unit Markdown exports; Markdown dry run (4 files, 25 chunks); Pinecone upsert (25 vectors); successful Pinecone queries for VWAP and IPO/slippage notes; successful Obsidian query for simulator loss controls; frontend production build and browser launch.
- **Follow-ups:** Only 13 of 538 additional detected Wistia videos expose English captions. Add future notes incrementally when the LMS publishes more caption tracks or official handouts.
- **Related:** Updated the 2026-07-10 Windows `UnicodeEncodeError` entry in `PROBLEM_LOG.md`.

## 2026-07-10 — Five Pillars scoring + Gap and Go signal (Phase 1, signal-only)

- **What:** Added `backend/strategy/` with two pure-logic modules: `five_pillars.py` scores
  any candidate stock dict against the 5 Pillars (price, % change, relative volume, catalyst,
  float) and returns a ✅ checkmark only when all 5 pass; `gap_and_go.py` layers on the 9:30–10:00
  AM ET entry window and a pre-market-high breakout check, computing entry/stop/target from
  `constants.py` thresholds. Exposed read-only via three new `GET /api/strategy/*` endpoints
  (`backend/routes/strategy.py`). 22 new pytest unit tests run against mock data.
- **Why:** User asked to formalize the 5 Pillars as a pass/fail checklist with a checkmark,
  verify it with unit tests against mock data, and implement Gap and Go as the first automated
  setup — while guaranteeing no hidden automation (every automated capability must be legible
  to the user).
- **Files touched:** `backend/constants.py` (new `FIVE_PILLARS_*` / `GAP_AND_GO_*` constants),
  `backend/strategy/__init__.py`, `five_pillars.py`, `gap_and_go.py`, `backend/routes/strategy.py`,
  `backend/main.py` (router registration only), `backend/tests/test_five_pillars.py`,
  `test_gap_and_go.py`, `knowledge/obsidian/02-Strategies/Five-Pillars-and-Gap-and-Go-Spec.md`,
  `knowledge/obsidian/03-Nova-Decisions/Automation-Strategy-Backbone.md` (decision log).
- **How it works now:** Both strategy modules are pure functions over plain dicts — no network
  calls, no state, no order-placing code path anywhere in either file. `GapAndGoSignal` hard-codes
  `would_execute = False`. The new routes are strictly `GET` (no `POST`/`PUT`/`DELETE`) and every
  response carries a `note` field stating it never places, modifies, or cancels orders. `routes/strategy.py`
  imports `main` lazily inside functions (same pattern as `hod_momo_enrichment.py`) to avoid a
  circular import with `main.py`, which registers the router. There is still no "Automate" button
  in the UI — this is backend signal logic only; the transparency principle (every automation
  control must state what it does/doesn't do, in plain language, next to the control) is now
  written into the backbone doc so it applies whenever that UI is built.
- **Verified by:** `py -3 -m pytest backend/tests/ -v` → 30/30 passed (22 new + 8 pre-existing
  IBKR safety tests unaffected). Confirmed `main.py` still imports cleanly with the new router
  registered (no circular-import regression).
- **Follow-ups:** No UI panel yet for these signals; Phase 2 (paper execution via IBKR) is not
  started — see backbone doc §5 for the phased plan and go/no-go bar before any order is placed.

## 2026-07-10 — Dual memory: Pinecone course RAG + Obsidian vault + recall router

- **What:** Added `tools/course_memory/` to ingest Warrior slide PDFs into Pinecone, plus an Obsidian vault at `knowledge/obsidian/` for curated Nova decisions. `recall.py` auto-routes questions to Obsidian, Pinecone, or both.
- **Why:** User wants accurate long-term recall of course material and a place for “what should Nova automate?” decisions without manually choosing a database.
- **Files touched:** `tools/course_memory/*`, `knowledge/obsidian/**`, `.env.example`, `.gitignore`.
- **How it works now:** PDFs → chunk/embed → Pinecone (`ingest.py`). Decisions live in Obsidian notes. Ask via `py recall.py "…"`. Router: Nova/build/decide → Obsidian first; course/setup/rules → Pinecone first; ambiguous → both. Trust order: Obsidian decisions > Pinecone citations > model guesses.
- **Verified by:** `ingest.py --dry-run` (1080 chunks from 34 1pp PDFs); `recall.py` Obsidian path after Unicode fix.
- **Follow-ups:** User adds `PINECONE_API_KEY` + `OPENAI_API_KEY`, runs full `ingest.py`, opens vault in Obsidian.

## 2026-07-10 — IBKR optional trading module (Level 2 depth + paper order execution)

- **What:** Added an opt-in Interactive Brokers trading module alongside the existing Alpaca-powered scanner. New "Trading" tab provides IBKR connection status, Level 2 order book (with L1 fallback while entitlement processes), an order ticket (market + limit, buy + sell), and a positions/account panel. All existing Alpaca tabs (Gappers, Movers, Afterhours, Catalysts, HOD Momo) are untouched.
- **Why:** User requested IBKR integration for Level 2 data and paper/live order execution. Alpaca has no L2; IBKR is the cheapest option (~$27.50/mo) with a 3-symbol simultaneous depth cap.
- **Files touched:** `backend/ibkr/` (new package: `client.py`, `depth.py`, `orders.py`, `account.py`), `backend/routes/` (new: `trading.py`, `__init__.py`), `backend/constants.py` (IBKR_* constants), `backend/requirements.txt` (`ib_async`), `backend/main.py` (router wire-in + lifespan hooks only), `frontend/src/ibkr/` (new module: all types, hooks, DepthLadder, OrderTicket, PositionsPanel, TradingTab), `frontend/src/components/TabNav.tsx` (new: tab bar extracted + Trading tab added), `frontend/src/App.tsx` (imports + new tab panel only), `frontend/src/constants.ts` (IBKR_* constants), `frontend/src/index.css` (IBKR styles + badge styles), `.env.example` (IBKR vars), `gemini.md` + `AGENTS.md` (Invariant #7 amendment), `backend/tests/test_ibkr_safety.py` (pytest coverage).
- **How it works now:** `IBKR_ENABLED` defaults `false` — Nova behaves exactly as before when the flag is absent or when IB Gateway isn't running. Setting `IBKR_ENABLED=true` in `.env` activates the client; it connects to IB Gateway paper port (4002) automatically and reconnects on drop. For live money, `IBKR_LIVE_TRADING_CONFIRMED=true` is also required (hard gate in `orders.py`). The depth subscription manager caps at 3 simultaneous symbols and falls back to L1 top-of-book if depth entitlement is not yet active. Nova does NOT launch Gateway — user runs it manually once per week (IBKR Mobile 2FA).
- **Verified by:** Frontend TypeScript build (`npm run build`), `pytest backend/tests/test_ibkr_safety.py` (all tests pass without a live Gateway), manual dev run confirming existing tabs render identically and Trading tab shows the disconnected guide when Gateway is not running.
- **Follow-ups:** Automated momentum strategy execution (needs user-provided symbol list + strategy rules), bracket/OCO order support.
- **Related:** gemini.md §11 maintenance-log entry 2026-07-10.

## 2026-07-10 — Windows Electron desktop + local API sidecar

- **What:** Added an Electron shell around the existing Vite/React UI and a local FastAPI sidecar (dev: `run_api.py` / packaged: PyInstaller `nova-api.exe`). Web UI on Vercel is unchanged.
- **Why:** User wants a full local stack (faster/stabler for a future trading machine) plus an installable Windows app, without rewriting the scanner UI.
- **Files touched:** `frontend/electron/*`, `frontend/package.json`, `frontend/vite.config.ts`, `frontend/src/main.tsx`, `frontend/src/constants.ts`, `backend/run_api.py`, `backend/paths.py`, `backend/nova_api.spec`, `backend/main.py`, `backend/cache.py`, `backend/constants.py`, `backend/hod_momo.py`, `README.md`.
- **How it works now:** `npm run electron:dev` starts Vite + Electron; Electron spawns the API on `127.0.0.1:8000`, waits for `/api/health`, then loads the UI. `npm run electron:pack` builds the sidecar, builds the renderer with `base: './'`, and produces an NSIS installer via electron-builder. Desktop data lives under `%APPDATA%\Nova` via `NOVA_ENV_PATH` / `NOVA_CACHE_DIR` / `NOVA_LOG_DIR`.
- **Verified by:** `npm run build` (web) OK; Electron launched against Vite and reused healthy API; packaged `nova-api.exe` returned `/api/health` connected; `electron-builder` produced `Nova-Setup-0.1.0.exe` (~156 MB).
- **Follow-ups:** App icon / code-signing; if `frontend/release` hits Windows EPERM during pack, build with `--config.directories.output` under `%TEMP%`.

## 2026-05-06 — Add nova.altaystudio.com domain to Vercel

- **What:** Assigned the custom domain `nova.altaystudio.com` to the frontend Vercel project (`stock-alert`).
- **Why:** To make the stock alert frontend accessible via a branded, production-ready domain.
- **Files touched:** None locally (Vercel configuration only).
- **How it works now:** Vercel will automatically route requests for `nova.altaystudio.com` to the latest production deployment of the frontend.
- **Verified by:** Vercel CLI domain addition success output.

## 2026-05-04 — Add frontend-specific Railway configuration

- **What:** Added `frontend/railway.toml` to explicitly configure the builder and healthcheck for the frontend service.
- **Why:** Railway's monorepo deployment was attempting to use the root `/railway.toml` (which uses a Python Dockerfile) for the frontend service, causing builds to fail. This file instructs Railway to use Nixpacks/Railpack for the frontend directory.
- **Files touched:** `frontend/railway.toml`
- **How it works now:** The frontend service will use this specific configuration file when the "Config as code" path in Railway is pointed to `/frontend/railway.toml`.
- **Verified by:** Merged PR #1 generated by Railway AI.

## 2026-05-04 — Fix invalid GitHub Actions workflow and clean up pycache

- **What:** Fixed a parsing error in `.github/workflows/deploy.yml` that prevented CI checks from running. Removed `__pycache__` directories from Git tracking.
- **Why:** GitHub Actions does not allow accessing repository secrets in job-level conditionals. This caused the entire CI check suite to fail immediately, which in turn blocked Railway from deploying the frontend. Python bytecode files were also accidentally committed.
- **Files touched:** `.github/workflows/deploy.yml`, `backend/__pycache__/`
- **How it works now:** The deployment step now runs and checks if `$RAILWAY_TOKEN` is set using bash. If it is omitted, the step skips gracefully without failing the job, allowing Railway's native deploy to proceed.
- **Verified by:** Pushed the commit and verified the CI check suite executes.
- **Related:** PROBLEM_LOG 2026-05-04

## 2026-04-28 — HOD Momo RVOL fallback to yfinance for IEX feed

- **What:** The HOD Momo scanner now uses `yfinance` to compute RVOL when running on the IEX free tier. A 5-minute warmup grace period has been added to allow strategies to fire without RVOL while fundamentals load in the background. The UI now displays a "YF" badge next to yfinance-sourced RVOLs and a banner explaining the IEX data source.
- **Why:** The scanner was failing to trigger any alerts because Alpaca's IEX feed historical bars are mostly empty, causing the average volume to be zero. Since RVOL was always null on IEX, the `master_rvol:unknown` gate blocked all alerts.
- **Files touched:** `backend/constants.py` (warmup grace and batch size), `backend/main.py` (`_fetch_fundamentals` extracts volumes), `backend/hod_momo.py` (`rvol_source` tracking and warmup bypass), `backend/hod_momo_enrichment.py` (feed-level switch to calculate RVOL), `frontend/src/hod_momo/types.ts` (`rvol_source`), `frontend/src/hod_momo/HodMomoTab.tsx` (YF badge and IEX banner), `frontend/src/App.tsx`, `frontend/src/index.css`.
- **How it works now:** In `hod_momo_enrichment.py`, if the active feed is `iex`, the pipeline bypasses Alpaca bars and proactively queues the ticker for `yfinance` fundamentals. `_fetch_fundamentals` grabs `average_volume` and `current_volume` from yfinance's `.info`, and the enrichment loop calculates RVOL from those two values. The symbol's snapshot is tagged with `rvol_source="yfinance"`. On the UI, this badge clarifies the origin of the data.
- **Verified by:** Verified `/api/hod-momo/debug/snaps` returns `rvol_source: "yfinance"` and populated RVOL fields.
- **Related:** PROBLEM_LOG same date.

## 2026-04-28 — Configurable data feed (IEX/SIP) with auto-fallback

- **What:** The Alpaca data feed is now selectable from the UI Settings panel (IEX or SIP), shown as a badge in the header, and persisted to `.env`. If SIP is selected but the user's plan doesn't support it, the system automatically falls back to IEX on 403/409 errors — with a visible "⚠ fallback" indicator in the header so the user knows.
- **Why:** The backend was hardcoded to default to `sip`, which requires a paid Alpaca subscription. Free-tier accounts got 403s on REST and 409s on WebSocket, resulting in empty gapper lists with no explanation. This was the root cause of the "no gappers" issue on 2026-04-28.
- **Files touched:** `backend/constants.py` (new `DATA_FEED_DEFAULT`, `DATA_FEED_OPTIONS`), `backend/main.py` (feed tracking, fallback logic, config endpoints, health/gappers responses), `backend/bars.py` (use `DATA_FEED_DEFAULT`), `frontend/src/constants.ts` (feed labels), `frontend/src/App.tsx` (settings dropdown, header badge, fallback hint), `frontend/src/index.css` (feed badge + select styles), `.env` (add `ALPACA_DATA_FEED=iex`).
- **How it works now:** `_active_feed` tracks the runtime feed (initialized from env → `DATA_FEED_DEFAULT`). On SIP rejection (403 REST or 409 WS), `_try_fallback_to_iex()` switches to IEX once per session and the caller retries. The feed badge in the header shows `IEX` (blue) or `SIP` (purple). Settings panel has a dropdown to change it. The `/api/health` and `/api/gappers` responses include `data_feed` and `feed_fell_back` fields.
- **Verified by:** `npm run build` clean, `py -3 -c "import py_compile; py_compile.compile('main.py')"` clean.
- **Related:** PROBLEM_LOG same date.

## 2026-04-23 — Skip `railway up` deploy job when `RAILWAY_TOKEN` is unset

- **What:** The **Deploy to Railway** job’s `if` now requires `secrets.RAILWAY_TOKEN != ''`. Header comments mark the token as optional when using Railway-only Git deploys.
- **Why:** An empty or placeholder secret still made the job run and fail; operators who only use Railway’s dashboard deploy don’t need `railway up` from GitHub at all. A bad/expired token still fails until the user replaces it at https://railway.com/account/tokens .
- **Files touched:** `.github/workflows/deploy.yml`.

## 2026-04-23 — Fix backend CI when pytest collects zero tests (exit 5)

- **What:** The `Run tests` step in `.github/workflows/deploy.yml` wraps pytest in `set +e` / `set -e` so exit code **5** (“no tests collected”) is handled before `errexit` kills the step.
- **Why:** Default Actions `bash` uses `-e`; `pytest` returning 5 made the step fail immediately, so the “treat 5 as OK” branch never ran and **Backend tests** failed even with no tests.
- **Files touched:** `.github/workflows/deploy.yml`.

## 2026-04-23 — Manual `workflow_dispatch` for CI / Deploy

- **What:** Added `workflow_dispatch` to `.github/workflows/deploy.yml`.
- **Why:** Operators may see the workflow listed with zero runs; they can start it from the Actions UI without an empty commit.
- **Files touched:** `.github/workflows/deploy.yml`.

## 2026-04-23 — GitHub Actions vs Railway `prebuild` (fix CI blocking Railway)

- **What:** `check-railway-api-base.mjs` treats a build as “Railway” only when `RAILWAY_PROJECT_ID` is set **and** `GITHUB_ACTIONS` is unset. The `frontend-build` job uses a bash default for `VITE_API_BASE_URL` when the Actions variable is empty.
- **Why:** Frontend deploys on Railway were **SKIPPED** (“CI check suite failed”) while **Wait for CI** was on. Copying `RAILWAY_PROJECT_ID` into GitHub made `prebuild` think the GitHub runner was Railway and require `VITE_API_BASE_URL` there.
- **Files touched:** `frontend/scripts/check-railway-api-base.mjs`, `.github/workflows/deploy.yml`.

## 2026-04-23 — Tab bar scroll so HOD Momo stays reachable

- **What:** `.tab-bar` now uses horizontal `overflow-x: auto` with `flex-wrap: nowrap`; `.tab` uses `flex-shrink: 0`.
- **Why:** `.main-col` has `overflow: hidden`, so on typical viewports the fifth tab (**HOD Momo**) was clipped with no way to scroll to it — production looked like the feature was missing.
- **Files touched:** `frontend/src/index.css`.

## 2026-04-23 — Wrap scanner tabs in `.tab-bar-scroll` (fix HOD Momo still hidden)

- **What:** Tab buttons live inside `.tab-bar-scroll` (`flex: 1; min-width: 0; overflow-x: auto`); “updated … ago” is a sibling `.tab-bar-meta` (`flex-shrink: 0`). Removed the old `.tab-spacer` flex filler between tabs and the timestamp.
- **Why:** A single flex row with `flex: 1` spacer between the last tab and the timestamp prevented the scroll region from shrinking, so **HOD Momo** stayed clipped even after adding `overflow-x: auto` on the outer `.tab-bar`.
- **Files touched:** `frontend/src/App.tsx`, `frontend/src/index.css`.

## 2026-04-23 — Inject API base into `index.html` for Railway static hosts

- **What:** `vite.config.ts` adds a `<meta name="nova-api-base" content="…">` at build time from `VITE_API_BASE_URL` / `NOVA_API_BASE` (same `process.env` Railway uses for `vite build`). `main.tsx` reads that meta first. `/config.json` is only trusted when the response looks like JSON (avoids accepting SPA fallback HTML that returned HTTP 200).
- **Why:** On Railway, `/config.json` was missing from the deploy artifact; the static server returned `index.html` with status 200, JSON parse failed, and the app fell back to `localhost` — “Backend unreachable” despite a correct `VITE_API_BASE_URL` variable.
- **Files touched:** `frontend/vite.config.ts`, `frontend/src/main.tsx`.
- **Verified by:** `npm run build` with and without `VITE_API_BASE_URL`; with env set, `dist/index.html` contains the meta tag and `dist/config.json` is written.

## 2026-04-23 — `/api/health` no longer stuck on `loading` without Alpaca keys

- **What:** On startup, if `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` are missing, the backend now sets cached health to `status: "error"` with an explanatory message and logs a warning, instead of leaving the default `loading` forever (which happened because `_ping_health` was never called).
- **Why:** Railway operators often omit broker keys at first; `/api/health` then looked like a hung request and was confused with “wrong host” or localhost routing.
- **Files touched:** `backend/main.py`.
- **Verified by:** Code path review; local uvicorn would log the warning when env vars are absent.
- **Related:** `PROBLEM_LOG.md` same date.

## 2026-04-23 — API root JSON + F12 API diagnostics

- **What:** FastAPI now serves `GET /` with a small JSON payload pointing to `/api/health` and `/docs` so opening the backend host in a browser is not mistaken for a broken deploy. The frontend logs structured errors on scanner fetch failure (`API_URL`, `API_BASE_URL`, hint to try `/api/health`). Optional verbose traces via `?apiDebug=1` or `localStorage.setItem('novaApiDebug','1')` plus `/config.json` resolution logging in `main.tsx`. Added `frontend/src/debug.ts`.
- **Why:** Operators saw `{"detail":"Not Found"}` at `/` and assumed the backend was down; that response was FastAPI’s default empty root. Separately, debugging “unreachable” needed clearer console and Network-tab guidance.
- **Files touched:** `backend/main.py`, `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/debug.ts`.
- **Verified by:** `npm run build` in `frontend/`; local `curl` to `/` after deploy is optional.
- **Related:** Same-day entries on Railway API base.

## 2026-04-23 — Runtime API base via `config.json` and bootstrap

- **What:** `main.tsx` now resolves the backend URL before loading `App`: use inlined `VITE_API_BASE_URL` when present, otherwise `fetch('/config.json')`. A `postbuild` script writes `dist/config.json` from `VITE_API_BASE_URL` or `NOVA_API_BASE` so production can reach the API even when Vite did not bake the variable into the bundle. `constants.ts` reads `window.__NOVA_API_BASE__` set during that bootstrap. HoD MoMo debug fetches use `API_BASE_URL` + `/api` paths instead of a hardcoded localhost.
- **Why:** The deployed Railway bundle still contained only `http://localhost:8000` while the dashboard variable was set—some builds were not inlining `VITE_*` into JS. Serving `config.json` from the same static origin avoids relying on that substitution alone.
- **Files touched:** `frontend/src/main.tsx`, `frontend/src/constants.ts`, `frontend/scripts/write-dist-api-config.mjs`, `frontend/scripts/check-railway-api-base.mjs`, `frontend/package.json`, `frontend/src/hod_momo/HodMomoDebugPanel.tsx`, `frontend/.env.example`.
- **How it works now:** Production: bootstrap loads `/config.json` when needed, sets `window.__NOVA_API_BASE__`, then the app module graph loads. Local `npm run dev` unchanged (no config file). Railway builds still require `VITE_API_BASE_URL` or `NOVA_API_BASE` so `postbuild` can emit `config.json`.
- **Verified by:** `npm run build` without env (no `config.json`); with `VITE_API_BASE_URL=https://stockalert-production.up.railway.app`, `dist/config.json` contains that URL.
- **Related:** Same-day PROBLEM_LOG entry.

## 2026-04-23 — Railway frontend builds must set `VITE_API_BASE_URL`

- **What:** Added `frontend/scripts/check-railway-api-base.mjs` and an npm `prebuild` hook so builds on Railway fail fast if `VITE_API_BASE_URL` is missing (otherwise Vite embeds `http://localhost:8000` and production shows “backend unreachable”). GitHub Actions workflow now runs on `master` as well as `main`, and the Railway deploy job runs on pushes to either branch.
- **Why:** Deployed frontend JS still pointed at localhost because the env var is only read at **build** time; adding it in the dashboard without a **redeploy** left an old bundle. “Wait for CI” on Railway also never saw a passing workflow when the repo only used `master`.
- **Files touched:** `frontend/scripts/check-railway-api-base.mjs`, `frontend/package.json`, `.github/workflows/deploy.yml`.
- **How it works now:** Local `npm run build` is unchanged. On Railway (`RAILWAY_PROJECT_ID` set), `prebuild` requires `VITE_API_BASE_URL` before `vite build`. After setting the variable, trigger a new Frontend deployment so the bundle is rebuilt.
- **Verified by:** `npm run build` in `frontend/` succeeds locally; same with `RAILWAY_PROJECT_ID=1` set and `VITE_API_BASE_URL=https://example.com` the prebuild passes (manual check).
- **Related:** `PROBLEM_LOG.md` same date.

## 2026-04-17 — Add agent-maintained CHANGELOG.md and `change-log` rule

- **What:** Introduced `CHANGELOG.md` at the repo root and a new always-on rule `.cursor/rules/change-log.mdc` that requires agents to prepend a human-readable summary after every non-trivial task. Sits alongside the existing `problem-log.mdc` / `commit-after-tasks.mdc` policies.
- **Why:** Reading raw diffs or `git log` is too slow when re-entering the project. The user wants a single "swipe through and understand" file, especially the *"how it works now"* narrative that commits and bug logs don't capture.
- **Files touched:** `CHANGELOG.md` (new), `.cursor/rules/change-log.mdc` (new).
- **How it works now:** Three agent-maintained docs cover different questions: `CHANGELOG.md` = "what does this codebase do now and why" (newest-first, prepend on every task), `PROBLEM_LOG.md` = "what bug happened and how was it fixed" (newest-first, prepend on resolutions), `.cursor/rules/*.mdc` = persistent policies. Task completion is not done until the changelog entry exists and ships in the same commit as the code.
- **Verified by:** Built and ran the app via `Run Stock Alert.bat` (uvicorn on `:8000`, Vite on `:5173`) — no code paths changed, doc-only change.
- **Follow-ups:** `progress.md` and `findings.md` (Phase-0 leftovers, last touched 2026-04-13) overlap with this file and should probably be archived or deleted in a future task.
- **Related:** Mirrors the newest-first `<!-- ENTRIES_START -->` convention in `PROBLEM_LOG.md`.
