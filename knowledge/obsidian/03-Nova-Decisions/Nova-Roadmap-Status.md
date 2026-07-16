# Nova Roadmap Status

> **Canonical product roadmap ledger** for the Master Roadmap A–Z.  
> **Plan (executable contract):** `C:\Users\aalta\.cursor\plans\nova_master_roadmap_a_z.plan.md`  
> **Canvas (human status board):** `C:\Users\aalta\.cursor\projects\c-Users-aalta-github-Nova\canvases\nova-master-roadmap.canvas.tsx`  
> **Ops protocol (Phase B):** `docs/paper-shadow-protocol.md`  

> **Nova OS engine status (closed map):** [[Nova-OS-Status]]  
> **Continuity rule:** `.cursor/rules/nova-roadmap-continuity.mdc`

Checkbox legend: `[ ]` pending · `[~]` in progress · `[x]` verified / complete

## Current position

- **Active phase:** Phase B — Paper shadow ops (**NEXT**)
- **State:** governance opened; Phase B not yet verified
- **Last verified commit (baseline):** `fb330cf` (continuity refresh)
- **Governance open commit:** `9c6433c`
- **Last updated:** 2026-07-15 (Roadmap governance + Phase B enablement docs)
- **`auto_live`:** **NO-GO** — rejected in `backend/nova_os/control_mode.py`; do not enable or implement

## Exact next action

**Human ops — Phase B paper shadow. No feature builds.**

1. Follow `docs/paper-shadow-protocol.md`
2. Operate control modes: `signal` → `confirm` → `auto_paper` (Executor panel / `POST /api/strategy/executor/mode`)
3. After each completed market day: evening review (`GET /api/archive/review/{YYYY-MM-DD}`) when a compacted day exists; `walk_day` when cold archive is ready
4. Log findings in this note’s History + `PROBLEM_LOG.md` for bugs
5. **Hard ban:** no `auto_live`, no live orders, no Phase D–G feature work in this window

## COMPLETE history (do not reopen)

| Area | Status | Evidence / tip |
|------|--------|----------------|
| **Phase H — Modular Panel Workspace 0–6** | `[x]` | Playwright baseline; L2/T&S modules; `WorkspaceContext`; quote panels; registry; `layoutStore`; dnd-kit reorder |
| **Nova OS P0–P10 + hardening 1–6** | `[x]` | `backend/nova_os/`, executor ladder, flatten confirm, no-hindsight replay; see [[Nova-OS-Status]] |
| **Phase C partial — R2 keys + L2 health** | `[x]` (partial) | Local R2 keys + connectivity; `ARCHIVE_MAINTENANCE_ENABLED`; L2 bridge failures trip `archive_health` |
| **Continuity refresh** | `[x]` | Commits `1cc4de2` → `fb330cf`; verification baseline below |
| **HOD Momo / Stock View harden** | `[x]` | WS dedup/incremental; double-click detach + `100dvh` — shipped; not roadmap debt |
| **Tester + maintainer agents** | `[x]` | `.cursor/agents/` + `tools/maintainer_checks.py` |

## Verification baseline

Recorded at continuity refresh (`fb330cf`). Do not claim higher without re-running.

| Suite | Count | Result |
|-------|-------|--------|
| Backend pytest | **562** | PASS |
| Frontend Vitest | **131** | PASS |
| Playwright | **14** | PASS |
| `npm run build` | — | PASS |

## Phase ledger

### Phase B — Paper shadow ops — `[~]` NEXT (ops in progress once human runs days)

Ops proof only. No new product features.

- [x] Shadow-day protocol documented (`docs/paper-shadow-protocol.md` + this note)
- [ ] Market days operated in `signal` → `confirm` → `auto_paper`
- [ ] Evening review after each completed day
- [ ] ≥ 5 recorded shadow days with review artifacts
- [ ] Bugs → self-anneal + `PROBLEM_LOG.md`
- [x] **Hard rule:** `auto_live` remains blocked in `backend/nova_os/control_mode.py`

**Exit:** ≥ 5 shadow days with reviews; findings logged; still NO-GO for live.  
**Evidence:** (fill per day — date, mode ladder used, review route/CLI, journal notes)

