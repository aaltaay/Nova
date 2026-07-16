# Nova OS Status

## Definition

Nova OS is Nova's auditable trading decision and operations layer. It combines scanner/watchlist facts, strategy rules, catalyst quality, risk/session state, market microstructure, account safety, and user-selected control mode into an explicit `BUY | WAIT | NO_BUY` decision with evidence. It then either displays, stages, or executes the approved ticket according to `signal | confirm | auto_paper | auto_live`. Nova OS also owns the learning loop: durable market/journal history, replay, review, policy versioning, and a visible audit trail. It is not an unconstrained chatbot, not a promise of profit, and never bypasses IBKR/risk gates.

## Current position

- Phase: P10 + hardening sections 1–6 (all closed); post-map follow-ups: R2 live + L2 health gate
- State: verified — see per-phase exit-criteria table below (2026-07-15 re-verification), not a blanket claim
- Last verified commit: *(continuity-refresh tip; documenting prior HEAD `61ea86c` + this refresh — SHA filled after push)*
- Last updated: 2026-07-15 ~23:35 ET (continuity refresh)

## Completed this phase

- **P8** — R2 upload/health code (loud when unconfigured); trim still requires verified remote; `docs/r2-archive-setup.md`
- **P8 infra (2026-07-15)** — local `.env` now has R2 keys; connectivity verified (`head_bucket` on `nova-archive`, probe upload + delete, `archive_health` r2 configured). `ARCHIVE_MAINTENANCE_ENABLED=true` so compact+upload can run. Token rotation deferred (test credentials for now).
- **L2 health gate (2026-07-15)** — `l2_bridge_failed_days` now trips top-level `archive_health` `ok`/`problems` when R2 is enabled+configured (was report-only).
- **P9** — no-hindsight replay/walk/review (`replay.py::slice_bars_as_of`/`replay_at`/`walk_day`) + CLI + real `ArchiveRewind.tsx` rewind slider + archive APIs (hardening section 5, commit `3aa6c3a`)
- **P10** — Live-readiness review: **NO-GO for auto_live** (explicit; separate phase required)
- **Hardening section 6 (phase-status correction)** — re-verified each of the five gaps a post-P10 audit found in P2–P7 against current code; replaced blanket P0–P7 claim with per-phase exit-criteria table.
- **Modular Panel Workspace Phases 0–6 (2026-07-15, separate from Nova OS plan map)** — **DONE / do not reopen.** Playwright baseline; independent L2 + Time & Sales modules; shared `WorkspaceContext`; quote-panel decomposition; registry-driven tabs/visibility; persisted panel order (`layoutStore`); dnd-kit drag reorder. Optional later polish (cross-slot drag / resize) is not plan debt.
- **Post-pause product work through `61ea86c`** — HOD Momo WS/dedup/incremental render; Stock View double-click + detached popup + `100dvh` viewport lock; tester + maintainer agents; archive R2/L2 health (see CHANGELOG).

## Phase exit criteria (re-verified 2026-07-15, evidence-based)

The 2026-07-15 post-P10 audit found P2–P7 were partial/prototype: **unsafe flatten**, **non-atomic staged approval**, **mode-receipt split-brain**, **ambiguous startup recovery**, **consecutive- vs daily-loss policy** confusion. Hardening sections 1–5 (commits `52cf76e`, `8997358`, `46403e0`, `3aa6c3a`) claimed to fix all five. This table re-checks each claim against the current code (not comments) as of this entry — every row was independently verified by reading the actual guard/transition logic, not just docstrings.

