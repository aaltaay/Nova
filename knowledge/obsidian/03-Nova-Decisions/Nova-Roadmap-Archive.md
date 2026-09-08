# Nova Roadmap Archive (closed phases + history)

> **Read-only archive.** Live status, product NEXT, and blockers live in [[Nova-Roadmap-Status]].
> Rows and sections here were moved verbatim from that ledger on 2026-09-08 so the live note stays a short status page.
> Do not reopen anything on this page without a proven regression. Append new History rows to the **live** note.

Checkbox legend: `[ ]` pending · `[~]` in progress · `[x]` verified / complete

## COMPLETE history (do not reopen)

| Area | Status | Evidence / tip |
|------|--------|----------------|
| **Phase H — Modular Panel Workspace 0–6** | `[x]` | Playwright baseline; L2/T&S; WorkspaceContext; layoutStore; dnd-kit |
| **Nova OS P0–P10 + hardening 1–6** | `[x]` | `backend/nova_os/`, executor ladder; see [[Nova-OS-Status]] |
| **Phase C partial — R2 keys + L2 health** | `[x]` (partial) | Local R2 keys + connectivity; L2 → `archive_health` |
| **Continuity refresh** | `[x]` | `1cc4de2` → `fb330cf` |
| **Governance** | `[x]` | Roadmap-Status + continuity.mdc + paper-shadow protocol (`9c6433c`) |
| **Phase A — Skills library** | `[x]` | `.cursor/skills/` + Skills-Library + Reference-Repos; commit `9f4ca3f` |
| **Phase D — Outbound alerts** | `[x]` | `backend/alerts/` + Settings; finish pass `722d614` |
| **Phase E — Backtest UX** | `[x]` | `backend/backtest/` + BacktestPanel; finish pass `722d614` |
| **Phase F — Reports v2** | `[x]` | tags / R / drawdown / IBKR import; finish pass `722d614` |
| **Phase G — Hotkeys + brackets** | `[x]` | `useHotkeys` + approveStaged bracket; finish pass `722d614` |
| **Phase G2 — DAS hotkey manager** | `[x]` | Settings Hotkeys; `.htk` I/O; authoring only (no execution) · `645761b` |
| **Phase G3 — Nova Actions executable** | `[x]` | Typed cancel/buy/sell/exit + Map-to-Nova-Action; one dispatcher; paper-first; `hotkeys` specialist · `c2c8d61` |
| **Phase J — Productization** | `[x]` | [[Productization-Decision]] local-first; finish pass `722d614` |
| **HOD Momo / Stock View harden** | `[x]` | Shipped; not roadmap debt |
| **Tester + maintainer agents** | `[x]` | `.cursor/agents/` + `tools/maintainer_checks.py` |

## Verification baseline

Close remediation Phase 7 **2026-07-16** (fresh gates):

| Suite | Count | Result |
|-------|-------|--------|
| Backend pytest | **636** | PASS |
| Tools pytest | **122** | PASS |
| Frontend Vitest | **187** | PASS |
| ESLint / Ruff | — | PASS (exit 0) |
| Maintainer `--fail-on-findings` | 0 non-baseline | PASS |
| `npm run build` | — | PASS |
| `npm audit --omit=dev` | 0 | PASS |
| `pip-audit` | torch residual CVEs | Documented compensating controls |
| Playwright | **14** | last-known (not re-run this close) |

Prior finish-pass baseline was 592 / 178 / 14 @ `722d614`.

## Retired pointers and point-in-time notes

- **Master plan file:** `nova_master_roadmap_a_z.plan.md` (repo root or Cursor plans folder) -- frequently absent; do not fabricate it. The live ledger is the SSOT for NEXT.
- **Phase B ops protocol (waived track):** `docs/paper-shadow-protocol.md` · day log `docs/shadow-day-log-template.md` -- optional reference only.
- **Execution proof (2026-07-17, user-directed, not a Phase I unlock):** ADR 007 centralized path + synthetic p95 ack pass -- `docs/trading-execution-validation.md`. Did **not** complete Phase B or Phase I.
- **IBKR ops snapshot (2026-07-20 evening):** paper Gateway on port 4002; `GET /api/ibkr/status` → `connected=true`, `mode=paper`, `spend_status=paper_armed`, `live_trading_confirmed=false`. Point-in-time only -- read live status from the API, never from this line.

