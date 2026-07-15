# Nova OS Status

## Definition

Nova OS is Nova's auditable trading decision and operations layer. It combines scanner/watchlist facts, strategy rules, catalyst quality, risk/session state, market microstructure, account safety, and user-selected control mode into an explicit `BUY | WAIT | NO_BUY` decision with evidence. It then either displays, stages, or executes the approved ticket according to `signal | confirm | auto_paper | auto_live`. Nova OS also owns the learning loop: durable market/journal history, replay, review, policy versioning, and a visible audit trail. It is not an unconstrained chatbot, not a promise of profit, and never bypasses IBKR/risk gates.

## Current position

- Phase: P2
- State: verified
- Last verified commit: 528cc7f17715db564bed31ebe7390def6c87e9fb
- Last updated: 2026-07-15 ~15:20 ET

## Completed this phase

- **P2 — `decide()` engine (signal only):**
  - Ordered gates in `backend/nova_os/gates.py` + orchestrator `decide.py`: session/risk/loss-policy → Five Pillars → setup (+ first-minute volume + watchlist rank) → ticket math → news-impact catalyst (soft) → microstructure placeholder.
  - Every call writes a `record_receipt()`; `would_execute` / `executed` always False in P2.
  - Tunables + new reason codes in `constants.py`; policy version `nova-os-p2-2026-07-15`.
  - API: `GET /api/nova-os/decide/{symbol}`, `GET /api/nova-os/decide` (watchlist batch); policy endpoint exposes decide tunables.
  - `setups_stream` routes eligible setups through `decide()`; only `BUY` reaches `executor.on_signal` (still armed-gated).
  - Tests: `test_nova_os_decide.py`.

## Prior phases

- **P1** — audit foundation (events DB, vocabulary, loss policy, read API) — commit 9fbdaff / status 7e03b1a.
- **P0** — continuity baseline — commit e2d649c.

## In progress / uncommitted

- Unrelated WIP preserved (not part of P2): scanner density, HOD Momo UI, earnings-today hooks, dashboard layout — left unstaged; see `git status`

## Crash or blocker

- Symptom: none
- Root cause: n/a
- Evidence/log: n/a
- Safe next action: proceed to P3 after this phase's commit+push

## Verification ledger

- Command: `cd backend && py -3 -m pytest tests/test_executor.py tests/test_risk.py tests/test_journal.py tests/test_l2.py tests/test_l2_recorder.py tests/test_watchlist.py tests/test_setups.py tests/test_five_pillars.py tests/test_nova_os_events.py tests/test_nova_os_codes.py tests/test_nova_os_decide.py -q`
- Result: **140 passed** in ~4s (2026-07-15)
- Command: `py -3 -c "import main"` → 4 `/api/nova-os` routes (`policy`, `events`, `decide`, `decide/{symbol}`)
- Command: `cd frontend && npm run build`
- Result: **PASS** (tsc + vite build; chunk-size warning only; exit 0)
- Browser path: not required for P2 (backend decide + stream wiring; DecisionPanel UI is P3)

## User action needed

- None for P2. R2 bucket setup is deferred to P8 (`user-r2-setup`).

## Phase-close / Next chat starts here

**Every phase ends with commit + push before a new chat starts.** Phase completion is incomplete until `git add` (intentional files) → `git commit` → `git push`, with SHA recorded here.

1. Read this note, the Nova OS plan (`nova_os_decision_engine_c4367abc.plan.md`), CHANGELOG, and relevant PROBLEM_LOG entry.
2. Confirm git status and active phase (should be P3 after P2 verified).
3. Run the recorded baseline/smoke check.
4. Continue from: **P3 — Decision UX and operator visibility** — DecisionPanel gate-audit UI, Signals/Stock View consume the unified decision shape, thin read-only CLI, attention strip/toast/sound framework (muteable). Do not enable confirm/auto order paths yet.
