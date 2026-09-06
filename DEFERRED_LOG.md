# Deferred log (agent-maintained -- MANDATORY)

This file is the **shared parking lot for work we already know about and did not do**. Known bugs found mid-task. Features the human asked for that got parked because they are too big, need an ADR, or were the wrong job for that session.

**Mandatory for every agent** in this project (parent sessions and all Nova specialists). Rule: `.cursor/rules/deferred-log.mdc`. Finding a real bug (or parking a real feature) and walking away with no entry here is a constitution violation -- same severity as skipping `PROBLEM_LOG.md` after a real fix. Lifecycle footers must declare `deferred_log=<D-NNN>|none|skipped|n/a`.

This is **not** `PROBLEM_LOG.md` (that is closed: symptom / cause / fix). This is **not** `Nova-Roadmap-Status.md` (that is product NEXT / phases L-Z). This is **not** an agent-memory Backlog (those are specialist scratchpads; they are not the SSOT).

Ranked list without reading the whole file:

```text
py -3 tools/deferred_log.py status
py -3 tools/deferred_log.py priorities
py -3 tools/deferred_log.py next-id
```

`priorities` is the same ranked list as `status`. When the human asks "what's on the to-do / what's missing / priorities," run that command -- do not invent a second tracker.

Every new chat also sees open P0/P1 items in the session-start fleet brief.

## How to triage (so a human can decide)

| Field | What it answers |
|-------|-----------------|
| **Kind** | `bug` (wrong today) / `feature` (wanted, not built) / `decision` (blocked on a human call) |
| **Severity** | `P0` desk-broken, wrong money, trading safety, cannot operate. `P1` daily-use wrong (a column, a number, a control the operator uses every session). `P2` edge session / annoying / honesty gap that is not silent-wrong-money. `P3` polish. |
| **Effort** | `S` hours in one session. `M` a full session, shape is known. `L` architectural / multi-session / needs an ADR. |
| **Why parked** | Doing other work / too big for this task / needs an ADR / blocked on a human decision. Never "didn't feel like it." |
| **Blast radius** | What else is lying or missing while this stays open. |
| **Unblock** | The one decision or missing piece that lets an agent start. |
| **Next** | One concrete first step, not a design essay. |
| **Evidence** | How we know it is real (endpoint, screenshot, log line). No entry without this. |

Pull into a session when: severity is P0, or the human names the ID, or you are already in that module and Effort is S. Do **not** silently expand the current task into an L item -- write it here and finish what you were asked.

## How agents update this file

1. **When:** You found a real bug and did not fix it this session; or the human asked for a feature you parked; or you fully diagnosed a root cause and deferred the patch. Search this file first -- extend an existing ID rather than duplicating.
2. **Where (open):** Prepend a new `## D-NNN` section **immediately below** the `<!-- OPEN_START -->` marker. IDs are durable. Get the next one with `py -3 tools/deferred_log.py next-id`. Never reuse an ID.
3. **Where (done):** Cut the whole `##` section from Open into Closed (below `<!-- CLOSED_START -->`), set **Status:** `done`, add **Closed:** date plus **Related:** PROBLEM_LOG / CHANGELOG / task-log. Do not delete history.
4. **Keep it short:** A few lines per field. No secrets, tokens, or personal data.

Entry template (copy and fill in):

```markdown
## D-NNN -- Short descriptive title

- **Status:** open
- **Kind:** bug | feature | decision
- **Severity:** P0 | P1 | P2 | P3
- **Effort:** S | M | L
- **Domain:** market-feed | news | execution | hod-momo | ...
- **User-visible:** yes | no
- **Logged:** YYYY-MM-DD
- **Why parked:** One or two sentences. Name the task you were in.
- **Blast radius:** What else is wrong or missing while this stays open.
- **Unblock:** The decision or missing piece that lets an agent start.
- **Next:** One concrete first step.
- **Evidence:** Endpoint, log line, or screenshot that proves it.
- **Keywords:** comma, separated, terms, for, search
```

**Status values:** `open` (actionable) | `blocked` (waiting on Unblock) | `parked` (explicitly not this month) | `wontfix` (human said no) | `done` (belongs in Closed).

<!-- OPEN_START -->

> **2026-09-06 deep-dive batch (D-011 .. D-040).** Read-only audit of every product section (execution, IBKR feed, frontend honesty, news/HOD/fundamentals, persistence, CI/ops, tests). No code was changed. Gates at audit time: pytest 1481 passed, Vitest 858 passed, `tsc`/`vite build` green, ESLint 4 errors + 6 warnings, ruff 11 findings. Narrative: `knowledge/task-log/2026-09-06-deferred-log-deep-dive.md`. Pull P0 first (D-011), then the spend-safety pair (D-037, D-038), then the P1 honesty cluster (D-021, D-022, D-023, D-014).

## D-040 -- `POST /api/config` rewrites `.env` with no auth on loopback

- **Status:** open
- **Kind:** decision
- **Severity:** P2
- **Effort:** M
- **Domain:** security
- **User-visible:** no
- **Logged:** 2026-09-06
- **Why parked:** `auth.py` documents the open-loopback posture as a single-operator desktop choice, so this is a decision to record, not a bug to patch silently. CORS is restricted to `CORS_ALLOWED_ORIGINS_DEFAULT`, which limits browser-origin abuse; any local process can still call it.
- **Blast radius:** `routes/health.update_config` persists Alpaca keys / base URL / feed settings into the env file for any unauthenticated request on `127.0.0.1:8000`. A bad or malicious local write breaks news + listing metadata until an operator notices, and there is no audit line of who changed what.
- **Unblock:** Operator decision: require `NOVA_API_KEY` for mutating routes even on loopback (Electron can inject it), or accept the posture and add a write-audit log line.
- **Next:** At minimum log every `update_config` diff (keys redacted) at INFO; then decide on the key requirement.
- **Evidence:** `backend/auth.py:3-4,36-48`; `backend/routes/health.py:144-180`; `backend/app_lifespan.py:95-110` (CORS defaults).
- **Keywords:** /api/config, update_config, .env write, loopback, NOVA_API_KEY, CORS, audit log

## D-039 -- Scanner reqIds survive a full reconnect; Error 101 has no ticker budget

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** S
- **Domain:** market-feed
- **User-visible:** yes (Error 101 = new symbols get no L1)
- **Logged:** 2026-09-06
- **Why parked:** Two CHANGELOG follow-ups (lines 1732, 1832) that never became entries; both are on the IB socket so they need a live reconnect to verify.
- **Blast radius:** `discovery._inflight_scan_reqids` is never cleared when `reconnect_loop` builds a fresh `IB()`; a new socket invalidates old reqIds, so `recover_scanner_slots` can try to cancel ids the new session never issued. `session_errors.py` names Error 101 (max tickers) but nothing budgets `reqMktData` lines across scanner owner + HOD pool + detail + depth fallback (D-020) + listing_flags -- when the Gateway limit trips, new roster names silently sit at `price=null`.
- **Unblock:** None.
- **Next:** Clear `_inflight_scan_reqids` in `client._on_session_ready`; count live `reqMktData` lines per owner in `ticks.py` and expose the total + IB limit in `/api/ibkr/status` so Error 101 becomes a visible number before it fires.
- **Evidence:** `backend/ibkr/discovery.py:65,205,250,302,337`; `backend/ibkr/session_errors.py:5-6`; CHANGELOG 1732, 1832.
- **Keywords:** _inflight_scan_reqids, reconnect, reqId, recover_scanner_slots, Error 101, max tickers, reqMktData budget, price=null

