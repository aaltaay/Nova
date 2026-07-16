# Nova Roadmap Status

> **Canonical product roadmap ledger** for the Master Roadmap A–Z.  
> **Plan (executable contract):** `C:\Users\aalta\.cursor\plans\nova_master_roadmap_a_z.plan.md`  
> **Canvas (human status board):** `C:\Users\aalta\.cursor\projects\c-Users-aalta-github-Nova\canvases\nova-master-roadmap.canvas.tsx`  
> **Ops protocol (Phase B):** `docs/paper-shadow-protocol.md` · day log: `docs/shadow-day-log-template.md`  
> **Productization (Phase J):** [[Productization-Decision]]  
> **Live gate (Phase I):** [[Nova-OS-Live-Readiness-Review]]

> **Nova OS engine status (closed map):** [[Nova-OS-Status]]  
> **Continuity rule:** `.cursor/rules/nova-roadmap-continuity.mdc`

Checkbox legend: `[ ]` pending · `[~]` in progress · `[x]` verified / complete

## Current position

- **Active ops:** Phase B — Paper shadow (**`[~]` protocol ready / awaiting ≥5 live shadow days**)
- **Feature track:** Phases A, D, E, F, G, J implemented in code/docs; I evidence-framework ready (verdict NO-GO)
- **State:** implementable roadmap work shipped; human market sessions remain the B/C blocker
- **Last verified commit:** `722d614` (finish pass) · tip `7749181` (SHA stamp)
- **Phase A skills commit:** `9f4ca3f`
- **Last updated:** 2026-07-15 (Master Roadmap finish pass — D–G code + B/C/I/J honesty)
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
| **Governance** | `[x]` | Roadmap-Status + continuity.mdc + paper-shadow protocol |
| **Phase A — Skills library** | `[x]` | `.cursor/skills/` + Skills-Library + Reference-Repos; commit `9f4ca3f` |
| **HOD Momo / Stock View harden** | `[x]` | Shipped; not roadmap debt |
| **Tester + maintainer agents** | `[x]` | `.cursor/agents/` + `tools/maintainer_checks.py` |

## Verification baseline

Finish pass 2026-07-15 (implementable roadmap close):

| Suite | Count | Result |
|-------|-------|--------|
| Backend pytest | **592** | PASS |
| Frontend Vitest | **149** | PASS |
| Playwright | **14** | PASS |
| `npm run build` | — | PASS |

Prior continuity baseline was 562 / 131 / 14 @ `fb330cf`.

## Phase ledger

### Phase B — Paper shadow ops — `[~]` protocol ready / awaiting ≥5 live shadow days

- [x] Shadow-day protocol documented (`docs/paper-shadow-protocol.md`)
- [x] Day log template (`docs/shadow-day-log-template.md`)
- [ ] Market days operated in `signal` → `confirm` → `auto_paper`
- [ ] Evening review after each completed day
- [ ] ≥ 5 recorded shadow days with review artifacts
- [ ] Bugs → self-anneal + `PROBLEM_LOG.md`
- [x] **Hard rule:** `auto_live` remains blocked

**Blocker:** cannot invent 5 real market sessions overnight — human ops required.  
**Evidence table:** use shadow-day log template (0/5 rows filled).

### Phase C — Durable archive — `[~]` PARTIAL

**Done:**

- [x] R2 keys + connectivity; `ARCHIVE_MAINTENANCE_ENABLED`
- [x] L2 bridge failures fold into `archive_health`
- [x] Bucket Lock + token rotation **steps documented** in `docs/r2-archive-setup.md`

**Still missing (honest):**

- [ ] R2 Bucket Lock enabled in Cloudflare console (operator)
- [ ] Temporary/test R2 token rotated (operator)
- [ ] Upload/restore on a **real** compacted production day
- [ ] `walk_day` on that real cold day

**Blocker (2026-07-15):** `backend/.cache/archive_cold/` empty — no compacted day; hot tape-only day exists without bars for walk. Do not fake `[x]`.

### Phase A — Skills library — `[x]` COMPLETED

