# Nova Roadmap Status

> **Canonical product roadmap ledger** for the Master Roadmap A–Z.  
> **Plan (executable contract):** `nova_master_roadmap_a_z.plan.md` (repo root or Cursor plans folder)  
> **Canvas (project homepage):** `canvases/nova-home.canvas.tsx`  
> **Ops protocol (Phase B — WAIVED 2026-07-28):** `docs/paper-shadow-protocol.md` · day log: `docs/shadow-day-log-template.md` (optional reference only)  
> **Productization (Phase J):** [[Productization-Decision]]  
> **Live gate (Phase I):** [[Nova-OS-Live-Readiness-Review]]  
> **Expansion idea bank (Jesse/LLM-study pattern):** [[Nova-Expansion-Ideas]]

> **Nova OS engine status (closed map):** [[Nova-OS-Status]]  
> **Continuity rule:** `.cursor/rules/nova-roadmap-continuity.mdc`

Checkbox legend: `[ ]` pending · `[~]` in progress · `[x]` verified / complete

## Current position

- **Active ops:** Phase B — Paper shadow (**`[~]` WAIVED** by user 2026-07-28 — not verified-complete; 0 evidence rows)
- **Feature track:** Phases **A, D, E, F, G, G2, G3, J** complete; **I** evidence-framework ready (**verdict NO-GO**); **K** short entry **`[~]` IN PROGRESS** (full E2E K0–K4; ungated after B waive)
- **Maintenance track:** Pattern-Driven Architecture (Phases 0–13) + **close remediation (Phases 1–7)** — **CLOSED** · metrics `architecture/program-close-metrics.md`
- **Reliability track:** Problem-root elimination (WS0–WS7) opened 2026-08-18 from PROBLEM_LOG pattern analysis -- does not replace Phase K product NEXT; `auto_live` still NO-GO
- **State:** Phase K is product NEXT; Phase B ops track closed by waive; Phase C remainder still optional operator work; `auto_live` NO-GO
- **Last verified commit (finish pass):** `722d614` (D–G code + B/C/I/J honesty)
- **Last verified commit:** `aad9bf9` (Architecture close remediation Phase 7)
- **Phase G3 commit:** `c2c8d61` (Map-to-Nova-Action + browser verify) · prior open `ce1da59`
- **Tip SHA:** follow `git rev-parse --short HEAD` (stamp commits may trail the verified close)
- **Prior tip stamps:** `bb281f4` / `71ec21e` / `95884f7` / `2111511` / `342b6cc`
- **Phase A skills commit:** `9f4ca3f`
- **Phase G2 commit:** `645761b`
- **Last updated:** 2026-08-18 (Reliability track WS0-WS7 shipped; WS1 proof pending first unattended morning)
- **Last verified commit (gap closure):** `378be02` (execution-ledger test isolation fix + full backend/frontend/docs backlog from 2026-07-19/20)
- **`auto_live`:** **NO-GO** — rejected in `backend/nova_os/control_mode.py`; do not enable or implement
- **Execution proof (user-directed, not Phase I unlock):** ADR 007 centralized path + synthetic p95 ack pass — see `docs/trading-execution-validation.md`. Does **not** complete Phase B or Phase I.
- **IBKR ops (2026-07-20 evening):** Paper Gateway logged in on port **4002**. `GET /api/ibkr/status` → `connected=true`, `mode=paper`, `broker_account_kind=paper`, `gateway_mode=paper`, `preferred_port_reachable=true`, `orders_enabled=true`, `live_trading_confirmed=false`, `spend_status=paper_armed`. Account summary reads (`BuyingPower` present). Live-readiness scorecard still **NO-GO** (0/5 shadow days, 0 closed non-mock trades).

## Reliability track -- problem-root elimination (2026-08-18)

Closes the five PROBLEM_LOG root patterns (236 entries). Product NEXT stays Phase K. Do not treat this as a Master Roadmap letter phase.

