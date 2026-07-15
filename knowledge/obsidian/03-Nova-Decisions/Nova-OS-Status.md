# Nova OS Status

## Definition

Nova OS is Nova's auditable trading decision and operations layer. It combines scanner/watchlist facts, strategy rules, catalyst quality, risk/session state, market microstructure, account safety, and user-selected control mode into an explicit `BUY | WAIT | NO_BUY` decision with evidence. It then either displays, stages, or executes the approved ticket according to `signal | confirm | auto_paper | auto_live`. Nova OS also owns the learning loop: durable market/journal history, replay, review, policy versioning, and a visible audit trail. It is not an unconstrained chatbot, not a promise of profit, and never bypasses IBKR/risk gates.

## Current position

- Phase: P5
- State: verified
- Last verified commit: 181b16e12029fc74ce57a07a9620f94893a2d819
- Last updated: 2026-07-15 ~16:00 ET

## Completed this phase

- **P5 — Automatic paper execution + recovery:**
  - `auto_paper` mode gated (paper Gateway, orders enabled, risk, holiday calendar)
  - `auto_live` still rejected
  - Restart → always `signal`; `recovery.py` reconstructs tracked positions from events/IBKR
  - ExecutorPanel: Auto Paper + blocked Auto Live
  - Policy `nova-os-p5-2026-07-15`

## Prior phases

- P4 confirm — ecc6f88 · P3 UX — fd007a9 · P2 decide — 528cc7f · P1 — 9fbdaff · P0 — e2d649c

## In progress / uncommitted

- P6/P7 archive sources need recreate (pycache present; sources lost in branch switch) — next
- Unrelated HOD/earnings WIP in stash

## Crash or blocker

- none for P5
- Safe next: recreate P6/P7 archive package, then P8–P10

## Verification ledger

- pytest auto_paper + control + staged + executor: 42 passed
- npm run build: PASS

## User action needed

- P8 will need Cloudflare R2 keys (user-r2-setup)

## Phase-close / Next chat starts here

Continue **P6/P7 archive recreate → P8 R2 → P9 replay → P10 GO/NO-GO**
