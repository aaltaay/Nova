# Nova OS Status

## Definition

Nova OS is Nova's auditable trading decision and operations layer. It combines scanner/watchlist facts, strategy rules, catalyst quality, risk/session state, market microstructure, account safety, and user-selected control mode into an explicit `BUY | WAIT | NO_BUY` decision with evidence. It then either displays, stages, or executes the approved ticket according to `signal | confirm | auto_paper | auto_live`. Nova OS also owns the learning loop: durable market/journal history, replay, review, policy versioning, and a visible audit trail. It is not an unconstrained chatbot, not a promise of profit, and never bypasses IBKR/risk gates.

## Current position

- Phase: P0
- State: verified
- Last verified commit: _(filled after push)_
- Last updated: 2026-07-15 ~14:40 ET

## Completed this phase

- Canonical status note (`Nova-OS-Status.md`) and continuity rule (`.cursor/rules/nova-os-continuity.mdc`) with hard commit+push gate
- Mission canvas (`nova-os-mission.canvas.tsx`) — phase map, control modes, loss policy, model routing
- Duplicate L2 recorder constants consolidated in `backend/constants.py` (single block ~598–612)
- Stale documentation corrected: `JournalPanel.tsx`, `risk.py` docstring, `Automation-Roadmap.md`, `Nova-OS-Decision-Brain.md`, `Local-Market-Data-Recorders.md`
- Baseline verification recorded below

## In progress / uncommitted

- Unrelated WIP preserved (not part of P0): scanner density, HOD Momo UI, earnings-today hooks, dashboard layout — left unstaged; see `git status`

## Crash or blocker

- Symptom: none
- Root cause: n/a
- Evidence/log: n/a
- Safe next action: proceed to P1 after this phase's commit+push

## Verification ledger

- Command: `cd backend && py -3 -m pytest tests/test_executor.py tests/test_risk.py tests/test_journal.py tests/test_l2.py tests/test_l2_recorder.py tests/test_watchlist.py tests/test_setups.py tests/test_five_pillars.py -q`
- Result: **109 passed** in 3.53s (2026-07-15)
- Command: `cd frontend && npm run build`
- Result: **PASS** (tsc + vite build; chunk-size warning only; exit 0)
- Browser path: not required for P0 (continuity artifacts + doc/constant fixes only)

## User action needed

- None for P0. R2 bucket setup is deferred to P8 (`user-r2-setup`).

## Phase-close / Next chat starts here

**Every phase ends with commit + push before a new chat starts.** Phase completion is incomplete until `git add` (intentional files) → `git commit` → `git push`, with SHA recorded here. Do not begin P1 until this P0 push is done.

1. Read this note, the Nova OS plan (`nova_os_decision_engine_c4367abc.plan.md`), CHANGELOG, and relevant PROBLEM_LOG entry.
2. Confirm git status and active phase (should be P1 after P0 verified).
3. Run the recorded baseline/smoke check.
4. Continue from: **P1 — Audit and event foundation** — add append-only decision/event schema and read API; define stable reason/action codes and policy-version metadata; encode no-silent-action receipts; add temporary loss-policy constants (first daily loss → `confirm`, third daily loss → halt).