- [x] Vendored skills + SOURCE-PINS (`9f4ca3f`)
- [x] Skills-Library.md + Reference-Repos.md + AGENTS pointer

### Governance — `[x]` COMPLETED

- [x] Nova-Roadmap-Status + continuity rule + paper-shadow protocol

### Phase D — Outbound alerts — `[x]` COMPLETED (code)

- [x] `backend/alerts/` Discord / Telegram / webhook + dispatch
- [x] `backend/routes/alerts.py`; Settings `AlertChannelsSettings.tsx`
- [x] HOD + Nova OS hooks; secrets masked; pytest + vitest

**Ops note:** first live Discord message from a real HOD alert still needs a configured channel + market session.

### Phase E — Backtest UX — `[x]` COMPLETED (code)

- [x] Nova-native scorer/engine on archive bars (no vectorbt runtime)
- [x] `/api/backtest` + `BacktestPanel` Watchlist sub-tab
- [x] Honesty labels; pytest

**Ops note:** productive runs need cold days with `bars_1m` (Phase C remainder).

### Phase F — Reports v2 — `[x]` COMPLETED (code)

- [x] Tags, R-multiples, drawdown APIs + Reports panels
- [x] IBKR import path (JSON upload / loud Gateway probe)
- [x] pytest + vitest

**Ops note:** rich views need paper trades from Phase B.

### Phase G — Hotkeys + brackets — `[x]` COMPLETED (code)

- [x] `useHotkeys` + defaults; signal-mode blocks order keys
- [x] Place bracket via existing `approveStaged` path
- [x] Flatten typed-confirm untouched; vitest

### Phase H — Panel workspace — `[x]` COMPLETED

**DONE. Do not reopen.** Optional: cross-slot drag/resize (not debt).

### Phase I — Live-readiness evidence — `[~]` framework ready / verdict NO-GO

- [x] GO/NO-GO thresholds written in [[Nova-OS-Live-Readiness-Review]] (Phase I section)
- [ ] Re-run review against real paper metrics from Phase B (+ E)
- [x] **`auto_live` stays rejected** in code

### Phase J — Productization — `[x]` COMPLETED (decision doc)

- [x] [[Productization-Decision]] — **local-first single-operator**; SaaS/cloud Gateway deferred

### Phases K–Z — `[~]` DEFERRED (parking lot documented)

Conversational scans, Holly-like coach, L2 scrubber, SMS/email, multi-broker, cloud Gateway, community, native mobile, CI expansion, mission canvas, reserved U–Z. **Not scheduled** until explicitly promoted. Plan todo `phases-k-z` = deferred-documented.

## Crash or blocker

- **Phase B:** awaiting human ≥5 shadow days (protocol + template ready).
- **Phase C remainder:** awaiting first real compacted day + Cloudflare Bucket Lock / token rotation (docs ready; console not automatable).
- **Phase I verdict:** NO-GO until B metrics exist; framework ready.
- **`auto_live`:** permanent NO-GO in this roadmap window.

## History (append-only)

Newest first. Do not rewrite prior rows — only append.

| Date | What | Commit |
|------|------|--------|
| 2026-07-15 | Finish pass: Phase A skills `9f4ca3f`; D alerts; E backtest; F reports v2; G hotkeys; B shadow-day template; C Bucket Lock/rotation docs; I evidence framework; J Productization-Decision; K–Z deferred parking; verify 592/149/14 | `722d614` |
| 2026-07-15 | Phase A skills library vendored + indexes | `9f4ca3f` |
| 2026-07-15 | Opened roadmap governance + Phase B protocol | `9c6433c` |
| 2026-07-15 | Continuity refresh: Nova-OS-Status + tester ledger; tip `fb330cf` | `fb330cf` |
| 2026-07-15 | Continuity refresh predecessor | `1cc4de2` |
| 2026-07-15 | Modular Panel Workspace Phases 0–6 complete (Phase H) | (workspace phase commits; see CHANGELOG) |
| 2026-07-15 | Nova OS P0–P10 + hardening closed; R2 keys + L2 health gate | (see [[Nova-OS-Status]]) |