| WS | Status | Closes |
|----|--------|--------|
| 0 Ledger | `[x]` | This section |
| 1 Morning autopilot | `[~]` | Tooling shipped 2026-08-18. Proof = first real 03:55 ET evidence line in `backend/logs/morning-check.log`. Jul 30 PROBLEM_LOG stays OPEN until then. |
| 2 IB-loop purity guard | `[x]` | `tools/maintainer_lib/ib_loop.py` + CI `--fail-on-kind ib_loop_sync_io` |
| 3 Fail-loud REST | `[x]` | `table_state` / `roster_ts` / `feed_error` on gappers/movers/AH |
| 4 Persisted-state rule | `[x]` | `.cursor/rules/persisted-state.mdc` + corrupt channels ERROR log |
| 5 SSOT audit | `[x]` | Remaining dual-read: `chart_bars.py` Alpaca path is gated (discovery coerced to ibkr); qty SSOT is `ib.positions()` with portfolio MTM join; Orders Today is ledger overlay. No new dual-source to add. |
| 6 Test isolation | `[x]` | conftest import-time `NOVA_CACHE_DIR` + paper Gateway pin |
| 7 Blast-radius verification | `[x]` | table in `verification-before-completion.mdc` |

**Operator (WS1):** configure one Phase D channel (Discord recommended); leave the PC on / enable wake timers; re-run `.\scripts\Install-NovaDailyTask.ps1` once so 03:40 ET start + 03:55 ET check exist. Weekly IBKR 2FA still needs the phone.

## Exact next action (human)

1. **K3 paper short days (human):** set `IBKR_SHORT_ENABLED=true` on paper Gateway; place short_entry orders; fill K3 Evidence (≥3 days) + sign-off before any live short.
2. **Reliability WS1 (human):** configure a Discord/Telegram channel in Settings; run `.\scripts\Install-NovaDailyTask.ps1` once; leave the PC on overnight (wake timers). First 03:55 ET `backend/logs/morning-check.log` line closes Jul 30 OPEN.
3. Optional Phase C remainder: Cloudflare Bucket Lock + R2 token rotation + cold `walk_day`.
4. **Hard ban:** no `auto_live`. Live short needs K3 sign-off + `IBKR_LIVE_TRADING_CONFIRMED` on top of `IBKR_SHORT_ENABLED`.
5. Phase B is **waived** -- do not block work on ≥5 B days.

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

## Phase ledger

### Phase B — Paper shadow ops — `[~]` WAIVED (user 2026-07-28)

- [x] Shadow-day protocol documented (`docs/paper-shadow-protocol.md`)
- [x] Day log template (`docs/shadow-day-log-template.md`)
- [ ] Market days operated in `signal` → `confirm` → `auto_paper` — **waived**
- [ ] Evening review after each completed day — **waived**
- [ ] ≥ 5 recorded shadow days with review artifacts — **waived** (0 rows; not retro-filled)
- [ ] Bugs → self-anneal + `PROBLEM_LOG.md` — n/a for waived track
- [x] **Hard rule:** `auto_live` remains blocked

**Waive note (2026-07-28):** User declined the Phase B ≥5 shadow-day exit ("cancel or complete -- I don't want it"). Marked **WAIVED**, not `[x]` complete -- inventing evidence would rewrite history. Protocol docs retained as optional reference. **Does not unlock live** and does **not** flip Phase I to GO. Product NEXT moves to Phase K.

#### Phase B Evidence

| # | Date | Modes | Paper Gateway | Review | Notes |
|---|------|-------|---------------|--------|-------|
| — | — | — | connected (pre-session) | — | Evidence collection **closed by waive** (2026-07-28); day-0 only |

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

**Progress (2026-07-17):** hot `bars_1m` backfilled from tape (331 bars; days 2026-07-15/16 cold JSONL recompacted). Still need operator Bucket Lock / token rotation + a **new** production session walk after compact. Do not fake Phase C `[x]`.

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