### Phase C — Durable archive — `[~]` PARTIAL

**Done:**

- [x] Cloudflare R2 bucket + API keys (local `.env`, not committed); connectivity verified
- [x] `ARCHIVE_MAINTENANCE_ENABLED=true`
- [x] L2 bridge failures fold into top-level `archive_health`

**Still missing:**

- [ ] R2 Bucket Lock (object immutability) in console; document in `docs/r2-archive-setup.md`
- [ ] Rotate temporary/test R2 token
- [ ] Upload/restore round-trip on a **real** compacted production day
- [ ] Exercise `walk_day` against that real cold day (`backend/archive/replay.py`)

**Exit:** health green; one real day uploaded + restored; `walk_day` on real day; Bucket Lock on.

### Phase A — Skills library — `[ ]` PENDING (after ops)

- [ ] Vendor vectorbt / backtesting / LLM-trading-security skills into `.cursor/skills/`
- [ ] `knowledge/obsidian/00-System/Skills-Library.md` + `Reference-Repos.md`
- [ ] Short pointer in `AGENTS.md`; Graphify rebuild

**Exit:** skills load in a fresh session; index + reference notes exist.

### Governance — Roadmap-Status + continuity rule — `[x]` COMPLETED (this entry)

- [x] `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md`
- [x] `.cursor/rules/nova-roadmap-continuity.mdc`
- [x] `docs/paper-shadow-protocol.md`
- [x] Pointers in `AGENTS.md` + [[Nova-OS-Status]] Next

### Phase D — Outbound alerts — `[ ]` PENDING

- [ ] `backend/alerts/` dispatcher; Discord / Telegram / webhook; Settings UI; tests

### Phase E — Backtest UX — `[ ]` PENDING

- [ ] `backend/backtest/` + `BacktestPanel`; depends on A + C

### Phase F — Reports v2 — `[ ]` PENDING

- [ ] Tags, R-multiples, drawdown, IBKR trade import

### Phase G — Hotkeys + brackets — `[ ]` PENDING

- [ ] Hotkeys + one-action brackets; safety gates intact

### Phase H — Panel workspace — `[x]` COMPLETED

**DONE 2026-07-15. Do not reopen.** Optional later: cross-slot drag/resize (not debt).

### Phase I — Live-readiness evidence — `[ ]` PENDING

- [ ] Written GO/NO-GO from Phase B (+ E) evidence; **`auto_live` stays rejected** until a separate approved unlock

### Phase J — Productization — `[ ]` DEFERRED

- [ ] Decision doc only (`Productization-Decision.md`) when promoted

### Phases K–Z — `[ ]` DEFERRED

Conversational scans, Holly-like coach, L2 scrubber, SMS/email, multi-broker, cloud Gateway, community, native mobile, CI expansion, mission canvas, reserved U–Z. **Not scheduled** until A–J near-term path is clear and the plan is updated.

## Crash or blocker

- None for governance open.
- Phase B waits on **human market-day ops** (IB Gateway logged in when discovery=`ibkr` — see `.cursor/rules/ibkr-gateway-login-warning.mdc`).
- Phase C remainder waits on first real compacted production day + console Bucket Lock / token rotation.

## History (append-only)

Newest first. Do not rewrite prior rows — only append.

| Date | What | Commit |
|------|------|--------|
| 2026-07-15 | Opened roadmap governance: `Nova-Roadmap-Status.md`, `nova-roadmap-continuity.mdc`, `docs/paper-shadow-protocol.md`; Phase B marked NEXT; Phase C partial; `auto_live` NO-GO; baseline 562/131/14 @ `fb330cf` | `9c6433c` |
| 2026-07-15 | Continuity refresh: Nova-OS-Status + tester ledger; tip `fb330cf` | `fb330cf` |
| 2026-07-15 | Continuity refresh predecessor | `1cc4de2` |
| 2026-07-15 | Modular Panel Workspace Phases 0–6 complete (Phase H) | (workspace phase commits; see CHANGELOG) |
| 2026-07-15 | Nova OS P0–P10 + hardening closed; R2 keys + L2 health gate | (see [[Nova-OS-Status]]) |