## Commit stamps (historical)

- **Last verified commit (finish pass):** `722d614` (D–G code + B/C/I/J honesty)
- **Last verified commit:** `aad9bf9` (Architecture close remediation Phase 7)
- **Phase G3 commit:** `c2c8d61` (Map-to-Nova-Action + browser verify) · prior open `ce1da59`
- **Prior tip stamps:** `bb281f4` / `71ec21e` / `95884f7` / `2111511` / `342b6cc`
- **Phase A skills commit:** `9f4ca3f`
- **Phase G2 commit:** `645761b`
- **Last verified commit (gap closure):** `378be02` (execution-ledger test isolation fix + full backend/frontend/docs backlog from 2026-07-19/20)

## Closed phase ledger

### Phase B — Paper shadow ops — `[~]` WAIVED (user 2026-07-28)

- [x] Shadow-day protocol documented (`docs/paper-shadow-protocol.md`)
- [x] Day log template (`docs/shadow-day-log-template.md`)
- [ ] Market days operated in `signal` → `confirm` → `auto_paper` — **waived**
- [ ] Evening review after each completed day — **waived**
- [ ] ≥ 5 recorded shadow days with review artifacts — **waived** (0 rows; not retro-filled)
- [ ] Bugs → self-anneal + `PROBLEM_LOG.md` — n/a for waived track
- [x] **Hard rule:** `auto_live` remains blocked

**Waive note (2026-07-28):** User declined the Phase B ≥5 shadow-day exit ("cancel or complete -- I don't want it"). Marked **WAIVED**, not `[x]` complete -- inventing evidence would rewrite history. Protocol docs retained as optional reference. **Does not unlock live** and does **not** flip Phase I to GO. Product NEXT moved to Phase K. Evidence collection closed by the waive (day-0 only; no rows).

### Phase A — Skills library — `[x]` COMPLETED

- [x] Vendored skills + SOURCE-PINS (`9f4ca3f`)
- [x] Skills-Library.md + Reference-Repos.md + AGENTS pointer

### Governance — `[x]` COMPLETED

- [x] Nova-Roadmap-Status + continuity rule + paper-shadow protocol (`9c6433c`)

### Phase D — Outbound alerts — `[x]` COMPLETED (code) · SHA `722d614`

- [x] `backend/alerts/` Discord / Telegram / webhook + dispatch
- [x] `backend/routes/alerts.py`; Settings `AlertChannelsSettings.tsx`
- [x] HOD + Nova OS hooks; secrets masked; pytest + vitest

**Ops note:** first live Discord message from a real HOD alert still needs a configured channel + market session.

### Phase E — Backtest UX — `[x]` COMPLETED (code) · SHA `722d614`

- [x] Nova-native scorer/engine on archive bars (no vectorbt runtime)
- [x] `/api/backtest` + `BacktestPanel` Watchlist sub-tab
- [x] Honesty labels; pytest

**Ops note:** productive runs need cold days with `bars_1m` (Phase C remainder).

### Phase F — Reports v2 — `[x]` COMPLETED (code) · SHA `722d614`

- [x] Tags, R-multiples, drawdown APIs + Reports panels
- [x] IBKR import path (JSON upload / loud Gateway probe)
- [x] pytest + vitest

**Ops note:** rich views need paper trades from Phase B.

### Phase G — Hotkeys + brackets — `[x]` COMPLETED (code) · SHA `722d614`

- [x] `useHotkeys` + defaults; signal-mode blocks order keys
- [x] Place bracket via existing `approveStaged` path
- [x] Flatten typed-confirm untouched; vitest

### Phase G2 — DAS-compatible hotkey manager — `[x]` COMPLETED (authoring only) · 2026-07-16