### Phase I — Live-readiness evidence — `[~]` framework ready / verdict NO-GO

- [x] GO/NO-GO thresholds written in [[Nova-OS-Live-Readiness-Review]] (Phase I section) · finish pass `722d614`
- [ ] Re-run review against real paper metrics from Phase B (+ E)
- [x] **`auto_live` stays rejected** in code

**Do not mark Phase I `[x]`.** Framework alone is not a GO.

### Phase J — Productization — `[x]` COMPLETED (decision doc) · SHA `722d614`

- [x] [[Productization-Decision]] — **local-first single-operator**; SaaS/cloud Gateway deferred

### Phase K — Short entry (short selling) — `[~]` IN PROGRESS (full E2E K0–K4)

**User direction (2026-07-28):** add short selling -- shortable / HTB visibility next to Level 2, safe short entry on paper first, live later. Later same day: waive Phase B and implement every K gap end-to-end.
**Single source of truth:** this ledger entry + ADR 009 (once written). (`nova_master_roadmap_a_z.plan.md` remains absent; do not fabricate it.)

**Sequencing:** Phase B gate **removed** (B waived). Implement K0→K4 in order. Live short still needs K3 paper drills + spend keys. `auto_live` remains NO-GO.

#### K0 — Design + constitution (SOP before code) `[x]` (this ship)

- [x] ADR `architecture/decisions/009-short-entry.md`: gate shape, journal `side="short"` convention, borrow-data flow, new reason codes
- [x] Constitution/rule touch-up: anti-short invariant reworded -- SELL is risk-reducing *unless* an explicit short-entry gate approved it
- [x] Reason codes: `SHORT_DISABLED`, `SHORT_NOT_SHORTABLE`, `SHORT_STALE_BORROW` (every refusal must explain itself in the receipt)

#### K1 — Shortability truth (validity) `[x]` (this ship)

- [x] Promote tick-236 into `ibkr/shortability.py` with states: `shortable_est` / `thin` / `htb_likely` / `unknown`
- [x] Fail-closed semantics: `unknown` is not shortable; stale reads refuse
- [x] Freshness TTL (`IBKR_SHORTABILITY_TTL_SEC`) near order time
- [x] Honest labels: IBKR tick 236 is an estimate; Alpaca never presented as IBKR locate

#### K2 — Execution gate (safety, paper first) `[x]` (this ship)

- [x] `ExecutionCommand.short_entry` explicit opt-in (never inferred)
- [x] `execution/validate.py`: short SELL when flag + shortability + `IBKR_SHORT_ENABLED`
- [x] Default path unchanged: no flag → `NO_POSITION` / `OVERSELL`; `source=flatten` unchanged for longs
- [x] Short brackets: `short_entry` → SELL entry + inverse legs (`EXECUTOR_ENTRY_SIDE_IBKR_SHORT`)
- [x] Flatten covers shorts (market BUY); `account.short_qty` SSOT
- [ ] Journal `side="short"` + R-multiples side-aware on live short fills — follow-up when short automation setups exist

#### K3 — Paper proof, then live unlock `[~]` criteria written / human days open

- [ ] ≥3 clean paper short days (`confirm` then `auto_paper`): receipts capture borrow state at order time
- [x] Code drills: short-entry validate matrix + flatten-from-short path (pytest)
- [x] Live criteria written below; live additionally requires `IBKR_LIVE_TRADING_CONFIRMED=true` on top of K2 gates
- [ ] Phase I scorecard re-run including short metrics (after paper shorts)
- [ ] Operator sign-off checkbox after ≥3 paper short days

**K3 live unlock criteria (operator):**
1. `IBKR_SHORT_ENABLED=true` on paper; ≥3 days with short_entry receipts + kill/flatten drills noted
2. No unresolved `SHORT_*` false-allow bugs in PROBLEM_LOG
3. Explicit sign-off in History; then live may use short_entry only with `IBKR_LIVE_TRADING_CONFIRMED=true`
4. `auto_live` remains NO-GO

