# Nova OS Status

## Definition

Nova OS is Nova's auditable trading decision and operations layer. It combines scanner/watchlist facts, strategy rules, catalyst quality, risk/session state, market microstructure, account safety, and user-selected control mode into an explicit `BUY | WAIT | NO_BUY` decision with evidence. It then either displays, stages, or executes the approved ticket according to `signal | confirm | auto_paper | auto_live`. Nova OS also owns the learning loop: durable market/journal history, replay, review, policy versioning, and a visible audit trail. It is not an unconstrained chatbot, not a promise of profit, and never bypasses IBKR/risk gates.

## Current position

- Phase: P4
- State: verified
- Last verified commit: (pending)
- Last updated: 2026-07-15 ~15:45 ET

## Completed this phase

- **P4 — Confirm mode + emergency controls** (backend + Automation UI)
- control_mode / staged_tickets; mode-aware executor; Approve/Reject; safer kill; flatten token; ExecutorPanel ladder

## Prior phases

- P3 Decision UX — fd007a9 · P2 decide — 528cc7f · P1 events — 9fbdaff · P0 — e2d649c

## In progress / uncommitted

- Unrelated WIP (HOD integrity/surge, earnings, scanner density) left unstaged

## Crash or blocker

- none · Next: **P5 auto_paper + recovery**

## Verification ledger

- pytest control_mode + staged + executor: 29 passed
- npm run build: PASS

## User action needed

- none (R2 still P8)

## Phase-close / Next chat starts here

Continue **P5 — Automatic paper execution and recovery**