| Phase | Exit criterion | Status | Evidence |
|---|---|---|---|
| P0 | Append-only event log, `nova_os` package structure exists | PASS (baseline, not an audit-named gap) | `backend/nova_os/events.py` |
| P1 | Explicit decision vocabulary (`BUY \| WAIT \| NO_BUY`) + audit trail | PASS (baseline) | `backend/nova_os/decide.py` |
| P2 | `decide()` receipts carry the *actual* effective control mode, not a hardcoded default (mode-receipt split-brain) | PASS | `backend/strategy/setups_stream.py:159` (`mode=_control_mode.get_mode()`); `backend/routes/nova_os.py:131,149` (`current_mode = _control_mode.get_mode()`); tests `test_setups_stream.py`, `test_routes_nova_os.py::test_uses_real_control_mode_not_hardcoded_default` |
| P2 | Loss-policy downgrade uses *daily* losses, not conflated with consecutive-loss streak | PASS | `backend/nova_os/codes.py:73-102` (`loss_policy_mode(losses_today, ...)` — deliberately not `consecutive_losses`); `backend/strategy/risk.py:74-80` tracks both counters distinctly; tests `test_risk.py::TestLossesTodayIsNotConsecutive`, `test_nova_os_codes.py::TestLossPolicy` |
| P3 | Control-mode ladder UI uses `signal/confirm/auto_paper/auto_live` terminology, not legacy Arm/Disarm language | PASS | `frontend/src/strategy/ExecutorPanel.tsx:194-247`, `TickerTradeAutomateControls.tsx:20-94`; one stale "Arm/disarm" tooltip found in `WatchlistTab.tsx:115` during this re-verification and corrected in this same commit |
| P3 | Global event-driven attention strip (not buried in one panel) | PASS | `frontend/src/App.tsx:26` (`useNovaOsEventAttention(true)`), `:41,71` (`<NovaOsAttentionStrip global />` on both dashboard and stock-view trees) |
| P4 | Staged ticket approval is atomic — no window where a ticket is marked approved without being claimed, or double-placed | PASS | `backend/nova_os/staged_tickets.py:189-264` (`approve()` claims via `dict.pop` *before* gates/placement; second call raises); test `test_nova_os_staged.py::test_approve_is_atomic_second_call_fails` |
| P5 | Flatten-all requires an explicit typed confirmation, not a single click (unsafe flatten) | PASS | `backend/strategy/executor_flatten.py:99-110` (`confirm_token != NOVA_OS_FLATTEN_CONFIRM_TOKEN` → raises); `backend/constants.py` `NOVA_OS_FLATTEN_CONFIRM_TOKEN = "FLATTEN"`; UI `ExecutorPanel.tsx:175-179` (`window.prompt` must equal token); test `test_executor.py::test_flatten_rejects_wrong_confirm_token` |
| P5 | Startup recovery reconciles paper positions and resolves to `signal` on ambiguity (not silently trusting stale state) | PASS | `backend/nova_os/recovery.py:122-234` — rebuilds `_open_positions` from `executed_paper` *only when IBKR confirms* open order ids; forces `signal` + system receipt on ambiguity (`force_signal("startup_recovery_ambiguous")`); wired at `app_lifespan.py:147-150`; tests `test_nova_os_auto_paper.py::TestRestartRecovery` |
| P6/P7 | Cold-archive manifest + JSONL writes are crash-safe (temp file + `os.replace`) | PASS | `backend/archive/manifest.py:58-70`, `backend/archive/compact.py:47-69`; `upload_day`/`restore_day_to_temp` hard-fail on missing/tampered manifests (section 4, commit `46403e0`) |
| P8 | R2 upload/health code fails loud (never silently skips) when unconfigured | PASS (code + infra) | `docs/r2-archive-setup.md`; local `.env` R2 keys set 2026-07-15; live probe: `head_bucket` + upload/delete + `configured=true` |
| P9 | Replay/review never let `decide()` see bars past the moment being replayed (no-hindsight) | PASS (section 5, commit `3aa6c3a`) | `backend/archive/replay.py::slice_bars_as_of/replay_at/walk_day`; `evening_review()` scores forward from each decision's real `as_of_ts`; tests `test_archive_replay.py::TestNoHindsight` |
| P10 | `auto_live` is rejected outright (no live-money path exists) | PASS | `backend/nova_os/control_mode.py` rejects `auto_live`; re-confirmed by full backend test suite (see ledger below) |

## In progress / uncommitted

- Working tree was clean at continuity refresh (pre-refresh HEAD `61ea86c`). No uncommitted HOD/modular-workspace WIP.
- Nova OS hardening plan sections 1–6 are **all closed**. Known remaining follow-ups (ops/infra, not code bugs): R2 Bucket Lock (console); rotate test R2 token later; `walk_day` on a real compacted production day when one exists; paper shadow + evening review. Mission canvas file `canvases/nova-os-mission.canvas.tsx` is referenced by continuity rules but is not present in the repo (skipped refresh).

## Crash or blocker

- None for R2 config (keys live; maintenance enabled). No compacted production day yet → first real `walk_day` still pending market capture.
- Graphify Obsidian rebuild (this refresh): **succeeded** after installing `graphifyy[gemini]` (`openai` was missing). Incremental Gemini extract of 4 changed notes → merge → `graph.json` / `GRAPH_REPORT.md` / `wiki/` rewritten.

## Verification ledger

- 2026-07-15 continuity refresh (this entry): `py -3 -m pytest backend/tests -q` — **562/562 backend tests passed**
- 2026-07-15 continuity refresh: `npx vitest run` — **131/131 frontend tests passed** (28 files)
- 2026-07-15 continuity refresh: `npx playwright test` — **14/14** (one baseline `tabs switch` flake on first parallel run; single-test retry PASS)
- 2026-07-15 continuity refresh: `npm run build` — PASS (tsc + vite)
- 2026-07-15 L2 health gate (earlier): `py -3 -m pytest tests/test_archive_r2.py::TestR2Status` — **3/3 passed**
- 2026-07-15 continuity refresh: Graphify Obsidian `--update --wiki` via Gemini — PASS (4 docs re-extracted; graph/wiki refreshed)

## User action needed

- Optional later: rotate R2 test token; enable Bucket Lock on `nova-archive`
- **Do not enable auto_live** without a new approved implementation phase after paper metrics clear

## Phase-close / Next chat starts here

**Nova OS P0–P10 + hardening + R2 live config are done. Modular Panel Workspace Phases 0–6 are done (do not reopen).** Next work is ops / a separate live phase — not more workspace scaffolding:

1. Paper shadow days (`signal` → `confirm` → `auto_paper`) + evening review annealing
2. After first finished market day with maintenance on: exercise `walk_day` + replay CLI on real cold archive
3. Separate explicit phase if/when live readiness flips to GO — **no `auto_live` without that phase**