#### K3 Evidence (paper short days)

| # | Date | Modes | Short fills | Review | Notes |
|---|------|-------|-------------|--------|-------|
| — | — | — | — | — | Awaiting human paper short sessions |

#### K4 — UI (shortability next to Level 2) `[x]` (this ship)

- [x] Stock View rail: Shortability chip beside L2 title (state + est. shares + staleness + TWS tooltip)
- [x] Order ticket: Long/Short direction; Short disabled with reason mirroring `SHORT_*` codes
- [ ] Deferred: scanner-level shortable filter

**Testability (every sub-phase ships tests):**

- pytest: short-gate matrix (flag off/on × shortability states × stale × fractional × cover-vs-oversell), inverse bracket legs, flatten-from-short, journal `side="short"`, shortability state mapping
- Vitest: chip states, ticket toggle disabled-reasons
- Playwright: chip visible next to L2; short toggle blocked with reason when `SHORT_DISABLED`

**Safety invariants (must never regress):**

- Short entry is explicit per-order opt-in + env gate; default OFF
- Anti-short default path unchanged; fail closed on unknown / stale borrow
- `auto_live` NO-GO; live short needs both second keys + K3 sign-off
- Every refusal leaves a receipt with a reason code

### Phases L–Z — `[~]` DEFERRED (parking lot documented)

Conversational scans, Holly-like coach, L2 scrubber, SMS/email, multi-broker, cloud Gateway, community, native mobile, CI expansion, mission canvas, reserved U–Z. **Not scheduled** until explicitly promoted. (K promoted to a defined phase on 2026-07-28 -- see above.) Plan todo `phases-k-z` = deferred-documented.

## Maintenance track — Pattern-Driven Architecture (Phases 0–13)

Plan: `maintenance-audit-roadmap_519236d4.plan.md` (repo root or Cursor plans folder)  
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

- **Phase B:** **WAIVED** (user 2026-07-28) -- not a blocker.
- **Phase K:** in progress (full E2E); Exact next action tracks K0→K4 slices.
- **Phase C remainder:** bars backfill done; still need Cloudflare Bucket Lock / token rotation + fresh session compact/walk (optional).
- **Phase I verdict:** NO-GO -- B metrics will not arrive via waived Phase B; framework ready; short metrics need K3 paper days later.
- **`auto_live`:** permanent NO-GO in this roadmap window.

## History (append-only)

Newest first. Do not rewrite prior rows — only append.

| Date | What | Commit |
|------|------|--------|
| 2026-08-31 | Public domain `nova.altaystudio.com` is a static marketing page (`site/`), not the hosted scanner. CTA is Nova-public. Phase J local-first. `auto_live` NO-GO. | (this commit) |
| 2026-08-18 | Reliability track WS0-WS7: morning check + system-event alerts, fail-loud scanner REST, pytest cache isolation, IB-loop purity CI gate, blast-radius + persisted-state rules. WS1 proof still needs first unattended 03:55 ET run. `auto_live` NO-GO. | (this commit) |
| 2026-07-28 | Phase B WAIVED + Phase K E2E ship: ADR 009, shortability module, `IBKR_SHORT_ENABLED` + `short_entry` gates, flatten cover, Shortability chip + Long/Short ticket. K3 human paper short days still open. `auto_live` NO-GO. | `125f3ce` |
| 2026-07-28 | Phase K short entry DEFINED (not started): K0 constitution+ADR 009, K1 shortability truth (tick 236, fail-closed), K2 execution gate (`IBKR_SHORT_ENABLED`, explicit opt-in, inverse brackets, buy-to-cover), K3 paper proof → live unlock, K4 shortability chip next to L2 + Long/Short ticket toggle; gated on Phase B; `auto_live` NO-GO. Ledger entry is the SSOT (master plan file absent). | (this commit) |
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