- [x] DAS-style Name / Key / Command(s) manager in Settings → Hotkeys
- [x] `.htk` parse/export (first-two-`:` split; long-script `~ length:` + 51-byte chunks)
- [x] Case-preserving command tokenizer + compatibility / evidence report
- [x] Local profile persistence; import preview then replace/cancel
- [x] Help capability catalog (filters + examples)
- [x] **Safety:** imported/edited commands never register with `useHotkeys`, never call order APIs
- [x] Six Phase G automation bindings unchanged (`HotkeySettings` + runtime)

**Hard rule:** execution of imported DAS commands is a future phase — not unlocked here. `auto_live` remains NO-GO.

### Phase G3 — Nova Actions executable core — `[x]` VERIFIED · 2026-07-18

- [x] `hotkeys` specialist Owned (`hotkeys-continuity.mdc`, `agent-hotkeys`)
- [x] Typed Nova Actions (not raw DAS scripts): `cancel_symbol`, `exit_pos` / `exit_pos_pct`, Ask±/Bid± fixed shares
- [x] One shell-level hotkey dispatcher + `event.repeat` guard
- [x] Settings → Hotkeys: editable Nova Actions + Trading quick-bar (`Show button`)
- [x] System 2 gates: PIN unlock, spend lock, place-confirm preference; Bid/Ask from L2 only
- [x] Vitest + build prove unmapped `.htk` still inactive; cancel-all route tests green
- [x] Map to Nova Action: DAS row → disabled typed action (TriggerOrder rejected; never runs raw script)
- [x] Tester browser pass: Settings → Hotkeys + Stock View quick-bar; import/Map never hit order APIs (`127.0.0.1:5173`)

**Hard rule:** `auto_live` remains NO-GO. Imported DAS Command strings stay inactive until Map to Nova Action.

### Phase H — Panel workspace — `[x]` COMPLETED

**DONE. Do not reopen.** Optional: cross-slot drag/resize (not debt).

### Phase J — Productization — `[x]` COMPLETED (decision doc) · SHA `722d614`

- [x] [[Productization-Decision]] — **local-first single-operator**; SaaS/cloud Gateway deferred

## Maintenance track — Pattern-Driven Architecture (Phases 0–13) — CLOSED

Plan: `maintenance-audit-roadmap_519236d4.plan.md` (repo root or Cursor plans folder)
Did **not** alter Phase B/C/I outcomes. One commit+push per phase on `master`. Close metrics: `architecture/program-close-metrics.md`.

| Phase | Status | SHA | Notes |
|-------|--------|-----|-------|
| 0 Baseline | `[x]` | `00f0d21` | Clean tree; metrics in `architecture/baseline-phase0.md` |
| 0A Architecture contract | `[x]` | `9fac089` | ADRs + dependency-rules before product moves |
| 1 Maintainer gates | `[x]` | `67d369a` | CSS + baseline growth + dep warnings |
| 2 CSS split | `[x]` | `e15f252` | `index.css` import-only (18 lines) |
| 3 Constants domains | `[x]` | `b03f34c` | Compatibility barrels |
| 4 Frontend components | `[x]` | `71170c3` | Hotkeys / HOD settings / debug |
| 5 Chart lifecycle | `[x]` | `60f4764` | `chart/` hooks |
| 6 Low-coupling backend | `[x]` | `b4e7033` | integrity / news / r2 / security_lib |
| 7 Scanner state | `[x]` | `50a14fe` | No production `import main` caches |
| 8 Scanner + ticker | `[x]` | `10e3996` | Ports/facades |
| 9 IBKR depth | `[x]` | `fc3535a` | state/subscribe/stream |
| 10 HOD Momo | `[x]` | `72ec84b` | Explicit state + focused facades |
| 11 Error visibility | `[x]` | `f14bcb8` | No swallowed `except: pass` |
| 12 Executor | `[x]` | `8a6de9b` | Deferred — see `architecture/phase-12-executor-deferral.md` |
| 13 Program close | `[x]` | `342b6cc` | Full verify + `architecture/program-close-metrics.md` |

