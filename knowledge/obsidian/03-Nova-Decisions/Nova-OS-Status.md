# Nova OS Status

## Definition

Nova OS is Nova's auditable trading decision and operations layer. It combines scanner/watchlist facts, strategy rules, catalyst quality, risk/session state, market microstructure, account safety, and user-selected control mode into an explicit `BUY | WAIT | NO_BUY` decision with evidence. It then either displays, stages, or executes the approved ticket according to `signal | confirm | auto_paper | auto_live`. Nova OS also owns the learning loop: durable market/journal history, replay, review, policy versioning, and a visible audit trail. It is not an unconstrained chatbot, not a promise of profit, and never bypasses IBKR/risk gates.

## Current position

- Phase: P1
- State: verified
- Last verified commit: PENDING_COMMIT
- Last updated: 2026-07-15 ~15:00 ET

## Completed this phase

- **P1 — Audit and event foundation:**
  - Append-only event log: `backend/nova_os/events_db.py` (schema, `nova_os_events.db` under `paths.cache_dir()`) + `events.py` (`record_receipt()` write path, `get_events()` read).
  - Stable vocabulary + policy metadata: `backend/nova_os/codes.py` — decision verdicts, control modes, action codes, reason codes, `policy_version()`, and validators (fail-closed on unknown codes). All code strings defined in `backend/constants.py` (Nova OS section).
  - No-silent-action receipts: every write validates + persists an immutable row and returns it; `would_execute` vs `executed` recorded separately.
  - Temporary loss policy: `NOVA_OS_LOSS_POLICY_*` constants + `codes.loss_policy_mode()` (first loss → `confirm`, third → halt; only ever lowers autonomy).
  - Read API: `GET /api/nova-os/policy`, `GET /api/nova-os/events` (`backend/routes/nova_os.py`), router wired in `main.py`, `init_db()` in `app_lifespan.py`.
  - Tests: `test_nova_os_codes.py`, `test_nova_os_events.py`.

## Prior phase (P0) — completed

- Canonical status note + continuity rule with hard commit+push gate; mission canvas; L2 constant dedupe; stale doc reconcile; baseline recorded (commit e2d649c).

## In progress / uncommitted

- Unrelated WIP preserved (not part of P0): scanner density, HOD Momo UI, earnings-today hooks, dashboard layout — left unstaged; see `git status`

## Crash or blocker

- Symptom: none
- Root cause: n/a
- Evidence/log: n/a
- Safe next action: proceed to P2 after this phase's commit+push

## Verification ledger

- Command: `cd backend && py -3 -m pytest tests/test_executor.py tests/test_risk.py tests/test_journal.py tests/test_l2.py tests/test_l2_recorder.py tests/test_watchlist.py tests/test_setups.py tests/test_five_pillars.py tests/test_nova_os_events.py tests/test_nova_os_codes.py -q`
- Result: **126 passed** in 3.90s (2026-07-15)
- Command: `py -3 -c "import main"` → app imports clean, 2 `/api/nova-os` routes registered
- Command: `cd frontend && npm run build`
- Result: **PASS** (tsc + vite build; chunk-size warning only; exit 0)
- Browser path: not required for P1 (backend audit foundation + read API only; no UI yet)

## User action needed

- None for P1. R2 bucket setup is deferred to P8 (`user-r2-setup`).

## Phase-close / Next chat starts here

**Every phase ends with commit + push before a new chat starts.** Phase completion is incomplete until `git add` (intentional files) → `git commit` → `git push`, with SHA recorded here. Do not begin P2 until this P1 push is done.

1. Read this note, the Nova OS plan (`nova_os_decision_engine_c4367abc.plan.md`), CHANGELOG, and relevant PROBLEM_LOG entry.
2. Confirm git status and active phase (should be P2 after P1 verified).
3. Run the recorded baseline/smoke check.
4. Continue from: **P2 — `decide()` engine** — implement the ordered decision gates (session/risk → Five Pillars → setup → ticket math → catalyst → microstructure) that emit `BUY | WAIT | NO_BUY` + reason codes and write a `record_receipt()` per candidate using the P1 vocabulary. Wire the loss policy (`codes.loss_policy_mode`) into the mode selection. Do not place orders (still signal/confirm surfaces); DecisionPanel UI can follow.
