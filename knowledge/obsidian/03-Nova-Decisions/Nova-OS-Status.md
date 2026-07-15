# Nova OS Status

## Definition

Nova OS is Nova's auditable trading decision and operations layer. It combines scanner/watchlist facts, strategy rules, catalyst quality, risk/session state, market microstructure, account safety, and user-selected control mode into an explicit `BUY | WAIT | NO_BUY` decision with evidence. It then either displays, stages, or executes the approved ticket according to `signal | confirm | auto_paper | auto_live`. Nova OS also owns the learning loop: durable market/journal history, replay, review, policy versioning, and a visible audit trail. It is not an unconstrained chatbot, not a promise of profit, and never bypasses IBKR/risk gates.

## Current position

- Phase: P7
- State: verified
- Last verified commit: 46654318e27773112751f8e3fdaa23011497f1f9
- Last updated: 2026-07-15 ~16:15 ET

## Completed this phase

- P6/P7 local capture + cold archive under `backend/archive/`

## Prior phases

- P5 auto_paper — 181b16e · P4 confirm — ecc6f88 · P3–P0 as before

## Crash or blocker

- none · Next: P8 R2 (needs user keys) → P9 replay → P10 GO/NO-GO

## Verification ledger

- archive pytest 11 passed

## User action needed

- P8: create Cloudflare R2 bucket + token (see docs)

## Phase-close / Next chat starts here

Continue **P8 cloud durability** (code + docs; upload waits on R2 keys)