**Phase 0 metrics snapshot:** index.css 6168 · hod_momo 1079 · constants.py 951 · constants.ts 821 · maintainer 38 findings (36 non-baseline) · pytest collected 617 · Vitest 178 PASS.

## History (archived rows)

Newest first. Moved verbatim from [[Nova-Roadmap-Status]] on 2026-09-08. Do not rewrite; append new rows to the live note.

| Date | What | Commit |
|------|------|--------|
| 2026-07-28 | Phase K short entry DEFINED (not started): K0 constitution+ADR 009, K1 shortability truth (tick 236, fail-closed), K2 execution gate (`IBKR_SHORT_ENABLED`, explicit opt-in, inverse brackets, buy-to-cover), K3 paper proof → live unlock, K4 shortability chip next to L2 + Long/Short ticket toggle; gated on Phase B; `auto_live` NO-GO. Ledger entry is the SSOT (master plan file absent). | (that commit) |
| 2026-07-21 | Operator unlocked live spend: `IBKR_LIVE_TRADING_CONFIRMED=true` so Flatten/place work on live Gateway (`spend_status=live_armed`). Explicit request — not Phase I GO. `auto_live` still NO-GO. Phase B shadow days should still prefer paper Gateway when practicing. | `.env` only (not committed) |
| 2026-07-21 | Bidirectional IBKR Gateway auto-detect: preferred port refused → heal to alternate (paper↔live); account kind must match mode; spend gates unchanged. Header shows online · LIVE when live Gateway is logged in. Phase B paper sessions remain operator discipline. | `5a48205` |
| 2026-07-20 | Roadmap gap closure: root-caused + fixed a real execution-ledger test/prod path collision (tests were writing into the dev API's live ledger file, causing 18 order-dependent pytest failures and a latent idempotency/max-concurrent risk); shipped the entire 2026-07-19/20 backlog (IBKR gateway-mode switch + sticky self-heal + port diagnostics, global app dialogs, Trader/Stock View docks, 26 task-log entries) in 5 scoped commits; found and fixed a stale API process still serving the old `.env` (drifted to `live` during earlier flatten-bug debugging) — restarted on current code with `IBKR_GATEWAY_MODE=paper` restored, `IBKR_LIVE_TRADING_CONFIRMED` confirmed still `false`. Remaining Phase B/C/I gaps are human-only (market days, Cloudflare console). | `378be02` |
| 2026-07-18 | Phase G3 verified: Map-to-Nova-Action UX + tester browser (Settings Hotkeys + Stock View quick-bar); TriggerOrder rejected; no order APIs on import/map. Phase B remains ops NEXT; `auto_live` NO-GO. | `c2c8d61` |
| 2026-07-18 | Phase G3 opened: `hotkeys` specialist Owned; typed Nova Actions (cancel/buy/sell/exit) paper-first via manual path; one dispatcher. Phase B remains ops NEXT; `auto_live` NO-GO. | `ce1da59` |
| 2026-07-17 | Paper Gateway ops ready: `.env` `IBKR_GATEWAY_MODE=paper`, API `:8000` → `connected`/`mode=paper`, executor `confirm`, orders locked. Scorecard **NO-GO** remains on 0/5 shadow days + 0 closed paper trades (not Gateway). Phase B day-0 NEXT. | (uncommitted until user asks) |
| 2026-07-17 | Live-readiness automation pass: tape→`bars_1m` feeder + backfill (331 bars), scorecard tool, journal gates→Phase I (50/90%), kill/flatten/auto_live drills. Scorecard still **NO-GO** (0/5 shadow days, 0 closed paper trades). Phase B remains NEXT. | (uncommitted until user asks) |
| 2026-07-17 | User-directed ADR 007 centralized execution proof: single `execute` path, idempotency, stage telemetry, synthetic p95 ack ~53 ms (Continue). Phase B still NEXT; `auto_live` still NO-GO; no live orders. | (uncommitted until user asks) |
| 2026-07-16 | User-directed Stock View terminal redesign (2×2 charts + dense right rail + always-visible order ticket; Quote Panel/Trading unchanged). Phase B remains NEXT — not a roadmap phase advance. | (uncommitted until user asks) |
| 2026-07-16 | Architecture close remediation Phases 1–7: truthful audit, deps/handlers, feed honesty, ports, barrels+CSS layers, lint/lifecycle, honest ledgers; verify 636/187 | `aad9bf9` |
| 2026-07-16 | Maintenance Phase 13: program close — metrics, maintainer memory (counts later corrected by close remediation) | `342b6cc` |
| 2026-07-16 | Maintenance Phase 12: defer executor.py split with written rationale (baseline 494) | `8a6de9b` |
| 2026-07-16 | Maintenance Phase 11: error visibility — no swallowed except:pass in production/tools | `f14bcb8` |
| 2026-07-16 | Maintenance Phase 10: explicit HOD state owner + persist/session/trade/alert/admin facades | `72ec84b` |
| 2026-07-16 | Maintenance Phase 9: IBKR depth package (state/handlers/subscribe/stream) | `fc3535a` |
| 2026-07-16 | Maintenance Phase 8: scan_runners + ticker ports/facades | `10e3996` |
| 2026-07-16 | Maintenance Phase 7: explicit scanner runtime_state; main.py composition-only | `50a14fe` |
| 2026-07-16 | Maintenance Phase 6: integrity/news/r2/security_lib strangler splits | `b4e7033` |
| 2026-07-16 | Maintenance Phase 5: TickerChart lifecycle hooks under chart/ | `60f4764` |
| 2026-07-16 | Maintenance Phase 4: HotkeyManager + HOD settings/debug component splits | `71170c3` |
| 2026-07-16 | Maintenance Phase 3: domain constants modules + compatibility barrels | `b03f34c` |
| 2026-07-16 | Maintenance Phase 2: mechanical index.css split into domain stylesheets | `e15f252` |
| 2026-07-16 | Maintenance Phase 1: CSS hard limit, baseline growth, import_main/cross-feature warnings | `67d369a` |
| 2026-07-16 | Maintenance Phase 0A: architecture ADRs + dependency rules + phase destination map | `9fac089` |
| 2026-07-16 | Maintenance Phase 0: working tree clean; line/maintainer/test baselines recorded; maintenance track opened | `00f0d21` |
| 2026-07-16 | Phase G2: DAS-compatible hotkey manager (Settings Hotkeys; `.htk` I/O; compatibility Help; authoring only — no execution) | `645761b` |
| 2026-07-16 | Canvas consolidation: single `nova-home.canvas.tsx` homepage; retired five stale boards; continuity rules retargeted | (docs/canvas; commit when user requests) |
| 2026-07-16 | Continuity sync after feature dump: status/plan/canvas aligned; A/D–G/J SHAs; B/C/I honest blockers; verify counts last-known 592/149/14 @ 2026-07-15; graphify AST update + wiki export | `5f7b4d2` |
| 2026-07-15 | Tip SHA stamps after finish pass | `89712d5` / `7749181` |
| 2026-07-15 | Finish pass: Phase A skills `9f4ca3f`; D alerts; E backtest; F reports v2; G hotkeys; B shadow-day template; C Bucket Lock/rotation docs; I evidence framework; J Productization-Decision; K–Z deferred parking; verify 592/149/14 | `722d614` |
| 2026-07-15 | Phase A skills library vendored + indexes | `9f4ca3f` |
| 2026-07-15 | Opened roadmap governance + Phase B protocol | `9c6433c` |
| 2026-07-15 | Continuity refresh: Nova-OS-Status + tester ledger; tip `fb330cf` | `fb330cf` |
| 2026-07-15 | Continuity refresh predecessor | `1cc4de2` |
| 2026-07-15 | Modular Panel Workspace Phases 0–6 complete (Phase H) | (workspace phase commits; see CHANGELOG) |
| 2026-07-15 | Nova OS P0–P10 + hardening closed; R2 keys + L2 health gate | (see [[Nova-OS-Status]]) |