## D-038 -- Live spend allowed with `broker_account_kind=unknown`; `spend_status` follows the env door, not the account

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** S
- **Domain:** execution
- **User-visible:** yes (spend chip can say `live_armed` on a paper socket, or arm before the account class is known)
- **Logged:** 2026-09-06
- **Why parked:** Found in the execution pass; it is a two-line gate change on `safety.py` but it is spend-gating code (Invariant #7 / ADR 013), so it must ship with tests and a paper attach check rather than in a docs session.
- **Blast radius:** `assert_place_allowed` paper branch refuses `kind != "paper"`; the live branch requires `IBKR_LIVE_TRADING_CONFIRMED` and refuses only `kind == "mixed"` -- `unknown` (managedAccounts not yet received) and `paper` both pass on a live door. `status_snapshot()` derives `spend_status` from `IBKR_GATEWAY_MODE` alone (`live_armed` / `paper_armed`), while ADR 013 makes `broker_account_kind` the capsule truth, so the header can show live-armed with a `DU...` account behind it.
- **Unblock:** None.
- **Next:** Refuse live place unless `kind == "live"`; compute `spend_status` from `(mode, kind)` and add `armed_for_account_kind`; tests for live+unknown and live+paper.
- **Evidence:** `backend/ibkr/safety.py:120-137` (live branch), `:66-88` (`status_snapshot`); ADR 013.
- **Keywords:** assert_place_allowed, broker_account_kind unknown, live_armed, spend_status, IBKR_LIVE_TRADING_CONFIRMED, managedAccounts, ADR 013, Invariant 7

## D-037 -- Kill switch does not stop manual / hotkey places, is memory-only, cancels brackets only

- **Status:** open
- **Kind:** decision
- **Severity:** P1
- **Effort:** M
- **Domain:** execution
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** `docs/trading-execution-validation.md` documents manual places skipping risk/concurrency as intentional discretionary trading, so the current shape is a product choice -- but "kill" reading as "automation only" is not what an operator under stress expects. Needs an explicit human call before any code moves.
- **Blast radius:** `service.execute` checks `is_kill_switch_tripped()` only inside `if not cmd.skip_risk`; `routes/trading_execution.py` sets `skip_risk=True, skip_concurrency=True` on manual place / bracket / hotkey paths, so a tripped kill still lets the Trading ticket and Nova Actions spend. `_kill_switch_tripped` is a module bool cleared by an API restart (no `reset_kill_switch()` needed to re-arm). `kill_switch()` cancels only tracked Nova OS parents; manual working LMTs survive. Cancel-all loops per-order `execute(cancel)` with fresh UUIDs and no global "orders paused" latch, so a place can land between cancels.
- **Unblock:** Operator decision: does Kill mean "stop Nova automation" (current) or "no Nova-originated spend of any source until reset"?
- **Next:** If the latter: check the kill flag before `skip_risk`, persist it in the execution ledger with a `schema_version`, and make kill cancel every open Nova order via `reqOpenOrders`; write the manual-place-under-kill test first.
- **Evidence:** `backend/execution/service.py:207-216`; `backend/routes/trading_execution.py:93-94,117-118,176-177`; `backend/strategy/executor.py:17,66,204-235`; `docs/trading-execution-validation.md`.
- **Keywords:** kill switch, skip_risk, manual place, hotkey, _kill_switch_tripped, restart clears kill, cancel unfilled parents only, cancel-all latch, KILL_SWITCH

## D-036 -- Untracked product follow-ups from CHANGELOG (UI + execution + HOD)

- **Status:** open
- **Kind:** feature
- **Severity:** P2
- **Effort:** L (as a set; each item S-M)
- **Domain:** widgets | execution | hod-momo
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** Found while mining 261 CHANGELOG `Follow-ups:` bullets during the deep-dive. These were named as real gaps at ship time and never got a `D-NNN`, so every new chat rediscovers them. Recording, not building.
- **Blast radius:** (a) Main scanner `activeTab` is not persisted across reload (resets to Gappers; HOD dock does persist). (b) Large Cap historical date-picker is not wired in the UI although `/api/history/large_cap/{date}` works. (c) Scanner Exchange column is a best-effort label because IB scan rows rarely carry `primaryExchange`; a per-row-accurate label needs a qualified-contract lookup. (d) Order ticket has no TIF/GTC or bracket TP/SL defaults on the backend. (e) Journal-on-close, IB `CommissionReport` net P/L, Reports import UI, and an Activity/trail page were all promised and not built. (f) Hotkeys Settings tab renders `HOTKEYS_TAB_SOON` ("Coming soon") for the non-default sub-tab and `OrderTicket.tsx` ships a permanently disabled "Automate (coming soon)" button. (g) Former Momo curated list holds 39/40 HOD slots and crowds live table-ranked admission (2026-07 WLDS case) -- a prune / raise-capacity / reserve decision is still owed. (h) L1-rolled 1Min bars carry `volume=0` until the ~30s hist reconciliation, so the VWAP tip lags 1-2 minutes; requesting generic tick `233` (RTVolume) would also give IBKR's own session VWAP as a free cross-check.
- **Unblock:** Human ranks the sub-items; (g) needs an explicit operator decision.
- **Next:** Split this entry into per-item `D-NNN`s the first time one is pulled; do not fix all eight in one session.
- **Evidence:** CHANGELOG lines (2026-09-06 snapshot): 643 (activeTab, `l1_active_hod` counter), 408 (Large Cap date-picker), 418 (exchange label), 1215 (TIF/GTC), 765/775/785 (journal-on-close, CommissionReport, Reports import, Activity page), 1666 (Former Momo 39/40), 380 (volume=0 VWAP lag, tick 233). `frontend/src/hotkeys/HotkeyManager.tsx:201`, `frontend/src/ibkr/OrderTicket.tsx:67-74`.
- **Keywords:** follow-ups, activeTab persist, large cap history, exchange label, TIF, GTC, bracket defaults, journal-on-close, CommissionReport, Reports import, Former Momo 39/40, volume=0, RTVolume 233, Coming soon, Automate

## D-035 -- Premarket stack must be up before 04:00 ET without a human (Jul 30 OPEN)

- **Status:** blocked
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** ibkr-ops
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** PROBLEM_LOG 2026-07-30 is still marked `OPEN/DEFERRED` and Roadmap-Status reliability WS1 is `[~]`, but nothing pointed at it from this file, so `deferred_log.py status` did not list the single most operator-visible morning failure. Recording here so it ranks with the other P1s. The fix is operator-side (Task Scheduler + IBC overnight) plus one evidence line.
- **Blast radius:** If API or Gateway comes up after 09:30 ET, that day's Gappers table is empty for the whole session by design (ADR 008 freeze). Every late morning start is a lost Gappers day. CHANGELOG 351 also notes the IBC `AutoRestartTime` overnight verification is still outstanding.
- **Unblock:** First real 03:55 ET line in `backend/logs/morning-check.log` from an unattended `NovaDailyStart` run (Roadmap-Status WS1 proof), plus one week with no unexpected IBC `Login attempt` other than the weekly 2FA.
- **Next:** Operator runs `.\scripts\Install-NovaDailyTask.ps1` once, enables wake timers, configures one Phase D channel; next morning an agent checks `morning-check.log` and `ibc` log, then closes both this entry and the Jul 30 PROBLEM_LOG line.
- **Evidence:** `PROBLEM_LOG.md` 2026-07-30 "OPEN/DEFERRED: Premarket stack must be up before 04:00 ET"; `Nova-Roadmap-Status.md` reliability table WS1 `[~]`; CHANGELOG 351 "Overnight verification still outstanding".
- **Keywords:** NovaDailyStart, 04:00 ET, morning-check.log, IBC AutoRestartTime, gappers empty after open, WS1, overnight Gateway, 2FA

## D-034 -- Stale comments and dead code contradict the ADRs

- **Status:** open
- **Kind:** bug
- **Severity:** P3
- **Effort:** S
- **Domain:** docs | market-feed
- **User-visible:** no
- **Logged:** 2026-09-06
- **Why parked:** Docs-only drift found across the deep-dive; each is a one-line fix but none belonged to the audit task.
- **Blast radius:** A future agent reading `scanner_l1.py` or `ibkr_bridge.hod_stream_symbols` sees "HOD discovery remains independent (volume seeds)" and "includes off-table volume seeds" -- exactly the side-channel scan ADR 008 bans -- and may "restore" it. `discovery.py` keeps a dead `_snapshot_lock` / `_get_snapshot_lock` next to ADR 010's single `cold_slot`, inviting a second mutex. `cache.py:29` still says "then Railway volume". `test_hod_pipeline_fake_feed.py` docstring says a reconnect test is an `xfail` although the G1 gap was fixed in `79f749e` and no xfail exists.
- **Unblock:** None.
- **Next:** Fix the four comments in one docs commit; delete `_get_snapshot_lock` if `rg` confirms zero callers.
- **Evidence:** `backend/ibkr/scanner_l1.py:4-6`; `backend/ibkr_bridge.py:194-196`; `backend/ibkr/discovery.py:52,80-84`; `backend/cache.py:29`; `backend/tests/test_hod_pipeline_fake_feed.py:11` vs `docs/audits/2026-07-28-hod-scanner-capture-audit.md` §5b.
- **Keywords:** volume seeds, ADR 008, _snapshot_lock, cold_slot, Railway comment, xfail docstring, stale comment

## D-033 -- Test coverage holes on the paths that lose money or freeze the desk

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** M
- **Domain:** tester
- **User-visible:** no
- **Logged:** 2026-09-06
- **Why parked:** Coverage inventory from the deep-dive; writing these tests is soft-TDD work for whoever pulls the matching D entry, not a standalone task.
- **Blast radius:** No test exists for: two concurrent same-symbol SELLs with different idempotency keys (D-011); kill switch vs `source=manual` place (D-012); live + `broker_account_kind=unknown` refuse (D-013); BUY cover qty vs `short_qty` (D-015); ledger `reserved`/`sent` reconcile on restart (D-014); hotkey double-fire (D-014); cancel-all atomic vs concurrent place. Frontend: no Vitest for `useTickerStream`, `useIbkrDepth`, `useIbkrTape` hook lifecycle (symbol gate, reconnect timer cancel, cleanup) -- only the pure helpers are tested. About 25 backend test files use real-time `sleep(` for flush/race windows (e.g. `test_hod_momo_consolidation.py` `asyncio.sleep(1.2)`), a CI flake source.
- **Unblock:** None.
- **Next:** When pulling any of D-011..D-015 or D-021, write the failing test named above first. Separately, replace the longest `asyncio.sleep` waits with injected clocks.
- **Evidence:** `rg -l "useTickerStream|useIbkrDepth|useIbkrTape" frontend/src --glob '*.test.*'` returns no hook tests; execution suite covers duplicate key, live-unconfirmed, LMT BUY BP, flat SELL, short matrix only (see `backend/tests/test_execution*.py`).
- **Keywords:** coverage, untested gates, useTickerStream test, sleep flake, soft TDD, idempotency race test

## D-032 -- Electron sidecar restart race and unsaved window geometry

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** M
- **Domain:** ibkr-ops | widgets
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** Desktop-shell finding; needs a Windows desk to reproduce. Backend lock orphan is already D-005; this is the Electron side of the same restart story.
- **Blast radius:** `restartApiSidecar` does `stopApiSidecar()` -> fixed 500 ms sleep -> `startApiSidecar()`; a concurrent `nova:restartApi` IPC or the `BackendStartButton` auto-heal can overlap and produce "health timed out" / Start API loops, or a second `run_api.py` fighting `api-instance.lock`. Main and detached Trader window bounds are never persisted, so every launch resets size/position (pop-out per monitor is an ADR 011 selling point).
- **Unblock:** None.
- **Next:** Serialize restart through one in-flight promise in `sidecar.mjs`; persist `BrowserWindow` bounds per window id in the Electron user-data dir with a `schema_version`.
- **Evidence:** `frontend/electron/sidecar.mjs:205-222`; `frontend/electron/main.mjs` fixed `windowOptions`; `frontend/electron/traderWindows.mjs` has no bounds save.
- **Keywords:** restartApiSidecar, sidecar.mjs, 500ms, double start, window bounds, traderWindows, Electron

## D-031 -- Frontend speed: full-grid re-render per price patch, 705 kB App chunk, oversized CSS

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** M
- **Domain:** widgets
- **User-visible:** yes (jank on busy Gainers / Large Cap; slower cold load)
- **Logged:** 2026-09-06
- **Why parked:** Performance shape, not a wrong number. Needs a profiler session on a live premarket desk to prove the win before touching table rendering.
- **Blast radius:** `components/ScannerTable.tsx` (288 lines) has no `React.memo` row boundary and no virtualization, so every `/ws/scanner` `price_patch` re-renders the entire visible grid (HOD alert table already virtualizes). `vite build` emits `App-*.js` at 705 kB minified (rolldown warning, no route/tab code splitting). `styles/settings-workspace.css` (1187) and `stock_view/stockViewTerminal.css` (1078) exceed the 1000-line stylesheet rule; `constantGroups/chart_api.ts` (670) and `market_ui.ts` (587) exceed the 400-line TS rule.
- **Unblock:** None.
- **Next:** Memoize `ScannerTable` rows keyed by symbol and patch only the changed row; then lazy-load the Settings / Reports / Backtest tabs to split the App chunk.
- **Evidence:** `/tmp/build.log` 2026-09-06: `dist/assets/App-Do4hKVkR.js 705.58 kB`, "(!) Some chunks are larger than 500 kB"; `tools/maintainer_checks.py` FILE_SIZE rows for the four files.
- **Keywords:** ScannerTable, re-render, price_patch, virtualization, chunk size, code splitting, settings-workspace.css, stockViewTerminal.css, chart_api.ts, market_ui.ts

## D-030 -- Railway leftovers still runnable; api-console.log never rotates

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** S
- **Domain:** ibkr-ops | docs
- **User-visible:** no
- **Logged:** 2026-09-06
- **Why parked:** CHANGELOG 964 already said "optional delete of deprecated `railway.toml` / `check-railway-api-base.mjs` once no env still sets `RAILWAY_*`"; nobody owned it. Log rotation is a launcher change.
- **Blast radius:** `railway.toml` (root + backend), both `Dockerfile`s (bind `0.0.0.0`), `paths.py` reading `RAILWAY_VOLUME_MOUNT_PATH`, and `frontend/package.json` `prebuild` still running `scripts/check-railway-api-base.mjs` keep a retired deploy path alive; `doc_invariants.py` guards docs, not these files. `scripts/Start-NovaApi.ps1` appends to `api-console.log` with `>>` and no rotation while `blast.log` / `hod_momo.log` do rotate -- multi-day desks grow the file without bound and crash triage gets slow.
- **Unblock:** Confirm no operator machine sets `RAILWAY_*` (grep `.env`).
- **Next:** Delete the Railway files and the `prebuild` hook in one commit; wrap the launcher log in a dated filename or size cap.
- **Evidence:** `railway.toml:1` "DEPRECATED (2026-08-05)"; `frontend/package.json` `"prebuild": "node scripts/check-railway-api-base.mjs"`; `scripts/Start-NovaApi.ps1` ~55 `>> "$LogFile"`; `backend/logging_setup.py` RotatingFileHandler only for the Python loggers.
- **Keywords:** railway.toml, Dockerfile 0.0.0.0, RAILWAY_VOLUME_MOUNT_PATH, check-railway-api-base, prebuild, api-console.log, log rotation

## D-029 -- CI does not run lint, Vitest, Playwright, or ruff; master is ESLint-red

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** tester
- **User-visible:** no
- **Logged:** 2026-09-06
- **Why parked:** Found by running every gate locally during the deep-dive. Adding CI jobs is its own change with its own flake risk (see D-004 Vitest lock path) and was out of scope for a docs-only audit.
- **Blast radius:** `.github/workflows` runs only `pytest backend/` and `npm run build`. `npm run lint` is not in CI and master already carries 4 ESLint errors + 6 warnings (`prefer-const` in `chart/barsStore.ts:150` and `chart/chartDrawingsStore.ts:137`, `no-extra-boolean-cast` x2 in `hotkeys/effectiveBindings.ts:52`, plus exhaustive-deps warnings). `npx vitest run` (858 tests) is never executed in CI. The 10 Playwright specs under `frontend/e2e/` are never run anywhere; `agent_fleet` records 3 of them as historically failing on the Stock View header. `ruff check backend` reports 11 findings (F401, F841, TRY400, E741, B008) and ruff is in `requirements-dev.txt` but not the workflow. Security scanners (gitleaks / osv / semgrep / `security_audit.py`) are `continue-on-error: true`, and `pytest` exit 5 is treated as green. Net: a frontend test regression, a lint regression, or a new HIGH vuln all merge green.
- **Unblock:** Fix D-004 first (Vitest must not touch `backend/.cache/start-api.lock`), otherwise the new Vitest job flakes on the operator machine only.
- **Next:** Add `npm run lint` + `npx vitest run` to `frontend-build`, fix the 4 ESLint errors in the same PR; add `ruff check backend` to `backend-test`; decide whether Playwright runs nightly against the sample-data shell.
- **Evidence:** `/tmp/eslint.log` 2026-09-06 "10 problems (4 errors, 6 warnings)" EXIT=1; `python3 -m ruff check backend` "Found 11 errors"; `rg -n "vitest|eslint|playwright|ruff" .github/workflows/*.yml` returns nothing; `deploy.yml` `continue-on-error: true` on security jobs.
- **Keywords:** CI, eslint, vitest, playwright, ruff, warning-only, continue-on-error, exit 5, frontend-build, backend-test

## D-028 -- HOD / alert honesty: mutual-vouch integrity, memory-only Large Cap dedupe, cooldown 0

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** S
- **Domain:** hod-momo
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** Three small alert-side gaps found in the deep-dive; each is S but they sit on live alert logic and need a live HOD session to verify.
- **Blast radius:** `hod_momo_integrity_scanner.py` still passes an empty Gappers/Losers with "OK if another scanner list is live" when the sibling is also empty (only the Gainers check fails loud) -- the exact two-empty-tables-vouch pattern `verification-before-completion.mdc` warns about. `large_cap_alerts._fired_today` is an in-memory dict, so an API restart re-fires the same Large Cap breakout to Discord/Telegram. `HOD_MOMO_COOLDOWN_SEC` defaults to `0.0`, so per-(symbol, strategy) dedupe is consolidation-window only unless the operator config raises it (needs confirmation what production configs hold).
- **Unblock:** None.
- **Next:** Make the sibling-vouch check require the sibling to actually be `live` with rows; persist `_fired_today` in the dated Large Cap snapshot with a `schema_version`.
- **Evidence:** `backend/hod_momo_integrity_scanner.py:154-186`; `backend/large_cap_alerts.py:25-60`; `backend/constants_hod_momo.py` `HOD_MOMO_COOLDOWN_SEC = 0.0`; `backend/hod_momo_trade.py:198-207,329-331`.
- **Keywords:** integrity, OK if another scanner list is live, mutual vouch, _fired_today, large_cap_alerts, restart re-fire, HOD_MOMO_COOLDOWN_SEC

## D-027 -- Depth cap force-evicts a live viewer instead of refusing the 4th symbol

- **Status:** open
- **Kind:** decision
- **Severity:** P2
- **Effort:** M
- **Domain:** market-feed
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** Capacity policy question, not a bug in isolation. PROBLEM_LOG 2026-08-25 fixed the silent variant (now logs a warning + pushes an error), but the eviction itself remains. ADR 011 says a 4th live symbol is blocked with a notice at the UI, so the backend eviction should be unreachable -- worth proving rather than assuming.
- **Blast radius:** When all `IBKR_MAX_DEPTH_SYMBOLS` slots have `viewer_count > 0`, `depth/subscribe.py` picks `others[0]`, zeros its `_ws_viewers`, and unsubscribes it. An operator with three real Trader L2 ladders who opens a fourth (or whose UI cap check races a detached window) loses an active ladder.
- **Unblock:** Operator decision: hard-refuse the 4th (return `capacity` error, keep the three live) vs LRU-evict.
- **Next:** Add a test that a 4th subscribe with three live viewers is refused and the three ladders keep streaming; then delete the force-evict branch or gate it behind `viewer_count == 0` only.
- **Evidence:** `backend/ibkr/depth/subscribe.py:147-168` ("force-evicting depth slot %s (viewer_count=%s, possible leak)").
- **Keywords:** depth cap, IBKR_MAX_DEPTH_SYMBOLS, force-evict, viewer_count, Level 2, TRADER_MAX_TABS, ADR 011

## D-026 -- Roster commit mutates state then reports failure if the WS push throws

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** S
- **Domain:** market-feed
- **User-visible:** yes (REST and WS disagree on the roster revision)
- **Logged:** 2026-09-06
- **Why parked:** Ordering bug inside `scanner_hydrate.commit_table`; needs a fenced test around the persistent-roster path (ADR 008), which the deep-dive did not have time to write.
- **Blast radius:** `commit_table` sets `state.<rows>`, calls `mark_live`, and persists **before** `broadcast_roster_replace`; if the broadcast raises, it logs at DEBUG and returns `False`. Callers and metrics treat the commit as failed while `/api/movers` already serves the new revision that no WebSocket client received -- split-brain between REST and the desk until the next commit.
- **Unblock:** None.
- **Next:** Either broadcast inside the same try and return `True` with a `push_failed` counter, or log at WARNING and schedule a re-broadcast; add a test that a raising broadcaster still yields a consistent REST/WS revision.
- **Evidence:** `backend/ibkr/scanner_hydrate.py:149-175` (`logger.debug("scanner_stream: roster push failed", exc_info=True); return False`).
- **Keywords:** commit_table, broadcast_roster_replace, mark_live, split-brain, revision, scanner_hydrate, ADR 008

## D-025 -- Historical fills still sleep on the IB loop for short pacing waits

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** M
- **Domain:** market-feed
- **User-visible:** yes (L1 ticks pause while a chart waits)
- **Logged:** 2026-09-06
- **Why parked:** Residual of the ADR 012 pacing work; the long 10-minute-bucket waits were moved to `call_later` (D-003 lineage) but the same-contract / identical-request waits were not. Related to D-003 but distinct: D-003 is about paint time, this is about what the loop does while waiting.
- **Blast radius:** `historical_service.request_bars` does `await asyncio.sleep(extra)` for the 2 s same-contract / 15 s identical-request windows while holding the hist semaphore on the IB loop. Up to ~15 s of loop occupancy per `open_chart` under identical-request pressure; `reqMktData` L1 ticks share that loop (same failure class as the 2026-08-18 Gainers freeze).
- **Unblock:** None -- shape is known (`call_later` reschedule like the bucket path).
- **Next:** Route the short waits through the same `call_later` reschedule used for bucket debt and release the semaphore while deferred; assert with a fake clock that no `sleep` > 0.5 s runs on the IB loop.
- **Evidence:** `backend/ibkr/historical_service.py:180-204` ("historical fill deferred %s %s: wait %.1fs priority=%s (in flight)" then `await asyncio.sleep(extra)`).
- **Keywords:** historical_service, asyncio.sleep, pacing, same-contract 2s, identical-request 15s, IB loop, call_later, ADR 012

## D-024 -- Unbounded in-process growth on a day-long desk

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** S
- **Domain:** market-feed
- **User-visible:** no (RSS growth; eventual slowdown)
- **Logged:** 2026-09-06
- **Why parked:** Five small leaks found across modules during the deep-dive; each is a one-line eviction but they need a soak to prove RSS is flat afterwards.
- **Blast radius:** `discovery._qualified_contracts` keeps every snapshotted symbol forever and is not cleared on READY (stale `Contract` objects reused after reconnect). `tape_stream._subscribe_locks` / `_cancelled_at` keep an entry per Trader symbol ever opened. `fundamentals._fundamentals_cache` checks TTL on read but never evicts expired keys while `mover_enrich_hooks` warms new symbols every roster commit. `archive/bar_builder._open` keeps a bucket per quiet tape symbol until an explicit flush (no `flush_elapsed` like `l1_minute`). Frontend `useSignalsStream` prepends every signal to state with no cap.
- **Unblock:** None.
- **Next:** Add a bounded LRU / TTL sweep to each map; log the map sizes in `/api/metrics/ops` so the soak has a number.
- **Evidence:** `backend/ibkr/discovery.py:49,452-477`; `backend/ibkr/tape_stream.py:44-50,314,402`; `backend/fundamentals.py:21-22,153-159`; `backend/archive/bar_builder.py:34,41-70`; `frontend/src/strategy/useSignalsStream.ts:54`.
- **Keywords:** memory leak, _qualified_contracts, _subscribe_locks, _cancelled_at, fundamentals cache evict, bar_builder _open, useSignalsStream unbounded, RSS

## D-023 -- Eleven independent `/api/ibkr/status` pollers; a failed poll keeps "connected"

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** ibkr-ops | widgets
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** Cross-cutting hook refactor (11 mount sites) found during the frontend honesty pass; needs one shared poller/context, which is bigger than the audit.
- **Blast radius:** `useIbkrStatus` is mounted in 11 non-test call sites (WorkspaceContext, Header, EmptyState, TradingTab, Prerequisites, ManualOrderTicket, StockViewPage, ...); each runs its own 5 s `setInterval` against `:8000`, so the desk fires ~2 status requests/second at idle. On fetch failure the `catch` is empty and the hook keeps the last-good `connected: true` from sessionStorage, so the Desk chip / Trading gate can say connected while `/api/ibkr/status` is unreachable. The same poll loops (`useScannerData.fetchData`, `useIbkrStatus`, `HodMomoIntegrityBanner`, `useGatewayDoorTrail`) have no in-flight guard, so slow responses stack and can apply out of order. Reconnect backoffs have no jitter (scanner cap 15 s, depth/tape 30 s), so every window reconnects in lockstep after a Gateway bounce. Poll intervals (`5_000`) and caps are inline literals, not `constantGroups`.
- **Unblock:** None.
- **Next:** Lift status polling into one provider (single interval, in-flight guard, `stale_since` on consecutive failures) and have the 11 callers read context; mark the chip stale after N missed polls.
- **Evidence:** `rg -l "useIbkrStatus\(" frontend/src --glob '!*.test.*' | wc -l` = 11; `frontend/src/ibkr/useIbkrStatus.ts:58-80` (empty `catch`, `setInterval(poll, 5_000)`); `frontend/src/hooks/useScannerPriceStream.ts:207-213`.
- **Keywords:** useIbkrStatus, poll fan-out, last-good connected, sessionStorage, in-flight guard, jitter, backoff, 5_000, Desk chip

## D-022 -- Scanner tables can look live while the feed is down or L1 never arrived

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** market-feed | widgets
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** Honesty cluster found in the frontend pass. Backend WS3 already ships `table_state` / `roster_ts` / `feed_error`; the UI does not paint most of it. Each piece is S but they should land together so the header, table chrome, and empty state tell one story.
- **Blast radius:** (1) `useScannerData.setTableRows` keeps the previous rows when a `roster_replace` or REST poll carries `[]` (deliberate last-good since 2026-07-20) but nothing on screen says "last-good / feed down", so yesterday's names read as a live list after a Warning 165 batch or disconnect. (2) `useScannerPriceStream.pricesStale` is `false` when `lastPriceTs === 0` unless the heartbeat is stale, and `ScannerBarBridge` falls back to roster `lastScan` for the age chip -- a green "Xs ago" with zero L1 ever received. (3) `subscriptionError` (L1 capacity / tab subscription failure) is computed and returned but never rendered anywhere; the operator sees a generic stale state with no cause. (4) `ScannerTabPanels.frozenTableLabel` handles only `state === 'frozen'`; `unavailable` is stored from the WS but not shown. (5) `EmptyState` tells the operator to "check the integrity banner" but `HodMomoIntegrityBanner` is mounted only inside the HOD Momo tab. (6) Catalysts / history fetch failures are swallowed and the table says "No news catalysts found yet -- scan running", so a dead feed and an empty market look identical.
- **Unblock:** None -- backend fields already exist.
- **Next:** Add a `lastGood` flag to the scanner store set when an empty payload was ignored; render `feed_error` / `subscriptionError` / `unavailable` as one chip text; make the price age chip say "no L1 yet" when `lastPriceTs === 0`.
- **Evidence:** `frontend/src/hooks/useScannerData.ts:30-36`; `frontend/src/hooks/useScannerPriceStream.ts:238-242`; `frontend/src/components/ScannerBarBridge.tsx:41-48`; `frontend/src/components/ScannerTabPanels.tsx:67-70`; `frontend/src/components/EmptyState.tsx:72-77` vs `HodMomoTab.tsx:183`; `frontend/src/components/CatalystsTable.tsx:186-189`.
- **Keywords:** last-good rows, setTableRows, pricesStale, lastPriceTs, subscriptionError, table_state unavailable, feed_error, EmptyState, integrity banner, catalysts empty, honesty

## D-021 -- Quote Panel ticker WebSocket never reconnects; stale price with no badge

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** market-feed
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** Found in the frontend pass and confirmed by reading the hook. Every other Nova WS hook (`useScannerPriceStream`, `useIbkrDepth`, `useIbkrTape`, `useHodMomoStream`, `useSignalsStream`) has backoff reconnect; this one is the odd one out and the fix touches the Quote Panel loading states.
- **Blast radius:** `useTickerStream` `onclose` / `onerror` only clear `loading` / `refreshing` and set `fetchFailed` **if no `initial` was received**. After an API restart or Gateway blip the Quote Panel keeps the last price/daily bar indefinitely with no reconnect timer and no stale marker; `rel_volume` keeps recomputing from the frozen snapshot. The HTTP seed `catch` and the `JSON.parse` `catch` are empty, so nothing ever surfaces. Combined with D-023 (status chip keeps last-good "connected") an operator can trade off a frozen quote.
- **Unblock:** None.
- **Next:** Copy the `useIbkrDepth` reconnect shape (backoff ref + timer ref + cleanup) into `useTickerStream`, expose `stale`/`disconnectedSince` in the returned state, and add the first Vitest for this hook (symbol switch clears state; close schedules reconnect; unmount cancels timer).
- **Evidence:** `frontend/src/hooks/useTickerStream.ts:163-184` (no `setTimeout(connect ...)`, no backoff); `:69-71` and `:158-160` empty catches; `frontend/src/ibkr/useIbkrDepth.ts:30-43,104-110` for the reference pattern.
- **Keywords:** useTickerStream, /ws/ticker, reconnect, onclose, stale quote, Quote Panel, fetchFailed, backoff, empty catch

## D-020 -- Off-owner `reqMktData` and a 1.8 s sleep on the IB loop (listing_flags, depth fallback)

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** S
- **Domain:** market-feed
- **User-visible:** yes (desk-wide L1 pause when a ticker detail opens)
- **Logged:** 2026-09-06
- **Why parked:** Found in the feed pass; the fix is small but sits on the shared IB socket and needs a live pacing check (blast-radius rule) that a docs-only session cannot run.
- **Blast radius:** `ibkr/listing_flags.py` opens its own `ib.reqMktData(contract, "236", ...)` then `await asyncio.sleep(1.8)` on the IB loop for the shortability tick; `listing_compare.fetch_shortability` wraps that in a sync `run_coro` from ticker builders. Every Stock View / detail open can pause the whole IB loop ~2 s per symbol and holds a second L1 line outside `ticks.py` ownership (Error 101 budget). `depth/subscribe.py` similarly opens a private `reqMktData` when `ticks.get_ticker` is None and never registers it in `ticks._subs`, so it can outlive the owner map after a reconnect. Timeouts `1.8` / `10.0` are inline, not in `constants_ibkr.py`.
- **Unblock:** None.
- **Next:** Route shortability through `ticks.subscribe(owner="listing")` with an event wait instead of a sleep, and make the depth fallback register an owner; move the two timeouts to `constants_ibkr.py`.
- **Evidence:** `backend/ibkr/listing_flags.py:21,111-114`; `backend/listing_compare.py:53-61`; `backend/ibkr/depth/subscribe.py:108-121`; `backend/ibkr/depth/handlers.py:110-125`.
- **Keywords:** listing_flags, shortable 236, asyncio.sleep 1.8, reqMktData owner, ticks._subs, depth fallback, Error 101, run_coro, ADR 010

## D-019 -- `apply_l1_quote` rebuilds every scanner cache list on each IB tick

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** market-feed
- **User-visible:** yes (loop lag spikes on a busy desk)
- **Logged:** 2026-09-06
- **Why parked:** Hot-path shape found in the feed pass; the rewrite touches the row-patch contract with `/ws/scanner` and needs a soak with `ib_loop_lag_ms` before/after.
- **Blast radius:** For every L1 quote, `ibkr_bridge.apply_l1_quote` list-comprehends new `gainer_cache`, `loser_cache`, `afterhours_cache`, `large_cap_cache` lists (touching each row to find the one symbol), may call `gapper_view.refresh`, and stamps `*_cache_ts` -- all on the IB callback path. Cost is roster size x tick rate on the same loop that carries scanner leases and orders; with 50 Gainers + 50 Large Cap + AH at premarket tick rates this is a steady CPU tax that shows up as `ib_loop_lag_ms` with no historical work in flight.
- **Unblock:** None.
- **Next:** Keep a `symbol -> row` index per table and patch the single row in place (immutability for frozen tables is already enforced upstream by `is_table_frozen`); measure `ib_loop_lag_ms.p95` before/after in `/api/metrics/ops`.
- **Evidence:** `backend/ibkr_bridge.py:250-325` (`state.gainer_cache = [_touch_row(r, ...) for r in state.gainer_cache]` repeated per table).
- **Keywords:** apply_l1_quote, O(n) per tick, gainer_cache rebuild, ib_loop_lag_ms, IB callback path, scanner_l1.on_l1_quote, hot path

## D-018 -- Historical fills write SQLite synchronously on the IB loop

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** market-feed
- **User-visible:** yes (L1 freezes during big chart fills)
- **Logged:** 2026-09-06
- **Why parked:** ADR 010 / ADR 012 gap found in the feed pass; tape and L1 already enqueue archive writes, hist does not. Needs the same queue plumbing plus a `wedged` soak, not a docs session.
- **Blast radius:** `historical_service.request_bars` runs under `assert_ib_loop()` and calls `bars_store.read` (SQLite open + select) and `bars_store.write_payload` (upsert per bar + coverage + `commit()`) inline. A 1441-bar 10Sec or multi-day 1Min fill blocks the IB loop for the duration of the disk write, the same class of stall as the 2026-08-18 archive-write wedge that `verification-before-completion.mdc` calls out ("Archive write path / SQLite on a callback").
- **Unblock:** None.
- **Next:** Hand `write_payload` to the archive write queue (or `asyncio.to_thread` -- allowed here because it is SQLite, not `ib.*`) and read the store off-loop before the request; verify `ib_loop_lag_ms.wedged` stays false while a cold 10Sec fill lands.
- **Evidence:** `backend/ibkr/historical_service.py:96,100,216,238-251`; `backend/bars_store.py:98-133` (`conn.execute(_HIST_UPSERT_SQL ...)` in a loop then `conn.commit()`).
- **Keywords:** historical_service, bars_store.write_payload, sqlite on IB loop, assert_ib_loop, wedged, ADR 010, ADR 012, archive write queue

## D-017 -- Persisted files still ship without `schema_version` (backend JSON + frontend localStorage)

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** M
- **Domain:** market-feed | hod-momo | news | widgets
- **User-visible:** no (until a schema change loads half-shaped rows)
- **Logged:** 2026-09-06
- **Why parked:** `persisted-state.mdc` names three known gaps and says "do not add a fourth"; the deep-dive found the list is much longer. Fixing means a load-path migration per file, which is a real change on restore paths that feed live rosters.
- **Blast radius:** Backend, no `schema_version`: dated `gappers-*/gainers-*/losers-*/movers-*/afterhours-*/large_cap-*.json`, `hod-momo-alerts-*.json`, `hod-momo-highs-*.json` (all via `cache._atomic_write` with `{date, ts, rows}`), `news_catalyst_persist` snapshot, `hod-momo-blocklist.json` (`{"symbols": [...]}`), `hod-momo-session-focus.json`, `alerts_channels.json` (holds webhook secrets; corrupt file logs ERROR then returns an empty channel list, so outbound alerts silently stop until re-entered). Frontend localStorage keys with no version/migration: `useExchangeFilter` (raw string array), `ChartGrid` `CHART_GRID_OPTIONAL_STORAGE_KEY`, `stockViewDockPersist`, `useOrderTableSort` (the layout store and hotkey profile do version). A restart after a payload change restores whatever parses.
- **Unblock:** None.
- **Next:** Add `schema_version` + refuse-loud to `cache._atomic_write` payloads in one pass (one constant per prefix), then the three named files, then a tiny versioned `readPref/writePref` helper on the frontend.
- **Evidence:** `backend/cache.py:234,270,284,324,352,380,425,473,559`; `backend/news_catalyst_persist.py:14-17`; `backend/hod_momo_session_focus.py:198-205`; `backend/alerts/channels_store.py:90-111`; `frontend/src/hooks/useExchangeFilter.ts`, `frontend/src/components/ChartGrid.tsx`, `frontend/src/stock_view/stockViewDockPersist.ts`, `frontend/src/ibkr/useOrderTableSort.ts`.
- **Keywords:** schema_version, persisted-state, _atomic_write, dated snapshot, blocklist, session-focus, alerts_channels, localStorage, migration, refuse-loud

## D-016 -- yfinance failure caches an empty row for 15 minutes, silently

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** S
- **Domain:** market-feed
- **User-visible:** yes (Float / Short Int. / Mkt Cap / RVOL blank for a whole scan cycle)
- **Logged:** 2026-09-06
- **Why parked:** Found in the enrichment pass; the fix is small but changes the cache contract used by mover, HOD, and Large Cap enrichment, so it deserves its own test.
- **Blast radius:** `fundamentals.fetch_fundamentals` catches `Exception`, stores `_EMPTY` under the symbol, stamps a fresh `now`, and returns -- with **no log line**. A transient Yahoo / network / rate-limit failure blanks float, short interest, market cap and the RVOL denominator for the full `FUNDAMENTALS_CACHE_TTL` (900 s) across every table, indistinguishable from "no float on file". Each call also spins a fresh `ThreadPoolExecutor(max_workers=1)` around `yf.Ticker(...).info`, and the batch warm is serial over missing symbols.
- **Unblock:** None.
- **Next:** Log the failure at WARNING with `describe_exc`, store a short negative-TTL (e.g. 60 s) instead of the full TTL, and reuse one executor; add a test that a raising fetch is retried after the short TTL.
- **Evidence:** `backend/fundamentals.py:103-106,150-162` (`except Exception: empty = dict(_EMPTY); _fundamentals_cache[symbol] = empty; _fundamentals_cache_ts[symbol] = now`); `backend/constants_scanner.py` `FUNDAMENTALS_CACHE_TTL = 900`.
- **Keywords:** fundamentals, yfinance, _EMPTY, negative cache, FUNDAMENTALS_CACHE_TTL, silent except, float blank, RVOL denominator, ThreadPoolExecutor per call

## D-015 -- News / Earnings: Catalysts limited to IBKR roster; FinBERT cold load on scan pool; Finnhub no 429 path

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** news
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** Four news-side gaps from the deep-dive, separate from D-001 (scanner NEWS badge). Each needs the news specialist's judgement on universe and model loading; not a docs-session fix.
- **Blast radius:** (1) `scan_loop` under `discovery=ibkr` builds catalysts only from `_find_ibkr_cache_row(sym)`, so a symbol with fresh news that is not already on Gainers/Gappers/AH is dropped -- while `CatalystsTable.tsx` promises "any ticker mentioned in recent market news, regardless of exchange or size". (2) `news/sentiment.py` lazily builds the `transformers.pipeline` on the first headline inside catalyst enrich, which runs on the 2-worker scan executor (`SCAN_EXECUTOR_WORKERS = 2`) and on `/api/news/impact/{symbol}`; the first load (download + torch import) can stall both for a long time. (3) `earnings_calendar.py` / `earnings_logos.py` treat HTTP 429 like any non-200: warn, return `None`, no `Retry-After` / backoff, so a month-view burst can empty the Earnings tab until TTL. (4) `earnings_calendar` with no `FINNHUB_API_KEY` but a disk snapshot returns the snapshot with `error=None`, so the tab looks live on stale data.
- **Unblock:** Decision on (1): is Catalysts a news universe or an "on-roster with news" view? The code and the UI copy disagree.
- **Next:** Fix the copy or the filter for (1); warm FinBERT in a background thread at startup behind `NEWS_SENTIMENT_ENABLED` for (2); honour `Retry-After` and surface `error="missing_key"` for (3)/(4).
- **Evidence:** `backend/scan_loop.py:116-125`; `frontend/src/components/CatalystsTable.tsx:1-2`; `backend/news/sentiment.py:34-47` via `news/enrich.py:25`, `news/impact_evaluate.py:80`; `backend/earnings_calendar.py:61-76,165-169`; `backend/earnings_logos.py:109-123`.
- **Keywords:** catalysts, _find_ibkr_cache_row, news universe, FinBERT, transformers pipeline, SCAN_EXECUTOR_WORKERS, Finnhub 429, Retry-After, FINNHUB_API_KEY missing, earnings stale

## D-014 -- Closed Orders / Open Orders dock default to mock sample rows when IB returns zero orders

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** S
- **Domain:** execution | widgets
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** Honesty gap found in the reports/sample-data pass. It is a deliberate demo affordance (banner + hide control exist) but it fires outside the global `?view=sample` shell, so it was logged as a product decision plus a default flip, not silently changed.
- **Blast radius:** `ClosedOrdersModule` starts with `preferSample = true`; when `useClosedOrders` returns zero rows and no error, it renders `buildMockClosedOrders(...)`. `StockViewOpenOrdersDock` does the same for working orders via `wantsWorkingSample`. On a quiet paper day, or right after reconnect before `reqCompletedOrders` lands, the blotter shows paper-style fills that never happened. The read-failure case is correctly excluded (`!error`), so this is a "zero real orders" lie, not a "feed down" lie.
- **Unblock:** Operator decision: sample rows only under global Sample mode, or keep the per-module toggle but default it off.
- **Next:** Flip `preferSample` / `wantsWorkingSample` defaults to false unless `useSampleDataOptional()` is active; keep the "Show sample" affordance as opt-in.
- **Evidence:** `frontend/src/closed_orders/ClosedOrdersModule.tsx:30-38`; `frontend/src/stock_view/StockViewOpenOrdersDock.tsx:81-88,268`; `frontend/src/ibkr/mockWorkingOrders.ts`.
- **Keywords:** preferSample, wantsWorkingSample, buildMockClosedOrders, sample data, blotter, Closed Orders, Open Orders dock, honesty

## D-013 -- Order UI: Place enabled while spend is locked; backend `detail` dropped; unknown status tone

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** S
- **Domain:** execution
- **User-visible:** yes
- **Logged:** 2026-09-06
- **Why parked:** Three order-ticket honesty nits from the execution pass; each is a small UI change but the rejection-copy one changes what the operator reads on a reject, so it should ship with a Vitest.
- **Blast radius:** `ManualOrderFooter` disables Place only on `!connected || submitting`; `spendLocked` fails only inside `executeOrder`, so the operator clicks into a guaranteed reject. `parseTimedExecutionResponse` returns the parsed body as-is; FastAPI HTTP-error bodies are `{detail: "..."}` with no `error`, so `ManualOrderTicket` shows the generic "Order failed" and the real reason (e.g. `OVERSELL`, kill switch, live-unconfirmed) is lost. `orderDisplay.ts` maps unknown broker statuses to the `pending` tone, so a new IB status string renders as if the order were still working.
- **Unblock:** None.
- **Next:** Disable Place when `spendLocked` with the lock reason as the title; map `detail` to `error` in `parseTimedExecutionResponse`; add an `unknown` tone.
- **Evidence:** `frontend/src/ibkr/ManualOrderFooter.tsx:80`; `frontend/src/ibkr/ManualOrderTicket.tsx:154-196,233-241`; `frontend/src/execution_latency/responseOutcome.ts:18-21`; `frontend/src/ibkr/orderDisplay.ts:110-130`.
- **Keywords:** ManualOrderFooter, spendLocked, disabled, Order failed, detail, responseOutcome, orderDisplay, pending tone, reject reason

## D-012 -- Ledger writes and cancel-verify run on the wrong thread (IB callbacks / `to_thread`)

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** execution | market-feed
- **User-visible:** yes (desk-wide L1 stall during a cancel or a fill burst)
- **Logged:** 2026-09-06
- **Why parked:** ADR 010 ban found in both the feed and execution passes; the cancel path needs an `on_ib` rewrite with an awaitable verify, which is a real execution change that must ship with a paper receipt round-trip (blast-radius rule).
- **Blast radius:** `execution/telemetry.py` persists ack / fill / facts to the SQLite ledger **inside** IB `orderStatus` / `execDetails` handlers, i.e. `sqlite3.connect` + `commit()` on the IB loop thread -- a disk stall wedges L1, scanner leases and other places. `execution/broker_send.py` cancels via `await asyncio.to_thread(cancel_order_verified, ...)`, which `time.sleep`-polls and calls `orders.open_orders()` -> `ib.openTrades()` from a worker thread with no `_ib_sync` / `call_on_ib` -- exactly the "`asyncio.to_thread` around `ib.*`" pattern `single-market-data-feed.mdc` lists as an anti-pattern.
- **Unblock:** None.
- **Next:** Hand ledger writes to a queue drained off-loop (same as archive); rewrite `cancel_order_verified` as an `on_ib` coroutine awaiting `orderStatusEvent` with a timeout instead of sleep-polling; run `tools/maintainer_lib/ib_loop.py` to confirm zero `ib_loop_sync_io` hits.
- **Evidence:** `backend/execution/telemetry.py:79-126,152-198`; `backend/execution/broker_send.py:109`; `backend/ibkr/cancel_verify.py:16-50` (`time.sleep(max(0.05, float(poll_sec)))`); `backend/ibkr/orders.py:289-305` (`trades = ib.openTrades()`).
- **Keywords:** telemetry persist on IB loop, sqlite orderStatus, to_thread cancel_order_verified, time.sleep poll, ib.openTrades off loop, ADR 010, ib_loop_sync_io

## D-011 -- Broker send happens after the execution lock is released (ADR 007 says inside)

- **Status:** open
- **Kind:** bug
- **Severity:** P0
- **Effort:** M
- **Domain:** execution
- **User-visible:** yes (double-size or accidental short on a fast double SELL)
- **Logged:** 2026-09-06
- **Why parked:** Found in the execution deep-dive and confirmed by reading `service.py` against ADR 007 decision 5. This is order-safety code under `execution-continuity.mdc`; the fix must ship with a concurrency regression test and a paper place/cancel receipt, which the docs-only audit could not run. Pull first.
- **Blast radius:** ADR 007: "The lock covers reservation, validation, and the synchronous broker send only." `execution.service.execute` holds `_lock` for `store.reserve` + validation + `get_ib()`, then exits the `async with` **before** `await send_broker(...)`. Two `place` SELLs on the same symbol with different `idempotency_key`s (hotkey twice, Exit + Flatten, two windows) can both pass `OVERSELL` against the same `long_qty` and both reach `placeOrder`. Idempotency only protects a repeated *same* key. Related gaps that widen this: the UI mints a fresh `uuid` per submit (`placeOrder.ts` `idempotencyKey || newIdempotencyKey()`), hotkeys have no in-flight lock (only `event.repeat` is filtered), BUY-to-cover has no `short_qty` overshoot gate (SELL has `OVERSELL`, BUY has only priced-order BP), and there is no restart reconciliation of ledger rows stuck in `reserved` / `sent` against `reqOpenOrders` / `reqExecutions` (Nova OS recovery rebuilds brackets only), so a timeout + retry is a second order.
- **Unblock:** None -- the ADR already states the intended shape.
- **Next:** Write the failing test first: two concurrent `execute()` SELLs, different keys, same symbol, `long_qty=100`, each qty 100 -> exactly one `placeOrder`. Then move `send_broker` inside the lock (ack wait stays outside), add a symmetric BUY <= `short_qty` check, make the UI/hotkeys reuse one key per user gesture, and add a startup sweep of non-terminal ledger rows.
- **Evidence:** `backend/execution/service.py:171-286` (`async with _lock:` ends before `receipt = await send_broker(...)`); `architecture/decisions/007-*.md` decision 5; `backend/execution/validate.py:153-174` (OVERSELL vs `long_qty` only); `frontend/src/ibkr/placeOrder.ts:24-47`; `frontend/src/hotkeys/HotkeyDispatchContext.tsx:151-156,201-203`; `backend/nova_os/recovery.py` (brackets only).
- **Keywords:** execution lock, send_broker outside lock, ADR 007, OVERSELL race, double place, idempotency_key per submit, hotkey in-flight, short_qty cover gate, ledger reconcile on restart, reqOpenOrders

## D-010 -- Trend Line two-click place pans the chart instead

- **Status:** parked
- **Kind:** bug
- **Severity:** P1
- **Effort:** L
- **Domain:** widgets
- **User-visible:** yes
- **Logged:** 2026-08-31
- **Why parked:** Operator recorded this and forbade a fix this session. They do not want another custom "armed / ready to draw" click collector. Pull only when they name D-010.
- **Blast radius:** Trend Line cannot be placed with two clicks. A click or drag pans the time scale (X-axis) instead of dropping anchors. The other two-anchor tools (Extended Line, Ray) likely share the same gesture. Operators cannot mark trends on the live desk.
- **Unblock:** Operator names D-010. Then use a drawing library that already does two-click place (click point A, click point B, line exists) without stealing pan -- do not invent a third Nova click protocol.
- **Next:** When unblocked, reproduce with Trend Line armed: two clicks on prices, no drag. Confirm whether `chart.subscribeClick` in `useChartDrawingManager.ts` even fires, or whether Lightweight Charts pan eats the gesture. Prefer `lightweight-charts-drawing` native placement (or a replacement library) over more `pendingAnchorRef` code.
- **Evidence:** Operator report 2026-08-31: select Trend Line, click a point expecting two-click draw; the chart moves on the X-axis. Current path: `ChartDrawToolsMenu` sets `activeTool` -> `handleChartClick` via `subscribeClick` collects two anchors while the chart's default drag is still pan. Record-only session -- no live screenshot, no chart code change.
- **Keywords:** trend line, TrendLine, two-click, pan, x-axis, lightweight-charts-drawing, handleChartClick, pendingAnchorRef, ChartDrawToolsMenu, ADR 015, D-010

## D-009 -- Ticker cold snapshot returns empty for a symbol chart bars fetch fine

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** M
- **Domain:** market-feed
- **User-visible:** yes (Stock View / ticker detail can show an empty quote for a symbol that is trading fine)
- **Logged:** 2026-08-31
- **Why parked:** Found while diagnosing the XAIR "not on Gappers" report. The scanner-side L1 starvation (separate root cause) was fixed and verified this session; this ticker-detail cold-snapshot path is a different code path (`ticker_ibkr.py`) that this session did not trace to a root cause.
- **Blast radius:** `GET /api/ticker/{symbol}` can return `snapshot: {}` (and `avg_volume`/`rel_volume: None`) for a symbol whose 1Min bars are fetching correctly via `reqHistoricalData` (5 fresh bars, real volume) at the same moment. `ticker_ibkr._price_from_l1_stream` and `_price_from_chart_bars` both apparently returned `None` too, since the code fell through to the slow `snapshot_quotes` cold path, which then failed with a blank exception message (`ticker IBKR snapshot failed for XAIR: `).
- **Unblock:** Reproduce on a currently-live symbol with the same shape (has bars, no scanner L1 owner yet) and add a non-blank exception message/traceback at the `logger.warning` call in `ticker_ibkr.py` (currently logs `%s` on an exception whose `str()` is empty) so the actual IB error surfaces.
- **Next:** Read `ticker_ibkr.py` around the cold `snapshot_quotes` fallback (roughly lines 110-150), reproduce with a symbol not in any active L1 pool, and get a non-empty exception detail before deciding whether the fix belongs in `ibkr/discovery.snapshot_quotes` or the fallback ordering in `ticker_ibkr.py`.
- **Evidence:** `backend/logs/api-console.log` 2026-08-31 08:06:03 -- `WARNING ticker_ibkr ticker IBKR snapshot failed for XAIR: ` (empty message) immediately followed by `WARNING ticker_detail ticker REST: IBKR snapshot empty for XAIR - returning empty (no Alpaca fallback)`. Same minute, `GET /api/ticker/XAIR/bars?timeframe=1Min` returned 5 real bars (`c=5.7, v=302768` on the last one). `GET /api/ticker/XAIR` returned `{"snapshot": {}, "avg_volume": null, "rel_volume": null, ...}`.
- **Keywords:** ticker_ibkr, snapshot_quotes, cold snapshot, empty exception, XAIR, Stock View, blank error message

## D-005 -- Aborted API terminal can leave a live process with no HTTP listener

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** ibkr-ops
- **User-visible:** yes
- **Logged:** 2026-08-26
- **Why parked:** Found while completing chart-tool verification; process supervision and safe stale-owner recovery are outside the chart UI task.
- **Blast radius:** Nova can show "Start API" while port 8000 refuses connections, but `run_api.py` refuses recovery because the lock owner PID is still active. The desk remains down until the orphan is identified and stopped.
- **Unblock:** Define a safe ownership rule that distinguishes a healthy active API from an orphaned, non-listening child without ever starting a second clientId 17 session.
- **Next:** Reproduce terminal abort in an isolated paper session, then make the launcher terminate its child on parent loss or add a listener/parent-aware stale-owner recovery after a bounded grace period.
- **Evidence:** Terminal 336841 was aborted at 21:52:45 ET; child `python3.13.exe` PID 35140 remained active through 22:01 with no port 8000 listener. A new start was rejected by `api-instance.lock`. Stopping the orphan and launcher, then starting once, restored `/api/health=connected`, IBKR `session=ready`, and 21 Gappers.
- **Keywords:** api-instance.lock, orphan API, terminal aborted, port 8000 refused, clientId 17, run_api.py, process supervision

## D-004 -- Vite restart-lock test shares the live lock path

- **Status:** open
- **Kind:** bug
- **Severity:** P2
- **Effort:** S
- **Domain:** frontend tooling
- **User-visible:** no
- **Logged:** 2026-08-26
- **Why parked:** Found while verifying the chart drawing task; changing API restart locking is unrelated to chart tools and needs its own focused test pass.
- **Blast radius:** `npx vitest run` can fail when a live Vite restart owns `backend/.cache/start-api.lock`, and the test's `afterEach` can delete that live lock, briefly removing restart-race protection.
- **Unblock:** None.
- **Next:** Make `acquireLock` / `releaseLock` accept an injected lock path or construct a lock owner around a path, then point the test at `tmpdir()` instead of the operator cache.
- **Evidence:** Full Vitest run at 21:57 ET failed `vite-nova-start-api.test.ts` because its first `acquireLock()` returned false while the running app held the production path; the test cleanup removed the lock and an immediate retry passed all 835 tests.
- **Keywords:** vite-nova-start-api, start-api.lock, test isolation, operator cache, restart race

## D-003 -- Trader 10Sec / Full Day sit on "Loading IBKR historical..." for minutes

- **Status:** blocked
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** market-feed
- **User-visible:** yes
- **Logged:** 2026-08-26
- **Why parked:** Phases 0-4 of the roadmap are implemented and pytest-green (fresh full-suite run, 1386 passed), but the running Nova API process could not be restarted from this agent session to live-verify (see Unblock) -- the process is not visible to this shell's `Get-Process` (likely a different Windows session/Electron sidecar), and the constitution forbids touching a live-trading process blindly. Do not close until a live restart confirms the pacing bucket and 10Sec paint time.
- **Blast radius:** Unchanged from the original diagnosis until live-verified: any ticker whose 10Sec/1Day series is not already in `bars_store` opens two black quadrants; Large Cap backfill competed for the same 60 req / 10 min IB bucket; stale 1Min/5Min took `open_chart` slots.
- **Unblock:** User restarts Nova (Desktop app relaunch, or the header "Start API" control, or `Run Nova.bat`) so the new code loads, then re-run the live checks in Next.
- **Next:** After restart, verify in the same session: (1) `/api/metrics/ops` -> `historical_pacing.window_used` stays well under 60 across two Large Cap roster commits (Phase 1). (2) Open a cold Trader symbol and confirm 10Sec paints within a few seconds via `/api/ticker/{symbol}/bars?timeframe=10Sec` (`bars` non-empty even before the hist fill lands) (Phases 2-4). (3) Re-check scanner L1 freshness (`/ws/scanner` patches or `/api/movers` ages) in the same window (blast-radius rule). Then move this entry to Closed and write the matching PROBLEM_LOG close-out.
- **Evidence (soak, 2026-08-26 ~19:32 ET):** Trader MSS: 5Min and 1Min painted; 10Sec and Full Day overlay. `/api/ticker/MSS/bars`: 10Sec n=0 filling=true; 1Day n=0 filling=true. `/api/metrics/ops` `ibkr.historical_bars` last_sample_age ~448s (no send for ~7.5 min). `backend/logs/blast.log` 18:53 shed storm of Large Cap 1Day (ORCL/T/F/PLTR/...).
- **Evidence (implementation, 2026-08-26 ~20:xx):** New `HistoricalPacing.snapshot()` unit-tested (`window_used` counts sends). `large_cap_hooks`/`large_cap_metrics` once-per-session + store-complete guards unit-tested (17 tests). `chart_bars.fetch_chart_bars` priority split (`open_chart` empty-store / `warm` stale-store / `background` unchanged for scan callers) unit-tested (36 tests). New `ibkr/tape_10sec.py` provisional 10Sec candles from tape prints (`source=ibkr_l1`, never fakes `store_series_complete`) unit-tested (4 tests) + wired into `tape_stream._on_tape_update` and `scanner_l1.flush_loop` heartbeat. Trader-seam warm fill on first tape subscriber, store-settled guarded, unit-tested (2 tests). Full backend suite: 1386 passed (excl. one pre-existing flaky transformers-import test unrelated to this change).
- **Keywords:** Loading IBKR historical, 10Sec, 1Day, Full Day, MSS, ADR 012, historical_service, 60/10 min pacing, Large Cap, open_chart, bars_store

## D-002 -- Afterhours Gap % equals Change %, not the open-vs-prior-close gap

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** S
- **Domain:** market-feed
- **User-visible:** yes
- **Logged:** 2026-08-26
- **Why parked:** The Gainers/Losers `reprice_mover_row` path now derives `gap_percent` from the IBKR session-open tick (tick 14). The afterhours reprice path (`ibkr_bridge.apply_l1_quote` afterhours branch / `_ah_discovery`) was not migrated in that same change, and the evening session was already on the afterhours table so we could not E2E the gainer gap at the same time.
- **Blast radius:** Afterhours Gap % on every row is a lie whenever the session move is not equal to the overnight gap. An operator can treat a +50% runner as a +50% gapper.
- **Unblock:** None -- shape is known. Do it in a session that can see a live afterhours roster.
- **Next:** Thread `open_price` through the afterhours L1 reprice the same way `discovery.reprice_mover_row` does; do not reuse `change_pct` as gap. Add a regression that an AH row with open != last keeps a real gap.
- **Evidence:** 2026-08-26 live OKTG: Gap % showed `+53.29%` (same as Change %) while open vs prior close was `-2.50%`.
- **Keywords:** afterhours, gap_percent, change_pct, OKTG, _ah_discovery, apply_l1_quote, tick 14, reprice_mover_row

## D-001 -- Scanner NEWS column is dead under discovery=ibkr

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** M
- **Domain:** news
- **User-visible:** yes
- **Logged:** 2026-08-26
- **Why parked:** Found while filling Gap % / RVOL / Float / Short Int. / Mkt Cap on IBKR movers. Every writer of `has_news` / `newest_headline_at` is still on the Alpaca-era movers/discovery runners, which early-return when `discovery=ibkr`. Fixing it is a new periodic job, not a one-line decorate, and that session was already shipping L1 + fundamentals.
- **Blast radius:** Gappers / Gainers / Losers / Afterhours NEWS column is empty every session. Catalysts elsewhere are unrelated -- this is the scanner table badge.
- **Unblock:** None on the human side. Do not write news flags into a frozen roster cache (ADR 008). Decorate at read time, same as `mover_enrich_view.decorate_rows`.
- **Next:** Periodic job over current roster symbols (the same set `mover_enrich_hooks.on_mover_roster_commit` already gathers), reuse Alpaca `_check_news`, stamp `has_news` / `newest_headline_at` at `routes/scan._strip_blocked`, `scanner_push.broadcast_roster_replace`, and `_snapshot_payload`.
- **Evidence:** 2026-08-26 live `/api/movers` Gainers rows carried neither `has_news` nor `newest_headline_at` (keys absent, not null). `scanner_runners/movers.py` returns immediately when discovery is ibkr.
- **Keywords:** has_news, newest_headline_at, NEWS column, discovery=ibkr, scanner_runners, mover_enrich_view, Alpaca news, ADR 008

<!-- OPEN_END -->

<!-- CLOSED_START -->

## D-008 -- Earnings-day-offset test fails; sentiment model import segfaults full suite

- **Status:** done
- **Kind:** bug
- **Severity:** P2
- **Effort:** S
- **Domain:** news
- **User-visible:** no (test-suite only)
- **Logged:** 2026-08-31
- **Closed:** 2026-09-02
- **Why parked:** Found mid-unrelated IBKR verification. Isolation half blocked Linux CI (`pytest backend/ -x`).
- **Closed how:** `earnings_window.earnings_day_offset` late-imports `market.now_et` instead of binding it at import. A prior suite import froze "today" to the real calendar date, so the 2026-08-27 fixture sat outside `EARNINGS_DOT_WINDOW_DAYS` (1) and returned `None`. `test_offset_follows_patched_market_now_et` locks it. The Windows `torchvision`/`transformers` `0xc0000139` crash was not reproduced on Linux CI and is a local DLL install issue, not a product bug.
- **Related:** PROBLEM_LOG 2026-09-02 Linux CI; CHANGELOG 2026-09-02 Linux CI; task-log `knowledge/task-log/2026-09-02-linux-ci-unblock.md`

## D-006 -- init_sentry + cache restore block HTTP yield for ~94s

- **Status:** done
- **Kind:** bug
- **Severity:** P1
- **Effort:** S
- **Domain:** ibkr-ops
- **User-visible:** yes
- **Logged:** 2026-08-28
- **Closed:** 2026-09-02
- **Why parked:** Found on the 08:22 daily start soak. Patch is `app_lifespan.py` (move `init_sentry` / heavy restore after `yield` or bound it). The live API is `reload=true`; a backend edit would WatchFiles-restart it and, after 09:30, today's Gappers cannot be rebuilt.
- **Blast radius:** Daily start's old 60s health wait declared the API dead while the process was still in lifespan. UI shows API down / Start API. A click then kills a live PID.
- **Unblock:** After a no-reload API start (tomorrow's daily, or a weekend restart), defer `init_sentry` until after `yield` and time `_restore_caches` / `_init_databases`.
- **Next:** Add a lifespan test that `yield` happens before Sentry/network, then restart API with `NOVA_API_RELOAD=0`.
- **Evidence:** `api-console.log` 08:22:25 `instance starting` -> 08:23:32 Sentry enabled -> 08:23:59 `HTTP ready`. `daily-start.log` 08:23:05 `API health still failing after 60s`. Soak health later missed 4s then answered in 3689ms; `http_loop_lag_ms.max_ms` reached 4360.
- **Close-out:** `lifespan` yields after tick/L1 configure. `_local_startup` (Sentry + caches + DBs) runs in `asyncio.to_thread` at the top of `_bootstrap_runtime`, with per-step ms logs. `/livez` can answer during that window; `/readyz` still waits for loops.
- **Related:** PROBLEM_LOG 2026-09-02 init_sentry blocked yield; CHANGELOG 2026-09-02 HTTP ready before Sentry; task-log `knowledge/task-log/2026-09-02-d006-http-ready-before-sentry.md`
- **Keywords:** init_sentry, lifespan yield, HTTP ready, HealthWaitSec, daily-start, API_WEDGED, Start API, D-006

## D-007 -- After-hours VWAP: Nova freezes at 16:00; Webull/DAS reset

- **Status:** done
- **Kind:** decision
- **Severity:** P2
- **Effort:** M
- **Domain:** market-feed
- **User-visible:** yes
- **Logged:** 2026-08-28
- **Closed:** 2026-08-31
- **Why parked:** Operator asked to record the platform mismatch and not change paint until the after-close consequences are clear. Premarket-in-the-same-line (04:00-16:00) already shipped this morning.
- **Blast radius:** After 16:00 Nova carries the 16:00 VWAP flat. Webull and DAS treat after-hours as a **new** VWAP (reset at 16:00), not more volume on the daytime line. TradingView with Extended Hours on keeps adding. A Webull vs Nova compare after the close will disagree. Overnight leftover still must not diagonal into tomorrow.
- **Unblock:** One live look -- Webull 1Min after 16:00: does the orange line sit still, start a new line, or keep walking? Do not flip `CHART_VWAP_SESSION_END_SEC` or add a second series without that.
- **Next:** After the cash close, screenshot Nova and Webull on the same symbol. Then either leave freeze (current), add a second AH VWAP (Webull/DAS), or keep adding (TradingView ETH).
- **Evidence:** TradingView help: VWAP "begins at the open and stops at the close" (ETH-on includes those bars). DAS docs: checkbox "also draw a VWAP line for pre and post" -- extra lines, not one blend. Community [Webull-Style Segmented VWAP](https://www.tradingview.com/script/E7GAlJYk-Webull-Style-Segmented-VWAP/) resets at premarket / regular / after-hours. Robinhood docs never state session bounds. Reddit r/Daytrading: IB / Webull / Fidelity / NinjaTrader printed different VWAPs the same morning.
- **Close-out:** LABT 2026-08-31: RTH VWAP $2.46 vs AH $3.41. Research: institutional VWAP stops at the cash close; DAS extra pre/post lines; Webull segmented reset. Shipped a 16:00 reset on the same orange series (not keep-adding, not a 09:30 reset). `sessionVwapPoints` + `CHART_VWAP_AFTERHOURS_END_SEC`.
- **Related:** PROBLEM_LOG 2026-08-31 after-hours VWAP freeze; CHANGELOG 2026-08-31 after-hours VWAP resets at 16:00; task-log `knowledge/task-log/2026-08-31-vwap-afterhours-reset.md`
- **Keywords:** VWAP, after-hours, 16:00, Webull, DAS, TradingView, session reset, CHART_VWAP_SESSION_END_SEC, D-007

<!-- CLOSED_END -->
