# Nova Roadmap Status

> **Canonical product roadmap ledger** for the Master Roadmap A–Z.  
> **Plan (executable contract):** `C:\Users\aalta\.cursor\plans\nova_master_roadmap_a_z.plan.md`  
> **Canvas (project homepage):** `C:\Users\aalta\.cursor\projects\c-Users-aalta-github-Nova\canvases\nova-home.canvas.tsx`  
> **Ops protocol (Phase B):** `docs/paper-shadow-protocol.md` · day log: `docs/shadow-day-log-template.md`  
> **Productization (Phase J):** [[Productization-Decision]]  
> **Live gate (Phase I):** [[Nova-OS-Live-Readiness-Review]]

> **Nova OS engine status (closed map):** [[Nova-OS-Status]]  
> **Continuity rule:** `.cursor/rules/nova-roadmap-continuity.mdc`

Checkbox legend: `[ ]` pending · `[~]` in progress · `[x]` verified / complete

## Current position

- **Active ops:** Phase B — Paper shadow (**`[~]` protocol ready / awaiting ≥5 live shadow days**)
- **Feature track:** Phases **A, D, E, F, G, G2, J** complete in code/docs; **I** evidence-framework ready (**verdict NO-GO**)
- **Maintenance track:** Pattern-Driven Architecture (Phases 0–13) + **close remediation (Phases 1–7)** — **CLOSED** · metrics `architecture/program-close-metrics.md`
- **State:** implementable roadmap work shipped; human market sessions remain the B/C blocker; structural maintenance + close remediation complete
- **Last verified commit (finish pass):** `722d614` (D–G code + B/C/I/J honesty)
- **Tip SHA:** `33768e9` · Phase 7 content `aad9bf9`
- **Prior tip stamps:** `bb281f4` / `71ec21e` / `95884f7` / `2111511` / `342b6cc`
- **Phase A skills commit:** `9f4ca3f`
- **Phase G2 commit:** `645761b`
- **Last updated:** 2026-07-16 (Architecture close remediation Phase 7)
- **`auto_live`:** **NO-GO** — rejected in `backend/nova_os/control_mode.py`; do not enable or implement

## Exact next action (human)

1. Follow `docs/paper-shadow-protocol.md` + fill `docs/shadow-day-log-template.md` rows
2. Operate `signal` → `confirm` → `auto_paper` on paper Gateway
3. Evening review per completed day; log bugs in `PROBLEM_LOG.md`
4. After first bars-rich session: compact → (optional R2) → `walk_day` / restore — clear Phase C remainder
5. Cloudflare console: Bucket Lock + R2 token rotation per `docs/r2-archive-setup.md`
6. **Hard ban:** no `auto_live`, no live orders

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

## Phase ledger

### Phase B — Paper shadow ops — `[~]` NEXT / BLOCKED on human market days

- [x] Shadow-day protocol documented (`docs/paper-shadow-protocol.md`)
- [x] Day log template (`docs/shadow-day-log-template.md`)
- [ ] Market days operated in `signal` → `confirm` → `auto_paper`
- [ ] Evening review after each completed day
- [ ] ≥ 5 recorded shadow days with review artifacts
- [ ] Bugs → self-anneal + `PROBLEM_LOG.md`
- [x] **Hard rule:** `auto_live` remains blocked

**Blocker:** cannot invent 5 real market sessions overnight — human ops required.  
**Evidence table:** use shadow-day log template (0/5 rows filled).

### Phase C — Durable archive — `[~]` PARTIAL / BLOCKED on console + cold day

**Done:**

- [x] R2 keys + connectivity; `ARCHIVE_MAINTENANCE_ENABLED`
- [x] L2 bridge failures fold into `archive_health`
- [x] Bucket Lock + token rotation **steps documented** in `docs/r2-archive-setup.md`

**Still missing (honest):**

- [ ] R2 Bucket Lock enabled in Cloudflare console (operator)
- [ ] Temporary/test R2 token rotated (operator)
- [ ] Upload/restore on a **real** compacted production day
- [ ] `walk_day` on that real cold day

**Blocker (2026-07-15, still true 2026-07-16):** `backend/.cache/archive_cold/` empty — no compacted day; hot tape-only day exists without bars for walk. Do not fake `[x]`.

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

### Phase H — Panel workspace — `[x]` COMPLETED

**DONE. Do not reopen.** Optional: cross-slot drag/resize (not debt).

### Phase I — Live-readiness evidence — `[~]` framework ready / verdict NO-GO

- [x] GO/NO-GO thresholds written in [[Nova-OS-Live-Readiness-Review]] (Phase I section) · finish pass `722d614`
- [ ] Re-run review against real paper metrics from Phase B (+ E)
- [x] **`auto_live` stays rejected** in code

**Do not mark Phase I `[x]`.** Framework alone is not a GO.

### Phase J — Productization — `[x]` COMPLETED (decision doc) · SHA `722d614`

- [x] [[Productization-Decision]] — **local-first single-operator**; SaaS/cloud Gateway deferred

### Phases K–Z — `[~]` DEFERRED (parking lot documented)

Conversational scans, Holly-like coach, L2 scrubber, SMS/email, multi-broker, cloud Gateway, community, native mobile, CI expansion, mission canvas, reserved U–Z. **Not scheduled** until explicitly promoted. Plan todo `phases-k-z` = deferred-documented.

## Maintenance track — Pattern-Driven Architecture (Phases 0–13)

Plan: `C:\Users\aalta\.cursor\plans\maintenance-audit-roadmap_519236d4.plan.md`  
Does **not** alter Phase B/C/I outcomes. One commit+push per phase on `master`.

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

## Crash or blocker

- **Phase B:** awaiting human ≥5 shadow days (protocol + template ready).
- **Phase C remainder:** awaiting first real compacted day + Cloudflare Bucket Lock / token rotation (docs ready; console not automatable).
- **Phase I verdict:** NO-GO until B metrics exist; framework ready.
- **`auto_live`:** permanent NO-GO in this roadmap window.

## History (append-only)

Newest first. Do not rewrite prior rows — only append.

| Date | What | Commit |
|------|------|--------|
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
