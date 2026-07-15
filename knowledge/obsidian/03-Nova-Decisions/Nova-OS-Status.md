# Nova OS Status

## Definition

Nova OS is Nova's auditable trading decision and operations layer. It combines scanner/watchlist facts, strategy rules, catalyst quality, risk/session state, market microstructure, account safety, and user-selected control mode into an explicit `BUY | WAIT | NO_BUY` decision with evidence. It then either displays, stages, or executes the approved ticket according to `signal | confirm | auto_paper | auto_live`. Nova OS also owns the learning loop: durable market/journal history, replay, review, policy versioning, and a visible audit trail. It is not an unconstrained chatbot, not a promise of profit, and never bypasses IBKR/risk gates.

## Current position

- Phase: P3
- State: verified
- Last verified commit: fd007a91220642bbd0e61aa219fbc6168e06d43d
- Last updated: 2026-07-15 ~15:20 ET

## Completed this phase

- **P3 — Decision UX + operator visibility:**
  - `DecisionPanel` gate audit sub-tab on Watchlist (first failing gate highlighted, ticket, citations, receipt).
  - Signals table shows Nova OS verdict column; WS `decision` frames consumed.
  - Attention strip + muteable Web Audio cues (`novaOsAttention.ts`).
  - Read-only CLI: `tools/nova_os_cli.py` (policy / events / decide).
  - Types + `useNovaOsDecide` hook; vitest for attention mute.

## Prior phases

- **P2** — decide() brain — 528cc7f
- **P1** — audit foundation — 9fbdaff
- **P0** — continuity — e2d649c

## In progress / uncommitted

- Unrelated WIP preserved (scanner density, HOD, earnings) — left unstaged

## Crash or blocker

- Symptom: none
- Safe next action: P4 confirm mode + emergency controls

## Verification ledger

- Command: `npx vitest run src/strategy/novaOsAttention.test.ts` → 2 passed
- Command: `npm run build` → PASS
- Browser: Decision sub-tab ships; full interactive browser optional for P3 (signal-only UI)

## User action needed

- None for P3

## Phase-close / Next chat starts here

1. Read this note + plan
2. Continue from: **P4 — Confirm mode + emergency controls** — stage/approve/reject, Stop Automation / Cancel Working Entry / Flatten, loss policy drops to confirm, restart → signal
